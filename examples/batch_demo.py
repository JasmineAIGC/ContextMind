#!/usr/bin/env python3
"""
ContextMind 批量对话测试Demo

使用Gradio界面进行批量对话测试

与 web_demo.py 的区别：
- 对话窗口直接输入预写好的对话内容（而非实时交互）
- 支持单轮对话和多轮对话
- 支持一次性输入和分批多次输入

使用方式:
    python examples/batch_demo.py
    python examples/batch_demo.py --port 7861
    python examples/batch_demo.py --log-level DEBUG
    python examples/batch_demo.py --fnctod-schema schema/anyihua_fnctod_domain.json
    python examples/batch_demo.py --pytod-apis schema/anyihua_pytod_apis.py
    python examples/batch_demo.py --pytod-apis output/step2/schema_pytod_apis.py --schema output/step1/schema.json
    python examples/batch_demo.py --genie-worksheet schema/anyihua_genie_worksheet.json

Schema 说明:
    FnCTOD 使用预生成的 companion JSON 文件（--fnctod-schema schema/xxx_fnctod_domain.json）
           也接受原始 schema（schema/xxx_schema.json），自动寻找 companion 文件
    PyTOD  使用预生成的 Python API 文件（--pytod-apis schema/xxx_pytod_apis.py）
           可选：通过 --schema 显式指定 schema.json（当自动推导路径不正确时使用）
    Genie  使用预生成的 Worksheet JSON 文件（--genie-worksheet schema/xxx_genie_worksheet.json）
           也接受原始 schema（--schema schema/xxx_schema.json），自动在同目录寻找 Worksheet 文件
           Worksheet 由 build_schema_data.py 自动从 schema.json 生成，无需人工编写
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，使得可以直接运行而无需安装
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import argparse
import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from contextmind.infra.llm_client import AdkLLMClient
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.pytod import AdkPyTODTracker
from contextmind.modes.pytod.schemas import load_schema_from_dict
from contextmind.scenarios import get_insurance_scenario
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent

# 模块级 schema 路径，由 main() 在启动时设置（Gradio 回调无法直接接收 CLI 参数）
_BATCH_FNCTOD_SCHEMA_PATH: Optional[str] = None
_BATCH_PYTOD_APIS_PATH: Optional[str] = None
_BATCH_PYTOD_SCHEMA_PATH: Optional[str] = None
_BATCH_GENIE_WORKSHEET_PATH: Optional[str] = None


def _load_fnctod_schema(json_path: str):
    """从 schema 文件加载 FnCTOD DomainSpec（及 ServiceSchema）。

    支持两种输入：

    1. ``*_fnctod_domain.json`` — 预生成的 companion 文件（推荐，由
       ``python examples/build_schema_data.py`` 生成）。
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
            logger.info(f"[FnCTOD] 优先使用预生成 companion 文件: {companion.name}")
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
            from contextmind.modes.pytod.schemas import load_schema_from_dict as _lsd
            svc_schema = _lsd(json.load(f))
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


class BatchDialogueTest:
    """批量对话测试类"""
    
    def __init__(
        self,
        max_history_turns: int = 10,
        fnctod_schema_path: Optional[str] = None,
        pytod_apis_path: Optional[str] = None,
        schema_json_path: Optional[str] = None,
        genie_worksheet_path: Optional[str] = None,
    ):
        """
        初始化测试类

        Args:
            max_history_turns:    DST 模式的最大历史轮数
            fnctod_schema_path:   FnCTOD 模式的 schema.json 路径
            pytod_apis_path:      PyTOD 模式的 *_pytod_apis.py 路径（预生成 API 函数文件）
            schema_json_path:     PyTOD / Genie 模式的 schema.json 路径（显式指定；优先于自动推导）
            genie_worksheet_path: Genie 模式的 *_genie_worksheet.json 路径（预生成 Worksheet 文件）
        """
        self.max_history_turns = max_history_turns
        self.llm_client = None
        self.tracker = None  # DST mode
        self.fnctod_tracker = None  # FnCTOD mode
        self.genie_tracker = None  # Genie mode
        self.config = None
        self.app = None
        self.current_mode = None
        self.results_history = []
        # FnCTOD：从 schema.json 加载 DomainSpec
        self._fnctod_domain_spec = None
        if fnctod_schema_path:
            try:
                _, self._fnctod_domain_spec = _load_fnctod_schema(fnctod_schema_path)
                logger.info(f"已加载 FnCTOD Schema: {fnctod_schema_path}")
            except Exception as exc:
                logger.warning(f"加载 FnCTOD Schema 失败: {exc}")
        # PyTOD：从 *_pytod_apis.py 加载 ServiceSchema（推导对应 JSON；显式 --schema 优先）
        self._pytod_schema = None
        self._pytod_apis_path: Optional[str] = pytod_apis_path
        if pytod_apis_path:
            try:
                self._pytod_schema = _load_pytod_service_schema(pytod_apis_path, schema_json_path)
                if self._pytod_schema is not None:
                    logger.info(f"已加载 PyTOD ServiceSchema（从 {pytod_apis_path} 推导）")
                logger.info(f"已加载 PyTOD APIs: {pytod_apis_path}")
            except Exception as exc:
                logger.warning(f"加载 PyTOD APIs 失败: {exc}")
        # Genie：从 Worksheet JSON 或 schema.json 加载 GenieSchema
        self._genie_schema = None
        self._genie_worksheet_path: Optional[str] = genie_worksheet_path
        self._schema_json_path: Optional[str] = schema_json_path
        if genie_worksheet_path or schema_json_path:
            try:
                self._genie_schema = _load_genie_schema(genie_worksheet_path, schema_json_path)
                if self._genie_schema is not None:
                    logger.info(f"已加载 Genie Schema: {self._genie_schema.service_name}")
            except Exception as exc:
                logger.warning(f"加载 Genie Schema 失败: {exc}")
        logger.info("BatchDialogueTest 实例创建完成")
    
    def initialize(self, mode: str = "dst"):
        """
        初始化模式
        
        Args:
            mode: "dst", "evolve", "fnctod", "pytod", 或 "genie"
        """
        self.current_mode = mode
        
        # 加载保险场景配置
        self.config = get_insurance_scenario()
        
        # 创建 LLM 客户端
        try:
            if self.llm_client is None:
                self.llm_client = AdkLLMClient()
                logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM客户端初始化失败: {e}")
            raise
        
        if mode == "dst":
            self._setup_dst_tracker()
        elif mode == "fnctod":
            self._setup_fnctod_tracker()
        elif mode == "pytod":
            self._setup_pytod_tracker()
        elif mode == "genie":
            self._setup_genie_tracker()
        else:
            self._setup_evolve_app()
        
        logger.info(f"✅ {mode.upper()} 模式初始化完成")
    
    def _setup_dst_tracker(self):
        """
        初始化 DST 模式
        
        使用工厂方法简化初始化
        """
        # 使用工厂方法创建DST追踪器
        self.tracker = DialogueStateTracker.from_scenario(
            llm_client=self.llm_client,
            scenario_config=self.config,
            max_history_turns=self.max_history_turns,
            enable_history_summary=True,
            use_llm_summary=False
        )
        
        logger.info("DST模式初始化完成")
    
    def _setup_fnctod_tracker(self):
        """
        初始化 FnCTOD 模式
        
        使用工厂方法简化初始化
        """
        # 使用工厂方法创建FnCTOD追踪器
        kwargs = {"use_two_stage": True, "max_history_turns": self.max_history_turns}
        if self._fnctod_domain_spec is not None:
            kwargs["domain_spec"] = self._fnctod_domain_spec
        self.fnctod_tracker = FnCTODTracker.from_scenario(
            llm_client=self.llm_client,
            scenario_config=self.config,
            **kwargs,
        )
        
        logger.info("FnCTOD 模式初始化完成")

    def _setup_pytod_tracker(self):
        """
        初始化 PyTOD 模式（程序执行型任务对话）

        使用工厂方法简化初始化，自动注册保险场景 API。
        """
        kwargs = {"max_history_turns": self.max_history_turns}
        if self._pytod_schema is not None:
            kwargs["schema"] = self._pytod_schema
        # 直接传入 *_pytod_apis.py 路径，load_pytod_api_module 可直接加载
        if self._pytod_apis_path is not None:
            kwargs["schema_path"] = self._pytod_apis_path
        self.pytod_tracker = AdkPyTODTracker.from_scenario(
            llm_client=self.llm_client,
            scenario_config=self.config,
            **kwargs,
        )

        logger.info("PyTOD 模式初始化完成")

    def _setup_genie_tracker(self):
        """
        初始化 Genie Worksheets 模式

        从预生成的 Worksheet JSON 文件或 schema.json 加载 GenieSchema，
        创建 GenieTracker 实例。
        """
        if self._genie_schema is None:
            raise ValueError(
                "Genie 模式需要 --genie-worksheet 或 --schema 参数。\n"
                "可通过以下命令预生成 Worksheet：\n"
                "  python examples/build_schema_data.py --genie-only --schema <schema.json>"
            )
        from contextmind.modes.genie.tracker import GenieTracker
        self.genie_tracker = GenieTracker(
            llm_client=self.llm_client,
            schema=self._genie_schema,
            scene_description=getattr(self.config, "scene_description", "") or self.config.name,
            max_history_turns=self.max_history_turns,
        )
        logger.info("Genie 模式初始化完成")

    def _setup_evolve_app(self):
        """
        初始化 Evolve 模式
        
        使用工厂方法简化初始化
        """
        # 使用工厂方法创建应用
        from contextmind.modes.evolve import create_app_for_scenario
        self.app = create_app_for_scenario(
            scenario_name=self.config.name,
            llm_client=self.llm_client,
            scenario_config=self.config,
            app_name_prefix="gradio_test"
        )
        
        logger.info("Evolve 模式初始化完成")
    
    def reset(self):
        """重置对话状态"""
        if self.current_mode == "dst" and self.tracker:
            self.tracker.current_state = {}
            self.tracker.dialogue_history = []
        elif self.current_mode == "fnctod" and self.fnctod_tracker:
            self.fnctod_tracker.reset()
        elif self.current_mode == "pytod" and hasattr(self, "pytod_tracker"):
            self.pytod_tracker.reset()
        elif self.current_mode == "genie" and self.genie_tracker:
            self.genie_tracker.reset()
        elif self.current_mode == "evolve" and self.app:
            # 重新初始化
            self._setup_evolve_app()

        self.results_history = []
        logger.info("对话状态已重置")
    
    def _extract_content_after_colon(self, line: str, prefix: str) -> str:
        """
        提取冒号后的内容，支持中英文冒号
        
        Args:
            line: 原始行
            prefix: 前缀（如 "销售员" 或 "客户"）
            
        Returns:
            冒号后的内容
        """
        # 匹配 "前缀：" 或 "前缀:" 后面的内容
        pattern = f'^{prefix}[：:](.*)$'
        match = re.match(pattern, line)
        if match:
            return match.group(1).strip()
        return ""
    
    def parse_dialogue_input(self, text: str) -> List[Dict]:
        """
        解析对话输入
        
        支持格式:
        1. 单轮对话:
           销售员：你好
           客户：你好
        
        2. 多轮对话:
           销售员：你好，我是保险顾问
           客户：你好
           销售员：请问您需要什么帮助？
           客户：我想了解癌症保险
        
        Args:
            text: 对话文本
            
        Returns:
            轮次列表，每轮包含 system_utterance 和 user_utterance
        """
        lines = text.strip().split('\n')
        turns = []
        current_system = []
        current_user = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 跳过注释和背景音
            if line.startswith('（') and line.endswith('）'):
                continue
            if line.startswith('(') and line.endswith(')'):
                continue
            if line.startswith('#'):
                continue
            
            # 解析销售员发言
            if line.startswith('销售员：') or line.startswith('销售员:'):
                # 如果之前有完整的对话轮次，保存
                if current_user and current_system:
                    turns.append({
                        'system_utterance': ' '.join(current_system),
                        'user_utterance': ' '.join(current_user)
                    })
                    current_system = []
                    current_user = []
                
                # 使用辅助函数提取销售员内容
                content = self._extract_content_after_colon(line, '销售员')
                if content:
                    current_system = [content]
            
            # 解析客户发言
            elif line.startswith('客户：') or line.startswith('客户:'):
                # 使用辅助函数提取客户内容
                content = self._extract_content_after_colon(line, '客户')
                if content:
                    if current_user:
                        # 同一轮中多条客户发言，合并
                        current_user.append(content)
                    else:
                        current_user = [content]
            
            # 其他内容（可能是续行）
            else:
                # 不处理无法识别的行
                pass
        
        # 保存最后一轮
        if current_user and current_system:
            turns.append({
                'system_utterance': ' '.join(current_system),
                'user_utterance': ' '.join(current_user)
            })
        
        return turns
    
    async def process_dialogue_dst(self, turns: List[Dict]) -> Tuple[str, Dict]:
        """
        使用 DST 模式处理对话
        
        复用 gradio_demo.py 中的处理逻辑
        
        Args:
            turns: 对话轮次列表
            
        Returns:
            (处理结果文本, 最终状态)
        """
        results = []
        result_text = ""  # 初始化结果文本
        
        for i, turn in enumerate(turns):
            system_utterance = turn.get('system_utterance', '')
            user_utterance = turn.get('user_utterance', '')
            
            # 处理这一轮对话 - 复用 gradio_demo.py 的流程
            state = await self.tracker.process_turn(
                system_utterance=system_utterance,
                user_utterance=user_utterance
            )
            
            # 记录结果
            turn_result = {
                'turn_id': i + 1,
                'system_utterance': system_utterance[:50] + '...' if len(system_utterance) > 50 else system_utterance,
                'user_utterance': user_utterance,
                'extracted_state': state
            }
            results.append(turn_result)
            
            # 累积格式化输出
            result_text += f"\n{'='*50}\n"
            result_text += f"轮次 {i + 1}\n"
            result_text += f"{'='*50}\n"
            result_text += f"销售员: {system_utterance[:80]}{'...' if len(system_utterance) > 80 else ''}\n"
            result_text += f"客户: {user_utterance}\n"
            result_text += f"\n提取状态:\n"
            for key, value in state.items():
                if value:  # 只显示非空值
                    result_text += f"  {key}: {value}\n"
        
        # 获取最终状态 - 使用最后一轮的状态
        if results:
            final_state = results[-1].copy()
        else:
            final_state = {}
        
        # 生成汇总
        summary = f"\n{'='*50}\n"
        summary += f"📊 测试总结 (DST 模式)\n"
        summary += f"{'='*50}\n"
        summary += f"处理轮数: {len(turns)}\n"
        summary += f"\n累积状态:\n"
        for key, value in final_state.items():
            if value:
                summary += f"  {key}: {value}\n"
        
        # 保存到历史
        self.results_history.append({
            'mode': 'dst',
            'turns': len(turns),
            'final_state': final_state
        })
        
        return result_text + summary, final_state
    
    async def process_dialogue_fnctod(self, turns: List[Dict]) -> Tuple[str, Dict]:
        """
        使用 FnCTOD 模式处理对话
        
        Args:
            turns: 对话轮次列表
            
        Returns:
            (处理结果文本, 最终状态)
        """
        # ✅ 为每个对话创建新的tracker实例，确保测试结果独立
        from contextmind.modes.fnctod import FnCTODTracker
        tracker = FnCTODTracker.from_scenario(
            self.llm_client,
            self.config,
            use_two_stage=True,
            max_history_turns=10
        )
        logger.info(f"✅ 为新对话创建FnCTOD tracker")
        
        results = []
        result_text = ""
        
        for i, turn in enumerate(turns):
            user_utterance = turn.get('user_utterance', '')
            
            # 处理这一轮对话
            result = await tracker.process_turn(
                user_utterance=user_utterance,
                system_utterance=""
            )
            
            # 记录结果
            turn_result = {
                'turn_id': i + 1,
                'user_utterance': user_utterance,
                'function_call': result.get('function_call'),
                'response': result.get('response'),
                'state': result.get('state')
            }
            results.append(turn_result)
            
            # 累积格式化输出
            result_text += f"\n{'='*50}\n"
            result_text += f"轮次 {i + 1}\n"
            result_text += f"{'='*50}\n"
            result_text += f"客户: {user_utterance}\n"
            if result.get('function_call'):
                fc = result['function_call']
                result_text += f"\n函数调用:\n"
                result_text += f"  函数: {fc.get('function', 'N/A')}\n"
                if fc.get('arguments'):
                    result_text += f"  参数:\n"
                    for k, v in fc['arguments'].items():
                        result_text += f"    {k}: {v}\n"
            result_text += f"\n助手: {result.get('response', '')}\n"
        
        # 获取最终状态 - 使用最后一轮的状态，而不是全局累积状态
        # 因为全局累积状态可能包含不同domain的槽位
        if results:
            final_state = results[-1].get('state', {})
        else:
            final_state = {}
        
        # 生成汇总
        summary = f"\n{'='*50}\n"
        summary += f"📊 测试总结 (FnCTOD 模式)\n"
        summary += f"{'='*50}\n"
        summary += f"处理轮数: {len(turns)}\n"
        summary += f"\n最终状态 (最后一轮):\n"
        for key, value in final_state.items():
            if value:
                summary += f"  {key}: {value}\n"
        
        # 保存到历史
        self.results_history.append({
            'mode': 'fnctod',
            'turns': len(turns),
            'final_state': final_state
        })
        
        return result_text + summary, final_state

    async def process_dialogue_pytod(self, turns: List[Dict]) -> Tuple[str, Dict]:
        """
        使用 PyTOD 模式处理对话。

        为每个对话创建独立的 PyTODTracker 实例，确保测试结果独立。

        Args:
            turns: 对话轮次列表

        Returns:
            (处理结果文本, 最终状态)
        """
        # 为每个对话创建新的 tracker 实例，确保测试结果独立
        _pytod_kwargs: Dict[str, Any] = {"max_history_turns": self.max_history_turns}
        if self._pytod_schema is not None:
            _pytod_kwargs["schema"] = self._pytod_schema
        # 直接传入 *_pytod_apis.py 路径，load_pytod_api_module 可直接加载
        if self._pytod_apis_path is not None:
            _pytod_kwargs["schema_path"] = self._pytod_apis_path
        tracker = AdkPyTODTracker.from_scenario(
            llm_client=self.llm_client,
            scenario_config=self.config,
            **_pytod_kwargs,
        )
        logger.info("✅ 为新对话创建 PyTOD tracker")

        results = []
        result_text = ""

        for i, turn in enumerate(turns):
            user_utterance = turn.get("user_utterance", "")

            result = await tracker.process_turn(user_utterance=user_utterance)

            turn_result = {
                "turn_id": i + 1,
                "user_utterance": user_utterance,
                "program_text": result.get("program_text", ""),
                "response": result.get("response", ""),
                "state": result.get("state", {}),
            }
            results.append(turn_result)

            result_text += f"\n{'='*50}\n"
            result_text += f"轮次 {i + 1}\n"
            result_text += f"{'='*50}\n"
            result_text += f"客户: {user_utterance}\n"
            if result.get("program_text") and result["program_text"] != "NONE()":
                result_text += f"\n[Action Parser] 程序:\n"
                for line in result["program_text"].splitlines():
                    result_text += f"  {line}\n"
            exec_res = result.get("execution")
            if exec_res and exec_res.success:
                for var, val in exec_res.variable_values.items():
                    if not isinstance(val, str):
                        result_text += f"\n[Execution Engine] {var} = {val}\n"
                if exec_res.hint_messages:
                    result_text += f"[Hint] {'; '.join(exec_res.hint_messages)}\n"
            result_text += f"\n助手: {result.get('response', '')}\n"

        final_state = results[-1].get("state", {}) if results else {}

        summary = f"\n{'='*50}\n"
        summary += f"📊 测试总结 (PyTOD 模式)\n"
        summary += f"{'='*50}\n"
        summary += f"处理轮数: {len(turns)}\n"
        summary += f"\n累积状态:\n"
        for key, value in final_state.items():
            if value:
                summary += f"  {key}: {value}\n"

        self.results_history.append({
            "mode": "pytod",
            "turns": len(turns),
            "final_state": final_state,
        })

        return result_text + summary, final_state

    async def process_dialogue_genie(self, turns: List[Dict]) -> Tuple[str, Dict]:
        """
        使用 Genie Worksheets 模式处理对话

        为每个对话创建独立的 GenieTracker 实例，确保测试结果独立。

        Args:
            turns: 对话轮次列表

        Returns:
            (处理结果文本, 最终状态)
        """
        if self._genie_schema is None:
            return (
                "❌ 未加载 Genie Schema。请通过 --genie-worksheet 或 --schema 参数提供 Worksheet 文件。\n"
                "   可通过以下命令预生成：\n"
                "   python examples/build_schema_data.py --genie-only --schema <schema.json>",
                {},
            )

        from contextmind.modes.genie.tracker import GenieTracker
        tracker = GenieTracker(
            llm_client=self.llm_client,
            schema=self._genie_schema,
            scene_description=getattr(self.config, "scene_description", "") or self.config.name,
            max_history_turns=self.max_history_turns,
        )
        logger.info("✅ 为新对话创建 Genie tracker")

        results = []
        result_text = ""

        for i, turn in enumerate(turns):
            user_utterance = turn.get("user_utterance", "")

            result = await tracker.process_turn(user_utterance=user_utterance)

            turn_result = {
                "turn_id": i + 1,
                "user_utterance": user_utterance,
                "response": result.get("response", ""),
                "state": result.get("state", {}),
            }
            results.append(turn_result)

            result_text += f"\n{'='*50}\n"
            result_text += f"轮次 {i + 1}\n"
            result_text += f"{'='*50}\n"
            result_text += f"客户: {user_utterance}\n"
            result_text += f"\n助手: {result.get('response', '')}\n"
            state = result.get("state", {})
            if state:
                result_text += "\n槽位状态:\n"
                for key, value in state.items():
                    if value:
                        result_text += f"  {key}: {value}\n"

        final_state = results[-1].get("state", {}) if results else {}

        summary = f"\n{'='*50}\n"
        summary += f"📊 测试总结 (Genie 模式)\n"
        summary += f"{'='*50}\n"
        summary += f"处理轮数: {len(turns)}\n"
        summary += f"服务: {self._genie_schema.service_name}\n"
        summary += f"\n累积状态:\n"
        for key, value in final_state.items():
            if value:
                summary += f"  {key}: {value}\n"

        self.results_history.append({
            "mode": "genie",
            "turns": len(turns),
            "final_state": final_state,
        })

        return result_text + summary, final_state

    async def process_dialogue_evolve(self, turns: List[Dict]) -> Tuple[str, Dict]:
        """
        使用 Evolve 模式处理对话
        
        复用 gradio_demo.py 中的处理逻辑
        
        Args:
            turns: 对话轮次列表
            
        Returns:
            (处理结果文本, 状态信息)
        """
        # ✅ 为每个对话创建新的应用实例，确保测试结果独立
        app = self._create_app_instance()
        logger.info(f"✅ 为新对话创建Evolve应用")
        
        result_text = ""
        
        for i, turn in enumerate(turns):
            user_utterance = turn.get('user_utterance', '')
            
            # 处理用户消息 - 复用 gradio_demo.py 的流程
            reply = await app.process_turn(user_utterance)
            
            # 格式化输出
            result_text += f"\n{'='*50}\n"
            result_text += f"轮次 {i + 1}\n"
            result_text += f"{'='*50}\n"
            result_text += f"用户输入: {user_utterance}\n"
            result_text += f"系统回复: {reply[:200]}{'...' if len(reply) > 200 else ''}\n"
        
        # 获取记忆库状态
        state_info = {}
        if app and hasattr(app, 'context_engine') and hasattr(app.context_engine, 'memory_bank'):
            memory_cache = app.context_engine.memory_bank.get_memory_cache()
            state_info['memory_count'] = len(memory_cache)
            state_info['recent_memories'] = []
            for mem in memory_cache[-5:]:  # 最近5条记忆
                content = mem.content if hasattr(mem, 'content') else str(mem)
                state_info['recent_memories'].append(content[:100])
        
        # 生成汇总
        summary = f"\n{'='*50}\n"
        summary += f"📊 测试总结 (Evolve 模式)\n"
        summary += f"{'='*50}\n"
        summary += f"处理轮数: {len(turns)}\n"
        summary += f"记忆数量: {state_info.get('memory_count', 0)}\n"
        if state_info.get('recent_memories'):
            summary += f"\n最近记忆:\n"
            for mem in state_info['recent_memories']:
                summary += f"  - {mem}...\n"
        
        # 保存到历史
        self.results_history.append({
            'mode': 'evolve',
            'turns': len(turns),
            'state_info': state_info
        })
        
        return result_text + summary, state_info
    
    def _create_app_instance(self):
        """
        为每个对话创建新的应用实例
        
        Returns:
            应用实例 (InsuranceApplication/CallCenterApplication/ChatApplication)
        """
        from contextmind.modes.evolve import EvolveEngine
        
        scenario_name = self.config.name
        session_id = f"batch_test_{id(self)}"
        
        # 创建Evolve引擎（所有应用都需要）
        evolve_engine = EvolveEngine(
            llm_client=self.llm_client,
            session_id=session_id
        )
        
        # 根据场景创建相应的应用
        if "保险" in scenario_name:
            from contextmind.scenarios.insurance import InsuranceApplication
            return InsuranceApplication(
                evolve_engine=evolve_engine,
                llm_client=self.llm_client,
                session_id=session_id,
                use_real_llm=True
            )
        elif "客服" in scenario_name or "callcenter" in scenario_name.lower():
            from contextmind.scenarios.callcenter import CallCenterApplication
            return CallCenterApplication(
                evolve_engine=evolve_engine,
                llm_client=self.llm_client,
                session_id=session_id,
                use_real_llm=True
            )
        else:
            from contextmind.scenarios.chat import ChatApplication
            return ChatApplication(
                evolve_engine=evolve_engine,
                llm_client=self.llm_client,
                session_id=session_id,
                use_real_llm=True
            )


# 全局测试实例
test_instance = None


def get_test_instance():
    """获取测试实例（延迟初始化）"""
    global test_instance
    if test_instance is None:
        test_instance = BatchDialogueTest(
            fnctod_schema_path=_BATCH_FNCTOD_SCHEMA_PATH,
            pytod_apis_path=_BATCH_PYTOD_APIS_PATH,
            schema_json_path=_BATCH_PYTOD_SCHEMA_PATH,
            genie_worksheet_path=_BATCH_GENIE_WORKSHEET_PATH,
        )
    return test_instance


async def process_dialogue_async(dialogue_text: str, mode: str) -> Tuple[str, str]:
    """
    异步处理对话
    
    Args:
        dialogue_text: 对话文本
        mode: "dst", "evolve", 或 "fnctod"
        
    Returns:
        (结果文本, 状态JSON)
    """
    try:
        instance = get_test_instance()
        
        # 初始化或切换模式
        if instance.current_mode != mode:
            instance.initialize(mode)
        
        # 解析对话
        turns = instance.parse_dialogue_input(dialogue_text)
        
        if not turns:
            return "❌ 未能解析出有效对话。\n\n请使用以下格式：\n销售员：xxx\n客户：xxx", "{}"
        
        # 处理对话
        if mode == "dst":
            result_text, state = await instance.process_dialogue_dst(turns)
        elif mode == "fnctod":
            result_text, state = await instance.process_dialogue_fnctod(turns)
        elif mode == "pytod":
            result_text, state = await instance.process_dialogue_pytod(turns)
        elif mode == "genie":
            result_text, state = await instance.process_dialogue_genie(turns)
        else:
            result_text, state = await instance.process_dialogue_evolve(turns)
        
        # 格式化状态为 JSON
        state_json = json.dumps(state, ensure_ascii=False, indent=2)
        
        return result_text, state_json
        
    except Exception as e:
        logger.error(f"处理对话时出错: {e}", exc_info=True)
        return f"❌ 处理出错: {str(e)}", "{}"


def process_dialogue(dialogue_text: str, mode: str) -> Tuple[str, str]:
    """
    同步包装器
    """
    return asyncio.run(process_dialogue_async(dialogue_text, mode))


def reset_state(mode: str) -> str:
    """重置状态"""
    try:
        instance = get_test_instance()
        if instance.current_mode:
            instance.reset()
            return "✅ 状态已重置"
        return "⚠️ 请先运行一次测试"
    except Exception as e:
        return f"❌ 重置失败: {str(e)}"


def load_test_dialogue(dialogue_num: int) -> str:
    """
    加载测试对话
    
    Args:
        dialogue_num: 对话编号 (1-7)
        
    Returns:
        对话文本
    """
    try:
        dialogue_path = Path(__file__).parent.parent / "tests" / "dialogues" / f"dialogue_{dialogue_num}.txt"
        if dialogue_path.exists():
            with open(dialogue_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return f"❌ 对话文件不存在: {dialogue_path}"
    except Exception as e:
        return f"❌ 加载失败: {str(e)}"


def create_test_ui():
    """创建测试 UI"""
    
    # 示例对话
    example_dialogue = """销售员：您好，我是札幌合作社团体癌症保险担当。请问您是合作社会员吗？
客户：是的。
销售员：今天是为了向您介绍会员专属的团体癌症保险。可以简单通过电话为您说明一下吗？
客户：好的，请说。
销售员：这款保险每月保费五千一百四十日元，可以享有十一项癌症保障，包括确诊即赔一百万日元。您有兴趣了解更多吗？
客户：我已经有其他保险了，暂时不需要。"""
    
    with gr.Blocks(
        title="ContextMind 批量对话测试",
        theme=gr.themes.Soft()
    ) as app:
        
        # 标题
        gr.Markdown("# 🧪 ContextMind 批量对话测试")
        gr.Markdown("直接输入对话内容进行 DST 或 Evolve 模式测试")
        
        with gr.Row():
            # 左侧 - 输入区
            with gr.Column(scale=1):
                gr.Markdown("### 📝 对话输入")
                
                # 模式选择
                mode_selector = gr.Radio(
                    choices=[
                        ("DST 模式 (槽位提取)", "dst"),
                        ("Evolve 模式 (记忆进化)", "evolve"),
                        ("FnCTOD 模式 (函数调用)", "fnctod"),
                        ("PyTOD 模式 (程序执行)", "pytod"),
                        ("Genie 模式 (声明式策略)", "genie"),
                    ],
                    value="dst",
                    label="选择模式"
                )
                
                # 对话输入框
                dialogue_input = gr.Textbox(
                    label="对话内容",
                    placeholder="请输入对话，格式：\n销售员：xxx\n客户：xxx",
                    lines=15,
                    value=example_dialogue
                )
                
                # 操作按钮
                with gr.Row():
                    process_btn = gr.Button("▶️ 运行测试", variant="primary")
                    reset_btn = gr.Button("🔄 重置状态")
                
                # 加载测试对话
                gr.Markdown("### 📂 加载测试对话")
                with gr.Row():
                    dialogue_selector = gr.Dropdown(
                        choices=[(f"对话 {i}", i) for i in range(1, 8)],
                        value=1,
                        label="选择对话",
                        scale=2
                    )
                    load_btn = gr.Button("📥 加载", scale=1)
            
            # 右侧 - 结果区
            with gr.Column(scale=1):
                gr.Markdown("### 📊 测试结果")
                
                # 结果显示
                result_output = gr.Textbox(
                    label="处理结果",
                    lines=20,
                    interactive=False
                )
                
                # 状态显示
                with gr.Accordion("🔍 详细状态", open=True):
                    state_output = gr.Code(
                        label="状态 JSON",
                        language="json",
                        lines=10
                    )
                
                # 重置状态显示
                reset_status = gr.Textbox(
                    label="状态",
                    lines=1,
                    interactive=False,
                    visible=False
                )
        
        # 使用说明
        with gr.Accordion("💡 使用说明", open=False):
            gr.Markdown("""
### 功能说明

这是一个批量对话测试界面，与 `web_demo.py` 的主要区别：

1. **直接输入对话内容**：不是实时交互，而是直接粘贴完整对话
2. **支持单轮/多轮**：可以输入一轮或多轮对话
3. **支持多次输入**：可以多次运行测试，状态会累积
4. **复用计算流程**：完全复用 `web_demo.py` 中的 DST 和 Evolve 计算逻辑

### 对话格式

```
销售员：你好，我是保险顾问
客户：你好
销售员：请问您有什么需要？
客户：我想了解癌症保险
```

### 模式说明

- **DST 模式**：提取对话中的槽位信息（意图、保险状态等）
- **Evolve 模式**：基于记忆的对话处理，会积累知识

### 测试对话

可以从 `tests/dialogues/` 目录加载预置的 7 个测试对话
            """)
        
        # 绑定事件
        process_btn.click(
            fn=process_dialogue,
            inputs=[dialogue_input, mode_selector],
            outputs=[result_output, state_output]
        )
        
        reset_btn.click(
            fn=reset_state,
            inputs=[mode_selector],
            outputs=[reset_status]
        ).then(
            fn=lambda: gr.update(visible=True),
            outputs=[reset_status]
        )
        
        load_btn.click(
            fn=load_test_dialogue,
            inputs=[dialogue_selector],
            outputs=[dialogue_input]
        )
    
    return app


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="ContextMind 批量对话测试Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python examples/batch_demo.py
  python examples/batch_demo.py --port 7861 --log-level DEBUG
  python examples/batch_demo.py --fnctod-schema schema/anyihua_fnctod_domain.json
  python examples/batch_demo.py --pytod-apis schema/anyihua_pytod_apis.py
  python examples/batch_demo.py --pytod-apis output/step2/schema_pytod_apis.py --schema output/step1/schema.json
  python examples/batch_demo.py --genie-worksheet schema/anyihua_genie_worksheet.json
  python examples/batch_demo.py --schema schema/anyihua_schema.json
        """,
    )
    parser.add_argument('--port', type=int, default=7861, help='端口号')
    parser.add_argument('--share', action='store_true', help='创建公共链接')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO')
    parser.add_argument(
        '--fnctod-schema', type=str, default=None, metavar='PATH',
        help='FnCTOD 模式的 schema 文件路径：推荐使用预生成的 *_fnctod_domain.json '
             '（可通过 build_schema_data.py 生成）；也接受 *_schema.json（自动寻找 companion 文件）',
    )
    parser.add_argument(
        '--pytod-apis', type=str, default=None, metavar='PATH',
        help='PyTOD 模式的 *_pytod_apis.py 路径（预生成 API 函数文件，schema/ 目录下）',
    )
    parser.add_argument(
        '--schema', type=str, default=None, dest='schema', metavar='PATH',
        help=(
            'schema.json 文件路径（PyTOD / Genie 模式均可使用）。'
            'PyTOD：与 --pytod-apis 配合显式指定 ServiceSchema。'
            'Genie：若未提供 --genie-worksheet，则在同目录自动寻找 *_genie_worksheet.json，'
            '找不到时直接从 schema.json 在线转换。'
        ),
    )
    parser.add_argument(
        '--genie-worksheet', type=str, default=None, metavar='PATH',
        help=(
            'Genie 模式的 Worksheet JSON 文件路径（*_genie_worksheet.json）。'
            '由 build_schema_data.py 自动从 schema.json 生成，无需人工编写。'
            '若不指定，则通过 --schema 指定的 schema.json 自动推导或在线转换。'
        ),
    )
    return parser.parse_args()


def main():
    """主函数"""
    global _BATCH_FNCTOD_SCHEMA_PATH, _BATCH_PYTOD_APIS_PATH, _BATCH_PYTOD_SCHEMA_PATH, _BATCH_GENIE_WORKSHEET_PATH
    args = parse_args()
    
    # 设置日志
    log_level = LogLevel.DEBUG if args.log_level == "DEBUG" else LogLevel.INFO
    setup_logging(level=log_level, save_to_file=True, log_dir="output/logs")

    if args.fnctod_schema:
        _BATCH_FNCTOD_SCHEMA_PATH = args.fnctod_schema
        logger.info(f"FnCTOD Schema: {args.fnctod_schema}")
    if args.pytod_apis:
        _BATCH_PYTOD_APIS_PATH = args.pytod_apis
        logger.info(f"PyTOD APIs: {args.pytod_apis}")
    if args.schema:
        _BATCH_PYTOD_SCHEMA_PATH = args.schema
        logger.info(f"Schema JSON: {args.schema}")
    if args.genie_worksheet:
        _BATCH_GENIE_WORKSHEET_PATH = args.genie_worksheet
        logger.info(f"Genie Worksheet: {args.genie_worksheet}")
    
    logger.info("启动 ContextMind 批量对话测试Demo")
    
    # 创建 UI
    app = create_test_ui()
    
    # 启动
    app.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share
    )


if __name__ == "__main__":
    main()
