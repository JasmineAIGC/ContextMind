"""
FnCTOD 对话任务全链路追踪脚本（单条会话）

展示目标：
    体现 FnCTOD（Function Calling for Task-Oriented Dialogue）算法在
    客服/外呼对话中的核心价值——通过「域选择 → 函数调用」两阶段范式，
    将对话状态追踪（DST）建模为结构化函数调用，同时生成自然语言回复。

功能：
  1. 从 resources/data/chat_test_100.json 中随机抽取一条安逸花外呼对话作为测试样本。
  2. 记录 FnCTOD 运行前的全部预置信息：
       函数 Schema（域/参数定义）、系统提示词模板、域描述。
  3. 完整追踪 FnCTOD 两阶段流水线的每步输入与输出：
       Stage 1 域选择（Domain Selection）— 识别当前对话涉及的业务域
       Stage 2 函数调用（Function Calling）— 以 function_call 格式提取状态 + 生成自然语言回复
  4. 将所有内容写入一个 Markdown 文件，各模块用标题和代码块清晰区分。
  5. 在文末对比 FnCTOD 提取的对话状态 vs 实际坐席回复，直观展示算法价值。

与 PyTOD 的对比：
    PyTOD：动作解析器 → 执行引擎（调用 CRM API）→ 对话管理器
    FnCTOD：域选择 → 函数调用（DST + 自然语言回复一步完成）
    FnCTOD 不调用外部 API，而是让 LLM 直接以 function_call 格式输出结构化状态。

环境要求：
    在项目根目录创建 .env 文件，填写：
        LLM_BASE_URL=https://your-endpoint/v1
        LLM_API_KEY=your_key_here        （或 QWEN3_API_KEY）
        LLM_MODEL=Qwen3-32B              （可选，默认 Qwen3-32B）

    若未配置 LLM 环境，脚本仍会运行：LLM 调用步骤以「⚠️ LLM 未配置」标注，
    其余预置信息（schema、提示词模板等）会完整输出。

用法：
    cd /path/to/ContextMind
    python examples/fnctod_trace_demo.py
    python examples/fnctod_trace_demo.py --seed 42            # 固定随机种子
    python examples/fnctod_trace_demo.py --index 5            # 直接指定第 5 条数据（0-based）
    python examples/fnctod_trace_demo.py --output /tmp/my_trace.md
    python examples/fnctod_trace_demo.py --verbose            # 同时打印追踪日志到控制台
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 将项目根目录加入 Python 搜索路径，使脚本可在任意目录直接执行
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.infra.llm_client import LLMConfig, SimpleLLMClient
from contextmind.modes.fnctod import FnCTODTracker, FunctionManager
from contextmind.modes.fnctod.function_manager import FunctionCall, DialogueTurn
from contextmind.modes.fnctod.schemas import get_callcenter_function_schema

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"

# 安逸花外呼场景上下文（注入 Stage 2 系统提示）
_SCENARIO_CONTEXT = (
    "这是一个外呼小额借款推介场景（安逸花外呼促活）。"
    "坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。"
    "标准流程：① 核实用户身份（姓名/手机尾号）→ ② 告知可用额度和利率 → "
    "③ 解答疑问（还款方式、账单争议等）→ ④ 引导用户在 APP 完成借款操作 → "
    "⑤ 确认无未解决诉求后礼貌告别。"
)

# 坐席/用户发言前缀（与 pytod_trace_demo 保持一致）
_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


# ===========================================================================
# 追踪型 FnCTOD Tracker（继承 FnCTODTracker，拦截两阶段 I/O）
# ===========================================================================

class TracingFnCTODTracker(FnCTODTracker):
    """
    在 FnCTODTracker 基础上增加逐步追踪能力的子类。

    每次调用 ``process_turn()`` 时，将两阶段的完整 I/O 写入 ``self.trace``：
      - Stage 1：域选择（Domain Selection）
            输入 messages + LLM 响应 + 解析出的 domain 列表
      - Stage 2：函数调用（Function Calling）
            输入 messages（含系统提示、对话历史、当前状态）
            + LLM 响应原文 + 解析出的 FunctionCall + 自然语言回复
    """

    def __init__(self, *args, verbose: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.verbose = verbose
        # 追踪数据根节点
        self.trace: Dict[str, Any] = {"turns": []}

    async def _select_domains(self, user_utterance: str) -> List[str]:
        """覆盖父类，在调用 LLM 前后插入追踪记录。"""
        from contextmind.modes.fnctod.function_manager import FunctionManager as _FM
        import time

        system_prompt = self.function_manager.build_system_prompt(include_all_specs=False)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for turn in self.dialogue_history[-3:]:
            messages.append({"role": "user", "content": turn.user_utterance})
            if turn.system_utterance:
                messages.append({"role": "assistant", "content": turn.system_utterance})
        messages.append({"role": "user", "content": user_utterance})

        stage_trace: Dict[str, Any] = {
            "stage": 1,
            "name": "域选择（Domain Selection）",
            "role": "根据用户发言，从所有可用业务域中选出当前对话涉及的域",
            "input_messages": messages,
        }

        if self.verbose:
            _print_stage_header(1, "域选择（Domain Selection）")
            _print_messages(messages)

        try:
            response = await self.llm_client.chat_async(messages)
            domains = self.parser.parse_domain_selection(response)
            if not domains:
                domains = [self.function_manager.get_domain_names()[0]]
            stage_trace.update({
                "llm_raw_response": response,
                "selected_domains": domains,
                "llm_ok": True,
            })
        except Exception as exc:
            domains = self.function_manager.get_domain_names()
            stage_trace.update({
                "llm_raw_response": None,
                "selected_domains": domains,
                "llm_ok": False,
                "error": str(exc),
            })

        if self.verbose:
            print(f"\n  ▶ 选出域：{domains}\n")

        # 附加到当前轮次的 stages 列表（由 process_turn 创建）
        self._current_turn_stages.append(stage_trace)
        return domains

    async def _call_function(
        self, user_utterance: str, domains: List[str]
    ) -> Tuple[Optional[FunctionCall], str]:
        """覆盖父类，在调用 LLM 前后插入追踪记录。"""
        system_prompt = self._build_function_call_prompt(domains)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for turn in self.dialogue_history[-self.max_history_turns:]:
            messages.append({"role": "user", "content": turn.user_utterance})
            if turn.function_call and turn.system_utterance:
                assistant_content = (
                    f"{turn.function_call.to_xml()}\n{turn.system_utterance}"
                )
                messages.append({"role": "assistant", "content": assistant_content})
            elif turn.system_utterance:
                messages.append({"role": "assistant", "content": turn.system_utterance})

        if self.current_state:
            state_by_domain: Dict[str, Dict] = {}
            for key, value in self.current_state.items():
                if "-" in key:
                    domain, param = key.split("-", 1)
                    state_by_domain.setdefault(domain, {})[param] = value
            messages.append({
                "role": "system",
                "content": (
                    f"Previous cumulative state:\n"
                    f"{json.dumps(state_by_domain, ensure_ascii=False, indent=2)}\n\n"
                    "Remember to include ALL previous parameters in your function call, "
                    "plus any new ones from the current turn."
                ),
            })

        messages.append({"role": "user", "content": user_utterance})

        stage_trace: Dict[str, Any] = {
            "stage": 2,
            "name": "函数调用（Function Calling）",
            "role": "以 function_call 格式提取对话状态（DST），同时生成自然语言回复",
            "input_messages": messages,
            "domains": domains,
        }

        if self.verbose:
            _print_stage_header(2, "函数调用（Function Calling）")
            _print_messages(messages)

        try:
            response = await self.llm_client.chat_async(messages)
            function_call, natural_response = self.parser.parse_function_call(response)
            if not function_call:
                natural_response = response
            stage_trace.update({
                "llm_raw_response": response,
                "function_call": function_call.to_dict() if function_call else None,
                "natural_response": natural_response,
                "llm_ok": True,
            })
        except Exception as exc:
            function_call = None
            natural_response = "（LLM 未配置，无法生成回复）"
            stage_trace.update({
                "llm_raw_response": None,
                "function_call": None,
                "natural_response": natural_response,
                "llm_ok": False,
                "error": str(exc),
            })

        if self.verbose:
            fc_str = (
                json.dumps(stage_trace["function_call"], ensure_ascii=False)
                if stage_trace["function_call"]
                else "（无 function_call）"
            )
            print(f"\n  ▶ function_call：{fc_str[:120]}")
            print(f"  ▶ 自然语言回复：{natural_response[:80]}\n")

        self._current_turn_stages.append(stage_trace)
        return function_call, natural_response

    async def process_turn(
        self, user_utterance: str, system_utterance: str = ""
    ) -> Dict[str, Any]:
        """覆盖父类，汇总当前轮次的所有阶段追踪。"""
        # 初始化本轮追踪容器（供 _select_domains / _call_function 填充）
        self._current_turn_stages: List[Dict[str, Any]] = []

        result = await super().process_turn(user_utterance, system_utterance)

        turn_trace: Dict[str, Any] = {
            "turn_index": self.turn_count,   # super() 已递增 turn_count
            "user_input": user_utterance,
            "stages": self._current_turn_stages,
            "final_state": result["state"],
            "function_call": result["function_call"],
            "final_response": result["response"],
        }
        self.trace["turns"].append(turn_trace)
        return result


# ===========================================================================
# 辅助：预定义配置采集
# ===========================================================================

def collect_predefined_config(
    function_manager: FunctionManager,
    scenario_context: str,
) -> Dict[str, Any]:
    """
    采集 FnCTOD 运行前的全部预定义/预置信息：
      - 场景上下文描述
      - 函数 Schema（域名、描述、所有参数）
      - 系统提示词（Domain Selection / Function Calling 两种版本）
    """
    domains_info = []
    for domain in function_manager.get_all_domains():
        domains_info.append({
            "name": domain.name,
            "description": domain.description,
            "parameters": [
                {
                    "name": p.name,
                    "description": p.description,
                    "type": p.param_type.value if hasattr(p.param_type, "value") else str(p.param_type),
                    "required": p.required,
                    "enum_values": p.enum_values,
                }
                for p in domain.parameters
            ],
            "prompt_format": domain.to_prompt_format(),
        })

    return {
        "scenario_context": scenario_context,
        "domains": domains_info,
        "system_prompt_domain_selection": function_manager.build_system_prompt(
            include_all_specs=False
        ),
        "system_prompt_function_calling": function_manager.build_system_prompt(
            include_all_specs=True
        ),
    }


# ===========================================================================
# Markdown 渲染器
# ===========================================================================

def _md_code(text: str, lang: str = "") -> str:
    """将文本包裹在 Markdown 代码块中。"""
    return f"```{lang}\n{text.strip()}\n```"


def _md_json(obj: Any) -> str:
    """将对象序列化为 JSON 代码块。"""
    return _md_code(json.dumps(obj, ensure_ascii=False, indent=2), "json")


def _messages_to_md(messages: Optional[List[Dict]]) -> str:
    """将 OpenAI-style messages 列表渲染为 Markdown 引用块。"""
    if not messages:
        return "_（无 messages）_"
    parts = []
    for msg in messages:
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        parts.append(f"**`[{role}]`**")
        parts.append(_md_code(content))
    return "\n\n".join(parts)


def render_markdown(trace: Dict[str, Any]) -> str:
    """
    将全量追踪数据渲染为可读的 Markdown 文档。

    文档结构：
      # FnCTOD 对话任务追踪报告
      ## 一、概述
      ## 二、对话背景（测试数据）
      ## 三、FnCTOD 预置配置（运行前定义）
      ## 四、FnCTOD 两阶段流水线追踪
      ## 五、结果对比与分析
    """
    meta = trace["metadata"]
    test = trace["test_data"]
    cfg = trace["predefined_config"]
    run = trace["fnctod_run"]
    turns = run["turns"]

    lines: List[str] = []

    # ------------------------------------------------------------------ #
    # 文档标题
    # ------------------------------------------------------------------ #
    lines += [
        "# FnCTOD 对话任务追踪报告",
        "",
        f"> **生成时间**：{meta['timestamp']}  ",
        f"> **会话 ID**：`{meta['session_id']}`  ",
        f"> **算法**：{meta['algorithm']}  ",
        f"> **场景**：{meta['scenario']}",
        "",
        "---",
        "",
    ]

    # ------------------------------------------------------------------ #
    # 一、概述
    # ------------------------------------------------------------------ #
    lines += [
        "## 一、概述",
        "",
        "本报告记录了 **FnCTOD（Function Calling for Task-Oriented Dialogue）** 算法",
        "在一条安逸花外呼真实对话上的完整运行过程。",
        "",
        "**FnCTOD 的核心价值**：传统 DST（对话状态追踪）直接提取「槽位-值」对，",
        "FnCTOD 将槽位提取建模为**函数调用**，输出更结构化、更易扩展，",
        "同时在同一次 LLM 调用中完成状态提取和自然语言回复生成。",
        "",
        "```",
        "用户输入",
        "  │",
        "  ▼",
        "┌─────────────────────────────────┐",
        "│  Stage 1  域选择                │  识别当前对话涉及的业务域",
        "│           Domain Selection      │  （多域场景下启用）",
        "└──────────────┬──────────────────┘",
        "               │ 候选 domain 列表",
        "               ▼",
        "┌─────────────────────────────────┐",
        "│  Stage 2  函数调用              │  LLM 以 <function_call> 格式",
        "│           Function Calling      │  提取对话状态 + 生成自然语言回复",
        "└──────────────┬──────────────────┘",
        "               │",
        "               ▼",
        "结构化状态（DST 结果）+ 自然语言回复",
        "```",
        "",
        "---",
        "",
    ]

    # ------------------------------------------------------------------ #
    # 二、对话背景（测试数据）
    # ------------------------------------------------------------------ #
    lines += [
        "## 二、对话背景（测试数据）",
        "",
        "**数据来源**：`resources/data/chat_test_100.json`，随机抽取一条会话",
        "",
        "### 2.1 用户信息",
        "",
        _md_code(test["用户信息"]),
        "",
        "### 2.2 完整对话历史",
        "",
        "> 以下为本条会话的原始对话记录，最后一条用户发言将作为 FnCTOD 的当前输入。",
        "",
    ]
    for idx, utt in enumerate(test["对话历史"]):
        if utt.startswith(_AGENT_PREFIX):
            speaker = "🤖 **坐席**"
            content = utt[len(_AGENT_PREFIX):]
        elif utt.startswith(_USER_PREFIX):
            speaker = "👤 **用户**"
            content = utt[len(_USER_PREFIX):]
        else:
            speaker = "❓"
            content = utt
        lines.append(f"**第 {idx + 1} 句** · {speaker}：{content}")
        lines.append("")

    lines += [
        "### 2.3 当前待处理的用户发言（FnCTOD 输入）",
        "",
        f"> 👤 **用户**：**{test['最后用户输入']}**",
        "",
        f"_（对话历史中共注入 {test['注入_tracker_history_turns']} 轮历史到 Tracker）_",
        "",
        "### 2.4 实际坐席回复（来自数据集，供对比）",
        "",
        f"> 🤖 **实际坐席回复**：{test['坐席回复_实际']}",
        "",
        f"**人工校验标签**：`{test['人工校验']}`",
        "",
        "---",
        "",
    ]

    # ------------------------------------------------------------------ #
    # 三、FnCTOD 预置配置（运行前定义）
    # ------------------------------------------------------------------ #
    lines += [
        "## 三、FnCTOD 预置配置（运行前定义）",
        "",
        "> 以下内容在 FnCTOD 启动前已完全定义，不依赖用户输入，是算法的「知识底座」。",
        "",
    ]

    # 3.1 场景上下文
    lines += [
        "### 3.1 场景上下文（注入系统提示的业务背景）",
        "",
        _md_code(cfg["scenario_context"]),
        "",
    ]

    # 3.2 函数 Schema
    lines += [
        "### 3.2 函数 Schema（域名、描述与参数定义）",
        "",
        "> FnCTOD 将每个业务域建模为一个「函数」，槽位对应函数参数。",
        "> LLM 通过调用函数并填写参数来完成对话状态追踪（DST）。",
        "",
    ]
    for domain in cfg["domains"]:
        lines += [
            f"#### 域：`{domain['name']}`",
            "",
            f"**描述**：{domain['description']}  ",
            f"**参数数量**：{len(domain['parameters'])}",
            "",
        ]
        req_params = [p for p in domain["parameters"] if p["required"]]
        opt_params = [p for p in domain["parameters"] if not p["required"]]
        if req_params:
            lines.append("**必填参数：**")
            lines.append("")
            for p in req_params:
                enum_str = (
                    f" ← 枚举值：{', '.join(f'`{v}`' for v in p['enum_values'])}"
                    if p["enum_values"]
                    else ""
                )
                lines.append(f"- `{p['name']}` — {p['description']}{enum_str}")
            lines.append("")
        if opt_params:
            lines.append("**可选参数（部分展示）：**")
            lines.append("")
            for p in opt_params[:8]:
                lines.append(f"- `{p['name']}` — {p['description']}")
            if len(opt_params) > 8:
                lines.append(f"- _…（另有 {len(opt_params) - 8} 个可选参数）_")
            lines.append("")
        lines += [
            "**函数提示词格式（注入 LLM 系统消息中的函数规格）：**",
            "",
            _md_code(domain["prompt_format"]),
            "",
        ]

    # 3.3 系统提示词（两个版本）
    lines += [
        "### 3.3 系统提示词",
        "",
        "#### Stage 1 系统提示（域选择，仅包含域描述）",
        "",
        _md_code(cfg["system_prompt_domain_selection"]),
        "",
        "#### Stage 2 系统提示（函数调用，包含完整参数规格）",
        "",
        _md_code(cfg["system_prompt_function_calling"]),
        "",
        "---",
        "",
    ]

    # ------------------------------------------------------------------ #
    # 四、FnCTOD 两阶段流水线追踪
    # ------------------------------------------------------------------ #
    lines += [
        "## 四、FnCTOD 两阶段流水线追踪",
        "",
        f"> 本次共处理 **{len(turns)} 轮**用户输入（demo 仅处理最后一轮，展示完整两阶段流程）。",
        "",
    ]

    for turn in turns:
        t_idx = turn["turn_index"]
        lines += [
            f"### 第 {t_idx} 轮",
            "",
            f"**用户输入**：{turn['user_input']}",
            "",
        ]

        for stage in turn["stages"]:
            s_num = stage["stage"]
            s_name = stage["name"]
            s_role = stage.get("role", "")

            lines += [
                f"#### Stage {s_num}：{s_name}",
                "",
                f"**作用**：{s_role}",
                "",
            ]

            # ---------- Stage 1：域选择 ----------
            if s_num == 1:
                lines.append("**📥 输入（发送给 LLM 的 messages）**")
                lines.append("")
                lines.append(_messages_to_md(stage.get("input_messages")))
                lines.append("")
                lines.append("**📤 输出**")
                lines.append("")
                if stage.get("llm_ok"):
                    raw = stage.get("llm_raw_response") or "（空）"
                    lines.append("_LLM 原始响应：_")
                    lines.append("")
                    lines.append(_md_code(raw))
                    lines.append("")
                    lines.append(
                        f"**选出的域**：{', '.join(f'`{d}`' for d in stage.get('selected_domains', []))}"
                    )
                else:
                    lines.append(
                        f"> ⚠️ **LLM 未配置或调用失败**：{stage.get('error', '')}  "
                    )
                    lines.append(
                        f"> 降级使用默认域：{', '.join(f'`{d}`' for d in stage.get('selected_domains', []))}"
                    )

            # ---------- Stage 2：函数调用 ----------
            elif s_num == 2:
                lines.append(
                    f"**目标域**：{', '.join(f'`{d}`' for d in stage.get('domains', []))}"
                )
                lines.append("")
                lines.append("**📥 输入（发送给 LLM 的 messages）**")
                lines.append("")
                lines.append(_messages_to_md(stage.get("input_messages")))
                lines.append("")
                lines.append("**📤 输出**")
                lines.append("")
                if stage.get("llm_ok"):
                    raw = stage.get("llm_raw_response") or "（空）"
                    lines.append("_LLM 原始响应：_")
                    lines.append("")
                    lines.append(_md_code(raw))
                    lines.append("")
                    fc = stage.get("function_call")
                    if fc:
                        lines.append("**解析出的 function_call（DST 结果）：**")
                        lines.append("")
                        lines.append(_md_json(fc))
                    else:
                        lines.append("> ⚠️ 未解析到 function_call，使用全文作为自然语言回复。")
                    lines.append("")
                    lines.append(
                        f"**自然语言回复**：{stage.get('natural_response', '—')}"
                    )
                else:
                    lines.append(
                        f"> ⚠️ **LLM 未配置或调用失败**：{stage.get('error', '')}"
                    )
                    lines.append(
                        f"> （回复占位）：{stage.get('natural_response', '—')}"
                    )

            lines.append("")

        # 本轮汇总
        fc_result = turn.get("function_call")
        lines += [
            f"**✅ 本轮 function_call（DST 结果）**：",
            "",
            _md_json(fc_result) if fc_result else "> _（无 function_call）_",
            "",
            f"**✅ 本轮自然语言回复**：{turn.get('final_response', '—')}",
            "",
            "**📊 本轮累积对话状态（Cumulative State）**：",
            "",
            _md_json(turn.get("final_state", {})),
            "",
        ]

    lines += ["---", ""]

    # ------------------------------------------------------------------ #
    # 五、结果对比与分析
    # ------------------------------------------------------------------ #
    final_state = run.get("final_state", {})
    lines += [
        "## 五、结果对比与分析",
        "",
        "| | 内容 |",
        "|---|---|",
        f"| 👤 **用户输入** | {test['最后用户输入']} |",
        f"| 🤖 **FnCTOD 生成回复** | {run['fnctod_response']} |",
        f"| 📝 **实际坐席回复** | {run['actual_response']} |",
        f"| 🏷️ **人工校验标签** | `{run['human_label']}` |",
        "",
        "### 提取的对话状态（DST 结果）",
        "",
        _md_json(final_state),
        "",
        "### 算法价值说明",
        "",
        "- **Stage 1（域选择）** 的价值：在多业务域场景下，自动聚焦到与当前对话相关的域，",
        "  减少无关参数噪声，提升 Stage 2 的提取精度。",
        "",
        "- **Stage 2（函数调用）** 的价值：将对话状态追踪（DST）建模为函数调用，",
        "  输出**结构化** `<function_call>` 格式，同时在同一次 LLM 调用中生成自然语言回复，",
        "  相比传统 DST 更易于扩展到新域（只需增加函数定义，无需重新训练）。",
        "",
        "- **累积状态（Cumulative State）** 的价值：FnCTOD 在多轮对话中",
        "  持续累积已提取的槽位值，形成完整的会话状态，",
        "  供下游系统（CRM 写入、工单生成等）直接使用。",
        "",
    ]

    if run.get("run_error"):
        lines += [
            "### ⚠️ 运行异常",
            "",
            _md_code(run["run_error"]),
            "",
        ]

    lines += [
        "---",
        "",
        "_本报告由 `examples/fnctod_trace_demo.py` 自动生成。_",
        "",
    ]

    return "\n".join(lines)


# ===========================================================================
# 辅助：控制台格式化打印
# ===========================================================================

def _print_stage_header(stage: int, name: str) -> None:
    """在控制台打印阶段分隔线。"""
    print(f"\n{'─'*60}")
    print(f"  Stage {stage}：{name}")
    print(f"{'─'*60}")


def _print_messages(messages: Optional[List[Dict]]) -> None:
    """简洁打印 messages 列表（仅显示 role 和前 200 字）。"""
    if not messages:
        return
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        preview = content[:200].replace("\n", " ")
        print(f"  [{role}] {preview}{'…' if len(content) > 200 else ''}")


# ===========================================================================
# 核心：构建追踪数据 + 运行 FnCTOD
# ===========================================================================

async def run_trace(
    session: Dict[str, Any],
    llm_client: Any,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    对单条会话数据执行完整的 FnCTOD 追踪流程，返回结构化追踪数据字典。

    流程：
      1. 加载 callcenter 函数 Schema 并初始化 FunctionManager
      2. 采集预定义配置快照（在任何 LLM 调用发生前）
      3. 将对话历史中除最后一条用户发言外的所有轮次注入 tracker.dialogue_history
      4. 以最后一条用户发言调用 process_turn()，触发两阶段追踪
    """
    # 使用 callcenter schema（与安逸花外呼场景匹配）
    schema = get_callcenter_function_schema()
    function_manager = FunctionManager()
    function_manager.add_domain(schema)

    # 在任何 LLM 调用发生前采集预置配置快照
    predefined_config = collect_predefined_config(function_manager, _SCENARIO_CONTEXT)

    if llm_client is None:
        class _NoLLMClient:
            """无 LLM 配置时的占位符。"""
            async def chat_async(self, messages, **_):
                raise RuntimeError("LLM_NOT_CONFIGURED：请配置 .env 文件后重新运行")
        llm_client = _NoLLMClient()

    # 只注册了一个 domain，use_two_stage=False 使父类 process_turn() 跳过
    # _select_domains() 直接调用 _call_function()，因此 Stage 1 不会执行。
    # TracingFnCTODTracker 中仍保留 _select_domains() 的追踪覆写，以备
    # 多域场景下（use_two_stage=True）启用时同样能被完整追踪。
    tracker = TracingFnCTODTracker(
        llm_client=llm_client,
        function_manager=function_manager,
        use_two_stage=False,
        max_history_turns=10,
        verbose=verbose,
    )

    # 注入对话历史（坐席/用户交替轮次）。
    # 循环终止于 len(history) - 2，保留最后两条（倒数第二条坐席发言 +
    # 最后一条用户发言），由循环后的两段代码单独处理，确保正确分开注入。
    history = session.get("对话历史", [])
    i = 0
    while i < len(history) - 2:
        agent_utt = history[i]
        user_utt = history[i + 1]
        if agent_utt.startswith(_AGENT_PREFIX) and user_utt.startswith(_USER_PREFIX):
            turn = DialogueTurn(
                turn_id=len(tracker.dialogue_history) + 1,
                user_utterance=user_utt[len(_USER_PREFIX):],
                system_utterance=agent_utt[len(_AGENT_PREFIX):],
                function_call=None,
                state={},
            )
            tracker.dialogue_history.append(turn)
            i += 2
        else:
            i += 1

    # 将倒数第二条坐席发言也注入（让 LLM 知晓上一轮坐席说了什么）
    if len(history) >= 2 and history[-2].startswith(_AGENT_PREFIX):
        turn = DialogueTurn(
            turn_id=len(tracker.dialogue_history) + 1,
            user_utterance="",
            system_utterance=history[-2][len(_AGENT_PREFIX):],
            function_call=None,
            state={},
        )
        tracker.dialogue_history.append(turn)

    last_user = (
        history[-1][len(_USER_PREFIX):]
        if history and history[-1].startswith(_USER_PREFIX)
        else (history[-1] if history else "")
    )

    injected_history_turns = len(tracker.dialogue_history)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  会话 ID：{session['session_id']}")
        print(f"  最后用户输入：{last_user[:80]}")
        print(f"{'='*60}")

    run_error: Optional[str] = None
    try:
        result = await tracker.process_turn(user_utterance=last_user)
    except Exception as exc:
        result = {
            "response": f"(运行异常: {exc})",
            "state": {},
            "function_call": None,
            "turn_id": 1,
        }
        run_error = traceback.format_exc()

    trace_data: Dict[str, Any] = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "script": "examples/fnctod_trace_demo.py",
            "session_id": session.get("session_id", ""),
            "algorithm": "FnCTOD（域选择 → 函数调用，两阶段 DST）",
            "scenario": "安逸花外呼促活（callcenter domain）",
        },
        "test_data": {
            "session_id": session.get("session_id", ""),
            "用户信息": session.get("用户信息", ""),
            "对话历史": session.get("对话历史", []),
            "坐席回复_实际": session.get("坐席回复", ""),
            "人工校验": session.get("人工校验", ""),
            "注入_tracker_history_turns": injected_history_turns,
            "最后用户输入": last_user,
        },
        "predefined_config": predefined_config,
        "fnctod_run": {
            "turns": tracker.trace["turns"],
            "fnctod_response": result.get("response", ""),
            "actual_response": session.get("坐席回复", ""),
            "human_label": session.get("人工校验", ""),
            "final_state": result.get("state", {}),
        },
    }
    if run_error:
        trace_data["fnctod_run"]["run_error"] = run_error

    return trace_data


# ===========================================================================
# 入口
# ===========================================================================

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="FnCTOD 对话任务全链路追踪脚本（输出 Markdown 报告）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--seed", type=int, default=None,
        help="随机种子（用于可复现抽样，默认不固定）",
    )
    p.add_argument(
        "--index", type=int, default=None,
        help="直接指定使用第 N 条数据（0-based），优先于 --seed 随机抽样",
    )
    p.add_argument(
        "--output", type=str, default=None,
        help=(
            "追踪报告输出路径（Markdown 格式，.md）。"
            "默认为 /tmp/fnctod_trace_<session_id>_<timestamp>.md"
        ),
    )
    p.add_argument(
        "--verbose", action="store_true",
        help="同时将每步追踪信息打印到控制台",
    )
    return p


async def _main(args: argparse.Namespace) -> None:
    if not _DATA_PATH.exists():
        print(f"[ERROR] 数据文件不存在：{_DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    dataset: List[Dict[str, Any]] = json.loads(
        _DATA_PATH.read_text(encoding="utf-8")
    )
    print(f"[INFO] 数据集已加载，共 {len(dataset)} 条记录")

    if args.index is not None:
        if not (0 <= args.index < len(dataset)):
            print(
                f"[ERROR] --index {args.index} 超出范围（0 ~ {len(dataset)-1}）",
                file=sys.stderr,
            )
            sys.exit(1)
        session = dataset[args.index]
        print(f"[INFO] 使用指定索引 {args.index}，会话 ID：{session['session_id']}")
    else:
        seed = args.seed if args.seed is not None else random.randint(0, 9999)
        rng = random.Random(seed)
        session = rng.choice(dataset)
        print(f"[INFO] 随机种子 {seed}（可用 --seed {seed} 复现本次抽样），已抽取会话 ID：{session['session_id']}")

    llm_client: Any = None
    try:
        config = LLMConfig.from_env()
        llm_client = SimpleLLMClient(config)
        print(f"[INFO] LLM 已配置：{config.model} @ {config.base_url}")
    except Exception as exc:
        print(f"[WARN] LLM 未配置（{exc}），LLM 步骤将以「⚠️ LLM 未配置」标注")

    print("[INFO] 开始运行 FnCTOD 追踪…")
    trace_data = await run_trace(session, llm_client, verbose=args.verbose)

    # 渲染 Markdown 报告
    md_content = render_markdown(trace_data)

    # 确定输出文件路径
    if args.output:
        output_path = Path(args.output)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sid = session.get("session_id", "unknown")[:20]
        output_path = Path(f"/tmp/fnctod_trace_{sid}_{ts}.md")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_content, encoding="utf-8")

    run = trace_data["fnctod_run"]
    test = trace_data["test_data"]
    print(f"\n{'='*60}")
    print("  追踪完成")
    print(f"  会话 ID        : {trace_data['metadata']['session_id']}")
    print(f"  用户输入       : {test['最后用户输入'][:60]}")
    print(f"  FnCTOD 生成回复: {run['fnctod_response'][:80]}")
    print(f"  实际坐席回复   : {run['actual_response'][:80]}")
    print(f"  人工校验标签   : {run['human_label']}")
    print(f"{'─'*60}")
    print(f"  📄 Markdown 报告已保存至：{output_path}")
    print(f"{'='*60}\n")


def main() -> None:
    args = _build_arg_parser().parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
