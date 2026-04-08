"""
S*（S-star）代码合成器。

实现 S*（arXiv:2502.14382，2025）在 PyTOD 意图函数生成场景下的适配版本：

  Phase P — 并行草稿生成（Parallel Draft Generation）：
    以 N 种不同思维模式并行生成 N 个候选实现，增加解空间覆盖率。

  Phase D — 执行追踪驱动修复（Trace-Guided Repair，LDB 风格）：
    对每个草稿，基于实际执行输出（execution traces）精准定位 bug 并修复，
    而非仅依赖文字错误信息。

  Phase S — 区分性测试选择（Adaptive Selection via Discriminating Inputs）：
    S* 核心创新：LLM 生成能区分两候选行为的测试输入，通过实际执行结果选择最优候选。
    综合评分 = 原始测试通过率（80%）+ 区分性测试通过率（20%）。

  Phase R — 最优候选精炼（Final Refinement）：
    对选出的最优候选继续迭代修复，直至达到通过率阈值或耗尽迭代预算。

单次合成（synthesize()）流程：
  1. Phase P：并行生成 N 个草稿（默认 N=3，对应 3 种思维模式）
  2. Phase D：逐草稿执行追踪修复（每草稿最多 K 轮，默认 K=3）
  3. Phase S：若最优草稿未达阈值，生成区分性输入并选出最优候选
  4. Phase R：对最优候选继续精炼直到达到阈值或耗尽轮次

参考文献：
    Dacheng Li et al., "S*: Test Time Scaling for Code Generation",
    arXiv:2502.14382, 2025. https://arxiv.org/abs/2502.14382
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Any, Dict, List, Optional, Tuple

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema
from contextmind.schema_builder.pytod.models import FuncValidation, TestCaseItem

from contextmind.schema_builder.pytod.sstar.prompts import (
    DISCRIMINATE_SYSTEM,
    DISCRIMINATE_USER_TEMPLATE,
    DRAFT_SYSTEM_TEMPLATE,
    DRAFT_USER_TEMPLATE,
    JUDGE_SYSTEM,
    JUDGE_USER_TEMPLATE,
    REPAIR_SYSTEM,
    REPAIR_USER_TEMPLATE,
    THINKING_MODES,
)
from contextmind.schema_builder.pytod.generator import clean_llm_function_body

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _extract_function_body(raw: str, intent_name: str) -> Optional[str]:
    """从 LLM 输出中提取并规范化函数体（4空格缩进，不含 def 行和 docstring）。

    处理步骤：
    1. 优先从 markdown 代码块中提取（避免把 LLM 的解释性文字混入函数体）
    2. 无代码块时回退到全文提取并去除 markdown 标记
    3. 去除意外输出的 def 行
    4. 去除意外输出的 docstring
    5. 统一 4 空格缩进
    6. 用正则验证含 return 关键字（兼容 return{...} 和 return(...) 等无空格写法）

    Args:
        raw:         LLM 原始输出文本。
        intent_name: 意图名称（用于日志）。

    Returns:
        规范化的函数体字符串，无法提取时返回 None。
    """
    if not raw or not raw.strip():
        return None

    # 1. 优先从 markdown 代码块中提取（更可靠）
    code_block_match = re.search(r"```(?:\w+)?[ \t]*\n(.*?)\n?```", raw, re.DOTALL)
    if code_block_match:
        text = textwrap.dedent(code_block_match.group(1)).strip()
    else:
        # 回退：去除所有 markdown 标记后取全文
        text = re.sub(r"```(?:python)?\s*\n?", "", raw)
        text = re.sub(r"\n?```", "", text)
        text = text.strip()

    lines = text.splitlines()
    filtered: List[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # 跳过 def 行
        if stripped.startswith("def ") and "(" in stripped:
            i += 1
            continue

        # 跳过 triple-quote docstring（单行或多行）
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            if stripped.count(quote) >= 2 and len(stripped) > 3:
                i += 1
                continue
            else:
                i += 1
                while i < len(lines) and quote not in lines[i]:
                    i += 1
                i += 1
                continue

        filtered.append(lines[i])
        i += 1

    while filtered and not filtered[0].strip():
        filtered.pop(0)

    if not filtered:
        return None

    non_empty = [ln for ln in filtered if ln.strip()]
    if not non_empty:
        return None

    min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
    normalized: List[str] = []
    for line in filtered:
        if line.strip():
            normalized.append("    " + line[min_indent:].rstrip())
        else:
            normalized.append("")

    body = "\n".join(normalized).rstrip()

    # 用正则检测 return 关键字（兼容 return{...}、return(...) 等无空格写法）
    if not re.search(r"\breturn\b", body):
        logger.warning(f"[S*] {intent_name}: 提取的函数体不含 return 语句")
        return None

    return body


def _build_header(intent: IntentDefinition) -> str:
    """构建函数 def 行 + docstring（不含函数体）。"""
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    return f'def {intent.name}({param_str}):\n    """{desc}"""'


def _build_param_str(intent: IntentDefinition) -> str:
    """构建函数参数字符串（用于提示词中的签名展示）。"""
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    return ", ".join([f"{p}=None" for p in params]) if params else ""


def _build_required_return_keys(intent: IntentDefinition) -> str:
    """构建骨架约束说明文本（列出必须出现在 return 字典中的所有键）。"""
    keys = list(intent.result_slots) if intent.result_slots else []
    if "status" not in keys:
        keys = ["status"] + keys
    lines = [f'  "{k}": ...' for k in keys]
    keys_str = "{\n" + ",\n".join(lines) + "\n}"
    return (
        f"{keys_str}\n\n"
        f"必须出现的键（缺少任何一个都算测试失败）：{', '.join(repr(k) for k in keys)}"
    )


def _build_input_slots_desc(intent: IntentDefinition, all_slot_descs: Dict[str, str]) -> str:
    """构建输入槽位描述文本。"""
    seen: set = set()
    slots_ordered: List[str] = []
    for s in list(intent.required_slots) + list(intent.optional_slots):
        if s not in seen:
            seen.add(s)
            slots_ordered.append(s)

    lines = []
    for slot in slots_ordered:
        desc = all_slot_descs.get(slot, "")
        required = "（必填）" if slot in intent.required_slots else "（可选）"
        lines.append(f"- {slot}{required}: {desc}" if desc else f"- {slot}{required}")
    return "\n".join(lines) if lines else "（无输入参数）"


def _format_test_cases(test_cases: List[TestCaseItem], max_cases: int = 5) -> str:
    """将测试用例格式化为 LLM 友好文本。"""
    if not test_cases:
        return "（暂无测试用例）"
    lines: List[str] = []
    for i, tc in enumerate(test_cases[:max_cases], 1):
        desc = f"【{tc.description}】" if tc.description else f"用例 {i}"
        input_str = json.dumps(tc.input_slots, ensure_ascii=False)
        ev_str = ""
        if tc.expected_values:
            ev_str = f"\n  期望输出: {json.dumps(tc.expected_values, ensure_ascii=False)}"
        lines.append(f"用例 {i} {desc}\n  输入: {input_str}{ev_str}")
    return "\n\n".join(lines)


def _format_execution_traces(failures: List[Dict[str, Any]], total: int) -> str:
    """将失败详情格式化为执行追踪文本（LDB 风格）。

    LDB（Large Language Debugger）利用实际执行输出（而非仅错误类型）
    来精准定位 bug 位置，本函数将 validate_function() 产生的失败信息
    格式化为适合 LLM 阅读的执行追踪格式。
    """
    if not failures:
        return "（无失败用例）"
    lines: List[str] = []
    for i, f in enumerate(failures[:5], 1):
        lines.append(
            f"追踪 {i}:\n"
            f"  输入: {json.dumps(f.get('input_slots', {}), ensure_ascii=False)}\n"
            f"  实际输出/错误: {f.get('error', '未知')}"
        )
    return "\n\n".join(lines)


def _find_disc_result(disc_val: FuncValidation, inp: Dict[str, Any]) -> str:
    """从验证结果中找到与给定输入匹配的执行结果描述。

    用于 LLM 裁判阶段：展示两候选在相同区分性输入上的实际返回值差异。
    """
    if disc_val.failures:
        for f in disc_val.failures:
            if f.get("input_slots") == inp:
                return f.get("error", "执行失败")
    # 未在失败列表中找到 → 该用例通过（返回成功状态）
    return "执行成功（返回包含 status='success' 的字典）"


# ---------------------------------------------------------------------------
# 主合成器类
# ---------------------------------------------------------------------------

class SStarSynthesizer:
    """S* 代码合成器（S*: Test Time Scaling for Code Generation，arXiv:2502.14382，2025）。

    在 PyTOD 意图函数生成场景下的适配版本，实现 4 阶段流水线：

    Phase P：并行生成 N 个候选草稿（N 种不同思维模式各一）
    Phase D：逐草稿执行追踪驱动修复（LDB 风格，基于 execution traces 精准修复）
    Phase S：S* 核心 — 生成区分性测试输入，基于执行行为选出最优候选
    Phase R：对最优候选继续精炼直到达到通过率阈值

    Args:
        llm_client:  AdkLLMClient 实例。
        n_drafts:    并行草稿数量（默认 3，上限为 THINKING_MODES 数量）。
        k_per_draft: 每草稿 Phase D 最大修复轮次（默认 3）。
    """

    def __init__(
        self,
        llm_client: Any,
        n_drafts: int = 3,
        k_per_draft: int = 3,
    ) -> None:
        self._llm = llm_client
        self._n_drafts = min(n_drafts, len(THINKING_MODES))
        self._k_per_draft = k_per_draft

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def synthesize(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        test_cases: List[TestCaseItem],
        max_iterations: int = 10,
        pass_rate_threshold: float = 0.9,
        dialogue_hint: str = "",
    ) -> Tuple[str, FuncValidation]:
        """完整 S* 合成流水线：P → D → S → R。

        Args:
            intent:              当前意图定义。
            schema:              服务 schema（提供业务上下文）。
            all_slot_descs:      槽位名 → 描述字典。
            test_cases:          Phase 2 生成的测试用例列表。
            max_iterations:      总最大迭代轮次（跨所有阶段共享预算）。
            pass_rate_threshold: 通过率阈值（达到后提前终止）。
            dialogue_hint:       可选，KB 业务背景字符串（来自真实对话数据）。

        Returns:
            (func_code, validation) 元组：
            - func_code:   完整函数代码（含 def 行）
            - validation:  最终验证结果（含通过率、失败详情、迭代次数）
        """
        from contextmind.schema_builder.pytod.helpers import SHARED_HELPERS
        from contextmind.schema_builder.pytod.validator import validate_function

        header = _build_header(intent)
        stub_code = header + '\n    return {"status": "success"}'

        # 无测试用例时：生成一个草稿即返回
        if not test_cases:
            body = self._generate_draft(intent, all_slot_descs, [], "", thinking_mode_idx=0)
            func_code = (header + "\n" + body) if body else stub_code
            return func_code, FuncValidation(intent_name=intent.name, total=0, passed=0)

        # ── Phase P：并行生成 N 个草稿 ────────────────────────────────────
        logger.info(f"[S*]   Phase P: {intent.name} — 并行生成 {self._n_drafts} 个草稿...")
        candidates: List[Tuple[str, FuncValidation]] = []

        for mode_idx in range(self._n_drafts):
            mode_name = THINKING_MODES[mode_idx]["name"]
            logger.info(f"[S*]     草稿 {mode_idx + 1}/{self._n_drafts}「{mode_name}」")
            body = self._generate_draft(
                intent, all_slot_descs, test_cases, dialogue_hint,
                thinking_mode_idx=mode_idx,
            )
            func_code = (header + "\n" + body) if body else stub_code
            validation = validate_function(intent, func_code, test_cases, SHARED_HELPERS)
            candidates.append((func_code, validation))
            logger.info(
                f"[S*]     草稿 {mode_idx + 1}「{mode_name}」："
                f"通过率 {validation.pass_rate:.1%} ({validation.passed}/{validation.total})"
            )
            if validation.pass_rate >= pass_rate_threshold:
                logger.info(f"[S*]   草稿 {mode_idx + 1} 已达阈值，跳过后续草稿生成")
                break

        # 按通过率降序排列
        candidates.sort(key=lambda x: x[1].pass_rate, reverse=True)
        best_code, best_validation = candidates[0]

        if best_validation.pass_rate >= pass_rate_threshold:
            logger.info(f"[S*]   Phase P 后已达阈值，跳过 D/S/R 阶段")
            return best_code, best_validation

        # ── Phase D：逐草稿执行追踪驱动修复 ──────────────────────────────
        logger.info(
            f"[S*]   Phase D: {intent.name} — 执行追踪修复 "
            f"({len(candidates)} 草稿 × 最多 {self._k_per_draft} 轮)..."
        )
        # Phase P 中每个草稿生成算一次 LLM 调用，从预算中扣除
        remaining = max(0, max_iterations - len(candidates))
        repaired_candidates: List[Tuple[str, FuncValidation]] = []

        for c_idx, (draft_code, draft_validation) in enumerate(candidates):
            if remaining <= 0:
                repaired_candidates.append((draft_code, draft_validation))
                continue

            if draft_validation.pass_rate >= pass_rate_threshold:
                repaired_candidates.append((draft_code, draft_validation))
                continue

            repaired_code, repaired_val = self._repair_draft(
                intent, draft_code, draft_validation, test_cases,
                max_repair_rounds=min(self._k_per_draft, remaining),
                all_slot_descs=all_slot_descs,
            )
            remaining -= repaired_val.iterations
            repaired_candidates.append((repaired_code, repaired_val))

            logger.info(
                f"[S*]     草稿 {c_idx + 1} Phase D 后："
                f"通过率 {repaired_val.pass_rate:.1%} ({repaired_val.passed}/{repaired_val.total})，"
                f"迭代 {repaired_val.iterations} 轮"
            )

            if repaired_val.pass_rate >= pass_rate_threshold:
                logger.info(f"[S*]   草稿 {c_idx + 1} 修复后已达阈值")
                break

        repaired_candidates.sort(key=lambda x: x[1].pass_rate, reverse=True)
        best_code, best_validation = repaired_candidates[0]

        if best_validation.pass_rate >= pass_rate_threshold:
            return best_code, best_validation

        # ── Phase S：S* 区分性测试选择（锦标赛模式，遍历所有候选对）──────────
        if len(repaired_candidates) >= 2 and remaining > 0:
            logger.info(
                f"[S*]   Phase S: {intent.name} — "
                f"S* 区分性测试（当前最优 {best_validation.pass_rate:.1%}，"
                f"{len(repaired_candidates)} 候选参与锦标赛）..."
            )
            # 锦标赛：当前冠军逐一与其余候选对比，胜者晋级
            champion_code, champion_val = repaired_candidates[0]
            for challenger_code, challenger_val in repaired_candidates[1:]:
                if remaining <= 0:
                    break
                winner_code, winner_val = self._select_winner(
                    intent, all_slot_descs, test_cases,
                    (champion_code, champion_val), (challenger_code, challenger_val),
                )
                # 每次 _select_winner 消耗 1 轮（生成区分性输入 + LLM judge）
                remaining -= 1
                if winner_val.pass_rate >= champion_val.pass_rate:
                    champion_code, champion_val = winner_code, winner_val

            logger.info(
                f"[S*]   Phase S 锦标赛选出最优候选："
                f"通过率 {champion_val.pass_rate:.1%} ({champion_val.passed}/{champion_val.total})"
            )
            if champion_val.pass_rate >= best_validation.pass_rate:
                best_code = champion_code
                best_validation = champion_val

        if best_validation.pass_rate >= pass_rate_threshold:
            return best_code, best_validation

        # ── Phase R：最优候选继续精炼 ─────────────────────────────────────
        if remaining > 0:
            logger.info(
                f"[S*]   Phase R: {intent.name} — "
                f"精炼最优候选（剩余预算 {remaining} 轮）..."
            )
            final_code, final_val = self._repair_draft(
                intent, best_code, best_validation, test_cases,
                max_repair_rounds=remaining,
                all_slot_descs=all_slot_descs,
            )
            logger.info(
                f"[S*]   Phase R 完成："
                f"通过率 {final_val.pass_rate:.1%} ({final_val.passed}/{final_val.total})，"
                f"迭代 {final_val.iterations} 轮"
            )
            if final_val.pass_rate > best_validation.pass_rate:
                best_code = final_code
                best_validation = final_val

        return best_code, best_validation

    # ------------------------------------------------------------------
    # Phase P：单草稿生成
    # ------------------------------------------------------------------

    def _generate_draft(
        self,
        intent: IntentDefinition,
        all_slot_descs: Dict[str, str],
        test_cases: List[TestCaseItem],
        dialogue_hint: str,
        thinking_mode_idx: int = 0,
    ) -> Optional[str]:
        """以指定思维模式生成一个候选函数体（4空格缩进，不含 def 行）。"""
        mode = THINKING_MODES[thinking_mode_idx % len(THINKING_MODES)]
        system = DRAFT_SYSTEM_TEMPLATE.format(
            thinking_mode=mode["name"],
            thinking_mode_detail=mode["detail"],
        )
        param_str = _build_param_str(intent)
        dialogue_hint_block = (
            f"\n## 业务背景（真实对话样本）\n{dialogue_hint}\n"
            if dialogue_hint else ""
        )
        user = DRAFT_USER_TEMPLATE.format(
            intent_name=intent.name,
            param_str=param_str,
            description=intent.description or intent.name,
            input_slots_desc=_build_input_slots_desc(intent, all_slot_descs),
            required_return_keys=_build_required_return_keys(intent),
            test_cases_str=_format_test_cases(test_cases),
            dialogue_hint_block=dialogue_hint_block,
        )
        try:
            raw = self._chat_sync([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            body = clean_llm_function_body(raw or "", intent.name, param_str)
            if body is None:
                logger.warning(
                    f"[S*] {intent.name}: 草稿 {thinking_mode_idx + 1} 函数体提取失败（含语法错误或无效输出），"
                    f"响应片段: {(raw or '')[:200]!r}"
                )
            return body
        except Exception as exc:
            logger.warning(f"[S*] {intent.name}: 草稿 {thinking_mode_idx + 1} LLM 调用失败 — {exc}")
            return None

    # ------------------------------------------------------------------
    # Phase D：执行追踪驱动修复（LDB 风格）
    # ------------------------------------------------------------------

    def _repair_draft(
        self,
        intent: IntentDefinition,
        func_code: str,
        validation: FuncValidation,
        test_cases: List[TestCaseItem],
        max_repair_rounds: int,
        all_slot_descs: Dict[str, str],
    ) -> Tuple[str, FuncValidation]:
        """对单个草稿进行执行追踪驱动修复（Phase D）。

        LDB（Large Language Debugger）风格：将 execution traces（实际执行输出 vs 期望）
        提供给 LLM，使其能精确定位 bug 位置而非盲目猜测。

        Returns:
            (best_code, best_validation) — 修复后的最优结果。
        """
        from contextmind.schema_builder.pytod.helpers import SHARED_HELPERS
        from contextmind.schema_builder.pytod.validator import validate_function

        best_code = func_code
        best_validation = validation
        total_iterations = 0

        for round_i in range(1, max_repair_rounds + 1):
            if best_validation.pass_rate >= 1.0:
                break

            # 提取函数体部分（去掉 def 行和 docstring，包括多行 docstring）
            current_body = _extract_function_body(best_code, intent.name) or best_code
            param_str = _build_param_str(intent)

            execution_traces = _format_execution_traces(
                best_validation.failures, best_validation.total
            )
            user = REPAIR_USER_TEMPLATE.format(
                intent_name=intent.name,
                param_str=param_str,
                description=intent.description or intent.name,
                current_body=current_body,
                fail_count=len(best_validation.failures),
                total_count=best_validation.total,
                execution_traces=execution_traces,
                required_return_keys=_build_required_return_keys(intent),
            )

            try:
                raw = self._chat_sync([
                    {"role": "system", "content": REPAIR_SYSTEM},
                    {"role": "user", "content": user},
                ])
            except Exception as exc:
                logger.warning(
                    f"[S*] {intent.name}: Phase D 第 {round_i} 轮 LLM 调用失败 — {exc}"
                )
                break

            body = clean_llm_function_body(raw or "", intent.name, param_str)
            if body is None:
                logger.warning(
                    f"[S*] {intent.name}: Phase D 第 {round_i} 轮函数体提取失败（含语法错误或无效输出）"
                )
                break

            header = _build_header(intent)
            repaired_code = header + "\n" + body
            new_validation = validate_function(intent, repaired_code, test_cases, SHARED_HELPERS)
            total_iterations += 1

            if new_validation.pass_rate > best_validation.pass_rate:
                best_code = repaired_code
                best_validation = new_validation
                logger.info(
                    f"[S*]       Phase D 第 {round_i} 轮改善："
                    f"通过率 {new_validation.pass_rate:.1%} ({new_validation.passed}/{new_validation.total})"
                )
            else:
                logger.info(
                    f"[S*]       Phase D 第 {round_i} 轮无改善："
                    f"通过率 {new_validation.pass_rate:.1%}"
                )

            if best_validation.pass_rate >= 1.0:
                break

        best_validation = FuncValidation(
            intent_name=best_validation.intent_name,
            total=best_validation.total,
            passed=best_validation.passed,
            failures=best_validation.failures,
            iterations=total_iterations,
            error=best_validation.error,
        )
        return best_code, best_validation

    # ------------------------------------------------------------------
    # Phase S：S* 区分性测试选择
    # ------------------------------------------------------------------

    def _select_winner(
        self,
        intent: IntentDefinition,
        all_slot_descs: Dict[str, str],
        test_cases: List[TestCaseItem],
        candidate_a: Tuple[str, FuncValidation],
        candidate_b: Tuple[str, FuncValidation],
    ) -> Tuple[str, FuncValidation]:
        """S* 核心：生成区分性测试输入，通过实际执行结果和 LLM 裁判选出最优候选。

        完整实现 S* 论文 Selection Phase：
        1. 让 LLM 生成能揭示两候选行为差异的测试输入（Discriminating Inputs）
        2. 在区分性输入上实际执行两候选，捕获实际返回值
        3. 将执行结果提供给 LLM 裁判，由 LLM 判断哪个候选更符合业务语义
        4. 以 LLM 裁判结果为主、原始通过率差异为辅做最终决策

        Returns:
            (winner_code, winner_validation)
        """
        from contextmind.schema_builder.pytod.helpers import SHARED_HELPERS
        from contextmind.schema_builder.pytod.validator import validate_function

        a_code, a_val = candidate_a
        b_code, b_val = candidate_b

        # 生成区分性输入
        disc_inputs = self._generate_discriminating_inputs(
            intent, all_slot_descs, a_code, b_code
        )

        if not disc_inputs:
            logger.warning(
                f"[S*] {intent.name}: 区分性输入生成失败，"
                f"按原始测试通过率选择（A: {a_val.pass_rate:.1%}, B: {b_val.pass_rate:.1%}）"
            )
            return (a_code, a_val) if a_val.pass_rate >= b_val.pass_rate else (b_code, b_val)

        # 构造区分性测试用例（只验证结构，不验证具体值）
        expected_keys = list(intent.result_slots) if intent.result_slots else []
        if "status" not in expected_keys:
            expected_keys = ["status"] + expected_keys
        disc_test_cases = [
            TestCaseItem(
                input_slots=inp,
                expected_keys=expected_keys,
                description=f"S*区分性测试-{i + 1}",
            )
            for i, inp in enumerate(disc_inputs)
        ]

        # 在区分性输入上实际执行两候选，收集结果
        a_disc_val = validate_function(intent, a_code, disc_test_cases, SHARED_HELPERS)
        b_disc_val = validate_function(intent, b_code, disc_test_cases, SHARED_HELPERS)
        logger.info(
            f"[S*]     区分性测试（{len(disc_test_cases)} 条）："
            f"A={a_disc_val.pass_rate:.1%}, B={b_disc_val.pass_rate:.1%}"
        )

        # 调用 LLM 裁判：根据实际执行结果（含失败详情）判断哪个候选更优
        # 这是 S* 论文 Selection Phase 的核心：Execution-Grounded Judging
        judge_result = self._judge_candidates(
            intent, a_code, b_code,
            a_disc_val, b_disc_val,
            disc_inputs,
        )

        if judge_result == "A":
            logger.info(f"[S*]     LLM 裁判选择：A（{a_val.pass_rate:.1%}）")
            return a_code, a_val
        elif judge_result == "B":
            logger.info(f"[S*]     LLM 裁判选择：B（{b_val.pass_rate:.1%}）")
            return b_code, b_val
        else:
            # LLM 裁判失败，回退到综合评分
            a_score = 0.8 * a_val.pass_rate + 0.2 * a_disc_val.pass_rate
            b_score = 0.8 * b_val.pass_rate + 0.2 * b_disc_val.pass_rate
            logger.info(
                f"[S*]     LLM 裁判失败，综合评分回退：A={a_score:.3f}, B={b_score:.3f}，"
                f"选择{'A' if a_score >= b_score else 'B'}"
            )
            return (a_code, a_val) if a_score >= b_score else (b_code, b_val)

    def _judge_candidates(
        self,
        intent: IntentDefinition,
        a_code: str,
        b_code: str,
        a_disc_val: FuncValidation,
        b_disc_val: FuncValidation,
        disc_inputs: List[Dict[str, Any]],
    ) -> str:
        """调用 LLM 裁判，根据区分性测试的实际执行结果选择更优候选（S* 论文核心）。

        Returns:
            "A"、"B" 或 ""（失败时返回空字符串触发回退）。
        """
        # 构建执行对比文本（展示每个区分性输入下的实际执行结果）
        comparison_lines: List[str] = []
        for i, inp in enumerate(disc_inputs[:3], 1):
            inp_str = json.dumps(inp, ensure_ascii=False)
            # 从失败详情中找对应结果
            a_result = _find_disc_result(a_disc_val, inp)
            b_result = _find_disc_result(b_disc_val, inp)
            comparison_lines.append(
                f"测试 {i}: 输入 = {inp_str}\n"
                f"  A 实际输出: {a_result}\n"
                f"  B 实际输出: {b_result}"
            )
        execution_comparison = "\n\n".join(comparison_lines) if comparison_lines else "（无执行记录）"

        user = JUDGE_USER_TEMPLATE.format(
            intent_name=intent.name,
            description=intent.description or intent.name,
            candidate_a=a_code,
            candidate_b=b_code,
            execution_comparison=execution_comparison,
        )
        try:
            raw = self._chat_sync([
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ])
            verdict = (raw or "").strip().upper()
            if "A" in verdict and "B" not in verdict:
                return "A"
            if "B" in verdict and "A" not in verdict:
                return "B"
            # 如果同时包含 A 和 B，取第一个出现的字母
            for ch in verdict:
                if ch == "A":
                    return "A"
                if ch == "B":
                    return "B"
        except Exception as exc:
            logger.warning(f"[S*] {intent.name}: LLM 裁判调用失败 — {exc}")
        return ""

    def _generate_discriminating_inputs(
        self,
        intent: IntentDefinition,
        all_slot_descs: Dict[str, str],
        candidate_a: str,
        candidate_b: str,
    ) -> List[Dict[str, Any]]:
        """调用 LLM 生成能区分两候选行为的测试输入（S* 核心）。

        Returns:
            槽位值字典列表（每个元素是一个测试输入），失败时返回空列表。
        """
        user = DISCRIMINATE_USER_TEMPLATE.format(
            intent_name=intent.name,
            description=intent.description or intent.name,
            input_slots_desc=_build_input_slots_desc(intent, all_slot_descs),
            candidate_a=candidate_a,
            candidate_b=candidate_b,
        )
        try:
            raw = self._chat_sync([
                {"role": "system", "content": DISCRIMINATE_SYSTEM},
                {"role": "user", "content": user},
            ])
        except Exception as exc:
            logger.warning(f"[S*] {intent.name}: 区分性输入 LLM 调用失败 — {exc}")
            return []

        if not raw:
            return []

        # 从 LLM 输出中提取 JSON 数组
        cleaned = raw.strip()
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON 数组片段
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    if isinstance(data, list):
                        return [d for d in data if isinstance(d, dict)]
                except json.JSONDecodeError:
                    pass
            logger.warning(
                f"[S*] {intent.name}: 区分性输入 JSON 解析失败，"
                f"响应片段: {cleaned[:200]!r}"
            )
        return []

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _chat_sync(self, messages: List[Dict[str, str]]) -> str:
        """同步调用 LLM，返回助手消息内容。"""
        if hasattr(self._llm, "chat_sync"):
            return self._llm.chat_sync(messages)
        if hasattr(self._llm, "chat"):
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._llm.chat(messages))
            finally:
                loop.close()
        if hasattr(self._llm, "chat_async"):
            import asyncio
            import concurrent.futures

            async def _call() -> str:
                return await self._llm.chat_async(messages)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, _call()).result()
            else:
                return asyncio.run(_call())
        raise RuntimeError("LLM client 不支持 chat_sync 或 chat 方法")
