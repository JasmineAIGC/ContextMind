"""
CodeTree 代码合成器。

实现 CodeTree（arXiv:2411.04329，2024/2025）在 PyTOD 意图函数生成场景下的适配版本：

  Phase G — 根节点生成（Root Generation）：
    生成初始候选函数，作为搜索树的根节点。

  Phase E — 树扩展（Tree Expansion）：
    对每个失败测试用例独立生成修复分支（子节点）。
    每条分支专注修复一个失败用例，避免"一刀切"修复影响其他用例。

  Phase S — 节点选择（UCB-guided Selection）：
    使用 UCB（Upper Confidence Bound）评分在整棵树中选择下一个待扩展节点：
    UCB = pass_rate + C × sqrt(ln(parent_visits + 1) / (node_visits + 1))
    高通过率节点优先（exploitation）+ 访问少的节点获得额外奖励（exploration）。

  Phase V — 叶节点验证（Optional Leaf Validation）：
    对候选叶节点做业务语义快速评审（LLM 反思），过滤掉语义不合理的候选。

与 ACIA（线性修复链）和 S*（平铺并行）的关键区别：
  - CodeTree：树形搜索，每次针对单个失败用例生成专用修复分支
  - 不同分支互不干扰，可同时探索多种修复策略
  - UCB 机制平衡深度优先（利用）和广度优先（探索）

参考文献：
    CodeTree: Agent-guided Tree Search for Code Generation
    with Large Language Models, arXiv:2411.04329, 2024/2025.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema
from contextmind.schema_builder.pytod.models import FuncValidation, TestCaseItem

from contextmind.schema_builder.pytod.ctree.prompts import (
    EXPAND_SYSTEM,
    EXPAND_USER_TEMPLATE,
    REFLECT_SYSTEM,
    REFLECT_USER_TEMPLATE,
    ROOT_SYSTEM,
    ROOT_USER_TEMPLATE,
)

logger = get_logger(__name__)

# UCB 探索系数：越大越倾向于探索未访问节点
_UCB_C = 1.4

# 每次扩展最多生成的子节点数（对应每次最多处理的失败用例数）
_MAX_EXPAND_CHILDREN = 2


# ---------------------------------------------------------------------------
# 树节点
# ---------------------------------------------------------------------------

class _TreeNode:
    """CodeTree 搜索树节点。

    每个节点保存一个候选函数实现及其验证结果。
    子节点通过针对父节点失败用例的修复生成。

    Attributes:
        func_code:   完整函数代码（含 def 行和 docstring）。
        validation:  测试验证结果。
        depth:       节点深度（根节点为 0）。
        visits:      该节点被选中扩展的次数（UCB 分母）。
        parent:      父节点引用（根节点为 None）。
        children:    子节点列表。
        target_case: 导致此节点生成的目标失败用例（根节点为 None）。
    """

    def __init__(
        self,
        func_code: str,
        validation: FuncValidation,
        depth: int = 0,
        parent: Optional["_TreeNode"] = None,
        target_case: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.func_code = func_code
        self.validation = validation
        self.depth = depth
        self.parent = parent
        self.target_case = target_case
        self.children: List["_TreeNode"] = []
        self.visits: int = 0

    def ucb_score(self, parent_visits: int, c: float = _UCB_C) -> float:
        """计算 UCB 分数（Upper Confidence Bound）。

        UCB = pass_rate + C × sqrt(ln(parent_visits + 1) / (visits + 1))

        当 pass_rate 相近时，访问次数少的节点获得更高探索奖励，
        避免搜索集中在单一路径上。
        """
        exploit = self.validation.pass_rate
        explore = c * math.sqrt(math.log(parent_visits + 1) / (self.visits + 1))
        return exploit + explore

    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def all_descendants(self) -> List["_TreeNode"]:
        """返回该节点下所有后代节点（含自身）。"""
        result = [self]
        for child in self.children:
            result.extend(child.all_descendants())
        return result


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _extract_function_body(raw: str, intent_name: str) -> Optional[str]:
    """从 LLM 输出中提取并规范化函数体（4空格缩进，不含 def 行和 docstring）。"""
    if not raw or not raw.strip():
        return None

    text = re.sub(r"```(?:python)?\s*\n?", "", raw)
    text = re.sub(r"\n?```", "", text)
    text = text.strip()

    lines = text.splitlines()
    filtered: List[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if stripped.startswith("def ") and "(" in stripped:
            i += 1
            continue

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

    if "return " not in body:
        logger.warning(f"[CodeTree] {intent_name}: 提取的函数体不含 return 语句")
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
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    return ", ".join([f"{p}=None" for p in params]) if params else ""


def _build_input_slots_desc(intent: IntentDefinition, all_slot_descs: Dict[str, str]) -> str:
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


def _build_required_return_keys(intent: IntentDefinition) -> str:
    keys = list(intent.result_slots) if intent.result_slots else []
    if "status" not in keys:
        keys = ["status"] + keys
    lines = [f'  "{k}": ...' for k in keys]
    keys_str = "{\n" + ",\n".join(lines) + "\n}"
    return (
        f"{keys_str}\n\n"
        f"必须出现的键（缺少任何一个都算测试失败）：{', '.join(repr(k) for k in keys)}"
    )


def _format_test_cases(test_cases: List[TestCaseItem], max_cases: int = 5) -> str:
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


def _format_failures(failures: List[Dict[str, Any]], max_failures: int = 3) -> str:
    if not failures:
        return "（无失败用例）"
    lines: List[str] = []
    for i, f in enumerate(failures[:max_failures], 1):
        lines.append(
            f"失败 {i}:\n"
            f"  输入: {json.dumps(f.get('input_slots', {}), ensure_ascii=False)}\n"
            f"  错误: {f.get('error', '未知')}"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# 主合成器类
# ---------------------------------------------------------------------------

class CodeTreeSynthesizer:
    """CodeTree 代码合成器（arXiv:2411.04329，2024/2025）。

    通过 UCB 引导的树搜索生成 PyTOD 意图函数，每次扩展专注于修复
    单个失败测试用例，避免线性修复中"修好一个破坏另一个"的问题。

    Args:
        llm_client:    AdkLLMClient 实例。
        max_children:  每次扩展的最大子节点数（默认 2）。
        ucb_c:         UCB 探索系数（默认 1.4）。
    """

    def __init__(
        self,
        llm_client: Any,
        max_children: int = _MAX_EXPAND_CHILDREN,
        ucb_c: float = _UCB_C,
    ) -> None:
        self._llm = llm_client
        self._max_children = max_children
        self._ucb_c = ucb_c

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
        """完整 CodeTree 合成流水线：G → E/S 循环（树搜索）→ 返回最优节点。

        Args:
            intent:              当前意图定义。
            schema:              服务 schema（提供上下文）。
            all_slot_descs:      槽位名 → 描述的映射字典。
            test_cases:          Phase 2 生成的测试用例列表。
            max_iterations:      最大扩展轮次（预算）。
            pass_rate_threshold: 通过率阈值（达到后提前终止）。
            dialogue_hint:       可选，KB 业务背景字符串。

        Returns:
            (func_code, validation) 元组。
        """
        from contextmind.schema_builder.pytod.helpers import SHARED_HELPERS
        from contextmind.schema_builder.pytod.validator import validate_function

        header = _build_header(intent)
        stub_code = header + '\n    return {"status": "success"}'

        # 无测试用例时：生成一个根节点即返回
        if not test_cases:
            body = self._generate_root(intent, all_slot_descs, [], dialogue_hint)
            func_code = (header + "\n" + body) if body else stub_code
            return func_code, FuncValidation(intent_name=intent.name, total=0, passed=0)

        # ── Phase G：根节点生成 ────────────────────────────────────────
        logger.info(f"[CodeTree]   Phase G: {intent.name} — 生成根节点...")
        body = self._generate_root(intent, all_slot_descs, test_cases, dialogue_hint)
        func_code = (header + "\n" + body) if body else stub_code
        validation = validate_function(intent, func_code, test_cases, SHARED_HELPERS)
        logger.info(
            f"[CodeTree]   根节点: {intent.name} — "
            f"通过率 {validation.pass_rate:.1%} ({validation.passed}/{validation.total})"
        )

        # 初始化搜索树
        root = _TreeNode(func_code=func_code, validation=validation, depth=0)
        total_iterations = 1  # 根节点生成算一次迭代

        if validation.pass_rate >= pass_rate_threshold:
            logger.info(f"[CodeTree]   根节点已达阈值，无需树搜索")
            validation = FuncValidation(
                intent_name=validation.intent_name,
                total=validation.total,
                passed=validation.passed,
                failures=validation.failures,
                iterations=total_iterations,
                error=validation.error,
            )
            return func_code, validation

        # ── Phase E/S 循环：树扩展 + UCB 选择 ────────────────────────
        logger.info(
            f"[CodeTree]   开始树搜索（最多 {max_iterations - total_iterations} 轮扩展）..."
        )

        for expand_iter in range(1, max_iterations - total_iterations + 1):
            # 选择：UCB 评分选出最优叶节点
            selected = self._select_node(root)
            if selected is None:
                logger.info(f"[CodeTree]   树已耗尽可扩展节点，停止搜索")
                break

            selected.visits += 1
            logger.info(
                f"[CodeTree]   扩展第 {expand_iter} 轮: {intent.name} "
                f"— 深度 {selected.depth}，通过率 {selected.validation.pass_rate:.1%}"
            )

            # 扩展：针对每个失败用例生成修复子节点
            failures = selected.validation.failures
            if not failures:
                logger.info(f"[CodeTree]   节点无失败用例但未达阈值，跳过扩展")
                continue

            # 最多扩展 self._max_children 个失败用例
            expand_targets = failures[:self._max_children]
            new_children_added = 0

            for fail in expand_targets:
                if total_iterations >= max_iterations:
                    break
                child_body = self._expand_node(
                    intent, all_slot_descs, selected.func_code,
                    selected.validation, test_cases, fail,
                )
                total_iterations += 1
                if child_body is None:
                    continue

                child_code = header + "\n" + child_body
                child_val = validate_function(intent, child_code, test_cases, SHARED_HELPERS)
                child_node = _TreeNode(
                    func_code=child_code,
                    validation=child_val,
                    depth=selected.depth + 1,
                    parent=selected,
                    target_case=fail,
                )
                selected.children.append(child_node)
                new_children_added += 1
                logger.info(
                    f"[CodeTree]     子节点（深度 {child_node.depth}）："
                    f"通过率 {child_val.pass_rate:.1%} "
                    f"({child_val.passed}/{child_val.total})，"
                    f"目标用例: {json.dumps(fail.get('input_slots', {}), ensure_ascii=False)}"
                )
                if child_val.pass_rate >= pass_rate_threshold:
                    logger.info(f"[CodeTree]   子节点已达阈值，停止搜索")
                    break

            if new_children_added == 0:
                logger.info(f"[CodeTree]   扩展失败（所有 LLM 调用均返回 None），继续选择")

            # 检查是否有节点达到阈值
            best_so_far = self._best_node(root)
            if best_so_far.validation.pass_rate >= pass_rate_threshold:
                logger.info(
                    f"[CodeTree]   搜索完成：最优节点通过率 "
                    f"{best_so_far.validation.pass_rate:.1%}（已达阈值）"
                )
                break

        # 从整棵树中选出最优节点
        best_node = self._best_node(root)
        logger.info(
            f"[CodeTree]   树搜索完成：{intent.name} — "
            f"最优通过率 {best_node.validation.pass_rate:.1%} "
            f"({best_node.validation.passed}/{best_node.validation.total})，"
            f"共扩展 {total_iterations} 轮"
        )

        final_val = FuncValidation(
            intent_name=best_node.validation.intent_name,
            total=best_node.validation.total,
            passed=best_node.validation.passed,
            failures=best_node.validation.failures,
            iterations=total_iterations,
            error=best_node.validation.error,
        )
        return best_node.func_code, final_val

    # ------------------------------------------------------------------
    # Phase G：根节点生成
    # ------------------------------------------------------------------

    def _generate_root(
        self,
        intent: IntentDefinition,
        all_slot_descs: Dict[str, str],
        test_cases: List[TestCaseItem],
        dialogue_hint: str,
    ) -> Optional[str]:
        """生成根节点函数体（初始候选）。"""
        dialogue_hint_block = (
            f"\n## 业务背景（对话摘录）\n{dialogue_hint[:800]}\n"
            if dialogue_hint else ""
        )
        user = ROOT_USER_TEMPLATE.format(
            intent_name=intent.name,
            param_str=_build_param_str(intent),
            description=intent.description or intent.name,
            input_slots_desc=_build_input_slots_desc(intent, all_slot_descs),
            required_return_keys=_build_required_return_keys(intent),
            test_cases_str=_format_test_cases(test_cases),
            dialogue_hint_block=dialogue_hint_block,
        )
        try:
            raw = self._chat_sync([
                {"role": "system", "content": ROOT_SYSTEM},
                {"role": "user", "content": user},
            ])
            body = _extract_function_body(raw or "", intent.name)
            if body is None:
                logger.warning(
                    f"[CodeTree] {intent.name}: 根节点函数体提取失败，"
                    f"响应片段: {(raw or '')[:200]!r}"
                )
            return body
        except Exception as exc:
            logger.warning(f"[CodeTree] {intent.name}: 根节点 LLM 调用失败 — {exc}")
            return None

    # ------------------------------------------------------------------
    # Phase E：树扩展（针对单个失败用例生成子节点）
    # ------------------------------------------------------------------

    def _expand_node(
        self,
        intent: IntentDefinition,
        all_slot_descs: Dict[str, str],
        current_code: str,
        validation: FuncValidation,
        test_cases: List[TestCaseItem],
        target_failure: Dict[str, Any],
    ) -> Optional[str]:
        """针对特定失败测试用例生成修复子节点函数体。

        CodeTree 的核心扩展策略：每个扩展分支专注于修复一个失败用例，
        避免通用修复同时影响多个用例间的依赖关系。
        """
        current_body = _extract_function_body(current_code, intent.name) or current_code
        target_input = json.dumps(target_failure.get("input_slots", {}), ensure_ascii=False)
        target_error = target_failure.get("error", "未知错误")

        # 其他用例摘要（提醒 LLM 不要破坏通过的用例）
        passing_cases = [
            tc for tc in test_cases
            if tc.input_slots not in [f.get("input_slots") for f in validation.failures]
        ]
        other_cases_str = _format_test_cases(passing_cases[:3])

        execution_traces = _format_failures(validation.failures[:3])

        user = EXPAND_USER_TEMPLATE.format(
            intent_name=intent.name,
            param_str=_build_param_str(intent),
            description=intent.description or intent.name,
            current_body=current_body,
            target_input=target_input,
            target_error=target_error,
            other_cases_str=other_cases_str,
            execution_traces=execution_traces,
            required_return_keys=_build_required_return_keys(intent),
        )
        try:
            raw = self._chat_sync([
                {"role": "system", "content": EXPAND_SYSTEM},
                {"role": "user", "content": user},
            ])
            body = _extract_function_body(raw or "", intent.name)
            if body is None:
                logger.warning(
                    f"[CodeTree] {intent.name}: 扩展节点函数体提取失败，"
                    f"响应片段: {(raw or '')[:200]!r}"
                )
            return body
        except Exception as exc:
            logger.warning(f"[CodeTree] {intent.name}: 扩展节点 LLM 调用失败 — {exc}")
            return None

    # ------------------------------------------------------------------
    # Phase S：UCB 节点选择
    # ------------------------------------------------------------------

    def _select_node(self, root: _TreeNode) -> Optional[_TreeNode]:
        """使用 UCB 评分在树中选择下一个待扩展的叶节点。

        UCB = pass_rate + C × sqrt(ln(parent_visits + 1) / (node_visits + 1))

        只选择有失败用例的叶节点（有可扩展空间）。
        """
        all_nodes = root.all_descendants()
        # 只考虑叶节点（未展开）且有失败用例的节点
        expandable = [
            n for n in all_nodes
            if n.is_leaf() and n.validation.failures
        ]
        if not expandable:
            return None

        parent_visits = root.visits
        best = max(expandable, key=lambda n: n.ucb_score(parent_visits, self._ucb_c))
        return best

    def _best_node(self, root: _TreeNode) -> _TreeNode:
        """从整棵树中找出通过率最高的节点。"""
        all_nodes = root.all_descendants()
        return max(all_nodes, key=lambda n: (n.validation.pass_rate, -n.depth))

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
