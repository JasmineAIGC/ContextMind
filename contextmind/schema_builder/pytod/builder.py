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
from contextmind.modes.pytod.schemas import ServiceSchema, load_schema_from_dict
from contextmind.schema_builder.utils import companion_path

from .generator import PyTODApiCodeGenerator
from .helpers import SHARED_HELPERS
from .models import FuncValidation, TestCaseItem
from .rule_generator import (
    function_def_header,
    generate_function_lines,
    generate_generic_function_lines,
)
from .validator import validate_function, write_validation_report

logger = get_logger(__name__)


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

    Returns:
        写入成功时返回生成的文件路径，否则返回 None。
    """
    schema_path = Path(schema_path)
    out_path = companion_path(schema_path, "pytod_apis", suffix=".py")

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
    if kb_dir is not None:
        kb_context = PyTODApiCodeGenerator.load_kb_context(kb_dir)
        if _dlg_path is None and kb_context.get("dialogues_path"):
            _sgd_dlg_path = kb_context["dialogues_path"]
            logger.info(f"[PyTOD] kb_dir: 使用 dialogues_001.json → {_sgd_dlg_path}")
        if kb_context.get("discovery_path"):
            _discovery_path = kb_context["discovery_path"]
            logger.info(f"[PyTOD] kb_dir: 使用 discovery_raw.json → {_discovery_path}")

    # ------------------------------------------------------------------
    # Phase 2：构建测试用例（LLM 模式）
    # ------------------------------------------------------------------
    test_cases_by_intent: Dict[str, List[TestCaseItem]] = {}
    if llm_generator is not None and schema.intents:
        logger.info(f"[PyTOD] Phase 2: 为 {len(schema.intents)} 个意图生成测试用例 ...")
        test_cases_by_intent = llm_generator.build_test_cases(
            schema,
            dialogue_data_path=_dlg_path,
            max_cases_per_intent=max_test_cases_per_intent,
            discovery_data_path=_discovery_path,
            sgd_dialogue_data_path=_sgd_dlg_path,
        )
        total_cases = sum(len(v) for v in test_cases_by_intent.values())
        logger.info(
            f"[PyTOD] Phase 2 完成 — "
            f"{len(test_cases_by_intent)} 个意图共 {total_cases} 条测试用例"
        )

    # ------------------------------------------------------------------
    # Phase 3：初始函数生成（LLM 逐函数 + 测试用例 few-shot）
    # Phase 4：验证与迭代优化
    # ------------------------------------------------------------------
    all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}
    intent_lines: List[str] = []
    validations: Dict[str, FuncValidation] = {}
    mode_str = ""

    if not schema.intents:
        # 无意图定义时生成通用函数
        intent_lines.extend(generate_generic_function_lines(schema))
        intent_lines.append('')
        mode_str = "通用函数（无意图定义）"

    elif llm_generator is not None:
        # LLM 模式：逐函数生成 + few-shot + 迭代修复
        llm_count = 0
        rule_count = 0
        logger.info(f"[PyTOD] Phase 3: 逐函数 LLM 生成（{len(schema.intents)} 个意图）...")

        for intent in schema.intents:
            intent_test_cases = test_cases_by_intent.get(intent.name, [])

            # Phase 3：LLM 生成初始函数体（带 few-shot 测试用例）
            llm_body = llm_generator.generate_function_body(
                intent, schema, all_slot_descs, test_cases=intent_test_cases
            )

            if llm_body is not None:
                func_code = "\n".join(function_def_header(intent)) + "\n" + llm_body
                llm_count += 1
            else:
                # LLM 失败时回退到规则生成
                func_code = "\n".join(generate_function_lines(intent))
                rule_count += 1

            # Phase 4：执行测试验证 + 迭代修复（仅当有测试用例且 LLM 生成成功）
            if intent_test_cases and llm_body is not None:
                validation = validate_function(
                    intent, func_code, intent_test_cases, SHARED_HELPERS
                )
                logger.info(
                    f"[PyTOD] Phase 4: {intent.name} — "
                    f"初始通过率: {validation.pass_rate:.1%} "
                    f"({validation.passed}/{validation.total})"
                )

                for iteration in range(1, max_iterations + 1):
                    if validation.pass_rate >= pass_rate_threshold:
                        break  # 已达到通过率阈值，停止迭代

                    logger.info(
                        f"[PyTOD] Phase 4: {intent.name} — "
                        f"第 {iteration} 轮修复（通过率 {validation.pass_rate:.1%} "
                        f"< 阈值 {pass_rate_threshold:.1%}）..."
                    )
                    repaired_code = llm_generator.repair_function(
                        intent, schema, all_slot_descs,
                        current_code=func_code,
                        failures=validation.failures,
                        iteration=iteration,
                        total=validation.total,
                        passed=validation.passed,
                    )
                    if repaired_code is None:
                        logger.warning(f"[PyTOD] Phase 4: {intent.name} 修复失败，停止迭代")
                        break

                    new_validation = validate_function(
                        intent, repaired_code, intent_test_cases, SHARED_HELPERS
                    )
                    logger.info(
                        f"[PyTOD] Phase 4: {intent.name} 第 {iteration} 轮后 "
                        f"通过率: {new_validation.pass_rate:.1%} "
                        f"({new_validation.passed}/{new_validation.total})"
                    )
                    # 通过率提升或持平时接受修复结果（持平也接受，后续轮次可能继续改善）
                    if new_validation.pass_rate >= validation.pass_rate:
                        func_code = repaired_code
                        validation = new_validation
                        validation.iterations = iteration

                validations[intent.name] = validation
            else:
                # 无测试用例或规则兜底：记录空验证结果
                validations[intent.name] = FuncValidation(
                    intent_name=intent.name, total=0, passed=0
                )

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

    else:
        # 规则模式：无 LLM
        rule_count = 0
        for intent in schema.intents:
            intent_lines.extend(generate_function_lines(intent))
            intent_lines.append('')
            rule_count += 1
        mode_str = f"规则引擎生成 {rule_count} 个意图函数"

    # ------------------------------------------------------------------
    # Phase 5：组装完整 Python 文件 + 写入磁盘
    # ------------------------------------------------------------------
    n_dialogue = (
        f"（参考对话数据: {_dlg_path.name}）" if _dlg_path else ""
    )
    mode_info = (
        f"LLM 逐函数生成 + 迭代优化{n_dialogue}" if llm_generator
        else "规则引擎生成（含共享工具函数调用）"
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
        write_validation_report(schema_path, validations, test_cases_by_intent)

    return out_path
