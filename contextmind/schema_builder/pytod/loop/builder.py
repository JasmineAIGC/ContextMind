"""
PyTOD companion 文件构建器。

本模块提供 :func:`build_pytod_apis` 函数，实现将 ``*_schema.json`` 文件
转换为 PyTOD ``*_pytod_apis.py`` companion 文件的完整 5 阶段流水线。

5 阶段生成流程（plan.md）
-------------------------
1. **Phase 1 — 解析 schema**：提取所有意图和槽位定义。
2. **Phase 2 — 构建测试用例**（LLM 模式）：为每个意图生成真实业务值的测试用例。
3. **Phase 3 — 初始函数生成**：逐意图调用 LLM 生成函数体，可选带 few-shot 测试用例。
4. **Phase 4 — 验证与迭代优化**（LLM 模式）：执行测试、计算通过率、迭代修复。
5. **Phase 5 — 组装文件**：生成完整 .py 文件并可选写入验证报告。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema, load_schema_from_dict
from contextmind.schema_builder.utils import companion_path

from contextmind.schema_builder.pytod.generator import PyTODApiCodeGenerator
from contextmind.schema_builder.pytod.helpers import SHARED_HELPERS
from contextmind.schema_builder.pytod.models import FuncValidation, TestCaseItem
from contextmind.schema_builder.pytod.validator import validate_function, write_validation_report

logger = get_logger(__name__)


def _function_def_header(intent: IntentDefinition) -> List[str]:
    """返回函数 def 行 + docstring 行（不含函数体）。"""
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    return [
        f"def {intent.name}({param_str}):",
        f'    """{desc}"""',
    ]


def _generate_stub_function_lines(intent: IntentDefinition) -> List[str]:
    """为意图生成最小 stub 函数（LLM 不可用时的简单兜底）。"""
    header = _function_def_header(intent)
    return header + [
        '    return {"status": "success"}',
    ]


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
    """在终端打印带标题的分隔线，用于 verbose 模式的分段显示。"""
    line = "─" * width
    print(line, flush=True)
    print(f"  {title}", flush=True)
    print(line, flush=True)


def build_pytod_apis(
    schema_path: Union[str, Path],
    schema: Optional[ServiceSchema] = None,
    *,
    overwrite: bool = True,
    llm_client: Optional[Any] = None,
    dialogue_data_path: Optional[Union[str, Path]] = None,
    max_iterations: int = 3,
    pass_rate_threshold: float = 0.9,
    max_test_cases_per_intent: int = 5,
    generate_report: bool = False,
    kb_dir: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    verbose: bool = False,
) -> Optional[Path]:
    """从 schema.json 生成 PyTOD ``*_pytod_apis.py`` companion 文件。

    实现 plan.md 定义的完整 5 阶段生成流程：

    - **Phase 1**：解析 schema，提取意图与槽位定义。
    - **Phase 2**（LLM 模式）：为每个意图生成真实业务值的测试用例（``TestCaseItem``）。
    - **Phase 3**：逐意图 LLM 生成函数体，Prompt 包含 few-shot 测试用例。
      LLM 不可用时回退到规则生成。
    - **Phase 4**（LLM 模式）：执行测试用例、计算通过率；通过率低于阈值时
      调用 LLM 修复，最多迭代 ``max_iterations`` 轮。
    - **Phase 5**：组装完整 Python 文件（头注释 + 共享工具函数 + 意图函数 +
      ``INTENT_REGISTRY``）。可选写入 ``*_validation_report.json``。

    生成模式（优先级从高到低）：

    - **LLM 全流程模式**：``llm_client`` 可用时，Phase 2→4 完整运行。
    - **规则模式**（兜底）：无 LLM 时使用意图名前缀语义推断函数体。

    Args:
        schema_path:              ``*_schema.json`` 文件路径。
        schema:                   已加载的 ServiceSchema（传入可省略重复 IO）。
        overwrite:                目标文件已存在时是否覆盖（默认 True）。
        llm_client:               可选的 AdkLLMClient 实例。
        dialogue_data_path:       可选的真实对话数据文件路径（LLM 模式业务背景）。
                                  支持 chat_test_100.json / chat_test_500.json 格式。
        max_iterations:           Phase 4 最大修复轮次（默认 3）。
        pass_rate_threshold:      Phase 4 通过率阈值（默认 0.9）。
        max_test_cases_per_intent: Phase 2 每意图最多测试用例数（默认 5）。
        generate_report:          是否写入 ``*_validation_report.json``（默认 False）。
        kb_dir:                   可选，KB 输出目录路径（由 KnowledgeBaseBuilder.save_dataset()
                                  生成）。提供后自动加载目录内的 ``dialogues_001.json``、
                                  ``discovery_raw.json``、``conversion_summary.json``，
                                  为 LLM 生成函数提供更丰富的业务背景。
                                  ``dialogue_data_path`` 优先级高于 ``kb_dir``。
        output_dir:               可选的输出目录。指定时输出到该目录，否则输出到 schema 文件同目录。
        verbose:                  是否输出详细进度信息（测试用例内容、每轮迭代后函数代码、
                                  通过率等）。默认 False。

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
        logger.debug(f"[PyTOD] 跳过已存在文件: {out_path}")
        return None

    # ------------------------------------------------------------------
    # Phase 1：解析 schema
    # ------------------------------------------------------------------
    if schema is None:
        try:
            with open(schema_path, encoding="utf-8") as fh:
                schema = load_schema_from_dict(json.load(fh))
        except Exception as exc:
            logger.error(f"[PyTOD] 加载 schema 失败: {schema_path} — {exc}")
            return None

    # 根据是否提供 llm_client 决定生成模式
    llm_generator: Optional[PyTODApiCodeGenerator] = None
    if llm_client is not None:
        try:
            llm_generator = PyTODApiCodeGenerator(llm_client=llm_client)
            logger.info(
                f"[PyTOD] Phase 1 完成 — 服务: {schema.service_name}, "
                f"意图数: {len(schema.intents)}, 模式: LLM"
            )
        except Exception as exc:
            logger.warning(f"[PyTOD] LLM 初始化失败，回退到规则生成: {exc}")
    else:
        logger.info(
            f"[PyTOD] Phase 1 完成 — 服务: {schema.service_name}, "
            f"意图数: {len(schema.intents)}, 模式: 规则"
        )

    # ------------------------------------------------------------------
    # 解析 KB 目录（可选）—— 当 kb_dir 存在时自动发现补充数据文件
    # ------------------------------------------------------------------
    _dlg_path = Path(dialogue_data_path) if dialogue_data_path else None
    _discovery_path: Optional[Path] = None
    _sgd_dlg_path: Optional[Path] = None
    _summary_path: Optional[Path] = None
    if kb_dir is not None:
        kb_context = PyTODApiCodeGenerator.load_kb_context(kb_dir)
        if _dlg_path is None and kb_context.get("dialogues_path"):
            _sgd_dlg_path = kb_context["dialogues_path"]
            logger.info(f"[PyTOD] kb_dir: 使用 dialogues_001.json → {_sgd_dlg_path}")
        if kb_context.get("discovery_path"):
            _discovery_path = kb_context["discovery_path"]
            logger.info(f"[PyTOD] kb_dir: 使用 discovery_raw.json → {_discovery_path}")
        if kb_context.get("summary_path"):
            _summary_path = kb_context["summary_path"]
            logger.info(f"[PyTOD] kb_dir: 使用 conversion_summary.json → {_summary_path}")

    # ------------------------------------------------------------------
    # Phase 2~4：逐函数流式处理
    # 对每个函数依次执行：Phase 2（测试用例）→ Phase 3（生成代码）→ Phase 4（验证修复）
    # 一个函数完整生成完毕后再处理下一个，日志按函数为单位输出。
    # ------------------------------------------------------------------
    all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}
    intent_lines: List[str] = []
    validations: Dict[str, FuncValidation] = {}
    test_cases_by_intent: Dict[str, List[TestCaseItem]] = {}
    mode_str = ""

    # 预先构建对话提示（所有意图共用，避免重复 IO）
    dialogue_hint = ""
    if llm_generator is not None and schema.intents:
        dialogue_hint = llm_generator._prepare_dialogue_hint(
            dialogue_data_path=_dlg_path,
            sgd_dialogue_data_path=_sgd_dlg_path,
            discovery_data_path=_discovery_path,
            summary_data_path=_summary_path,
        )
        if dialogue_hint:
            logger.info(
                f"[PyTOD] 对话提示已构建（{len(dialogue_hint)} 字符），将注入每个意图的测试用例生成 Prompt"
            )
        else:
            logger.info("[PyTOD] 对话提示为空（未提供对话数据或加载失败），函数生成将仅依赖 schema 定义")

    if not schema.intents:
        # 无意图定义时生成通用函数
        intent_lines.extend(_generate_generic_function_lines(schema))
        intent_lines.append('')
        mode_str = "通用函数（无意图定义）"

    elif llm_generator is not None:
        # LLM 模式：每个函数独立经历 Phase 2 → Phase 3 → Phase 4，完成后再处理下一个
        llm_count = 0
        rule_count = 0
        total_intents = len(schema.intents)
        logger.info(f"[PyTOD] 开始逐函数生成（共 {total_intents} 个意图）...")

        for idx, intent in enumerate(schema.intents, 1):
            logger.info(
                f"[PyTOD] ── 函数 {idx}/{total_intents}: {intent.name} ──────────────"
            )
            if verbose:
                _print_section(f"函数 {idx}/{total_intents}: {intent.name}")

            # Phase 2：为本函数生成测试用例
            logger.info(f"[PyTOD]   Phase 2: {intent.name} — 生成测试用例 ...")
            intent_test_cases = llm_generator.build_test_cases_for_intent(
                intent, schema, all_slot_descs, dialogue_hint, max_test_cases_per_intent
            )
            if intent_test_cases:
                test_cases_by_intent[intent.name] = intent_test_cases
                logger.info(
                    f"[PyTOD]   Phase 2 完成: {intent.name} — "
                    f"{len(intent_test_cases)} 条测试用例"
                )
            else:
                logger.warning(
                    f"[PyTOD]   Phase 2: {intent.name} — 未获得测试用例，跳过验证"
                )
            if verbose and intent_test_cases:
                print(f"  📌 测试用例（{len(intent_test_cases)} 条）:", flush=True)
                for i, tc in enumerate(intent_test_cases, 1):
                    desc = f" [{tc.description}]" if tc.description else ""
                    print(f"    用例 #{i}{desc}", flush=True)
                    print(f"      input_slots  : {tc.input_slots}", flush=True)
                    if tc.expected_keys:
                        print(f"      expected_keys: {tc.expected_keys}", flush=True)
                    if tc.expected_values:
                        print(f"      expected_vals: {tc.expected_values}", flush=True)
                print(flush=True)

            # Phase 3：LLM 生成初始函数体（带 few-shot 测试用例 + KB 业务背景）
            logger.info(f"[PyTOD]   Phase 3: {intent.name} — LLM 生成函数体 ...")
            llm_body = llm_generator.generate_function_body(
                intent, schema, all_slot_descs,
                test_cases=intent_test_cases,
                dialogue_hint=dialogue_hint,
            )

            if llm_body is not None:
                func_code = "\n".join(_function_def_header(intent)) + "\n" + llm_body
                llm_count += 1
            else:
                # LLM 失败时回退到 stub 生成
                func_code = "\n".join(_generate_stub_function_lines(intent))
                rule_count += 1
                logger.warning(
                    f"[PyTOD]   Phase 3: {intent.name} — LLM 失败，回退到 stub 生成"
                )

            if verbose:
                _print_section(f"Phase 3 — {intent.name} 初始函数代码")
                print(func_code, flush=True)
                print(flush=True)

            # Phase 4：执行测试验证 + 迭代修复（仅当有测试用例且 LLM 生成成功）
            if intent_test_cases and llm_body is not None:
                validation = validate_function(
                    intent, func_code, intent_test_cases, SHARED_HELPERS
                )
                logger.info(
                    f"[PyTOD]   Phase 4: {intent.name} — "
                    f"初始通过率: {validation.pass_rate:.1%} "
                    f"({validation.passed}/{validation.total})"
                )

                # probe_code/probe_validation 始终追踪最新一次修复尝试的结果（即使未改善
                # 也继续前进），给 LLM 提供不同的失败用例视角，避免重复相同修复提示而陷入循环。
                # func_code/validation 则只在通过率提升或持平时更新，保留最优结果用于输出。
                probe_code = func_code
                probe_validation = validation

                for iteration in range(1, max_iterations + 1):
                    if validation.pass_rate >= pass_rate_threshold:
                        break  # 已达到通过率阈值，停止迭代

                    logger.info(
                        f"[PyTOD]   Phase 4: {intent.name} — "
                        f"第 {iteration} 轮修复（最优通过率 {validation.pass_rate:.1%} "
                        f"< 阈值 {pass_rate_threshold:.1%}）..."
                    )
                    repaired_code = llm_generator.repair_function(
                        intent, schema, all_slot_descs,
                        current_code=probe_code,
                        failures=probe_validation.failures,
                        iteration=iteration,
                        total=probe_validation.total,
                        passed=probe_validation.passed,
                        dialogue_hint=dialogue_hint,
                    )
                    if repaired_code is None:
                        logger.warning(f"[PyTOD]   Phase 4: {intent.name} 修复失败，停止迭代")
                        break

                    new_validation = validate_function(
                        intent, repaired_code, intent_test_cases, SHARED_HELPERS
                    )
                    logger.info(
                        f"[PyTOD]   Phase 4: {intent.name} 第 {iteration} 轮后 "
                        f"通过率: {new_validation.pass_rate:.1%} "
                        f"({new_validation.passed}/{new_validation.total})"
                    )
                    if verbose:
                        _print_section(
                            f"Phase 4 — {intent.name} 第 {iteration} 轮修复后代码"
                            f"（通过率: {new_validation.pass_rate:.1%}"
                            f" {new_validation.passed}/{new_validation.total}）"
                        )
                        print(repaired_code, flush=True)
                        print(flush=True)
                    # 始终将 probe 推进到最新一次修复结果，确保下一轮从不同的失败状态出发
                    probe_code = repaired_code
                    probe_validation = new_validation
                    # 通过率提升或持平时更新最优结果（持平也接受，后续轮次可能继续改善）
                    if new_validation.pass_rate >= validation.pass_rate:
                        func_code = repaired_code
                        validation = new_validation
                        validation.iterations = iteration

                validations[intent.name] = validation
                status_sym = "✅" if validation.pass_rate >= pass_rate_threshold else "⚠️ "
                logger.info(
                    f"[PyTOD]   {status_sym} {intent.name} 完成 — "
                    f"通过率 {validation.pass_rate:.1%} ({validation.passed}/{validation.total})，"
                    f"迭代 {validation.iterations} 轮"
                )
            else:
                # 无测试用例或规则兜底：记录空验证结果
                validations[intent.name] = FuncValidation(
                    intent_name=intent.name, total=0, passed=0
                )
                logger.info(f"[PyTOD]   {intent.name} 完成（无验证）")

            intent_lines.extend(func_code.splitlines())
            intent_lines.append('')

        # 汇总生成模式信息
        if llm_count > 0 and rule_count > 0:
            mode_str = f"LLM 生成 {llm_count} 个，规则 fallback {rule_count} 个"
        elif llm_count > 0:
            mode_str = f"LLM 逐函数生成 {llm_count} 个意图"
        else:
            mode_str = f"规则生成 {rule_count} 个意图函数"

        if validations:
            validated = [v for v in validations.values() if v.total > 0]
            if validated:
                avg_rate = sum(v.pass_rate for v in validated) / len(validated)
                total_p = sum(v.passed for v in validated)
                total_t = sum(v.total for v in validated)
                mode_str += f"，测试验证 {total_p}/{total_t} ({avg_rate:.1%})"

        if verbose and validations:
            _print_section("Phase 4 — 验证汇总")
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
        rule_count = 0
        for intent in schema.intents:
            intent_lines.extend(_generate_stub_function_lines(intent))
            intent_lines.append('')
            rule_count += 1
        mode_str = f"stub 生成 {rule_count} 个意图函数（无 LLM）"

    # ------------------------------------------------------------------
    # Phase 5：组装完整 Python 文件 + 写入磁盘
    # ------------------------------------------------------------------
    n_dialogue = (
        f"（参考对话数据: {_dlg_path.name}）" if _dlg_path else ""
    )
    mode_info = (
        f"LLM 逐函数生成 + 迭代优化{n_dialogue}" if llm_generator
        else "stub 生成（无 LLM，使用最小返回值）"
    )

    # 文件头部：模块注释 + import + 共享工具函数
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

    # 意图函数到名称的映射注册表
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
            f"[PyTOD] Phase 5 完成 — 已写入: {out_path} "
            f"({len(schema.intents)} 个意图，{mode_str})"
        )
    except Exception as exc:
        logger.error(f"[PyTOD] 写入失败: {out_path} — {exc}")
        return None

    # 可选：写入验证报告
    if generate_report and test_cases_by_intent:
        write_validation_report(schema_path, validations, test_cases_by_intent, output_dir=_output_dir)

    return out_path
