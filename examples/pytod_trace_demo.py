"""
PyTOD 单条会话全链路追踪脚本

功能：
  1. 从 resources/data/chat_test_100.json 中随机抽取一条对话数据作为测试样本。
  2. 使用安逸花外呼生成任务（Generation）的 PyTOD 算法处理该样本：
       动作解析器（Action Parser）→ 执行引擎（Execution Engine）→ 对话管理器（Dialogue Manager）
  3. 记录 PyTOD 运行过程中每一步的输入与输出（LLM messages、程序文本、API 执行结果等）。
  4. 同时记录 PyTOD 运行前的预置/预定义信息：
       ServiceSchema（意图/槽位定义）、已注册 API 签名、系统提示模板、场景上下文。
  5. 将以上所有信息写入一个 JSON 追踪文件，路径由 --output 参数指定（默认放在 /tmp/）。

环境要求：
    在项目根目录创建 .env 文件，填写：
        LLM_BASE_URL=https://your-endpoint/v1
        LLM_API_KEY=your_key_here        （或 QWEN3_API_KEY）
        LLM_MODEL=Qwen3-32B              （可选，默认 Qwen3-32B）

    若未配置 LLM 环境，脚本仍会运行：LLM 调用步骤将记录为 "LLM_NOT_CONFIGURED"，
    其余预置信息（schema、API、模板等）会完整保存。

用法：
    cd /path/to/ContextMind
    python examples/pytod_trace_demo.py
    python examples/pytod_trace_demo.py --seed 42            # 固定随机种子
    python examples/pytod_trace_demo.py --index 5            # 直接指定第 5 条数据（0-based）
    python examples/pytod_trace_demo.py --output /tmp/my_trace.json
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

    所有步骤记录挂载到 ``self.trace["pytod_run"]["turns"]`` 列表中，
    每轮追踪为一个字典，包含 turn_index、user_input、steps 三个字段。
    """

    def __init__(self, *args, verbose: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.verbose = verbose
        # 追踪数据根节点，由外部代码在构建后挂载到总 trace_data 结构中
        self.trace: Dict[str, Any] = {
            "turns": []
        }
        # 当前轮追踪缓存（每次 process_turn 开始时初始化）
        self._current_turn_trace: Dict[str, Any] = {}
        # 存储最近一次 _call_llm 调用的上下文（用于区分是 AP 调用还是 DM 调用）
        self._last_ap_messages: Optional[List[Dict]] = None
        self._last_dm_messages: Optional[List[Dict]] = None

    async def process_turn(
        self,
        user_utterance: str,
        system_utterance: str = "",
    ) -> Dict[str, Any]:
        """
        覆盖父类 process_turn()，在每步调用前后插入追踪记录。

        追踪信息写入 self._current_turn_trace，处理结束后追加到 self.trace["turns"]。
        """
        turn_trace: Dict[str, Any] = {
            "turn_index": self.turn_count + 1,  # 当前轮次编号（从 1 开始）
            "user_input": user_utterance,
            "steps": [],
        }

        # ------------------------------------------------------------------ #
        # Step 1：动作解析器（Action Parser）
        #   输入：build_action_parser_messages() 生成的 messages 列表
        #   输出：LLM 返回的 PyTOD 程序文本
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
            "input": {
                "description": "发送给 LLM 的 messages 列表，要求 LLM 生成 PyTOD 程序",
                "messages": ap_messages,
            },
        }

        if self.verbose:
            _print_step_header(1, "动作解析器（Action Parser）")
            _print_messages(ap_messages)

        try:
            program_text = await self._call_llm(ap_messages)
            ap_step["output"] = {
                "description": "LLM 生成的 PyTOD 程序文本",
                "program_text": program_text.strip(),
            }
        except Exception as exc:
            program_text = "NONE()"
            ap_step["output"] = {
                "error": str(exc),
                "program_text": program_text,
            }

        program_text = program_text.strip()
        turn_trace["steps"].append(ap_step)

        if self.verbose:
            print(f"\n  ▶ 程序文本输出：\n{program_text}\n")

        # ------------------------------------------------------------------ #
        # Step 2：执行引擎（Execution Engine）
        #   输入：动作解析器生成的程序文本
        #   输出：API 执行结果（变量值、Hint 消息、say 输出、错误列表）
        # ------------------------------------------------------------------ #
        exec_step: Dict[str, Any] = {
            "step": 2,
            "name": "执行引擎（Execution Engine）",
            "input": {
                "description": "待执行的 PyTOD 程序文本（来自动作解析器）",
                "program_text": program_text,
            },
        }

        exec_result = None
        if program_text and program_text != "NONE()":
            try:
                exec_result = self.execution_engine.execute_program(program_text)
                if exec_result.success:
                    self._update_state(exec_result)

                exec_step["output"] = {
                    "description": "执行引擎返回的结果（API 返回值、Hint 消息、say 输出）",
                    "success": exec_result.success,
                    "variable_values": exec_result.variable_values,
                    "hint_messages": exec_result.hint_messages,
                    "say_output": exec_result.say_output,
                    "errors": exec_result.errors,
                    "context_text": exec_result.to_context_text(),
                }
            except Exception as exc:
                exec_step["output"] = {
                    "success": False,
                    "error": str(exc),
                }
        else:
            # NONE() 表示无 API 调用
            exec_step["output"] = {
                "description": "程序为 NONE()，无 API 调用，跳过执行",
                "success": True,
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
        #   输入：build_dialogue_manager_messages() 或 build_fallback_messages() 的 messages
        #   输出：LLM 生成的自然语言回复
        # ------------------------------------------------------------------ #
        dm_step: Dict[str, Any] = {
            "step": 3,
            "name": "对话管理器（Dialogue Manager）",
        }

        if exec_result is not None and exec_result.say_output:
            # say() 已给出完整回复，直接使用，无需再次调用 LLM
            response = exec_result.say_output
            dm_step["input"] = {
                "description": "执行引擎 say() 直接输出，跳过 LLM 调用",
                "messages": None,
            }
            dm_step["output"] = {
                "description": "来自执行引擎 say() 的回复（未调用 LLM）",
                "response": response,
                "source": "say_output",
            }
        elif exec_result is not None:
            # 有 API 执行结果，交由对话管理器 LLM 生成回复
            dm_messages = self.prompt_builder.build_dialogue_manager_messages(
                user_input=user_utterance,
                execution_result=exec_result,
                history=self.history,
                current_state=self.current_state if self.current_state else None,
                scenario_context=self.scenario_context,
            )
            dm_step["input"] = {
                "description": "发送给 LLM 的 messages 列表（含执行结果），要求生成自然语言回复",
                "messages": dm_messages,
            }
            if self.verbose:
                _print_step_header(3, "对话管理器（Dialogue Manager）")
                _print_messages(dm_messages)
            try:
                response = await self._call_llm(dm_messages)
                dm_step["output"] = {
                    "description": "LLM 生成的自然语言回复",
                    "response": response,
                    "source": "dialogue_manager_llm",
                }
            except Exception as exc:
                response = "抱歉，处理您的请求时出现了问题，请稍后重试。"
                dm_step["output"] = {
                    "error": str(exc),
                    "response": response,
                    "source": "fallback_on_error",
                }
        else:
            # NONE() 情况，使用后备提示生成纯自然语言回复
            dm_messages = self.prompt_builder.build_fallback_messages(
                user_input=user_utterance,
                history=self.history,
                scenario_description=self.scenario_name,
                current_state=self.current_state if self.current_state else None,
            )
            dm_step["input"] = {
                "description": "NONE() 后备 messages（无 API 执行结果，纯自然语言生成）",
                "messages": dm_messages,
            }
            if self.verbose:
                _print_step_header(3, "对话管理器（Dialogue Manager）- 后备模式")
                _print_messages(dm_messages)
            try:
                response = await self._call_llm(dm_messages)
                dm_step["output"] = {
                    "description": "LLM 生成的后备自然语言回复",
                    "response": response,
                    "source": "fallback_llm",
                }
            except Exception as exc:
                response = "抱歉，处理您的请求时出现了问题，请稍后重试。"
                dm_step["output"] = {
                    "error": str(exc),
                    "response": response,
                    "source": "fallback_on_error",
                }

        turn_trace["steps"].append(dm_step)
        turn_trace["final_response"] = response

        if self.verbose:
            print(f"\n  ▶ 最终回复：{response[:120]}\n")

        # 更新父类对话历史（与父类保持一致，不重复调用 super()）
        self.history.append(ConversationTurn(role="user", content=user_utterance))
        self.history.append(ConversationTurn(role="assistant", content=response))
        if len(self.history) > self.max_history_turns * 2:
            self.history = self.history[-(self.max_history_turns * 2):]
        self.turn_count += 1
        self.current_state["_last_response"] = response

        # 追加本轮追踪记录
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
    采集 PyTOD 运行前的所有预定义/预置信息：
      - ServiceSchema（意图、槽位、prompt 文本）
      - 执行引擎已注册的 API（函数签名 + docstring）
      - Prompt 模板原文（Action Parser、Dialogue Manager、Fallback）
      - 场景上下文描述

    返回可直接序列化为 JSON 的字典。
    """
    # ---- Schema 信息 ----
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

    # ---- 已注册 API 信息 ----
    api_list = []
    for name, func in sorted(engine.registry.items()):
        try:
            sig = inspect.signature(func)
            sig_str = f"{name}{sig}"
        except (ValueError, TypeError):
            sig_str = f"{name}(...)"
        docstring = inspect.getdoc(func) or "(无文档)"
        api_list.append({
            "name": name,
            "signature": sig_str,
            "docstring": docstring,
        })

    # ---- Prompt 模板原文 ----
    # 从 PyTODPromptBuilder 类属性中提取三个系统提示模板
    templates = {
        "action_parser_system_template": getattr(
            builder, "_ACTION_PARSER_TEMPLATE", "(未找到)"
        ),
        "dialogue_manager_system_template": getattr(
            builder, "_DIALOGUE_MANAGER_TEMPLATE", "(未找到)"
        ),
        "fallback_system_template": getattr(
            builder, "_FALLBACK_TEMPLATE", "(未找到)"
        ),
    }

    return {
        "schema": schema_info,
        "registered_apis": api_list,
        "api_prompt_text": engine.to_prompt_text(),
        "prompt_templates": templates,
        "scenario_context": scenario_context,
        "max_history_turns": builder.max_history_turns,
        "response_language": builder.response_language,
    }


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
    对单条会话数据执行完整的 PyTOD 追踪流程。

    流程：
      1. 用会话数据构建执行引擎（注册安逸花 CRM API）
      2. 构建 PyTODPromptBuilder（使用 ANYIHUA_SCHEMA 约束意图）
      3. 采集预定义配置快照
      4. 将对话历史中除最后一条用户发言外的所有轮次注入追踪 tracker 的 history
      5. 以最后一条用户发言调用 process_turn()，触发三步追踪

    参数:
        session:    chat_test_100.json 中的单条记录
        llm_client: LLM 客户端（为 None 时 LLM 步骤标记为未配置）
        verbose:    是否在控制台打印追踪日志

    返回:
        完整追踪数据字典，可直接 json.dumps 序列化
    """
    # ---- 构建执行引擎和 prompt builder ----
    engine = build_generation_engine(session)
    builder = PyTODPromptBuilder(
        schema=ANYIHUA_SCHEMA,
        max_history_turns=10,
        response_language="中文",
    )

    # ---- 采集预定义配置快照（在 LLM 调用发生前）----
    predefined_config = collect_predefined_config(engine, builder, _SCENARIO_CONTEXT)

    # ---- 构建追踪 Tracker ----
    if llm_client is None:
        # 创建空白占位符 client，LLM 调用会抛异常并被记录为 "未配置"
        class _NoLLMClient:
            """无 LLM 配置时的占位符，调用即抛出明确错误。"""
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

    # ---- 将对话历史（除最后一轮用户发言）注入 tracker.history ----
    # 目的：让 LLM 在 [HISTORY] 中看到"已发生的"历史，
    #       在 [CURRENT] 中看到"正在发生的"当前用户输入。
    history = session["对话历史"]
    i = 0
    while i < len(history) - 2:
        if history[i].startswith(_AGENT_PREFIX) and history[i + 1].startswith(_USER_PREFIX):
            agent_utt = history[i].removeprefix(_AGENT_PREFIX)
            user_utt = history[i + 1].removeprefix(_USER_PREFIX)
            tracker.history.append(ConversationTurn(role="assistant", content=agent_utt))
            tracker.history.append(ConversationTurn(role="user", content=user_utt))
            i += 2
        else:
            i += 1

    # 将倒数第二条坐席发言注入，让 LLM 知晓坐席上一轮说了什么
    if len(history) >= 2 and history[-2].startswith(_AGENT_PREFIX):
        tracker.history.append(
            ConversationTurn(
                role="assistant",
                content=history[-2].removeprefix(_AGENT_PREFIX),
            )
        )

    # 取最后一条用户发言作为当前轮输入
    last_user = history[-1].removeprefix(_USER_PREFIX) if history else ""

    if verbose:
        print(f"\n{'='*60}")
        print(f"  会话 ID：{session['session_id']}")
        print(f"  最后用户输入：{last_user[:80]}")
        print(f"{'='*60}")

    # ---- 执行追踪 ----
    try:
        result = await tracker.process_turn(user_utterance=last_user)
    except Exception as exc:
        result = {
            "response": f"(运行异常: {exc})",
            "program_text": "",
            "state": {},
            "execution": None,
        }
        tracker.trace["error"] = traceback.format_exc()

    # ---- 组装完整追踪数据 ----
    trace_data: Dict[str, Any] = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "script": "examples/pytod_trace_demo.py",
            "session_id": session.get("session_id", ""),
            "algorithm": "PyTOD（动作解析器→执行引擎→对话管理器）",
            "scenario": "安逸花外呼促活（Generation 任务）",
            "schema": "ANYIHUA_SCHEMA（contextmind/scenarios/anyihua/generation/schema.py）",
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
        description="PyTOD 单条会话全链路追踪脚本",
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
            "追踪文件输出路径（JSON 格式）。"
            "默认为 /tmp/pytod_trace_<session_id>_<timestamp>.json"
        ),
    )
    p.add_argument(
        "--verbose", action="store_true",
        help="同时将每步追踪信息打印到控制台",
    )
    return p


async def _main(args: argparse.Namespace) -> None:
    # ---- 加载数据集 ----
    if not _DATA_PATH.exists():
        print(f"[ERROR] 数据文件不存在：{_DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    dataset: List[Dict[str, Any]] = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    print(f"[INFO] 数据集已加载，共 {len(dataset)} 条记录")

    # ---- 选择测试样本 ----
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
        print(f"[INFO] 随机种子 {seed}，已抽取会话 ID：{session['session_id']}")

    # ---- 构建 LLM 客户端（可选）----
    llm_client: Any = None
    try:
        config = LLMConfig.from_env()
        llm_client = SimpleLLMClient(config)
        print(f"[INFO] LLM 已配置：{config.model} @ {config.base_url}")
    except Exception as exc:
        print(f"[WARN] LLM 客户端初始化失败（{exc}），LLM 调用步骤将标记为 LLM_NOT_CONFIGURED")

    # ---- 执行追踪 ----
    print(f"[INFO] 开始运行 PyTOD 追踪…")
    trace_data = await run_trace(session, llm_client, verbose=args.verbose)

    # ---- 确定输出文件路径 ----
    if args.output:
        output_path = Path(args.output)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sid = session.get("session_id", "unknown")[:20]
        output_path = Path(f"/tmp/pytod_trace_{sid}_{ts}.json")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- 写入 JSON 文件 ----
    output_path.write_text(
        json.dumps(trace_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ---- 控制台摘要 ----
    turns = trace_data["pytod_run"]["turns"]
    print(f"\n{'='*60}")
    print(f"  追踪完成")
    print(f"  会话 ID       : {trace_data['metadata']['session_id']}")
    print(f"  最后用户输入  : {trace_data['test_data']['最后用户输入'][:60]}")
    print(f"  PyTOD 生成回复: {trace_data['pytod_run']['pytod_response'][:80]}")
    print(f"  实际坐席回复  : {trace_data['pytod_run']['actual_response'][:80]}")
    print(f"  人工校验标签  : {trace_data['pytod_run']['human_label']}")
    print(f"  追踪轮次数    : {len(turns)}")
    print(f"{'─'*60}")
    print(f"  追踪文件已保存至：{output_path}")
    print(f"{'='*60}\n")

    # ---- 打印预定义 API 列表摘要 ----
    print("预置 API（执行引擎已注册）：")
    for api in trace_data["predefined_config"]["registered_apis"]:
        print(f"  · {api['signature']}")

    print("\n预置 Schema 意图：")
    schema = trace_data["predefined_config"]["schema"]
    if "intents" in schema:
        for intent in schema["intents"]:
            req = ", ".join(intent["required_slots"]) or "—"
            print(f"  · {intent['name']}  必填槽位: {req}")
    else:
        print(f"  · {schema.get('mode', '(无)')}")


def main() -> None:
    args = _build_arg_parser().parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
