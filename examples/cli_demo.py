#!/usr/bin/env python3
"""
ContextMind 命令行交互 Demo

支持三个场景：chat（闲聊）、callcenter（客服）、insurance（保险）
支持四种模式：dst / evolve / fnctod / pytod

使用方式:
    python examples/cli_demo.py --scenario chat --mode evolve
    python examples/cli_demo.py --scenario callcenter --mode dst
    python examples/cli_demo.py --scenario insurance --mode fnctod
    python examples/cli_demo.py --scenario insurance --mode pytod
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
import argparse
import logging
from typing import Optional

import json
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.pytod import AdkPyTODTracker
from contextmind.modes.pytod.schemas import load_schema_from_dict
from contextmind.scenarios import get_chat_scenario, get_callcenter_scenario, get_insurance_scenario
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent


def _load_external_schemas(schema_path: str):
    """从 schema.json 文件加载 PyTOD ServiceSchema 和 FnCTOD DomainSpec。"""
    from contextmind.modes.fnctod.function_manager import FunctionManager
    with open(schema_path, encoding="utf-8") as f:
        data = json.load(f)
    svc = load_schema_from_dict(data)
    fm = FunctionManager()
    fm.add_domain_from_slots(
        domain_name=svc.service_name,
        domain_description=svc.description,
        slots={slot.name: slot.description for slot in svc.slots},
        categorical_slots={
            slot.name: slot.possible_values
            for slot in svc.slots if slot.possible_values
        } or None,
        required_slots=[slot.name for slot in svc.slots if slot.is_required] or None,
    )
    domains = fm.get_all_domains()
    if not domains:
        raise ValueError(f"Schema produced no valid domains")
    domain_spec = domains[0]
    return svc, domain_spec


class InteractiveDemo:
    """统一的命令行交互 Demo。"""

    def __init__(
        self,
        scenario: str = "chat",
        mode: str = "evolve",
        max_history_turns: int = 10,
        schema_path: Optional[str] = None,
    ):
        self.scenario = scenario
        self.mode = mode
        self.max_history_turns = max_history_turns
        self.config = self._load_scenario_config()
        self.llm_client: Optional[AdkLLMClient] = None
        self.tracker = None
        self.app = None
        self.last_system_reply: str = ""
        # 外部 Schema（PyTOD ServiceSchema 和 FnCTOD DomainSpec）
        self._pytod_schema = None
        self._fnctod_domain_spec = None
        self._schema_path: Optional[str] = schema_path  # 保存路径，用于加载 companion 预生成函数
        if schema_path:
            try:
                self._pytod_schema, self._fnctod_domain_spec = _load_external_schemas(schema_path)
                print(f"✓ 已加载外部 Schema: {schema_path}")
            except Exception as exc:
                print(f"❌ 加载 Schema 失败: {exc}")
                print(f"   请确认 schema 文件格式正确，或运行: python examples/build_schema_data.py")

        if mode == "dst":
            self._setup_dst()
        elif mode == "fnctod":
            self._setup_fnctod()
        elif mode == "pytod":
            self._setup_pytod()
        else:
            self._setup_evolve()

    def _load_scenario_config(self):
        scenarios = {
            "chat": get_chat_scenario,
            "callcenter": get_callcenter_scenario,
            "insurance": get_insurance_scenario,
        }
        if self.scenario not in scenarios:
            raise ValueError(f"未知场景: {self.scenario}，可选: {list(scenarios.keys())}")
        return scenarios[self.scenario]()

    def _get_llm_client(self) -> AdkLLMClient:
        if self.llm_client is None:
            try:
                self.llm_client = AdkLLMClient()
            except ValueError as e:
                print(f"\n❌ 错误: {e}")
                print("\n请在 .env 文件中设置：")
                print("  QWEN3_API_KEY=sk-...")
                print("  QWEN3_BASE_URL=http://localhost:8000/v1")
                print("  QWEN3_MODEL=Qwen3-32B")
                sys.exit(1)
        return self.llm_client

    def _setup_dst(self):
        logger.info(f"初始化 DST 模式 - {self.config.name}")
        self.tracker = DialogueStateTracker.from_scenario(
            llm_client=self._get_llm_client(),
            scenario_config=self.config,
            max_history_turns=self.max_history_turns,
        )
        self.last_system_reply = self.config.welcome_message or "你好！"

    def _setup_fnctod(self):
        logger.info(f"初始化 FnCTOD 模式 - {self.config.name}")
        kwargs = {}
        if self._fnctod_domain_spec is not None:
            kwargs["domain_spec"] = self._fnctod_domain_spec
        self.tracker = FnCTODTracker.from_scenario(self._get_llm_client(), self.config, **kwargs)

    def _setup_pytod(self):
        logger.info(f"初始化 PyTOD 模式 - {self.config.name}")
        kwargs = {}
        if self._pytod_schema is not None:
            kwargs["schema"] = self._pytod_schema
        # 传入 schema_path 让 from_scenario() 自动加载 companion *_pytod_apis.py 预生成函数
        if self._schema_path is not None:
            kwargs["schema_path"] = self._schema_path
        self.tracker = AdkPyTODTracker.from_scenario(self._get_llm_client(), self.config, **kwargs)

    def _setup_evolve(self):
        logger.info(f"初始化 Evolve 模式 - {self.config.name}")
        from contextmind.modes.evolve import create_app_for_scenario
        self.app = create_app_for_scenario(
            scenario_name=self.scenario,
            llm_client=self._get_llm_client(),
            scenario_config=self.config,
            app_name_prefix="cli_demo",
        )

    def print_welcome(self):
        mode_labels = {
            "dst": "DST（对话状态追踪）",
            "evolve": "Evolve（演化式记忆）",
            "fnctod": "FnCTOD（ADK 原生函数调用）",
            "pytod": "PyTOD（ADK 原生工具调用）",
        }
        print("\n" + "=" * 60)
        print("📱 ContextMind 命令行 Demo")
        print("=" * 60)
        print(f"场景: {self.config.name}   模式: {mode_labels.get(self.mode, self.mode)}")
        print("=" * 60)
        print("命令: /quit 退出  /reset 重置  /state 查看状态")
        print("=" * 60 + "\n")

    async def _chat(self, user_message: str) -> str:
        if self.mode == "dst":
            state = await self.tracker.process_turn(
                system_utterance=self.last_system_reply,
                user_utterance=user_message,
            )
            messages = [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": f"用户: {user_message}\n状态: {state}\n请回复用户。"},
            ]
            reply = await self._get_llm_client().chat_async(messages=messages)
            self.last_system_reply = reply
            return reply
        elif self.mode in ("fnctod", "pytod"):
            result = await self.tracker.process_turn(user_utterance=user_message)
            return result.get("response", str(result))
        else:
            return await self.app.process_turn(user_input=user_message, debug=False)

    def show_state(self):
        if self.mode not in ("dst", "fnctod", "pytod") or self.tracker is None:
            print("⚠️  状态查看仅在 dst/fnctod/pytod 模式下可用")
            return
        state = self.tracker.get_current_state()
        print("\n" + "=" * 40)
        print("📊 当前对话状态:")
        for k, v in state.items():
            print(f"  {k}: {v}")
        print("=" * 40 + "\n")

    def reset(self):
        if self.mode == "dst" and self.tracker:
            self.tracker.reset()
            self.last_system_reply = self.config.welcome_message or "你好！"
        elif self.mode in ("fnctod", "pytod") and self.tracker:
            self.tracker.reset()
        else:
            self._setup_evolve()
        print("✅ 对话已重置\n")

    async def run(self):
        self.print_welcome()
        welcome = self.config.welcome_message or "你好！"
        print(f"助手: {welcome}\n" + "-" * 60 + "\n")
        turn = 0
        while True:
            try:
                user_input = input("你: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("/quit", "/exit"):
                    print("\n👋 再见！")
                    break
                elif user_input.lower() == "/reset":
                    self.reset()
                    turn = 0
                    continue
                elif user_input.lower() == "/state":
                    self.show_state()
                    continue
                turn += 1
                reply = await self._chat(user_input)
                print(f"\n助手: {reply}\n" + "-" * 60 + "\n")
            except KeyboardInterrupt:
                print("\n\n👋 检测到中断，退出")
                break
            except Exception as e:
                logger.error(f"处理错误: {e}", exc_info=True)
                print(f"\n❌ 错误: {e}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="ContextMind 命令行 Demo")
    parser.add_argument("--scenario", choices=["chat", "callcenter", "insurance"],
                        default="chat", help="场景")
    parser.add_argument("--mode", choices=["dst", "evolve", "fnctod", "pytod"],
                        default="evolve", help="对话模式")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        default="INFO", help="日志级别")
    parser.add_argument("--max-history-turns", type=int, default=10,
                        metavar="N", help="最大历史轮数")
    parser.add_argument(
        "--schema", type=str, default=None, metavar="PATH",
        help="schema.json 路径（SGD 格式，schema/ 目录下），用于 PyTOD / FnCTOD 模式",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    level = LogLevel.DEBUG if args.log_level == "DEBUG" else LogLevel.INFO
    setup_logging(level=level, save_to_file=True, log_dir="output/logs")
    demo = InteractiveDemo(
        scenario=args.scenario,
        mode=args.mode,
        max_history_turns=args.max_history_turns,
        schema_path=args.schema,
    )
    await demo.run()


if __name__ == "__main__":
    asyncio.run(main())
