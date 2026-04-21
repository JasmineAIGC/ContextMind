#!/usr/bin/env python3
"""
ContextMind Web界面Demo

支持四个场景：chat（闲聊）、callcenter（客服）、insurance（保险）、anyihua（安逸花外呼）
支持五种模式：DST对话状态追踪、Evolve记忆进化、FnCTOD函数调用、PyTOD程序执行、Genie声明式策略

使用方式:
    python examples/web_demo.py
    python examples/web_demo.py --log-level DEBUG --port 8080
    python examples/web_demo.py --max-history-turns 20 --share
    python examples/web_demo.py --fnctod-schema schema/anyihua_fnctod_domain.json
    python examples/web_demo.py --pytod-apis schema/anyihua_pytod_apis.py
    python examples/web_demo.py --pytod-apis output/step2/schema_pytod_apis.py --schema output/step1/schema.json
    python examples/web_demo.py --genie-worksheet schema/anyihua_genie_worksheet.json
    python examples/web_demo.py --schema schema/anyihua_schema.json

Schema 说明:
    FnCTOD 使用预生成的 companion JSON 文件（--fnctod-schema schema/xxx_fnctod_domain.json）
           也接受原始 schema（schema/xxx_schema.json），自动寻找 companion 文件
    PyTOD  使用预生成的 Python API 文件（--pytod-apis schema/xxx_pytod_apis.py）
           可选：通过 --schema 显式指定 schema.json（当自动推导路径不正确时使用）
    Genie  使用预生成的 Worksheet JSON 文件（--genie-worksheet schema/xxx_genie_worksheet.json）
           也接受 --schema schema/xxx_schema.json（自动推导或在线转换）
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
import re
import time
from typing import List, Tuple, Optional
from datetime import datetime

from contextmind.infra.llm_client import AdkLLMClient
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.pytod import AdkPyTODTracker
from contextmind.modes.pytod.schemas import load_schema_from_dict
from contextmind.modes.pytod.tracker import load_pytod_api_module
from contextmind.scenarios import get_chat_scenario, get_callcenter_scenario, get_insurance_scenario, get_anyihua_scenario
from contextmind.ui.components import create_gradio_ui, CUSTOM_CSS
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

# 使用统一的logger from utils/logger.py
logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent


def _load_fnctod_schema(json_path: str):
    """从 schema.json 文件加载 FnCTOD DomainSpec（及 ServiceSchema）。

    先尝试从预生成的 companion 文件加载（``*_fnctod_domain.json``），
    若不存在则从 schema.json 在线构建 FunctionManager domain。

    Returns:
        (ServiceSchema, DomainSpec) 二元组；加载失败时记录错误并返回 (None, None)。
    """
    import json as _json
    from contextmind.modes.fnctod.function_manager import FunctionManager
    from pathlib import Path as _Path
    try:
        with open(json_path, encoding="utf-8") as f:
            data = _json.load(f)
        svc = load_schema_from_dict(data)

        # 优先从预生成的 companion fnctod_domain.json 加载 FunctionManager 域
        sp = _Path(json_path)
        base = sp.stem[: -len("_schema")] if sp.stem.endswith("_schema") else sp.stem
        fnctod_domain_path = sp.parent / f"{base}_fnctod_domain.json"

        fm = FunctionManager()
        if fnctod_domain_path.exists():
            try:
                with open(fnctod_domain_path, encoding="utf-8") as fh:
                    dd = _json.load(fh)
                # New format: OpenAI JSON Schema (name/description/parameters.properties)
                if "parameters" in dd and "properties" in dd.get("parameters", {}):
                    from contextmind.modes.fnctod.function_manager import (
                        DomainSpec, FunctionParameter, ParameterType,
                    )
                    spec = DomainSpec(
                        name=dd["name"],
                        description=dd.get("description", ""),
                    )
                    params_schema = dd["parameters"]
                    required_set = set(params_schema.get("required", []))
                    for slot_name, prop in params_schema.get("properties", {}).items():
                        spec.add_parameter(FunctionParameter(
                            name=slot_name,
                            description=prop.get("description", ""),
                            param_type=ParameterType.STRING,
                            required=slot_name in required_set,
                            enum_values=prop.get("enum"),
                        ))
                    fm.add_domain(spec)
                else:
                    # Legacy format: add_domain_from_slots() input
                    fm.add_domain_from_slots(
                        domain_name=dd.get("domain_name", dd.get("name", svc.service_name)),
                        domain_description=dd.get("description", svc.description),
                        slots=dd.get("slots", {}),
                        categorical_slots=dd.get("categorical_slots") or None,
                        required_slots=dd.get("required_slots") or None,
                    )
                logger.info(f"已从 companion 文件加载 FnCTOD 域: {fnctod_domain_path.name}")
            except Exception as exc:
                logger.warning(f"companion fnctod_domain 加载失败，改用在线构建: {exc}")
                fm = FunctionManager()  # reset
                _build_fnctod_domain_inline(fm, svc)
        else:
            _build_fnctod_domain_inline(fm, svc)

        domains = fm.get_all_domains()
        if not domains:
            raise ValueError(f"Schema '{json_path}' produced no valid domains")
        domain_spec = domains[0]
        logger.info(f"已加载 FnCTOD Schema: {json_path} (service={svc.service_name})")
        return svc, domain_spec
    except Exception as exc:
        logger.error(f"加载 FnCTOD Schema 失败: {json_path} — {exc}")
        return None, None


def _load_pytod_service_schema(apis_py_path: str, schema_json_path: Optional[str] = None):
    """从 *_pytod_apis.py 路径推导 schema.json 并加载 ServiceSchema。

    若 schema_json_path 已显式指定，则直接加载该文件。
    否则按以下优先级自动推导（均与 apis_py_path 同目录）：

    1. ``{base}_schema.json``（标准命名，如 ``anyihua_pytod_apis.py`` → ``anyihua_schema.json``）
    2. ``{base}.json``（兜底，如 ``schema_pytod_apis.py`` → ``schema.json``）

    若均不存在则返回 None，PyTOD 将退化为无结构 prompt 模式。
    """
    import json as _json
    from pathlib import Path as _Path

    def _load_json(path: "_Path"):
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return load_schema_from_dict(_json.load(f))

    if schema_json_path:
        return _load_json(_Path(schema_json_path))

    p = _Path(apis_py_path)
    stem = p.stem  # e.g. "anyihua_pytod_apis"
    base = stem[: -len("_pytod_apis")] if stem.endswith("_pytod_apis") else stem
    # 优先尝试标准命名
    schema = _load_json(p.parent / f"{base}_schema.json")
    if schema is not None:
        return schema
    # 兜底：base 本身不含 "_schema" 后缀时（如 schema_pytod_apis.py → base="schema"），
    # {base}_schema.json 会变成 schema_schema.json（不存在），回退到 {base}.json
    return _load_json(p.parent / f"{base}.json")


def _build_fnctod_domain_inline(fm: any, svc: any) -> None:
    """从 ServiceSchema 在线构建 FnCTOD FunctionManager 域（fallback）。"""
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


class UnifiedGradioDemo:
    """统一的Gradio Demo类"""
    
    def __init__(
        self,
        max_history_turns: int = 10,
        fnctod_schema_path: Optional[str] = None,
        pytod_apis_path: Optional[str] = None,
        schema_json_path: Optional[str] = None,
        genie_worksheet_path: Optional[str] = None,
    ):
        """
        初始化Demo

        Args:
            max_history_turns:    最大历史轮数（所有模式）
            fnctod_schema_path:   FnCTOD 模式的 schema 文件路径
            pytod_apis_path:      PyTOD 模式的 *_pytod_apis.py 路径（预生成 API 函数文件）
            schema_json_path:     PyTOD / Genie 模式的 schema.json 路径（显式指定；优先于自动推导）
            genie_worksheet_path: Genie 模式的 *_genie_worksheet.json 路径（预生成 Worksheet 文件）
        """
        self.current_scenario = None
        self.current_mode = None
        self.config = None
        self.llm_client = None
        self.tracker = None  # For DST mode
        self.fnctod_tracker = None  # For FnCTOD mode
        self.pytod_tracker = None  # For PyTOD mode
        self.genie_tracker = None  # For Genie mode
        self.max_history_turns = max_history_turns
        self.app = None
        self.initialized = False
        self.history = []
        # 存储用户输入处理后、机器人回复前的对话状态
        self.post_user_state = None
        # FnCTOD：从 schema.json 加载 DomainSpec
        self._fnctod_domain_spec = None
        if fnctod_schema_path:
            _, self._fnctod_domain_spec = _load_fnctod_schema(fnctod_schema_path)
        # PyTOD：从 *_pytod_apis.py 加载 ServiceSchema（推导对应 JSON；显式 --schema 优先）
        self._pytod_schema = None
        self._pytod_apis_path: Optional[str] = pytod_apis_path
        if pytod_apis_path:
            self._pytod_schema = _load_pytod_service_schema(pytod_apis_path, schema_json_path)
        # Genie：从 Worksheet JSON 或 schema.json 加载 GenieSchema
        self._genie_schema = None
        self._genie_worksheet_path: Optional[str] = genie_worksheet_path
        self._schema_json_path: Optional[str] = schema_json_path
        if genie_worksheet_path or schema_json_path:
            try:
                from examples.batch_demo import _load_genie_schema
                self._genie_schema = _load_genie_schema(genie_worksheet_path, schema_json_path)
                if self._genie_schema is not None:
                    logger.info(f"已加载 Genie Schema: {self._genie_schema.service_name}")
            except Exception as exc:
                logger.warning(f"加载 Genie Schema 失败: {exc}")
        logger.info("Demo实例创建完成（延迟初始化）")
    
    def initialize_scenario(self, scenario: str, mode: str):
        """初始化场景和模式"""
        self.current_scenario = scenario
        self.current_mode = mode
        
        # 加载场景配置
        if scenario == "chat":
            self.config = get_chat_scenario()
        elif scenario == "callcenter":
            self.config = get_callcenter_scenario()
        elif scenario == "insurance":
            self.config = get_insurance_scenario()
        elif scenario == "anyihua":
            self.config = get_anyihua_scenario()
        else:
            raise ValueError(f"未知场景: {scenario}")
        
        # 根据模式初始化
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
        
        logger.info(f"✅ 场景初始化完成: {scenario}, 模式: {mode}")
    
    def _get_welcome_message(self) -> str:
        """获取欢迎消息"""
        return self.config.welcome_message if self.config.welcome_message else "你好！"
    
    def _setup_dst_tracker(self):
        """初始化DST模式"""
        try:
            if self.llm_client is None:
                self.llm_client = AdkLLMClient()
                logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            error_msg = f"❌ LLM客户端初始化失败: {str(e)}\n\n"
            if "API" in str(e).upper() or "KEY" in str(e).upper():
                error_msg += "📝 请检查以下配置：\n"
                error_msg += "1. 确认.env文件存在\n"
                error_msg += "2. 配置以下环境变量之一：\n"
                error_msg += "   - QWEN3_API_KEY\n"
                error_msg += "   - CONTEXTMIND_API_KEY\n"
                error_msg += "   - LLM_API_KEY\n"
                error_msg += "   - OPENAI_API_KEY\n"
                error_msg += "3. 重启程序\n"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # 使用工厂方法创建DST追踪器
        self.tracker = DialogueStateTracker.from_scenario(
            llm_client=self.llm_client,
            scenario_config=self.config,
            max_history_turns=10,
            enable_history_summary=True,
            use_llm_summary=False
        )
        
        logger.info("DST模式初始化完成")
    
    def _setup_fnctod_tracker(self):
        """初始化FnCTOD模式"""
        if self.llm_client is None:
            self.llm_client = AdkLLMClient()
        kwargs = {}
        if self._fnctod_domain_spec is not None:
            kwargs["domain_spec"] = self._fnctod_domain_spec
        self.fnctod_tracker = FnCTODTracker.from_scenario(self.llm_client, self.config, **kwargs)
        logger.info("FnCTOD模式初始化完成")

    def _setup_pytod_tracker(self):
        """初始化PyTOD模式（三步流程：AP → EE → DM）"""
        if self.llm_client is None:
            self.llm_client = AdkLLMClient()
        kwargs = {}
        if self._pytod_schema is not None:
            kwargs["schema"] = self._pytod_schema
        # 直接传入 *_pytod_apis.py 路径，load_pytod_api_module 可直接加载
        if self._pytod_apis_path is not None:
            kwargs["schema_path"] = self._pytod_apis_path
        self.pytod_tracker = AdkPyTODTracker.from_scenario(self.llm_client, self.config, **kwargs)
        logger.info("PyTOD模式初始化完成 (三步流程: AP→EE→DM)")

    def _setup_genie_tracker(self):
        """初始化 Genie Worksheets 模式（声明式策略追踪）"""
        if self._genie_schema is None:
            raise ValueError(
                "Genie 模式需要 --genie-worksheet 或 --schema 参数。\n"
                "可通过以下命令预生成 Worksheet：\n"
                "  python examples/build_schema_data.py --genie-only --schema <schema.json>"
            )
        if self.llm_client is None:
            self.llm_client = AdkLLMClient()
        from contextmind.modes.genie.tracker import GenieTracker
        self.genie_tracker = GenieTracker(
            llm_client=self.llm_client,
            schema=self._genie_schema,
            scene_description=getattr(self.config, "scene_description", "") or self.config.name,
            max_history_turns=self.max_history_turns,
        )
        logger.info("Genie 模式初始化完成")

    def _setup_evolve_app(self):
        """初始化Evolve模式"""
        try:
            if self.llm_client is None:
                self.llm_client = AdkLLMClient()
                logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            error_msg = f"❌ LLM客户端初始化失败: {str(e)}\n\n"
            if "API" in str(e).upper() or "KEY" in str(e).upper():
                error_msg += "📝 请检查.env配置文件\n"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # 使用工厂方法创建应用
        from contextmind.modes.evolve import create_app_for_scenario
        self.app = create_app_for_scenario(
            scenario_name=self.current_scenario,
            llm_client=self.llm_client,
            scenario_config=self.config,
            app_name_prefix="gradio_demo"
        )
        
        logger.info("Evolve模式初始化完成")
    
    async def chat(self, message: str, history: List) -> List:
        """处理对话"""
        try:
            # 首次使用时初始化
            if not self.initialized:
                self.initialize_scenario("chat", "evolve")
                self.initialized = True
                # 如果历史为空，添加欢迎消息作为第一条消息
                if not history:
                    welcome_msg = self._get_welcome_message()
                    history = [{"role": "assistant", "content": welcome_msg}]
            
            if not message or not message.strip():
                return history
            
            # 开始计时 - 从接收输入到生成结果
            start_time = time.time()
            
            # 用于记录各步骤耗时
            timing_breakdown = {}
            
            # 处理对话
            if self.current_mode == "dst":
                # DST模式
                # 获取上一轮系统回复
                # history格式: [{user_msg}, {assistant_msg}, {user_msg}, {assistant_msg}, ...]
                # 安全地获取上一轮的assistant回复内容
                # 如果没有历史记录，使用欢迎消息作为默认值
                default_system_utterance = self._get_welcome_message()
                system_utterance = next(
                    (msg.get('content', default_system_utterance) for msg in reversed(history) if msg.get('role') == 'assistant'),
                    default_system_utterance
                )
                
                # 确保system_utterance是字符串类型（防止list等其他类型）
                if not isinstance(system_utterance, str):
                    if isinstance(system_utterance, list):
                        # 如果是列表，提取第一个元素或转换为字符串
                        system_utterance = str(system_utterance[0]) if system_utterance else default_system_utterance
                    else:
                        # 其他类型转换为字符串
                        system_utterance = str(system_utterance) if system_utterance else default_system_utterance
                
                # 移除耗时标记，避免影响DST提取和历史累积
                # 格式: "\n\n<small style='color: #888;'>⏱️ 生成耗时: X.XX秒</small>"
                system_utterance = re.sub(r'\n\n<small style=.*?生成耗时:.*?</small>', '', system_utterance)

                # 步骤1: 槽位提取（process_turn）
                # 步骤2: 回复生成（包含历史上下文，与槽位提取并行执行节省延迟）
                # 注意：回复生成使用对话历史而非槽位提取结果，因此可并行
                system_prompt = self.config.system_prompt

                # 构建包含历史的回复消息列表（修复：之前版本缺失历史上下文）
                reply_messages: list = [{"role": "system", "content": system_prompt}]
                timing_tag_re = re.compile(r'\n\n<small style=.*?</small>', re.DOTALL)
                for hist_msg in history[-self.max_history_turns * 2:]:
                    role = hist_msg.get("role", "user")
                    content = hist_msg.get("content", "")
                    if isinstance(content, str):
                        content = timing_tag_re.sub("", content)
                    reply_messages.append({"role": role, "content": content})
                reply_messages.append({"role": "user", "content": message})

                step_start = time.time()
                state, reply = await asyncio.gather(
                    self.tracker.process_turn(
                        system_utterance=system_utterance,
                        user_utterance=message
                    ),
                    self.llm_client.chat_async(messages=reply_messages)
                )
                timing_breakdown['槽位提取+回复生成(并行)'] = time.time() - step_start

                # 收集DST内部的详细步骤耗时
                if hasattr(self.tracker, 'step_timings'):
                    timing_breakdown.update(self.tracker.step_timings)

                # 步骤2: 状态捕获（槽位提取已通过 gather 完成）
                step_start = time.time()
                self._capture_post_user_state()
                timing_breakdown['状态捕获'] = time.time() - step_start
                
            elif self.current_mode == "fnctod":
                # FnCTOD模式
                step_start = time.time()
                result = await self.fnctod_tracker.process_turn(
                    user_utterance=message,
                    system_utterance=""
                )
                reply = result.get("response", "")
                timing_breakdown['函数调用处理'] = time.time() - step_start

                # 收集FnCTOD内部的详细步骤耗时
                if hasattr(self.fnctod_tracker, 'step_timings'):
                    timing_breakdown.update(self.fnctod_tracker.step_timings)
                    if '函数调用处理' in timing_breakdown and len(self.fnctod_tracker.step_timings) > 0:
                        del timing_breakdown['函数调用处理']

                # 状态捕获
                step_start = time.time()
                self._capture_post_user_state()
                timing_breakdown['状态捕获'] = time.time() - step_start

            elif self.current_mode == "pytod":
                # PyTOD模式（论文三步流程：动作解析器 → 执行引擎 → 对话管理器）
                step_start = time.time()
                result = await self.pytod_tracker.process_turn(user_utterance=message)
                reply = result.get("response", "")
                timing_breakdown['PyTOD总计'] = time.time() - step_start

                # 收集 PyTODTracker 内部各步骤（AP/EE/DM）耗时
                if hasattr(self.pytod_tracker, 'step_timings') and self.pytod_tracker.step_timings:
                    timing_breakdown.update(self.pytod_tracker.step_timings)
                    if 'PyTOD总计' in timing_breakdown and len(self.pytod_tracker.step_timings) > 0:
                        del timing_breakdown['PyTOD总计']

                # 状态捕获
                step_start = time.time()
                self._capture_post_user_state()
                timing_breakdown['状态捕获'] = time.time() - step_start

            else:
                # Evolve模式
                step_start = time.time()
                reply = await self.app.process_turn(message)
                timing_breakdown['对话处理'] = time.time() - step_start
                
                # 收集Evolve内部的详细步骤耗时
                if hasattr(self.app, 'step_timings'):
                    timing_breakdown.update(self.app.step_timings)
                    # 移除重复的'对话处理'（使用Evolve内部的详细步骤）
                    if '对话处理' in timing_breakdown and len(self.app.step_timings) > 0:
                        del timing_breakdown['对话处理']
                
                # 状态捕获
                # Evolve模式：process_turn是原子操作，包含了上下文构建和回复生成
                # 这里捕获的是内部用于生成回复的上下文状态
                # 注意：Evolve的状态是从记忆库和上下文中构建的
                step_start = time.time()
                self._capture_post_user_state()
                timing_breakdown['状态捕获'] = time.time() - step_start
            
            # 计算总耗时（从接收输入到生成结果）
            elapsed_time = time.time() - start_time
            
            # 添加总计到timing_breakdown
            timing_breakdown['总计'] = elapsed_time
            
            # 构建详细的耗时信息显示（单行格式）
            if timing_breakdown and len(timing_breakdown) > 1:
                # 单行显示，用 | 分隔各步骤
                timing_parts = []
                total_time = timing_breakdown.get('总计', elapsed_time)
                
                for key, value in timing_breakdown.items():
                    if key != '总计':
                        timing_parts.append(f"{key}{value:.2f}s")
                
                # 添加总计
                timing_parts.append(f"总计{total_time:.2f}s")
                
                timing_display = "⏱️ " + " | ".join(timing_parts)
            else:
                timing_display = f"⏱️ 生成耗时: {elapsed_time:.2f}秒"
            
            # 在回复中添加耗时信息（小号灰色文本）
            reply_with_timing = f"{reply}\n\n<small style='color: #888;'>{timing_display}</small>"
            
            # 更新历史 - 使用Gradio 6.0格式 (flat list)
            return history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": reply_with_timing}
            ]
            
        except ValueError as e:
            # API密钥错误
            if "API" in str(e).upper() or "KEY" in str(e).upper():
                error_msg = "⚠️ 配置错误：缺少API密钥\n\n" + \
                           "请配置.env文件中的以下变量之一：\n" + \
                           "- QWEN3_API_KEY\n" + \
                           "- CONTEXTMIND_API_KEY\n" + \
                           "- LLM_API_KEY\n" + \
                           "- OPENAI_API_KEY\n\n" + \
                           f"详细错误: {str(e)}"
                return history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": error_msg}
                ]
            else:
                return history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": f"❌ 错误: {str(e)}"}
                ]
        except Exception as e:
            logger.error(f"对话处理错误: {e}", exc_info=True)
            return history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": f"❌ 系统错误: {str(e)}"}
            ]
    
    def _capture_post_user_state(self):
        """
        捕获用户输入处理后的对话状态（用于辅助回复生成的状态）
        
        调用时机因模式而异：
        - DST模式：process_turn()之后，LLM生成回复之前
          状态提取 → 状态捕获 → 回复生成（理想时机）
        
        - FnCTOD模式：process_turn()之后（内部已完成状态提取和回复生成）
          虽然UI捕获在回复之后，但捕获的是内部用于生成回复的"回复前状态"
        
        - Evolve模式：process_turn()之后（内部已完成上下文构建和回复生成）
          虽然UI捕获在回复之后，但捕获的是内部用于生成回复的"回复前状态"
        
        重要说明：
        所有模式的核心逻辑都是"先提取状态，再生成回复"，这样状态才能辅助回复生成。
        只是UI显示的捕获时机不同，但捕获的都是用于辅助生成回复的状态。
        """
        try:
            # 直接构建状态字典，避免调用get_state造成循环
            self.post_user_state = self._build_state_dict()
        except Exception as e:
            logger.warning(f"捕获对话状态时出错: {e}")
            # 如果捕获失败，设置为None，get_state会使用实时状态
            self.post_user_state = None
    
    def _build_state_dict(self) -> dict:
        """构建状态字典（内部方法）
        
        累积状态说明：
        - 累积状态显示从对话开始到当前轮次，所有已提取槽位的最新值
        - 本轮提取显示最近一轮对话中新提取或更新的槽位
        - 累积状态会随着对话进行不断更新，反映整个对话的完整信息
        """
        if self.current_mode == "dst" and self.tracker:
            # DST模式：本轮新提取槽位 + 累积状态
            state_info = {
                "模式": "DST (对话状态追踪)",
                "场景": self._get_scenario_name(self.current_scenario),
                "对话轮数": len(self.tracker.dialogue_history),
            }

            # 本轮新提取/更新的槽位
            if self.tracker.dialogue_history:
                last_turn = self.tracker.dialogue_history[-1]
                if last_turn.turn_updates:
                    state_info["本轮提取"] = {
                        k: str(v) for k, v in last_turn.turn_updates.items()
                    }
                else:
                    state_info["本轮提取"] = "（本轮无新提取）"
            else:
                state_info["本轮提取"] = "（暂无对话记录）"

            # 累积状态：过滤空值后展示
            non_empty_slots = {
                k: (str(v)[:60] + "..." if len(str(v)) > 60 else str(v))
                for k, v in self.tracker.current_state.items()
                if v and str(v).strip()
            }
            state_info["累积状态"] = non_empty_slots if non_empty_slots else "（暂无）"

            return state_info

        elif self.current_mode == "fnctod" and self.fnctod_tracker:
            # FnCTOD模式：本轮函数调用提取的槽位 + 累积状态
            state_info = {
                "模式": "FnCTOD (函数调用DST)",
                "场景": self._get_scenario_name(self.current_scenario),
                "对话轮数": self.fnctod_tracker.turn_count,
            }

            # 本轮提取（通过函数调用识别的槽位）
            last_updates = self.fnctod_tracker.last_turn_updates
            if last_updates:
                state_info["本轮提取"] = {
                    k: (str(v)[:60] + "..." if len(str(v)) > 60 else str(v))
                    for k, v in last_updates.items()
                }
            elif self.fnctod_tracker.turn_count > 0:
                state_info["本轮提取"] = "（本轮无新提取）"
            else:
                state_info["本轮提取"] = "（暂无对话记录）"

            # 累积状态（所有轮次槽位合并）
            non_empty_slots = {
                k: (str(v)[:60] + "..." if len(str(v)) > 60 else str(v))
                for k, v in self.fnctod_tracker.get_current_state().items()
                if v and str(v).strip()
            }
            state_info["累积状态"] = non_empty_slots if non_empty_slots else "（暂无）"

            return state_info

        elif self.current_mode == "pytod" and self.pytod_tracker:
            # PyTOD模式（AP→EE→DM）：本轮AP程序 + 本轮执行结果 + 累积状态
            import json as _json

            state_info = {
                "模式": "PyTOD (AP→EE→DM)",
                "场景": self._get_scenario_name(self.current_scenario),
                "对话轮数": self.pytod_tracker.turn_count,
            }

            if self.pytod_tracker.turn_count == 0:
                state_info["状态"] = "等待用户输入…"
                return state_info

            # 本轮AP生成的程序（意图+槽位的可读表示）
            last_prog = self.pytod_tracker.last_program_text
            if last_prog:
                state_info["本轮程序"] = last_prog.strip()

            # 本轮执行结果：提取的变量值（即本轮状态）
            ee_result = self.pytod_tracker.last_execution_result
            if ee_result is not None:
                if not ee_result.success:
                    errors = getattr(ee_result, "errors", [])
                    state_info["本轮状态"] = "执行失败：" + (
                        "; ".join(str(e) for e in errors) if errors else "未知错误"
                    )
                else:
                    var_values = getattr(ee_result, "variable_values", {})
                    cur_vars = {k: v for k, v in var_values.items() if not k.startswith("_anon")}
                    if cur_vars:
                        state_info["本轮状态"] = {
                            k: (
                                _json.dumps(v, ensure_ascii=False)[:80] + "..."
                                if len(_json.dumps(v, ensure_ascii=False)) > 80
                                else _json.dumps(v, ensure_ascii=False)
                            )
                            for k, v in cur_vars.items()
                        }
                    else:
                        state_info["本轮状态"] = "（本轮无槽位提取）"

            # 累积状态（跨轮次变量值）
            cumulative = {
                k: v for k, v in self.pytod_tracker.current_state.items()
                if not k.startswith("_anon")
            }
            if cumulative:
                state_info["累积状态"] = {
                    k: (
                        _json.dumps(v, ensure_ascii=False)[:80] + "..."
                        if len(_json.dumps(v, ensure_ascii=False)) > 80
                        else _json.dumps(v, ensure_ascii=False)
                    )
                    for k, v in cumulative.items()
                }
            else:
                state_info["累积状态"] = "（暂无）"

            return state_info

        elif self.current_mode == "evolve" and self.app:
            # Evolve模式：显示当前上下文和记忆库信息
            engine = self.app.evolve_engine
            state_info = {
                "模式": "Evolve (记忆进化)",
                "场景": self._get_scenario_name(self.current_scenario),
            }

            # 本轮 optimize() 使用的上下文（会话历史 + 召回记忆）
            if hasattr(engine, 'last_context_result') and engine.last_context_result is not None:
                cr = engine.last_context_result
                meta = cr.metadata or {}
                session_cnt = meta.get("session_history_count", 0)
                memory_cnt = meta.get("long_term_memory_count", 0)
                state_info["本轮上下文"] = f"会话历史 {session_cnt} 条 | 召回记忆 {memory_cnt} 条"

                # 显示召回的记忆条目（source != HISTORY 的 ContextItem）
                from contextmind.modes.evolve.core.data_models import ContextSource
                recalled = [
                    item for item in cr.items
                    if getattr(item, 'source', None) != ContextSource.HISTORY
                ]
                if recalled:
                    state_info["召回记忆"] = [
                        (item.content[:80] + "..." if len(item.content) > 80 else item.content)
                        for item in recalled[:5]
                    ]

            # 记忆库（从历轮 extract_knowledge 后台任务积累）
            if hasattr(engine, 'memory_bank'):
                memory_cache = engine.memory_bank.get_memory_cache()
                total_memories = len(memory_cache)
                state_info["记忆库总数"] = total_memories
                if memory_cache:
                    memories_display = []
                    for mem in memory_cache[-5:]:
                        content = str(mem.content if hasattr(mem, 'content') else mem)
                        if len(content) > 80:
                            content = content[:77] + '...'
                        memories_display.append(content)
                    state_info["记忆库内容(最近5条)"] = memories_display

            # 会话消息数
            if hasattr(engine, 'session_manager'):
                sm = engine.session_manager
                session_msgs = len(getattr(sm, '_messages', []))
                state_info["会话消息数"] = session_msgs

            return state_info
        else:
            return {"状态": "未初始化", "提示": "请先应用场景配置"}
    
    def get_state(self) -> dict:
        """
        获取对话状态
        
        返回用于辅助生成回复的对话状态（"回复前状态"）
        
        状态说明：
        - 这个状态反映了系统对用户输入的理解
        - 这个状态被用于辅助生成更好的回复
        - 逻辑上，状态提取发生在回复生成之前（所有模式都遵循此原则）
        - UI显示的是这个"回复前状态"，即使某些模式在完整轮次后才捕获
        
        如果尚未捕获状态（如第一次调用），则返回当前实时状态
        """
        if self.post_user_state is not None:
            return self.post_user_state
        else:
            # 如果还没有捕获的状态，返回当前实时状态
            return self._build_state_dict()
    
    def _get_scenario_name(self, scenario: str) -> str:
        """获取场景中文名称"""
        scenario_names = {
            "chat": "💬 闲聊对话",
            "callcenter": "📞 智能客服",
            "insurance": "🏥 保险咨询",
            "anyihua": "💳 安逸花外呼",
        }
        return scenario_names.get(scenario, scenario)
    
    def reset_conversation(self):
        """重置对话"""
        if self.current_mode == "dst" and self.tracker:
            self.tracker.current_state = {}
            self.tracker.dialogue_history = []
        elif self.current_mode == "fnctod" and self.fnctod_tracker:
            self.fnctod_tracker.reset()
        elif self.current_mode == "pytod" and self.pytod_tracker:
            self.pytod_tracker.reset()
        elif self.current_mode == "genie" and self.genie_tracker:
            self.genie_tracker.reset()
        elif self.current_mode == "evolve" and self.app:
            # 重新初始化app
            self.initialize_scenario(self.current_scenario, self.current_mode)

        logger.info("对话已重置")
        return []
    
    def change_scenario_or_mode(self, scenario: str, mode: str):
        """切换场景或模式"""
        self.initialize_scenario(scenario, mode)
        self.initialized = True
        
        scenario_names = {
            "chat": "闲聊对话",
            "callcenter": "智能客服",
            "insurance": "保险咨询",
            "anyihua": "安逸花外呼",
        }
        
        status = f"📌 当前配置: 场景={scenario_names.get(scenario, scenario)}, 模式={mode}"
        logger.info(f"配置已更新: {scenario}, {mode}")
        
        # 机器人主动发起对话 - 使用欢迎消息作为第一句话
        welcome_msg = self._get_welcome_message()
        initial_history = [
            {"role": "assistant", "content": welcome_msg}
        ]
        
        return initial_history, status
    
    
    def update_settings(self, max_history_turns: int, enable_summary: bool, use_llm_summary: bool,
                        enable_memory: bool, enable_evolution: bool):
        """更新设置"""
        self.max_history_turns = max_history_turns
        
        # 如果当前是DST模式且已初始化，更新追踪器设置
        if self.current_mode == "dst" and self.tracker:
            self.tracker.max_history_turns = max_history_turns
            self.tracker.enable_history_summary = enable_summary
            self.tracker.use_llm_summary = use_llm_summary
            logger.info(f"DST设置已更新: max_history_turns={max_history_turns}, enable_summary={enable_summary}, use_llm_summary={use_llm_summary}")
            
            summary_status = "启用" if enable_summary else "禁用"
            llm_summary_status = "LLM" if use_llm_summary else "模板"
            return f"⚙️ DST设置: 历史={max_history_turns}轮, 摘要={summary_status}, 方式={llm_summary_status}"
        
        elif self.current_mode == "evolve" and self.app:
            # Evolve模式的设置（记忆和进化是在初始化时设置的）
            logger.info(f"Evolve设置: 记忆={enable_memory}, 进化={enable_evolution}")
            
            memory_status = "启用" if enable_memory else "禁用"
            evolution_status = "启用" if enable_evolution else "禁用"
            return f"⚙️ Evolve设置: 记忆={memory_status}, 进化={evolution_status}, 最大事件={max_history_turns}"
        
        return "⚙️ 请先应用场景配置"


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="ContextMind Web界面Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python examples/web_demo.py
  python examples/web_demo.py --log-level DEBUG
  python examples/web_demo.py --port 8080 --share
  python examples/web_demo.py --max-history-turns 20 --log-level INFO
  python examples/web_demo.py --fnctod-schema schema/anyihua_fnctod_domain.json
  python examples/web_demo.py --pytod-apis schema/anyihua_pytod_apis.py
        """
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别 (默认: INFO)'
    )
    
    parser.add_argument(
        '--max-history-turns',
        type=int,
        default=10,
        help='最大历史轮数（所有模式，默认: 10）'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=7860,
        help='Web服务器端口 (默认: 7860)'
    )
    
    parser.add_argument(
        '--share',
        action='store_true',
        help='创建公共分享链接'
    )

    parser.add_argument(
        '--fnctod-schema',
        type=str,
        default=None,
        metavar='PATH',
        help='FnCTOD 模式的 schema 文件路径：推荐使用预生成的 *_fnctod_domain.json '
             '（可通过 build_schema_data.py 生成）；也接受 *_schema.json（自动寻找 companion 文件）',
    )

    parser.add_argument(
        '--pytod-apis',
        type=str,
        default=None,
        metavar='PATH',
        help='PyTOD 模式的 *_pytod_apis.py 路径（预生成 API 函数文件，schema/ 目录下）。例如: --pytod-apis schema/anyihua_pytod_apis.py',
    )

    parser.add_argument(
        '--schema',
        type=str,
        default=None,
        dest='schema',
        metavar='PATH',
        help=(
            'schema.json 文件路径（PyTOD / Genie 模式均可使用）。'
            'PyTOD：与 --pytod-apis 配合显式指定 ServiceSchema（推荐）。'
            '若不指定，则从 *_pytod_apis.py 文件名自动推导同目录下的 xxx_schema.json 或 xxx.json。'
            'Genie：若未提供 --genie-worksheet，则在同目录自动寻找 *_genie_worksheet.json，'
            '找不到时直接从 schema.json 在线转换。'
        ),
    )

    parser.add_argument(
        '--genie-worksheet',
        type=str,
        default=None,
        metavar='PATH',
        help=(
            'Genie 模式的 Worksheet JSON 文件路径（*_genie_worksheet.json）。'
            '由 build_schema_data.py 自动从 schema.json 生成，无需人工编写。'
            '若不指定，则通过 --schema 指定的 schema.json 自动推导或在线转换。'
        ),
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    # 使用setup_logging配置日志系统
    log_level = LogLevel.DEBUG if args.log_level == "DEBUG" else LogLevel.INFO
    setup_logging(level=log_level, save_to_file=True, log_dir="output/logs")
    
    logger.info("[__main__] 启动 ContextMind Gradio Demo")
    logger.info(f"参数配置: 日志级别={args.log_level}, 最大历史轮数={args.max_history_turns}, 端口={args.port}, 分享={args.share}")
    if args.fnctod_schema:
        logger.info(f"FnCTOD Schema: {args.fnctod_schema}")
    if args.pytod_apis:
        logger.info(f"PyTOD APIs: {args.pytod_apis}")
    if args.schema:
        logger.info(f"Schema JSON: {args.schema}")
    if args.genie_worksheet:
        logger.info(f"Genie Worksheet: {args.genie_worksheet}")
    
    # 创建Demo实例
    try:
        demo_instance = UnifiedGradioDemo(
            max_history_turns=args.max_history_turns,
            fnctod_schema_path=args.fnctod_schema,
            pytod_apis_path=args.pytod_apis,
            schema_json_path=args.schema,
            genie_worksheet_path=args.genie_worksheet,
        )
        logger.info("✅ Demo实例创建成功")
    except Exception as e:
        logger.error(f"❌ Demo初始化失败: {e}")
        print(f"\n{'='*60}")
        print(f"❌ 错误: {e}")
        print(f"{'='*60}\n")
        raise
    
    # 创建UI（传入demo_instance以绑定事件）
    try:
        app, components = create_gradio_ui(demo_instance)
        logger.info("✅ UI创建成功")
    except Exception as e:
        logger.error(f"❌ UI创建失败: {e}", exc_info=True)
        print(f"\n{'='*60}")
        print(f"❌ UI创建错误: {e}")
        print(f"请检查是否安装了gradio包: pip install gradio")
        print(f"{'='*60}\n")
        raise
    
    # 启动应用（CSS和theme参数移到这里，兼容Gradio 6.0）
    logger.info(f"启动Gradio应用... (端口: {args.port}, 分享: {args.share})")
    app.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"程序启动失败: {e}", exc_info=True)
        print(f"\n{'='*60}")
        print(f"❌ 程序启动失败")
        print(f"错误信息: {e}")
        print(f"\n常见问题排查:")
        print(f"1. 检查是否安装gradio: pip install gradio")
        print(f"2. 检查是否配置.env文件")
        print(f"3. 检查日志文件获取详细信息")
        print(f"{'='*60}\n")
        raise
