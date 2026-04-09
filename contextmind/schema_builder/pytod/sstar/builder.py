"""
S*（S-star）PyTOD API 构建器入口。

:func:`build_pytod_apis_sstar` 与
:func:`contextmind.schema_builder.pytod.builder.build_pytod_apis` 具有完全相同的函数签名，
可直接替换调用。

流水线结构
----------
- **Phase 1**：解析 schema（与 pytod/alpha 相同）
- **Phase 2**：测试用例生成（复用 :class:`~contextmind.schema_builder.pytod.shared.generator.PyTODApiCodeGenerator`）
- **Phase P→D→S→R**：SStarSynthesizer 四阶段合成
  （并行草稿 → 执行追踪修复 → 区分性测试选择 → 最优候选精炼）
- **Phase 5**：组装 Python 文件（与 pytod/alpha 相同格式，可被 load_pytod_api_module 直接加载）

论文参考
--------
Dacheng Li et al., "S*: Test Time Scaling for Code Generation",
arXiv:2502.14382, 2025. https://arxiv.org/abs/2502.14382
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema, load_schema_from_dict
from contextmind.schema_builder.utils import companion_path

from contextmind.schema_builder.pytod.shared.helpers import SHARED_HELPERS
from contextmind.schema_builder.pytod.shared.models import FuncValidation, TestCaseItem
from contextmind.schema_builder.pytod.shared.test_cache import load_test_cases, save_test_cases
from contextmind.schema_builder.pytod.shared.validator import validate_function, write_validation_report

from contextmind.schema_builder.pytod.sstar.synthesizer import SStarSynthesizer

logger = get_logger(__name__)


def _function_def_header(intent: IntentDefinition) -> str:
    """返回函数 def 行 + docstring 行（用于 stub 生成兜底）。"""
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    return f'def {intent.name}({param_str}):\n    """{desc}"""'


def _generate_stub_function(intent: IntentDefinition) -> str:
    """为意图生成最小 stub 函数（LLM 不可用时的简单兜底）。"""
    return _function_def_header(intent) + '\n    return {"status": "success"}'


def _generate_generic_function_lines(schema: ServiceSchema) -> List[str]:
    """schema 无意图定义时，生成一个以 service_name 命名的通用函数。"""
    slot_names = [s.name for s in schema.slots]
    param_str = ", ".join([f"{p}=None" for p in slot_names]) if slot_names else ""
    desc = schema.description.replace('"', '\\"') if schema.description else schema.service_name
    return [
        f"def {schema.service_name}({param_str}):",
        f'    """{desc}"""',
        f'    args = {{k: v for k, v in locals().items() if v is not None}}',
        f'    return {{"status": "success", **args}}',
    ]


def _print_section(title: str, width: int = 70) -> None:
    """打印带标题的分隔线（verbose 模式）。"""
    line = "─" * width
    print(line, flush=True)
    print(f"  {title}", flush=True)
    print(line, flush=True)


def build_pytod_apis_sstar(
    schema_path: Union[str, Path],
    schema: Optional[ServiceSchema] = None,
    *,
    overwrite: bool = True,
    llm_client: Optional[Any] = None,
    dialogue_data_path: Optional[Union[str, Path]] = None,
    max_iterations: int = 10,
    pass_rate_threshold: float = 0.9,
    max_test_cases_per_intent: int = 10,
    generate_report: bool = False,
    kb_dir: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    verbose: bool = False,
    test_cases_path: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """从 schema.json 用 S* 算法生成 PyTOD ``*_pytod_apis.py`` companion 文件。

    与 :func:`contextmind.schema_builder.pytod.builder.build_pytod_apis` 接口相同，
    可直接替换调用。差异在于内部使用 SStarSynthesizer 替代原有的生成器：

    - **Phase P（并行草稿）**：以 N 种不同思维模式并行生成 N 个候选实现
    - **Phase D（执行追踪修复）**：基于 execution traces 精准修复，而非仅凭错误信息
    - **Phase S（区分性测试选择）**：LLM 生成区分性输入，通过执行行为选出最优候选
    - **Phase R（最优候选精炼）**：对选出候选继续精炼直至达到通过率阈值

    Args:
        schema_path:               ``*_schema.json`` 文件路径。
        schema:                    已加载的 ServiceSchema（传入可省略重复 IO）。
        overwrite:                 目标文件已存在时是否覆盖（默认 True）。
        llm_client:                可选的 AdkLLMClient 实例。
        dialogue_data_path:        可选的真实对话数据文件路径（Phase 2 业务背景）。
        max_iterations:            总最大迭代轮次（跨 D/R 阶段共享，默认 10）。
        pass_rate_threshold:       通过率阈值（默认 0.9）。
        max_test_cases_per_intent: Phase 2 每意图最多测试用例数（默认 10）。
        generate_report:           是否写入验证报告（默认 False）。
        kb_dir:                    可选，KB 输出目录路径。
        output_dir:                可选的输出目录。
        verbose:                   是否输出详细进度信息（默认 False）。
        test_cases_path:           可选，预生成的测试用例缓存文件路径（``*_test_cases.json``）。
                                   若文件存在，Phase 2 直接加载跳过 LLM 生成；否则生成后自动保存。

    Returns:
        写入成功时返回生成的文件路径，否则返回 None。
    """
    schema_path = Path(schema_path)
    _output_dir = Path(output_dir) if output_dir is not None else None
    if _output_dir is not None:
        _output_dir.mkdir(parents=True, exist_ok=True)
    out_path = companion_path(schema_path, "pytod_apis", suffix=".py", output_dir=_output_dir)

    # 目标文件已存在且不覆盖时跳过
    if out_path.exists() and not overwrite:
        logger.debug(f"[S*] 跳过已存在文件: {out_path}")
        return None

    # ------------------------------------------------------------------
    # Phase 1：解析 schema
    # ------------------------------------------------------------------
    if schema is None:
        try:
            with open(schema_path, encoding="utf-8") as fh:
                schema = load_schema_from_dict(json.load(fh))
        except Exception as exc:
            logger.error(f"[S*] 加载 schema 失败: {schema_path} — {exc}")
            return None

    # 初始化 SStarSynthesizer（仅当有 llm_client 时）
    synthesizer: Optional[SStarSynthesizer] = None
    if llm_client is not None:
        try:
            synthesizer = SStarSynthesizer(llm_client=llm_client)
            logger.info(
                f"[S*] Phase 1 完成 — 服务: {schema.service_name}, "
                f"意图数: {len(schema.intents)}, 模式: S* (LLM)"
            )
        except Exception as exc:
            logger.warning(f"[S*] SStarSynthesizer 初始化失败，回退到 stub 生成: {exc}")
    else:
        logger.info(
            f"[S*] Phase 1 完成 — 服务: {schema.service_name}, "
            f"意图数: {len(schema.intents)}, 模式: stub（无 LLM）"
        )

    # ------------------------------------------------------------------
    # 解析 KB 目录（为 Phase 2 提供对话上下文）
    # ------------------------------------------------------------------
    _dlg_path = Path(dialogue_data_path) if dialogue_data_path else None
    _discovery_path: Optional[Path] = None
    _sgd_dlg_path: Optional[Path] = None
    _summary_path: Optional[Path] = None
    if kb_dir is not None:
        from contextmind.schema_builder.pytod.shared.generator import PyTODApiCodeGenerator
        kb_context = PyTODApiCodeGenerator.load_kb_context(kb_dir)
        if _dlg_path is None and kb_context.get("dialogues_path"):
            _sgd_dlg_path = kb_context["dialogues_path"]
            logger.info(f"[S*] kb_dir: 使用 dialogues_001.json → {_sgd_dlg_path}")
        if kb_context.get("discovery_path"):
            _discovery_path = kb_context["discovery_path"]
            logger.info(f"[S*] kb_dir: 使用 discovery_raw.json → {_discovery_path}")
        if kb_context.get("summary_path"):
            _summary_path = kb_context["summary_path"]
            logger.info(f"[S*] kb_dir: 使用 conversion_summary.json → {_summary_path}")

    # ------------------------------------------------------------------
    # Phase 2：测试用例生成（复用 PyTODApiCodeGenerator）
    # ------------------------------------------------------------------
    all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}
    intent_lines: List[str] = []
    validations: Dict[str, FuncValidation] = {}
    test_cases_by_intent: Dict[str, List[TestCaseItem]] = {}

    if not schema.intents:
        # 无意图定义时生成通用函数
        intent_lines.extend(_generate_generic_function_lines(schema))
        intent_lines.append("")
        mode_str = "通用函数（无意图定义）"

    elif synthesizer is not None:
        # S* LLM 模式
        from contextmind.schema_builder.pytod.shared.generator import PyTODApiCodeGenerator
        phase2_gen = PyTODApiCodeGenerator(llm_client=llm_client)

        # 预构建对话提示（所有意图共用）
        dialogue_hint = phase2_gen._prepare_dialogue_hint(
            dialogue_data_path=_dlg_path,
            sgd_dialogue_data_path=_sgd_dlg_path,
            discovery_data_path=_discovery_path,
            summary_data_path=_summary_path,
        )
        if dialogue_hint:
            logger.info(
                f"[S*] 对话提示已构建（{len(dialogue_hint)} 字符），注入 Phase 2 测试用例生成"
            )

        total_intents = len(schema.intents)
        logger.info(f"[S*] 开始逐函数 S* 合成（共 {total_intents} 个意图）...")

        # 尝试从缓存文件加载测试用例
        _tc_path = Path(test_cases_path) if test_cases_path is not None else None
        _cached_test_cases: Dict[str, List[TestCaseItem]] = {}
        _tc_existed = False
        if _tc_path is not None and _tc_path.exists():
            _loaded = load_test_cases(_tc_path)
            if _loaded:
                _cached_test_cases = _loaded
                _tc_existed = True
                logger.info(
                    f"[S*] Phase 2: 从缓存加载测试用例 "
                    f"({len(_cached_test_cases)} 个意图) ← {_tc_path}"
                )

        for idx, intent in enumerate(schema.intents, 1):
            logger.info(f"[S*] ── 函数 {idx}/{total_intents}: {intent.name} ──────────────")
            if verbose:
                _print_section(f"[S*] 函数 {idx}/{total_intents}: {intent.name}")

            # Phase 2：加载或生成测试用例
            if intent.name in _cached_test_cases:
                intent_test_cases = _cached_test_cases[intent.name]
                logger.info(
                    f"[S*]   Phase 2: {intent.name} — "
                    f"使用缓存测试用例（{len(intent_test_cases)} 条）"
                )
            else:
                logger.info(f"[S*]   Phase 2: {intent.name} — 生成测试用例...")
                intent_test_cases = phase2_gen.build_test_cases_for_intent(
                    intent, schema, all_slot_descs, dialogue_hint, max_test_cases_per_intent
                )
                if intent_test_cases:
                    logger.info(
                        f"[S*]   Phase 2 完成: {intent.name} — {len(intent_test_cases)} 条测试用例"
                    )
                else:
                    logger.warning(f"[S*]   Phase 2: {intent.name} — 未获得测试用例")
            if intent_test_cases:
                test_cases_by_intent[intent.name] = intent_test_cases
            if verbose and intent_test_cases:
                print(f"  📌 测试用例（{len(intent_test_cases)} 条）:", flush=True)
                for i, tc in enumerate(intent_test_cases, 1):
                    desc = f" [{tc.description}]" if tc.description else ""
                    print(f"    用例 #{i}{desc}: {tc.input_slots}", flush=True)
                print(flush=True)

            # Phase P→D→S→R：S* 合成
            func_code, validation = synthesizer.synthesize(
                intent=intent,
                schema=schema,
                all_slot_descs=all_slot_descs,
                test_cases=intent_test_cases,
                max_iterations=max_iterations,
                pass_rate_threshold=pass_rate_threshold,
                dialogue_hint=dialogue_hint,
            )

            if verbose:
                _print_section(
                    f"[S*] {intent.name} 最终代码"
                    + (
                        f"（通过率: {validation.pass_rate:.1%} "
                        f"{validation.passed}/{validation.total}）"
                        if validation.total > 0 else ""
                    )
                )
                print(func_code, flush=True)
                print(flush=True)

            validations[intent.name] = validation
            status_sym = (
                "✅" if (validation.total == 0 or validation.pass_rate >= pass_rate_threshold)
                else "⚠️ "
            )
            logger.info(
                f"[S*]   {status_sym} {intent.name} 完成 — "
                + (
                    f"通过率 {validation.pass_rate:.1%} ({validation.passed}/{validation.total})，"
                    f"迭代 {validation.iterations} 轮"
                    if validation.total > 0 else "无测试用例（跳过验证）"
                )
            )

            intent_lines.extend(func_code.splitlines())
            intent_lines.append("")

        # 汇总模式信息
        mode_str = f"S* 合成 {len(schema.intents)} 个意图"
        if validations:
            validated = [v for v in validations.values() if v.total > 0]
            if validated:
                avg_rate = sum(v.pass_rate for v in validated) / len(validated)
                total_p = sum(v.passed for v in validated)
                total_t = sum(v.total for v in validated)
                mode_str += f"，测试验证 {total_p}/{total_t} ({avg_rate:.1%})"

        # 若 test_cases_path 指定且文件不存在，保存本次生成的测试用例供后续复用
        if _tc_path is not None and not _tc_existed and test_cases_by_intent:
            save_test_cases(test_cases_by_intent, _tc_path)
            logger.info(f"[S*] 测试用例已缓存 → {_tc_path}（下次运行将自动复用）")

        if verbose and validations:
            _print_section("[S*] 验证汇总")
            for intent_name, v in validations.items():
                if v.total > 0:
                    status = "✅" if v.pass_rate >= pass_rate_threshold else "⚠️ "
                    print(
                        f"  {status} {intent_name}: "
                        f"{v.pass_rate:.1%} ({v.passed}/{v.total})"
                        f"，迭代 {v.iterations} 轮",
                        flush=True,
                    )
                    if v.failures:
                        for fail in v.failures[:3]:
                            print(f"       ✗ {fail}", flush=True)
                else:
                    print(f"  —  {intent_name}: 无测试用例（跳过验证）", flush=True)
            print(flush=True)

    else:
        # 规则模式：无 LLM，生成最小 stub 函数
        for intent in schema.intents:
            intent_lines.extend(_generate_stub_function(intent).splitlines())
            intent_lines.append("")
        mode_str = f"stub 生成 {len(schema.intents)} 个意图函数（无 LLM）"

    # ------------------------------------------------------------------
    # Phase 5：组装完整 Python 文件 + 写入磁盘
    # ------------------------------------------------------------------
    n_dialogue = f"（参考对话数据: {_dlg_path.name}）" if _dlg_path else ""
    mode_info = (
        f"S*（Test Time Scaling，arXiv:2502.14382）LLM 生成{n_dialogue}" if synthesizer
        else "stub 生成（无 LLM，使用最小返回值）"
    )

    header_lines: List[str] = [
        '"""',
        f'PyTOD API 函数集合 — 由 {schema_path.name} 生成',
        f'服务（Service）: {schema.service_name}',
        f'生成时间（Generated at）: {datetime.now(timezone.utc).isoformat()}',
        f'生成模式（Generation mode）: {mode_info}',
        '',
        '每个函数对应 schema 中的一个意图（intent），函数签名参数来自',
        'required_slots + optional_slots，返回值包含 result_slots 字段。',
        '文件头部定义了共享工具函数（_parse_amount、_ticket_id 等），',
        '意图函数通过调用这些工具函数实现真实计算逻辑。',
        '运行时通过 load_pytod_api_module() 加载并注册到 ExecutionEngine。',
        '"""',
        '',
        'from __future__ import annotations',
        '',
        SHARED_HELPERS,
    ]

    registry_lines: List[str] = [
        '',
        '# ---------------------------------------------------------------------------',
        '# INTENT_REGISTRY — intent 名称到函数的映射，供外部代码通过名称调用意图函数',
        '# ---------------------------------------------------------------------------',
        '',
        'INTENT_REGISTRY: dict = {',
    ]
    if schema.intents:
        for intent in schema.intents:
            registry_lines.append(f'    "{intent.name}": {intent.name},')
    else:
        registry_lines.append(f'    "{schema.service_name}": {schema.service_name},')
    registry_lines += ['}', '']

    source = '\n'.join(header_lines) + '\n'.join(intent_lines) + '\n'.join(registry_lines)

    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(source)
        logger.info(
            f"[S*] Phase 5 完成 — 已写入: {out_path} "
            f"({len(schema.intents)} 个意图，{mode_str})"
        )
    except Exception as exc:
        logger.error(f"[S*] 写入失败: {out_path} — {exc}")
        return None

    # 可选：写入验证报告
    if generate_report and test_cases_by_intent:
        write_validation_report(schema_path, validations, test_cases_by_intent, output_dir=_output_dir)

    return out_path
