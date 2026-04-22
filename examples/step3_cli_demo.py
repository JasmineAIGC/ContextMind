#!/usr/bin/env python3
"""
ContextMind 命令行交互 Demo

支持三个场景：chat（闲聊）、callcenter（客服）、insurance（保险）
支持五种模式：dst / evolve / fnctod / pytod / genie

使用方式:
    python examples/step3_cli_demo.py --scenario chat --mode evolve
    python examples/step3_cli_demo.py --scenario callcenter --mode dst
    python examples/step3_cli_demo.py --scenario insurance --mode fnctod --fnctod-schema schema/anyihua_fnctod_domain.json
    python examples/step3_cli_demo.py --scenario insurance --mode pytod --pytod-apis schema/anyihua_pytod_apis.py
    python examples/step3_cli_demo.py --scenario insurance --mode pytod --pytod-apis output/step2/schema_pytod_apis.py --schema output/step1/schema.json
    python examples/step3_cli_demo.py --scenario insurance --mode genie --genie-worksheet schema/anyihua_genie_worksheet.json

Schema 说明:
    FnCTOD 使用预生成的 companion JSON 文件（--fnctod-schema schema/xxx_fnctod_domain.json）
           也接受原始 schema（schema/xxx_schema.json），自动寻找 companion 文件
    PyTOD  使用预生成的 Python API 文件（--pytod-apis schema/xxx_pytod_apis.py）
           可选：通过 --schema 显式指定 schema.json（当自动推导路径不正确时使用）
    Genie  使用预生成的 Worksheet JSON 文件（--genie-worksheet schema/xxx_genie_worksheet.json）
           也接受原始 schema（--schema schema/xxx_schema.json），自动在同目录寻找 Worksheet 文件
           Worksheet 由 step2b_build_schema_data.py 自动从 schema.json 生成，无需人工编写
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


def _load_fnctod_schema(json_path: str):
    """从 schema 文件加载 FnCTOD DomainSpec（及 ServiceSchema）。

    支持两种输入：

    1. ``*_fnctod_domain.json`` — 预生成的 companion 文件（推荐，由
       ``python examples/step2b_build_schema_data.py`` 生成）。
    2. ``*_schema.json`` — 原始 schema 文件；若同目录存在对应的
       ``*_fnctod_domain.json`` 则自动优先使用它，否则在线构建。

    Returns:
        ``(ServiceSchema, DomainSpec)`` 二元组；加载失败时抛出异常。
    """
    from contextmind.modes.fnctod.schemas import load_domain_spec_from_file

    sp = Path(json_path)

    # 若传入 *_schema.json，自动检查同目录是否存在预生成的 companion 文件
    load_path = sp
    if sp.stem.endswith("_schema"):
        base = sp.stem[: -len("_schema")]
        companion = sp.parent / f"{base}_fnctod_domain.json"
        if companion.exists():
            load_path = companion

    domain_spec = load_domain_spec_from_file(load_path)

    # 同时加载 ServiceSchema（供需要服务元信息的调用方使用）
    svc = None
    raw_schema = Path(json_path)
    if raw_schema.stem.endswith("_schema") and raw_schema.exists():
        with open(raw_schema, encoding="utf-8") as f:
            svc = load_schema_from_dict(json.load(f))

    return svc, domain_spec


def _load_pytod_service_schema(apis_py_path: str, schema_json_path: Optional[str] = None):
    """从 *_pytod_apis.py 路径推导 schema.json 并加载 ServiceSchema。

    若 schema_json_path 已显式指定，则直接加载该文件。
    否则按以下优先级自动推导（均与 apis_py_path 同目录）：

    1. ``{base}_schema.json``（标准命名，如 ``anyihua_pytod_apis.py`` → ``anyihua_schema.json``）
    2. ``{base}.json``（兜底，如 ``schema_pytod_apis.py`` → ``schema.json``）

    若均不存在则返回 None，PyTOD 将退化为无结构 prompt 模式。
    """
    def _load_json(path: Path):
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return load_schema_from_dict(json.load(f))

    if schema_json_path:
        return _load_json(Path(schema_json_path))

    p = Path(apis_py_path)
    stem = p.stem  # e.g. "anyihua_pytod_apis"
    base = stem[: -len("_pytod_apis")] if stem.endswith("_pytod_apis") else stem
    # 优先尝试标准命名
    schema = _load_json(p.parent / f"{base}_schema.json")
    if schema is not None:
        return schema
    # 兜底：base 本身不含 "_schema" 后缀时（如 schema_pytod_apis.py → base="schema"），
    # {base}_schema.json 会变成 schema_schema.json（不存在），回退到 {base}.json
    return _load_json(p.parent / f"{base}.json")


def _load_genie_schema(worksheet_path: Optional[str], schema_json_path: Optional[str] = None):
    """加载 Genie GenieSchema（从 Worksheet JSON 或 schema.json）。

    优先级：
    1. 若提供 worksheet_path（``*_genie_worksheet.json``），直接加载。
    2. 若提供 schema_json_path（``*_schema.json``），自动在同目录寻找 ``*_genie_worksheet.json``；
       找不到时从 schema.json 在线转换（无需文件落盘）。
    3. 两者均未提供时返回 None。

    Returns:
        ``GenieSchema`` 实例，或 None（无法加载时）。
    """
    from contextmind.schema_builder.genie_worksheets import WorksheetLoader
    from contextmind.schema_builder.genie_worksheets.schema_types import (
        GenieIntent, GenieSchema, GenieSlot,
    )
    from contextmind.schema_builder.genie_worksheets.models import PolicyField

    # 优先使用 worksheet 文件
    if worksheet_path:
        ws_p = Path(worksheet_path)
        if ws_p.suffix.lower() in (".json", ".jsonl"):
            return WorksheetLoader.from_json(ws_p)
        elif ws_p.suffix.lower() == ".csv":
            return WorksheetLoader.from_csv(ws_p)
        raise ValueError(f"--genie-worksheet 只支持 .json / .csv，得到: {ws_p.suffix}")

    # 从 schema.json 推导
    if schema_json_path:
        sp = Path(schema_json_path)
        # 自动检查同目录的 *_genie_worksheet.json
        stem = sp.stem
        base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
        companion = sp.parent / f"{base}_genie_worksheet.json"
        if companion.exists():
            return WorksheetLoader.from_json(companion)
        # 在线转换
        with open(sp, encoding="utf-8") as f:
            from contextmind.modes.pytod.schemas import load_schema_from_dict
            svc_schema = load_schema_from_dict(json.load(f))
        slot_map = {s.name: s for s in svc_schema.slots}
        genie_slots = [
            GenieSlot(
                name=s.name, description=s.description,
                is_categorical=s.is_categorical,
                possible_values=list(s.possible_values),
                is_required=s.is_required,
            )
            for s in svc_schema.slots
        ]
        genie_intents = []
        for intent in svc_schema.intents:
            pf = []
            for sn in list(intent.required_slots) + list(intent.optional_slots):
                sd = slot_map.get(sn)
                pf.append(PolicyField(
                    name=sn,
                    description=sd.description if sd else "",
                    required=(sn in intent.required_slots),
                    field_type="enum" if (sd and sd.is_categorical) else "str",
                    possible_values=list(sd.possible_values) if sd else [],
                ))
            genie_intents.append(GenieIntent(
                name=intent.name, description=intent.description,
                required_slots=list(intent.required_slots),
                optional_slots=list(intent.optional_slots),
                result_slots=list(intent.result_slots),
                is_transactional=intent.is_transactional,
                policy_fields=pf,
            ))
        return GenieSchema(
            service_name=svc_schema.service_name,
            description=svc_schema.description,
            slots=genie_slots,
            intents=genie_intents,
        )

    return None


class InteractiveDemo:
    """统一的命令行交互 Demo。"""

    def __init__(
        self,
        scenario: str = "chat",
        mode: str = "evolve",
        max_history_turns: int = 10,
        fnctod_schema_path: Optional[str] = None,
        pytod_apis_path: Optional[str] = None,
        schema_json_path: Optional[str] = None,
        genie_worksheet_path: Optional[str] = None,
    ):
        self.scenario = scenario
        self.mode = mode
        self.max_history_turns = max_history_turns
        self.config = self._load_scenario_config()
        self.llm_client: Optional[AdkLLMClient] = None
        self.tracker = None
        self.app = None
        self.last_system_reply: str = ""
        # FnCTOD：从 schema.json 加载 DomainSpec
        self._fnctod_domain_spec = None
        if fnctod_schema_path:
            try:
                _, self._fnctod_domain_spec = _load_fnctod_schema(fnctod_schema_path)
                print(f"✓ 已加载 FnCTOD Schema: {fnctod_schema_path}")
            except Exception as exc:
                print(f"❌ 加载 FnCTOD Schema 失败: {exc}")
        # PyTOD：从 *_pytod_apis.py 加载 ServiceSchema（推导对应 JSON；显式 --schema 优先）
        self._pytod_schema = None
        self._pytod_apis_path: Optional[str] = pytod_apis_path
        if pytod_apis_path:
            try:
                self._pytod_schema = _load_pytod_service_schema(pytod_apis_path, schema_json_path)
                if self._pytod_schema is not None:
                    print(f"✓ 已加载 PyTOD ServiceSchema（从 {pytod_apis_path} 推导）")
                print(f"✓ 已加载 PyTOD APIs: {pytod_apis_path}")
            except Exception as exc:
                print(f"❌ 加载 PyTOD APIs 失败: {exc}")
                print(f"   请确认文件存在且格式正确，或运行: python examples/step2b_build_schema_data.py")
        # Genie：从 Worksheet JSON 或 schema.json 加载 GenieSchema
        self._genie_schema = None
        if mode == "genie":
            try:
                self._genie_schema = _load_genie_schema(genie_worksheet_path, schema_json_path)
                if self._genie_schema is not None:
                    print(f"✓ 已加载 Genie Schema: {self._genie_schema.service_name}")
                else:
                    print(
                        "⚠️  未提供 Genie Worksheet，请通过 --genie-worksheet 或 --schema 指定。\n"
                        "   可通过以下命令预生成 Worksheet：\n"
                        "   python examples/step2b_build_schema_data.py --genie-only --schema <schema.json>"
                    )
            except Exception as exc:
                print(f"❌ 加载 Genie Schema 失败: {exc}")

        if mode == "dst":
            self._setup_dst()
        elif mode == "fnctod":
            self._setup_fnctod()
        elif mode == "pytod":
            self._setup_pytod()
        elif mode == "genie":
            self._setup_genie()
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
        # 直接传入 *_pytod_apis.py 路径，load_pytod_api_module 可直接加载
        if self._pytod_apis_path is not None:
            kwargs["schema_path"] = self._pytod_apis_path
        self.tracker = AdkPyTODTracker.from_scenario(self._get_llm_client(), self.config, **kwargs)

    def _setup_genie(self):
        logger.info(f"初始化 Genie 模式 - {self.config.name}")
        if self._genie_schema is None:
            raise ValueError(
                "Genie 模式需要 --genie-worksheet 或 --schema 参数。\n"
                "可通过以下命令预生成 Worksheet：\n"
                "  python examples/step2b_build_schema_data.py --genie-only --schema <schema.json>"
            )
        from contextmind.modes.genie.tracker import GenieTracker
        self.tracker = GenieTracker(
            llm_client=self._get_llm_client(),
            schema=self._genie_schema,
            scene_description=getattr(self.config, "scene_description", "") or self.config.name,
            max_history_turns=self.max_history_turns,
        )

    def _setup_evolve(self):
        logger.info(f"初始化 Evolve 模式 - {self.config.name}")
        from contextmind.modes.evolve import create_app_for_scenario
        self.app = create_app_for_scenario(
            scenario_name=self.scenario,
            llm_client=self._get_llm_client(),
            scenario_config=self.config,
            app_name_prefix="step3_cli_demo",
        )

    def print_welcome(self):
        mode_labels = {
            "dst": "DST（对话状态追踪）",
            "evolve": "Evolve（演化式记忆）",
            "fnctod": "FnCTOD（ADK 原生函数调用）",
            "pytod": "PyTOD（ADK 原生工具调用）",
            "genie": "Genie（Worksheets 声明式策略）",
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
        elif self.mode in ("fnctod", "pytod", "genie"):
            result = await self.tracker.process_turn(user_utterance=user_message)
            return result.get("response", str(result))
        else:
            return await self.app.process_turn(user_input=user_message, debug=False)

    def show_state(self):
        if self.mode not in ("dst", "fnctod", "pytod", "genie") or self.tracker is None:
            print("⚠️  状态查看仅在 dst/fnctod/pytod/genie 模式下可用")
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
        elif self.mode in ("fnctod", "pytod", "genie") and self.tracker:
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
    parser = argparse.ArgumentParser(
        description="ContextMind 命令行 Demo",
        epilog="""
使用示例:
  python examples/step3_cli_demo.py --scenario chat --mode evolve
  python examples/step3_cli_demo.py --scenario callcenter --mode dst
  python examples/step3_cli_demo.py --scenario insurance --mode fnctod --fnctod-schema schema/anyihua_schema.json
  python examples/step3_cli_demo.py --scenario insurance --mode pytod --pytod-apis schema/anyihua_pytod_apis.py
  python examples/step3_cli_demo.py --scenario insurance --mode pytod --pytod-apis output/step2/schema_pytod_apis.py --schema output/step1/schema.json
  python examples/step3_cli_demo.py --scenario insurance --mode genie --genie-worksheet schema/anyihua_genie_worksheet.json
  python examples/step3_cli_demo.py --scenario insurance --mode genie --schema schema/anyihua_schema.json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--scenario", choices=["chat", "callcenter", "insurance"],
                        default="chat", help="场景")
    parser.add_argument("--mode", choices=["dst", "evolve", "fnctod", "pytod", "genie"],
                        default="evolve", help="对话模式")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        default="INFO", help="日志级别")
    parser.add_argument("--max-history-turns", type=int, default=10,
                        metavar="N", help="最大历史轮数")
    parser.add_argument(
        "--fnctod-schema", type=str, default=None, metavar="PATH",
        help="FnCTOD 模式的 schema 文件路径：推荐使用预生成的 *_fnctod_domain.json "
             "（可通过 step2b_build_schema_data.py 生成）；也接受 *_schema.json（自动寻找 companion 文件）",
    )
    parser.add_argument(
        "--pytod-apis", type=str, default=None, metavar="PATH",
        help="PyTOD 模式的 *_pytod_apis.py 路径（预生成 API 函数文件，schema/ 目录下）",
    )
    parser.add_argument(
        "--schema", type=str, default=None, dest="schema", metavar="PATH",
        help=(
            "schema.json 文件路径（PyTOD / Genie 模式均可使用）。"
            "PyTOD：与 --pytod-apis 配合显式指定 ServiceSchema，若不指定则从文件名自动推导。"
            "Genie：若未提供 --genie-worksheet，则在同目录自动寻找 *_genie_worksheet.json，"
            "找不到时直接从 schema.json 在线转换。"
        ),
    )
    parser.add_argument(
        "--genie-worksheet", type=str, default=None, metavar="PATH",
        help=(
            "Genie 模式的 Worksheet JSON 文件路径（*_genie_worksheet.json）。"
            "由 step2b_build_schema_data.py 自动从 schema.json 生成，无需人工编写。"
            "也接受 *_worksheet.csv 格式。"
            "若不指定，则通过 --schema 指定的 schema.json 自动推导或在线转换。"
        ),
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    level = LogLevel.DEBUG if args.log_level == "DEBUG" else LogLevel.INFO
    setup_logging(level=level, save_to_file=True, log_dir="log", log_name="cli_demo")
    demo = InteractiveDemo(
        scenario=args.scenario,
        mode=args.mode,
        max_history_turns=args.max_history_turns,
        fnctod_schema_path=args.fnctod_schema,
        pytod_apis_path=args.pytod_apis,
        schema_json_path=args.schema,
        genie_worksheet_path=args.genie_worksheet,
    )
    await demo.run()


if __name__ == "__main__":
    asyncio.run(main())
