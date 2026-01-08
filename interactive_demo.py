#!/usr/bin/env python3
"""
交互式对话演示 - 机器人主动发起对话，同时展示三种上下文方式的回复对比
"""

import asyncio
import os
import sys
import random
import time
from pathlib import Path

# 将项目根目录添加到 Python 搜索路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 自动加载 .env 文件
from dotenv import load_dotenv
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)

from contextmind import Client, ContextEngine
from contextmind.logger import setup_logging, get_logger, INFO
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService

# 设置日志
setup_logging(level=INFO, log_to_console=True)
logger = get_logger(__name__)


class InteractiveDemo:
    """交互式对话演示类"""
    
    # Box 格式化常量
    # 注意：这些常量假设使用等宽ASCII字符。Unicode字符（表情符号、中日韩文字）
    # 可能因显示宽度不同而导致轻微的视觉对齐偏差。
    BOX_BORDER_WIDTH = 78  # 盒子边框的总宽度（包括边框字符）
    BOX_CONTENT_WIDTH = 62  # 用户输入内容区域的宽度（不包括前缀/后缀）
    BOX_TITLE_WIDTH = 74    # 引擎盒子标题区域的宽度（不包括 ┌─ 和 ─┐）
    USER_INPUT_MAX_DISPLAY_LENGTH = 60  # 截断前显示的最大字符数
    
    def __init__(self):
        self.engines = {}
        self.client = None
        self.opening_scripts = []
        self.turn_counter = 0  # 添加轮次计数器
        
    def load_opening_scripts(self):
        """加载开场话术"""
        script_file = project_root / "opening_scripts.txt"
        try:
            with open(script_file, 'r', encoding='utf-8') as f:
                self.opening_scripts = [line.strip() for line in f if line.strip()]
            logger.info(f"加载了 {len(self.opening_scripts)} 个开场话术")
        except FileNotFoundError:
            logger.warning(f"开场话术文件不存在: {script_file}")
            # 使用默认话术
            self.opening_scripts = [
                "您好，请问是胡女士本人吗？耽误您一分钟，有项业务想跟您同步。"
            ]
        except Exception as e:
            logger.error(f"加载开场话术失败: {e}")
            self.opening_scripts = [
                "您好，请问是胡女士本人吗？耽误您一分钟，有项业务想跟您同步。"
            ]
    
    async def initialize(self):
        """初始化三个引擎"""
        logger.info("=" * 80)
        logger.info("🚀 [CLI] 开始初始化所有引擎...")
        logger.info("=" * 80)
        
        self.load_opening_scripts()
        
        try:
            # 创建一个共享的、无状态的客户端实例
            client = Client()

            self.engines['basic'] = self._create_engine('basic', client)
            self.engines['short_term'] = self._create_engine('short_term', client)
            self.engines['long_term'] = self._create_engine('long_term', client)
            await self._seed_long_term_memory()

            logger.info("✅ [CLI] 引擎初始化并植入记忆种子成功")
            return True
            
        except Exception as e:
            logger.error(f"[CLI] 引擎初始化失败: {e}")
            return False

    def _create_engine(self, engine_type: str, client: Client) -> ContextEngine:
        """根据类型创建并配置ContextEngine"""
        
        base_prompt = self._get_base_prompt()
        user_profile = self._get_user_profile()
        business_rules = self._get_business_rules()

        if engine_type == 'basic':
            engine = ContextEngine(
                app_name="callcenter-basic",
                user_id="interactive-basic",
                llm_client=client,
                max_recent_events=6,
                base_system_prompt=base_prompt,
            )
        elif engine_type == 'short_term':
            engine = ContextEngine(
                app_name="callcenter-short-term",
                user_id="interactive-short-term",
                llm_client=client,
                max_recent_events=6,
                base_system_prompt=base_prompt,
                user_profile=user_profile,
                business_rules=business_rules,
            )
        elif engine_type == 'long_term':
            engine = ContextEngine(
                app_name="callcenter-long-term",
                user_id="interactive-long-term",
                llm_client=client,
                max_recent_events=50,
                base_system_prompt=base_prompt,
                user_profile=user_profile,
                business_rules=business_rules,
                memory_service=InMemoryMemoryService(),
            )
        else:
            raise ValueError(f"Unknown engine type: {engine_type}")
            
        engine._engine_type = engine_type.upper()
        logger.info(f"🔧 [CLI] 已创建引擎: {engine_type.upper()}")
        return engine

    async def _seed_long_term_memory(self):
        """为长期记忆引擎植入种子数据。"""
        if 'long_term' in self.engines:
            # 尝试从文件加载记忆种子
            seed_file = project_root / "data" / "memory_seeds.txt"
            memory_seeds = []
            
            try:
                with open(seed_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # 跳过空行和注释
                        if line and not line.startswith('#'):
                            memory_seeds.append(line)
                logger.info(f"从 {seed_file} 加载了 {len(memory_seeds)} 条记忆种子")
            except FileNotFoundError:
                logger.warning(f"记忆种子文件不存在: {seed_file}，使用默认种子")
                # 回退到硬编码种子
                memory_seeds = [
                    "用户多次要求停止推销并威胁报警。",
                    "用户对重复来电极度反感，情绪长期处于愤怒状态。",
                    "所有客服在再次联系该用户时必须立即道歉并承诺不再打扰。",
                    "若用户强调'别烦我'或提及报警，需第一时间结束对话并致歉。",
                ]
            except Exception as e:
                logger.error(f"加载记忆种子失败: {e}，使用默认种子")
                memory_seeds = [
                    "用户多次要求停止推销并威胁报警。",
                    "用户对重复来电极度反感，情绪长期处于愤怒状态。",
                    "所有客服在再次联系该用户时必须立即道歉并承诺不再打扰。",
                    "若用户强调'别烦我'或提及报警，需第一时间结束对话并致歉。",
                ]
            
            await self.engines['long_term'].seed_memory(memory_seeds)

    def _get_base_prompt(self) -> str:
        """获取基础系统提示词 - 仅包含核心角色定义"""
        return """你是优逸花客服，负责电话外呼。你的回复必须专业、简洁、直接，严格遵守客服话术规范。"""

    def _get_user_profile(self) -> dict:
        """获取用户画像"""
        return {
            "姓名": "胡女士",
            "年龄": "35-45岁",
            "性别": "女", 
            "历史行为": "多次拒绝推销，对电话推销敏感",
            "风险等级": "高"
        }

    def _get_business_rules(self) -> dict:
        """获取业务规则"""
        return {
            "合规要求": "必须立即停止当用户要求",
            "质量标准": "回复必须礼貌",
            "核心职责": "专业、礼貌地介绍优逸花预留额度服务",
            "沟通策略": "根据用户反馈调整沟通策略，遇到拒绝时礼貌结束对话",
            "回复要求": "严格按照客服身份直接回复，不要使用任何格式标记"
        }
    
    async def chat_loop(self):
        """主对话循环"""
        logger.info("="*80)
        logger.info("交互式对话演示 - 机器人主动发起对话")
        logger.info("="*80)
        logger.info("三种方式说明：")
        logger.info("1. 无上下文：只记录最近3轮对话，不使用其他知识")
        logger.info("2. 短期记忆：最近3轮对话 + 用户画像 + 业务规则")
        logger.info("3. 长期记忆：所有对话历史 + 用户画像 + 业务规则 + 记忆服务")
        logger.info("="*80)
        
        # 开始第一轮对话
        await self._start_new_conversation()
        
        while True:
            try:
                # 使用更稳定的输入方式，避免终端光标问题
                import sys
                logger.info("用户: " + user_input)
                user_input = sys.stdin.readline().strip()
                
                if not user_input:  # 处理空输入
                    continue
                
                if user_input.lower() in ['quit', 'exit', '退出']:
                    logger.info("感谢使用交互式对话演示！")
                    break
                
                if user_input.lower() in ['help', '帮助']:
                    self._show_help()
                    continue
                
                if user_input.lower() in ['new', 'newchat', '新对话']:
                    await self._start_new_conversation()
                    continue
                
                # 处理用户输入
                await self._process_user_input(user_input)
                
            except KeyboardInterrupt:
                logger.info("\n程序被用户中断，退出...")
                break
            except Exception as e:
                logger.error(f"[CLI] 处理出错: {e}")
                continue
    
    async def _start_new_conversation(self):
        """开始新对话，机器人主动发起"""
        # 重置轮次计数器
        self.turn_counter = 0
        
        logger.info("🔄 [CLI] 开始新一轮对话，重置所有引擎状态...")
        if not await self.initialize():
            logger.error("[CLI] 无法开始新对话，引擎初始化失败。")
            return

        # 随机选择开场话术
        opening_script = random.choice(self.opening_scripts)
        
        logger.info("\n" + "="*80)
        logger.info("🤖 机器人发起新对话")
        logger.info("="*80)
        logger.info(f"机器人: {opening_script}")
        
        # 将开场话术添加到所有引擎的session中
        for engine_name, engine in self.engines.items():
            from google.adk.events.event import Event
            from google.genai.types import Content, Part
            
            await engine._ensure_session()
            event = Event(
                invocation_id=engine.new_invocation_id(),
                author="assistant",
                content=Content(role="assistant", parts=[Part(text=opening_script)]),
            )
            session = await engine.get_current_session()
            await engine.session_service.append_event(session=session, event=event)
    
    async def _process_user_input(self, user_input):
        """处理用户输入，获取三种回复"""
        import time
        from datetime import datetime
        start_time = time.time()
        
        # 增加轮次计数器
        self.turn_counter += 1
        
        # 打印用户输入顶部边框
        logger.info("╔" + "═" * self.BOX_BORDER_WIDTH + "╗")
        # 显示完整用户输入
        user_input_display = user_input
        # 动态计算填充空格，确保对齐，防止负数
        padding = max(0, self.BOX_CONTENT_WIDTH - len(user_input_display))
        logger.info(f"║  👤 用户输入: {user_input_display}{' ' * padding} ║")
        # 动态计算时间行的填充空格，防止负数
        time_str = f"║  📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 🔄 第{self.turn_counter}轮对话"
        time_padding = max(0, self.BOX_BORDER_WIDTH - len(time_str) - 1)  # -1 for closing ║
        logger.info(time_str + ' ' * time_padding + "║")
        logger.info("╚" + "═" * self.BOX_BORDER_WIDTH + "╝")
        logger.info("")  # 空行
        
        # 立即刷新输出，确保显示及时
        import sys
        sys.stdout.flush()
        
        results = {}
        
        # 使用 asyncio.gather 并发执行，获取 ContextTurnResult
        tasks = {
            name: self._get_engine_response(name, engine, user_input)
            for name, engine in self.engines.items()
        }
        
        responses = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        for name, response in zip(tasks.keys(), responses):
            if isinstance(response, Exception):
                results[name] = f"错误: {response}"
                logger.error(f"[CLI] 引擎 {name} 处理失败: {response}")
            else:
                results[name] = response

        # 显示结果对比（使用新的 box 格式）
        self._display_comparison_with_boxes(results)
        
        # 打印总结
        total_time = time.time() - start_time
        logger.info(f"✅ 所有引擎处理完成 (耗时: {total_time:.1f}s)")
        logger.info("")  # 空行
    
    async def _get_engine_response(self, name, engine, user_input):
        """获取单个引擎的回复，返回完整的 ContextTurnResult"""
        try:
            result = await engine.process_turn(user_input)
            return result  # 返回完整的结果对象，包含元数据
        except Exception as e:
            logger.error(f"[CLI] 引擎 {name} 处理失败: {e}")
            raise
    
    def _log_engine_box(self, engine_name: str, result, is_debug: bool = False):
        """打印单个引擎的 box 边框日志"""
        symbols = {'basic': '🔵', 'short_term': '🟡', 'long_term': '🟢'}
        symbol = symbols.get(engine_name, '📝')
        
        # 顶部边框
        title = f"{symbol} {engine_name.upper().replace('_', ' ')} 引擎"
        if is_debug:
            title += " [详细]"
        # 确保边框宽度计算不会产生负数
        title_padding = max(0, self.BOX_TITLE_WIDTH - len(title))
        logger.info("┌─ " + title + " " + "─" * title_padding + "┐")
        
        # 简洁模式内容
        logger.info("│ ⚙️  处理中...")
        
        context_parts = [f"💭 历史: {result.history_count}条对话"]
        if result.profile_summary:
            context_parts.append(f"👤 画像: {result.profile_summary}")
        if result.rules_count > 0:
            context_parts.append(f"📋 规则: {result.rules_count}条")
        if result.memory_count > 0:
            context_parts.append(f"🧠 记忆: {result.memory_count}条")
        
        logger.info("│ " + " | ".join(context_parts))
        
        # DEBUG 模式额外信息
        if is_debug:
            logger.debug("│ ")
            logger.debug(f"│ 📝 Prompt摘要 ({len(result.prompt)}字符):")
            # 提取 prompt 的前几行作为摘要
            prompt_lines = result.prompt.split('\n')[:3]
            for line in prompt_lines:
                if line.strip():
                    logger.debug(f"│   ├─ {line}")
            logger.debug("│ ")
            logger.debug(f"│ ⏱️  耗时: {result.processing_time:.1f}s")
        
        # 回复内容 - 显示完整回复
        logger.info(f"│ 🤖 回复: {result.response}")
        
        # 底部边框 - 使用常量保持一致性
        logger.info("└" + "─" * (self.BOX_BORDER_WIDTH - 1) + "┘")
        logger.info("")  # 空行
    
    def _display_comparison_with_boxes(self, results):
        """使用 box 格式显示三种回复的对比"""
        from contextmind.logger import ContextMindLogger
        import logging
        
        # 检查是否为 DEBUG 模式
        is_debug = ContextMindLogger.get_current_level() <= logging.DEBUG
        
        # 按顺序显示三种回复
        engine_order = ['basic', 'short_term', 'long_term']
        
        for engine_name in engine_order:
            if engine_name in results:
                result = results[engine_name]
                # 如果是错误字符串，跳过 box 格式
                if isinstance(result, str) and result.startswith("错误:"):
                    logger.error(f"❌ {engine_name.upper()} 引擎: {result}")
                else:
                    # 使用 box 格式化显示
                    self._log_engine_box(engine_name, result, is_debug)
    
    def _display_comparison(self, user_input, results):
        """显示三种回复的对比（旧版本，保留兼容性）"""
        logger.info(f"📝 用户输入: {user_input}")
        
        # 按顺序显示三种回复
        displays = {
            'basic': '🔵 基础对话',
            'short_term': '🟡 短期记忆', 
            'long_term': '🟢 长期记忆'
        }
        engine_order = ['basic', 'short_term', 'long_term']
        
        for engine_name in engine_order:
            if engine_name in results:
                display_name = displays[engine_name]
                response = results[engine_name]
                logger.info(f"{display_name}: {response}")
        
        logger.info("\n" + "="*80)
    
    def _show_help(self):
        """显示帮助信息"""
        logger.info("\n" + "="*60)
        logger.info("帮助信息")
        logger.info("="*60)
        logger.info("\n上下文类型说明:")
        logger.info("  🔵 基础对话: 只记录最近3轮对话，不使用其他知识")
        logger.info("  🟡 短期记忆: 最近3轮对话 + 其他知识")
        logger.info("  🟢 长期记忆: 所有轮对话 + 其他知识 + 定期总结")
        logger.info("="*60)

async def main():
    """主函数"""
    demo = InteractiveDemo()
    
    # 初始化
    if not await demo.initialize():
        logger.error("初始化失败，程序退出")
        return
    
    # 开始对话循环
    await demo.chat_loop()


if __name__ == "__main__":
    asyncio.run(main())
