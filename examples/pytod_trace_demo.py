"""
PyTOD 对话任务全链路追踪脚本（单条会话）

展示目标：
    体现 PyTOD 算法在任务型对话（TOD）中的核心价值——
    通过「动作解析 → API 执行 → 回复生成」三步流水线，
    将 CRM 真实数据注入对话，让坐席回复从模糊变精准。

功能：
  1. 从 resources/data/chat_test_100.json 中随机抽取一条安逸花外呼对话作为测试样本。
  2. 记录 PyTOD 运行前的全部预置信息：
       场景上下文、ServiceSchema（意图/槽位）、CRM API 签名、系统提示模板。
  3. 完整追踪 PyTOD 三步流水线的每步输入与输出：
       Step 1 动作解析器（Action Parser）— 识别意图，生成 PyTOD 程序
       Step 2 执行引擎（Execution Engine）— 调用真实 CRM API，获取数据
       Step 3 对话管理器（Dialogue Manager）— 融合数据，生成精准回复
  4. 将所有内容写入一个 Markdown 文件，各模块用标题和代码块清晰区分。
  5. 在文末对比 PyTOD 生成回复 vs 实际坐席回复，直观展示算法价值。

环境要求：
    在项目根目录创建 .env 文件，填写：
        LLM_BASE_URL=https://your-endpoint/v1
        LLM_API_KEY=your_key_here        （或 QWEN3_API_KEY）
        LLM_MODEL=Qwen3-32B              （可选，默认 Qwen3-32B）

    若未配置 LLM 环境，脚本仍会运行：LLM 调用步骤以「⚠️ LLM 未配置」标注，
    其余预置信息（schema、API、模板等）会完整输出。

用法：
    cd /path/to/ContextMind
    python examples/pytod_trace_demo.py
    python examples/pytod_trace_demo.py --seed 42            # 固定随机种子
    python examples/pytod_trace_demo.py --index 5            # 直接指定第 5 条数据（0-based）
    python examples/pytod_trace_demo.py --output /tmp/my_trace.md
    python examples/pytod_trace_demo.py --verbose            # 同时打印追踪日志到控制台
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import random
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 将项目根目录加入 Python 搜索路径，使脚本可在任意目录直接执行
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.infra.llm_client import LLMConfig, SimpleLLMClient
from contextmind.modes.pytod import (
    ExecutionEngine,
    PyTODPromptBuilder,
    PyTODTracker,
)
from contextmind.modes.pytod.prompt_builder import ConversationTurn
from contextmind.scenarios.anyihua.generation import ANYIHUA_SCHEMA, build_generation_engine

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"

# 安逸花外呼场景上下文描述（注入到 Action Parser 和 Dialogue Manager 的系统提示中）
_SCENARIO_CONTEXT = (
    "这是一个外呼小额借款推介场景（安逸花外呼促活）。"
    "坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。"
    "标准流程：① 核实用户身份（姓名/手机尾号）→ ② 告知可用额度和利率 → "
    "③ 解答疑问（还款方式、账单争议等）→ ④ 引导用户在 APP 完成借款操作 → "
    "⑤ 确认无未解决诉求后礼貌告别。"
    "注意：核实身份前不得告知账户详细信息；若用户有未解决诉求则不得直接告别。"
)

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


# ===========================================================================
# 追踪型 PyTOD Tracker（继承 PyTODTracker，拦截每一步 I/O）
# ===========================================================================

class TracingPyTODTracker(PyTODTracker):
    """
    在 PyTODTracker 基础上增加逐步追踪能力的子类。

    每次调用 ``process_turn()`` 时，将以下三步的完整 I/O 写入 ``self.trace``：
      - Step 1：动作解析器（Action Parser）— LLM 输入 messages + LLM 输出程序文本
      - Step 2：执行引擎（Execution Engine）— 程序文本 + 执行结果（变量/Hint/say/错误）
      - Step 3：对话管理器（Dialogue Manager）— LLM 输入 messages + LLM 输出回复文本
    """

    def __init__(self, *args, verbose: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.verbose = verbose
        # 追踪数据根节点
        self.trace: Dict[str, Any] = {"turns": []}

    async def process_turn(
        self,
        user_utterance: str,
        system_utterance: str = "",
    ) -> Dict[str, Any]:
        """覆盖父类 process_turn()，在每步调用前后插入追踪记录。"""
        turn_trace: Dict[str, Any] = {
            "turn_index": self.turn_count + 1,
            "user_input": user_utterance,
            "steps": [],
        }

        # ------------------------------------------------------------------ #
        # Step 1：动作解析器（Action Parser）
        #   输入：对话历史 + 用户输入 + 可用 API 列表
        #   输出：LLM 生成的 PyTOD 程序（声明调用哪些 CRM API）
        # ------------------------------------------------------------------ #
        ap_messages = self.prompt_builder.build_action_parser_messages(
            user_input=user_utterance,
            execution_engine=self.execution_engine,
            history=self.history,
            scenario_context=self.scenario_context,
        )
        ap_step: Dict[str, Any] = {
            "step": 1,
            "name": "动作解析器（Action Parser）",
            "role": "理解用户意图，决定调用哪些 CRM API",
            "input_messages": ap_messages,
        }
        if self.verbose:
            _print_step_header(1, "动作解析器（Action Parser）")
            _print_messages(ap_messages)
        try:
            program_text = await self._call_llm(ap_messages)
            ap_step["output_program"] = program_text.strip()
            ap_step["llm_ok"] = True
        except Exception as exc:
            program_text = "NONE()"
            ap_step["output_program"] = program_text
            ap_step["llm_ok"] = False
            ap_step["error"] = str(exc)
        program_text = program_text.strip()
        turn_trace["steps"].append(ap_step)
        if self.verbose:
            print(f"\n  ▶ 程序输出：\n{program_text}\n")

        # ------------------------------------------------------------------ #
        # Step 2：执行引擎（Execution Engine）
        #   输入：PyTOD 程序文本
        #   输出：真实 CRM 数据（账户额度、利率、借款记录等）
        # ------------------------------------------------------------------ #
        exec_step: Dict[str, Any] = {
            "step": 2,
            "name": "执行引擎（Execution Engine）",
            "role": "调用真实 CRM API，返回客观事实数据",
            "input_program": program_text,
        }
        exec_result = None
        if program_text and program_text != "NONE()":
            try:
                exec_result = self.execution_engine.execute_program(program_text)
                if exec_result.success:
                    self._update_state(exec_result)
                exec_step["output"] = {
                    "success": exec_result.success,
                    "variable_values": exec_result.variable_values,
                    "hint_messages": exec_result.hint_messages,
                    "say_output": exec_result.say_output,
                    "errors": exec_result.errors,
                    "context_text": exec_result.to_context_text(),
                }
            except Exception as exc:
                exec_step["output"] = {"success": False, "error": str(exc)}
        else:
            exec_step["output"] = {
                "success": True,
                "note": "NONE() — 本轮无需调用 API，直接进入对话管理器",
                "variable_values": {},
                "hint_messages": [],
                "say_output": None,
                "errors": [],
                "context_text": "(无执行结果)",
            }
        turn_trace["steps"].append(exec_step)
        if self.verbose:
            _print_step_header(2, "执行引擎（Execution Engine）")
            out = exec_step["output"]
            print(f"  success: {out.get('success')}")
            if out.get("variable_values"):
                print(f"  变量: {list(out['variable_values'].keys())}")
            if out.get("say_output"):
                print(f"  say: {out['say_output'][:80]}")
            if out.get("errors"):
                print(f"  错误: {out['errors']}")

        # ------------------------------------------------------------------ #
        # Step 3：对话管理器（Dialogue Manager）
        #   输入：执行结果（CRM 数据）+ 对话历史 + 用户输入
        #   输出：融合真实数据的自然语言回复
        # ------------------------------------------------------------------ #
        dm_step: Dict[str, Any] = {
            "step": 3,
            "name": "对话管理器（Dialogue Manager）",
            "role": "将 CRM 数据融入回复，生成精准的自然语言坐席话术",
        }
        if exec_result is not None and exec_result.say_output:
            # say() 直接输出，无需再次调用 LLM
            response = exec_result.say_output
            dm_step["input_messages"] = None
            dm_step["output_response"] = response
            dm_step["source"] = "execution_engine_say"
            dm_step["llm_ok"] = True
        elif exec_result is not None:
            dm_messages = self.prompt_builder.build_dialogue_manager_messages(
                user_input=user_utterance,
                execution_result=exec_result,
                history=self.history,
                current_state=self.current_state if self.current_state else None,
                scenario_context=self.scenario_context,
            )
            dm_step["input_messages"] = dm_messages
            dm_step["source"] = "dialogue_manager_llm"
            if self.verbose:
                _print_step_header(3, "对话管理器（Dialogue Manager）")
                _print_messages(dm_messages)
            try:
                response = await self._call_llm(dm_messages)
                dm_step["output_response"] = response
                dm_step["llm_ok"] = True
            except Exception as exc:
                response = "（LLM 未配置，无法生成回复）"
                dm_step["output_response"] = response
                dm_step["llm_ok"] = False
                dm_step["error"] = str(exc)
        else:
            # NONE()：无 API 结果，使用后备模式生成自然语言回复
            dm_messages = self.prompt_builder.build_fallback_messages(
                user_input=user_utterance,
                history=self.history,
                scenario_description=self.scenario_name,
                current_state=self.current_state if self.current_state else None,
            )
            dm_step["input_messages"] = dm_messages
            dm_step["source"] = "fallback_llm"
            if self.verbose:
                _print_step_header(3, "对话管理器（Dialogue Manager）— 后备模式")
                _print_messages(dm_messages)
            try:
                response = await self._call_llm(dm_messages)
                dm_step["output_response"] = response
                dm_step["llm_ok"] = True
            except Exception as exc:
                response = "（LLM 未配置，无法生成回复）"
                dm_step["output_response"] = response
                dm_step["llm_ok"] = False
                dm_step["error"] = str(exc)

        dm_step["final_response"] = response
        turn_trace["steps"].append(dm_step)
        turn_trace["final_response"] = response

        if self.verbose:
            print(f"\n  ▶ 最终回复：{response[:120]}\n")

        # 更新对话历史与状态
        self.history.append(ConversationTurn(role="user", content=user_utterance))
        self.history.append(ConversationTurn(role="assistant", content=response))
        if len(self.history) > self.max_history_turns * 2:
            self.history = self.history[-(self.max_history_turns * 2):]
        self.turn_count += 1
        self.current_state["_last_response"] = response
        self.trace["turns"].append(turn_trace)

        return {
            "response": response,
            "program_text": program_text,
            "state": dict(self.current_state),
            "execution": exec_result,
        }


# ===========================================================================
# 辅助：预定义配置采集
# ===========================================================================

def collect_predefined_config(
    engine: ExecutionEngine,
    builder: PyTODPromptBuilder,
    scenario_context: str,
) -> Dict[str, Any]:
    """
    采集 PyTOD 运行前的全部预定义/预置信息：
      - 场景上下文描述
      - ServiceSchema（意图、槽位、渲染后的 prompt 文本）
      - 执行引擎已注册的 API（函数签名 + docstring）
      - 三个系统提示模板原文（Action Parser / Dialogue Manager / Fallback）
    """
    schema = builder.schema
    if schema is not None:
        schema_info = {
            "service_name": schema.service_name,
            "description": schema.description,
            "intents": [
                {
                    "name": i.name,
                    "description": i.description,
                    "required_slots": i.required_slots,
                    "optional_slots": i.optional_slots,
                }
                for i in schema.intents
            ],
            "slots": [
                {
                    "name": s.name,
                    "description": s.description,
                    "is_categorical": s.is_categorical,
                    "possible_values": s.possible_values,
                    "is_required": s.is_required,
                }
                for s in schema.slots
            ],
            "prompt_text": schema.to_prompt_text(),
        }
    else:
        schema_info = {
            "mode": "开放域模式（schema=None）",
            "description": "无预定义意图/槽位，LLM 自由命名意图并提取任意槽位",
        }

    api_list = []
    for name in sorted(engine.registry.keys()):
        sig_str = engine.get_function_signature(name) or f"{name}(...)"
        api_list.append({
            "name": name,
            "signature": sig_str,
            "docstring": inspect.getdoc(engine.registry[name]) or "(无文档)",
        })

    templates = {
        "action_parser": getattr(builder, "_ACTION_PARSER_TEMPLATE", "(未找到)"),
        "dialogue_manager": getattr(builder, "_DIALOGUE_MANAGER_TEMPLATE", "(未找到)"),
        "fallback": getattr(builder, "_FALLBACK_TEMPLATE", "(未找到)"),
    }

    return {
        "scenario_context": scenario_context,
        "schema": schema_info,
        "registered_apis": api_list,
        "api_prompt_text": engine.to_prompt_text(),
        "prompt_templates": templates,
        "max_history_turns": builder.max_history_turns,
        "response_language": builder.response_language,
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
        # 角色标签
        parts.append(f"**`[{role}]`**")
        # 内容放进代码块（保留换行和缩进）
        parts.append(_md_code(content))
    return "\n\n".join(parts)


def render_markdown(trace: Dict[str, Any]) -> str:
    """
    将全量追踪数据渲染为可读的 Markdown 文档。

    文档结构：
      # PyTOD 对话任务追踪报告
      ## 一、概述
      ## 二、PyTOD 算法简介
      ## 三、对话背景（测试数据）
      ## 四、PyTOD 预置配置（运行前定义）
      ## 五、PyTOD 三步流水线追踪
      ## 六、结果对比与分析
    """
    meta = trace["metadata"]
    test = trace["test_data"]
    cfg = trace["predefined_config"]
    run = trace["pytod_run"]
    turns = run["turns"]

    lines: List[str] = []

    # ------------------------------------------------------------------ #
    # 文档标题
    # ------------------------------------------------------------------ #
    lines += [
        "# PyTOD 对话任务追踪报告",
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
        "本报告记录了 **PyTOD（Program-of-Thought Task-Oriented Dialogue）** 算法",
        "在一条安逸花外呼真实对话上的完整运行过程。",
        "",
        "**PyTOD 的核心价值**：传统对话系统直接用 LLM 凭记忆回答，容易产生幻觉（虚构金额、利率等）。",
        "PyTOD 在 LLM 生成回复之前，先让它生成一段**结构化程序**，",
        "由执行引擎调用真实 CRM API 获取客观数据，再将数据注入回复生成，从而保证数据准确性。",
        "",
        "```",
        "用户输入",
        "  │",
        "  ▼",
        "┌─────────────────────────────────┐",
        "│  Step 1  动作解析器             │  LLM 理解意图 → 生成 PyTOD 程序",
        "│          Action Parser          │",
        "└──────────────┬──────────────────┘",
        "               │ PyTOD 程序（API 调用声明）",
        "  ▼",
        "┌─────────────────────────────────┐",
        "│  Step 2  执行引擎               │  调用真实 CRM API → 返回客观数据",
        "│          Execution Engine       │",
        "└──────────────┬──────────────────┘",
        "               │ CRM 事实数据（额度、利率、借款记录…）",
        "  ▼",
        "┌─────────────────────────────────┐",
        "│  Step 3  对话管理器             │  融合数据 → 生成精准坐席话术",
        "│          Dialogue Manager       │",
        "└──────────────┬──────────────────┘",
        "               │",
        "  ▼",
        "坐席回复（基于真实数据，无幻觉）",
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
        f"**数据来源**：`resources/data/chat_test_100.json`，随机抽取一条会话",
        "",
        "### 2.1 用户信息",
        "",
        _md_code(test["用户信息"]),
        "",
        "### 2.2 完整对话历史",
        "",
        "> 以下为本条会话的原始对话记录，最后一条用户发言将作为 PyTOD 的当前输入。",
        "",
    ]
    for idx, utt in enumerate(test["对话历史"]):
        if utt.startswith(_AGENT_PREFIX):
            speaker = "🤖 **坐席**"
            content = utt.removeprefix(_AGENT_PREFIX)
        elif utt.startswith(_USER_PREFIX):
            speaker = "👤 **用户**"
            content = utt.removeprefix(_USER_PREFIX)
        else:
            speaker = "❓"
            content = utt
        lines.append(f"**第 {idx + 1} 句** · {speaker}：{content}")
        lines.append("")

    lines += [
        "### 2.3 当前待处理的用户发言（PyTOD 输入）",
        "",
        f"> 👤 **用户**：**{test['最后用户输入']}**",
        "",
        f"_（对话历史中共注入 {test['注入_tracker_history_turns']} 条历史发言到 Tracker）_",
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
    # 三、PyTOD 预置配置（运行前定义）
    # ------------------------------------------------------------------ #
    lines += [
        "## 三、PyTOD 预置配置（运行前定义）",
        "",
        "> 以下内容在 PyTOD 启动前已完全定义，不依赖用户输入，是算法的「知识底座」。",
        "",
    ]

    # 3.1 场景上下文
    lines += [
        "### 3.1 场景上下文（注入每一步 LLM 提示的业务背景）",
        "",
        _md_code(cfg["scenario_context"]),
        "",
    ]

    # 3.2 ServiceSchema
    schema = cfg["schema"]
    lines += [
        "### 3.2 ServiceSchema（服务意图与槽位定义）",
        "",
        f"**服务名**：`{schema.get('service_name', '—')}`  ",
        f"**描述**：{schema.get('description', '—')}  ",
        f"**意图数**：{len(schema.get('intents', []))}  ",
        f"**槽位数**：{len(schema.get('slots', []))}",
        "",
        "> ℹ️ **注**：Schema 是服务能力的设计文档，供系统设计者和 Action Parser 作意图参考。",
        "> 在 PyTOD 流程中，Schema 不直接注入 LLM 提示——Action Parser 实际接收的是",
        "> 执行引擎的 CRM API 签名列表（见 3.3 节）。",
        "",
    ]
    if "intents" in schema:
        lines.append("#### 意图列表")
        lines.append("")
        for intent in schema["intents"]:
            req_slots = "、".join(f"`{s}`" for s in intent["required_slots"]) if intent["required_slots"] else "—"
            opt_slots = "、".join(f"`{s}`" for s in intent.get("optional_slots", [])) if intent.get("optional_slots") else "—"
            lines.append(f"**`{intent['name']}`** — {intent['description']}")
            lines.append(f"- 必填槽位：{req_slots}")
            lines.append(f"- 可选槽位：{opt_slots}")
            lines.append("")

    # 3.3 注册 API
    lines += [
        "### 3.3 执行引擎注册的 CRM API",
        "",
        "> 这些 API 是 PyTOD 可调用的「工具箱」，每个函数对应一类真实 CRM 查询操作。",
        "> 以下签名与 Step 1 动作解析器收到的 SYSTEM 消息中的 API 列表**完全一致**。",
        "",
    ]
    for api in cfg["registered_apis"]:
        lines.append(f"**`{api['name']}`**")
        lines.append("")
        lines.append(_md_code(api["signature"]))
        # Render docstring as blockquote, preserving paragraph breaks
        doc_lines = api["docstring"].splitlines()
        for dl in doc_lines:
            lines.append(f"> {dl}" if dl.strip() else ">")
        lines.append("")

    # 3.4 Prompt 模板（渲染后版本，无占位符）
    #   - Action Parser：`{api_functions_text}` 已用 3.3 节中的实际 API 列表填充
    #   - DM / Fallback：运行时动态填充的字段（执行结果、状态等）以说明文字标注
    ap_rendered = cfg["prompt_templates"]["action_parser"].replace(
        "{api_functions_text}", cfg["api_prompt_text"]
    )
    dm_annotated = (
        cfg["prompt_templates"]["dialogue_manager"]
        .replace("{execution_result_text}", "← Step 2 执行结果（见第四章）")
        .replace("{state_text}", "← 当前会话累积状态（键值对）")
        .replace("{response_language}", cfg.get("response_language", "中文"))
    )
    fallback_annotated = (
        cfg["prompt_templates"]["fallback"]
        .replace("{scenario_desc}", f"你的服务场景是：{meta['scenario']}。")
        .replace("{state_text}", "← 当前会话累积状态（键值对）")
        .replace("{response_language}", cfg.get("response_language", "中文"))
    )
    lines += [
        "### 3.4 LLM 系统提示（渲染后）",
        "",
        "> 以下展示三个提示的最终形态。动作解析器提示已填入实际 API 列表，",
        "> 对话管理器和后备提示中的动态字段（执行结果、状态）以注释标记，",
        "> 其实际内容可在第四章各步骤的 📥 输入中查看。",
        "",
        "#### 动作解析器（Action Parser）— 完整系统提示",
        "",
        _md_code(ap_rendered),
        "",
        "#### 对话管理器（Dialogue Manager）— 系统提示（动态字段已注释）",
        "",
        _md_code(dm_annotated),
        "",
        "#### 后备模式（Fallback）— 系统提示（动态字段已注释）",
        "",
        _md_code(fallback_annotated),
        "",
        "---",
        "",
    ]

    # ------------------------------------------------------------------ #
    # 四、PyTOD 三步流水线追踪
    # ------------------------------------------------------------------ #
    lines += [
        "## 四、PyTOD 三步流水线追踪",
        "",
        f"> 本次共处理 **{len(turns)} 轮**用户输入（demo 仅处理最后一轮，展示完整三步流程）。",
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

        for step in turn["steps"]:
            s_num = step["step"]
            s_name = step["name"]
            s_role = step.get("role", "")
            lines += [
                f"#### Step {s_num}：{s_name}",
                "",
                f"**作用**：{s_role}",
                "",
            ]

            # ---------- Step 1：动作解析器 ----------
            if s_num == 1:
                lines.append("**📥 输入（发送给 LLM 的 messages）**")
                lines.append("")
                lines.append(_messages_to_md(step.get("input_messages")))
                lines.append("")
                lines.append("**📤 输出（LLM 生成的 PyTOD 程序）**")
                lines.append("")
                prog = step.get("output_program", "NONE()")
                if step.get("llm_ok"):
                    lines.append(_md_code(prog, "python"))
                else:
                    lines.append(f"> ⚠️ **LLM 未配置或调用失败**：{step.get('error', '')}")
                    lines.append("")
                    lines.append(_md_code(prog, "python"))

            # ---------- Step 2：执行引擎 ----------
            elif s_num == 2:
                lines.append("**📥 输入（待执行的 PyTOD 程序）**")
                lines.append("")
                lines.append(_md_code(step.get("input_program", "NONE()"), "python"))
                lines.append("")
                lines.append("**📤 输出（CRM API 执行结果）**")
                lines.append("")
                out = step.get("output", {})
                if out.get("note"):
                    lines.append(f"> ℹ️ {out['note']}")
                else:
                    lines.append(f"- **执行成功**：`{out.get('success', '—')}`")
                    var_vals = out.get("variable_values", {})
                    if var_vals:
                        lines.append("- **API 返回值**：")
                        lines.append("")
                        lines.append(_md_json(var_vals))
                    if out.get("hint_messages"):
                        lines.append(f"- **Hint 消息**：{out['hint_messages']}")
                    if out.get("say_output"):
                        lines.append(f"- **say() 输出**：{out['say_output']}")
                    if out.get("errors"):
                        lines.append(f"- **错误**：{out['errors']}")
                    if out.get("context_text") and out["context_text"] != "(无执行结果)":
                        lines.append("")
                        lines.append("**执行结果的上下文文本（注入对话管理器）**：")
                        lines.append("")
                        lines.append(_md_code(out["context_text"]))

            # ---------- Step 3：对话管理器 ----------
            elif s_num == 3:
                source = step.get("source", "")
                if source == "execution_engine_say":
                    lines.append(
                        "> ℹ️ 执行引擎 `say()` 直接输出回复，本步跳过 LLM 调用。"
                    )
                else:
                    lines.append("**📥 输入（发送给 LLM 的 messages，含 CRM 数据）**")
                    lines.append("")
                    lines.append(_messages_to_md(step.get("input_messages")))
                lines.append("")
                lines.append("**📤 输出（LLM 生成的自然语言回复）**")
                lines.append("")
                resp = step.get("output_response", "—")
                if step.get("llm_ok"):
                    lines.append(f"> 🤖 **PyTOD 生成回复**：{resp}")
                else:
                    lines.append(f"> ⚠️ **LLM 未配置**：{step.get('error', '')}")
                    lines.append(f"> （示意输出）：{resp}")

            lines.append("")

        lines += [
            f"**✅ 本轮最终回复**：{turn.get('final_response', '—')}",
            "",
        ]

    lines += ["---", ""]

    # ------------------------------------------------------------------ #
    # 五、结果对比与分析
    # ------------------------------------------------------------------ #
    lines += [
        "## 五、结果对比与分析",
        "",
        "| | 内容 |",
        "|---|---|",
        f"| 👤 **用户输入** | {test['最后用户输入']} |",
        f"| 🤖 **PyTOD 生成回复** | {run['pytod_response']} |",
        f"| 📝 **实际坐席回复** | {run['actual_response']} |",
        f"| 🏷️ **人工校验标签** | `{run['human_label']}` |",
        "",
        "### 算法价值说明",
        "",
        "- **Step 1（动作解析器）** 的价值：LLM 不直接回答用户，而是先「读懂意图」，",
        "  输出结构化的 API 调用程序——这使意图识别结果可审计、可调试。",
        "",
        "- **Step 2（执行引擎）** 的价值：用**真实 CRM 数据**替换 LLM 的记忆，",
        "  彻底消除坐席回复中的金额幻觉、利率幻觉等数据错误。",
        "",
        "- **Step 3（对话管理器）** 的价值：LLM 获得了真实数据后，",
        "  可以生成既符合业务逻辑、又语言自然的坐席话术，兼顾准确与流畅。",
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
        "_本报告由 `examples/pytod_trace_demo.py` 自动生成。_",
        "",
    ]

    return "\n".join(lines)


# ===========================================================================
# 辅助：控制台格式化打印
# ===========================================================================

def _print_step_header(step: int, name: str) -> None:
    """在控制台打印步骤分隔线。"""
    print(f"\n{'─'*60}")
    print(f"  Step {step}：{name}")
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
# 核心：构建追踪数据 + 运行 PyTOD
# ===========================================================================

async def run_trace(
    session: Dict[str, Any],
    llm_client: Any,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    对单条会话数据执行完整的 PyTOD 追踪流程，返回结构化追踪数据字典。

    流程：
      1. 用会话数据构建执行引擎（注册安逸花 CRM API）
      2. 构建 PyTODPromptBuilder（使用 ANYIHUA_SCHEMA 约束意图）
      3. 采集预定义配置快照（在任何 LLM 调用发生前）
      4. 将对话历史中除最后一条用户发言外的所有轮次注入 tracker.history
      5. 以最后一条用户发言调用 process_turn()，触发三步追踪
    """
    engine = build_generation_engine(session)
    builder = PyTODPromptBuilder(
        schema=ANYIHUA_SCHEMA,
        max_history_turns=10,
        response_language="中文",
    )

    # 在任何 LLM 调用发生前采集预置配置快照
    predefined_config = collect_predefined_config(engine, builder, _SCENARIO_CONTEXT)

    if llm_client is None:
        class _NoLLMClient:
            """无 LLM 配置时的占位符。"""
            async def chat_async(self, messages, **_):
                raise RuntimeError("LLM_NOT_CONFIGURED：请配置 .env 文件后重新运行")
        llm_client = _NoLLMClient()

    tracker = TracingPyTODTracker(
        llm_client=llm_client,
        execution_engine=engine,
        prompt_builder=builder,
        scenario_name="安逸花外呼",
        max_history_turns=10,
        scenario_context=_SCENARIO_CONTEXT,
        verbose=verbose,
    )

    # 注入历史（除最后一轮用户发言）
    history = session["对话历史"]
    i = 0
    while i < len(history) - 2:
        if history[i].startswith(_AGENT_PREFIX) and history[i + 1].startswith(_USER_PREFIX):
            tracker.history.append(ConversationTurn(
                role="assistant", content=history[i].removeprefix(_AGENT_PREFIX)
            ))
            tracker.history.append(ConversationTurn(
                role="user", content=history[i + 1].removeprefix(_USER_PREFIX)
            ))
            i += 2
        else:
            i += 1

    # 将倒数第二条坐席发言也注入（让 LLM 知晓上一轮坐席说了什么）
    if len(history) >= 2 and history[-2].startswith(_AGENT_PREFIX):
        tracker.history.append(ConversationTurn(
            role="assistant", content=history[-2].removeprefix(_AGENT_PREFIX)
        ))

    last_user = history[-1].removeprefix(_USER_PREFIX) if history else ""

    if verbose:
        print(f"\n{'='*60}")
        print(f"  会话 ID：{session['session_id']}")
        print(f"  最后用户输入：{last_user[:80]}")
        print(f"{'='*60}")

    try:
        result = await tracker.process_turn(user_utterance=last_user)
    except Exception as exc:
        result = {"response": f"(运行异常: {exc})", "program_text": "", "state": {}, "execution": None}
        tracker.trace["error"] = traceback.format_exc()

    trace_data: Dict[str, Any] = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "script": "examples/pytod_trace_demo.py",
            "session_id": session.get("session_id", ""),
            "algorithm": "PyTOD（动作解析器→执行引擎→对话管理器）",
            "scenario": "安逸花外呼促活（Generation 任务）",
        },
        "test_data": {
            "session_id": session.get("session_id", ""),
            "用户信息": session.get("用户信息", ""),
            "对话历史": session.get("对话历史", []),
            "坐席回复_实际": session.get("坐席回复", ""),
            "人工校验": session.get("人工校验", ""),
            "注入_tracker_history_turns": len(tracker.history),
            "最后用户输入": last_user,
        },
        "predefined_config": predefined_config,
        "pytod_run": {
            "turns": tracker.trace["turns"],
            "pytod_response": result.get("response", ""),
            "actual_response": session.get("坐席回复", ""),
            "human_label": session.get("人工校验", ""),
            "final_state": result.get("state", {}),
        },
    }
    if "error" in tracker.trace:
        trace_data["pytod_run"]["run_error"] = tracker.trace["error"]

    return trace_data


# ===========================================================================
# 入口
# ===========================================================================

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="PyTOD 对话任务全链路追踪脚本（输出 Markdown 报告）",
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
            "默认为 /tmp/pytod_trace_<session_id>_<timestamp>.md"
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

    dataset: List[Dict[str, Any]] = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    print(f"[INFO] 数据集已加载，共 {len(dataset)} 条记录")

    if args.index is not None:
        if not (0 <= args.index < len(dataset)):
            print(f"[ERROR] --index {args.index} 超出范围（0 ~ {len(dataset)-1}）", file=sys.stderr)
            sys.exit(1)
        session = dataset[args.index]
        print(f"[INFO] 使用指定索引 {args.index}，会话 ID：{session['session_id']}")
    else:
        seed = args.seed if args.seed is not None else random.randint(0, 9999)
        rng = random.Random(seed)
        session = rng.choice(dataset)
        print(f"[INFO] 随机种子 {seed}，已抽取会话 ID：{session['session_id']}")

    llm_client: Any = None
    try:
        config = LLMConfig.from_env()
        llm_client = SimpleLLMClient(config)
        print(f"[INFO] LLM 已配置：{config.model} @ {config.base_url}")
    except Exception as exc:
        print(f"[WARN] LLM 未配置（{exc}），LLM 步骤将以「⚠️ LLM 未配置」标注")

    print("[INFO] 开始运行 PyTOD 追踪…")
    trace_data = await run_trace(session, llm_client, verbose=args.verbose)

    # 渲染 Markdown 报告
    md_content = render_markdown(trace_data)

    # 确定输出文件路径
    if args.output:
        output_path = Path(args.output)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sid = session.get("session_id", "unknown")[:20]
        output_path = Path(f"/tmp/pytod_trace_{sid}_{ts}.md")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_content, encoding="utf-8")

    run = trace_data["pytod_run"]
    test = trace_data["test_data"]
    print(f"\n{'='*60}")
    print(f"  追踪完成")
    print(f"  会话 ID       : {trace_data['metadata']['session_id']}")
    print(f"  用户输入      : {test['最后用户输入'][:60]}")
    print(f"  PyTOD 生成回复: {run['pytod_response'][:80]}")
    print(f"  实际坐席回复  : {run['actual_response'][:80]}")
    print(f"  人工校验标签  : {run['human_label']}")
    print(f"{'─'*60}")
    print(f"  📄 Markdown 报告已保存至：{output_path}")
    print(f"{'='*60}\n")


def main() -> None:
    args = _build_arg_parser().parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
