#!/usr/bin/env python3
"""
Evolve 统一交互式Demo

支持三个场景：chat（闲聊）、callcenter（客服）、insurance（保险）
支持两种模式：dst（对话状态追踪）、evolve（基于记忆进化）

使用方式:
    python interactive_demo.py --scenario chat --mode evolve
    python interactive_demo.py --scenario callcenter --mode dst
    python interactive_demo.py --scenario insurance --mode evolve --log-level DEBUG
"""

import asyncio
import argparse
import logging
import sys
from typing import Optional
from datetime import datetime
from pathlib import Path

from utils.llm_client import SimpleLLMClient
from dst import DialogueStateTracker, PromptManager
from evolve import EvolveEngine
from scenarios import get_chat_scenario, get_callcenter_scenario, get_insurance_scenario
from apps.chat_app import ChatApplication
from apps.callcenter_app import CallCenterApplication
from apps.insurance_app import InsuranceApplication
from utils.logger import get_logger, setup_logging, LogLevel

# 使用统一的logger from utils/logger.py
logger = get_logger(__name__)


class UnifiedInteractiveDemo:
    """统一的交互式Demo类"""
    
    def __init__(
        self, 
        scenario: str = "chat", 
        mode: str = "evolve",
        max_history_turns: int = 10,
        enable_summary: bool = True,
        use_llm_summary: bool = False
    ):
        """
        初始化Demo
        
        Args:
            scenario: 场景类型 (chat/callcenter/insurance)
            mode: 对话模式 (dst/evolve)
            max_history_turns: DST模式的最大历史轮数
            enable_summary: 是否启用历史摘要
            use_llm_summary: 是否使用LLM生成摘要
        """
        self.scenario = scenario
        self.mode = mode
        self.max_history_turns = max_history_turns
        self.enable_summary = enable_summary
        self.use_llm_summary = use_llm_summary
        self.config = self._load_scenario_config()
        
        # 延迟初始化LLM客户端（只在需要时创建）
        self.llm_client = None
        
        # 初始化对应模式
        if mode == "dst":
            self._init_dst_mode()
        else:
            self._init_evolve_mode()
    
    def _load_scenario_config(self):
        """加载场景配置"""
        if self.scenario == "chat":
            return get_chat_scenario()
        elif self.scenario == "callcenter":
            return get_callcenter_scenario()
        elif self.scenario == "insurance":
            return get_insurance_scenario()
        else:
            raise ValueError(f"未知场景: {self.scenario}")
    
    def _get_welcome_message(self) -> str:
        """获取欢迎消息"""
        return self.config.welcome_message if self.config.welcome_message else "你好！"
    
    def _init_dst_mode(self):
        """初始化DST模式"""
        logger.info(f"初始化DST模式 - {self.config.name}")
        
        # 创建LLM客户端（如果还未创建）
        if self.llm_client is None:
            try:
                self.llm_client = SimpleLLMClient()
            except (ValueError, RuntimeError) as e:
                logger.error(f"LLM客户端初始化失败: {e}")
                print(f"\n{'='*60}")
                print(f"❌ 错误: {e}")
                print(f"{'='*60}")
                
                # 根据错误类型提供具体帮助
                error_str = str(e)
                if "API key" in error_str or "API_KEY" in error_str:
                    print("\n📝 请配置.env文件，添加以下内容：")
                    print("=" * 60)
                    print("# 选择一个配置即可")
                    print("QWEN3_API_KEY=sk-your-api-key-here")
                    print("QWEN3_BASE_URL=http://your-api-endpoint/v1")
                    print("QWEN3_MODEL=Qwen3-32B")
                    print("=" * 60)
                    print("\n支持的环境变量名：")
                    print("  - QWEN3_API_KEY, QWEN3_BASE_URL, QWEN3_MODEL")
                    print("  - LLM_API_KEY, LLM_BASE_URL, LLM_MODEL")
                    print("  - OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL")
                elif "OpenAI" in error_str:
                    print("\n请安装OpenAI包：")
                    print("  pip install openai")
                print()
                sys.exit(1)
        
        # 创建PromptManager，使用自定义模板（如果提供）
        pm = PromptManager(
            domain=self.config.name,
            enable_dynamic_slots=self.config.enable_dynamic_slots,  # 使用场景配置
            custom_template=getattr(self.config, 'dst_prompt_template', None)  # 使用自定义模板
        )
        
        # 添加预定义槽位
        for slot_name, slot_desc in self.config.dst_slots.items():
            # 检查是否有分类约束
            categorical_values = None
            if self.config.dst_categorical_slots and slot_name in self.config.dst_categorical_slots:
                categorical_values = self.config.dst_categorical_slots[slot_name]
            pm.add_slot(slot_name, slot_desc, categorical_values=categorical_values)
        
        # 创建DST追踪器
        self.dst_tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            use_llm_summary=self.use_llm_summary,  # 使用参数配置
            max_history_turns=self.max_history_turns,  # 使用参数配置
            enable_history_summary=self.enable_summary  # 使用参数配置
        )
        
        # 初始化系统回复（第一轮对话使用）- 使用欢迎消息
        self.last_system_reply = self._get_welcome_message()
        
        self.app = None  # DST模式不使用app
    
    def _init_evolve_mode(self):
        """初始化Evolve模式"""
        logger.info(f"初始化Evolve模式 - {self.config.name}")
        
        # 创建LLM客户端（如果还未创建）
        if self.llm_client is None:
            try:
                self.llm_client = SimpleLLMClient()
            except (ValueError, RuntimeError) as e:
                logger.error(f"LLM客户端初始化失败: {e}")
                print(f"\n{'='*60}")
                print(f"❌ 错误: {e}")
                print(f"{'='*60}")
                
                # 根据错误类型提供具体帮助
                error_str = str(e)
                if "API key" in error_str or "API_KEY" in error_str:
                    print("\n📝 请配置.env文件，添加以下内容：")
                    print("=" * 60)
                    print("# 选择一个配置即可")
                    print("QWEN3_API_KEY=sk-your-api-key-here")
                    print("QWEN3_BASE_URL=http://your-api-endpoint/v1")
                    print("QWEN3_MODEL=Qwen3-32B")
                    print("=" * 60)
                    print("\n支持的环境变量名：")
                    print("  - QWEN3_API_KEY, QWEN3_BASE_URL, QWEN3_MODEL")
                    print("  - LLM_API_KEY, LLM_BASE_URL, LLM_MODEL")
                    print("  - OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL")
                elif "OpenAI" in error_str:
                    print("\n请安装OpenAI包：")
                    print("  pip install openai")
                print()
                sys.exit(1)
        
        # 创建引擎和应用
        try:
            engine = EvolveEngine(
                app_name=f"interactive_demo_{self.scenario}",
                user_id="demo_user",
                llm_client=self.llm_client
            )
            
            # 创建对应的应用
            if self.scenario == "chat":
                self.app = ChatApplication(context_engine=engine, system_prompt=self.config.system_prompt)
            elif self.scenario == "callcenter":
                self.app = CallCenterApplication(context_engine=engine, system_prompt=self.config.system_prompt)
            elif self.scenario == "insurance":
                self.app = InsuranceApplication(context_engine=engine, system_prompt=self.config.system_prompt)
        except Exception as e:
            logger.error(f"引擎或应用初始化失败: {e}", exc_info=True)
            print(f"\n{'='*60}")
            print(f"❌ 错误: 引擎或应用初始化失败")
            print(f"详细信息: {e}")
            print(f"{'='*60}\n")
            sys.exit(1)
        
        self.dst_tracker = None  # Evolve模式不使用DST
    
    def print_welcome(self):
        """打印欢迎信息"""
        print("\n" + "="*60)
        print(f"📱 Evolve 统一交互式Demo v0.4.0")
        print("="*60)
        print(f"场景: {self.config.name}")
        print(f"模式: {'DST (对话状态追踪)' if self.mode == 'dst' else 'Evolve (基于记忆进化)'}")
        print(f"日志级别: {logging.getLevelName(logger.level)}")
        print(f"最大历史轮数: {self.max_history_turns}")
        print("="*60)
        
        if self.mode == "dst":
            print(f"✓ 已加载 {len(self.config.dst_slots)} 个槽位")
            if self.config.dst_intents:
                print(f"✓ 已加载 {len(self.config.dst_intents)} 个意图类别")
            print(f"✓ 历史摘要: {'启用' if self.enable_summary else '禁用'}")
            print(f"✓ 摘要方式: {'LLM生成' if self.use_llm_summary else '模板生成'}")
        else:
            print("✓ 五层架构: 感知层、记忆层、上下文层、生成层、进化层")
            print(f"✓ 记忆功能: {'启用' if self.config.enable_memory else '禁用'}")
            print(f"✓ 进化学习: {'启用' if self.config.enable_evolution else '禁用'}")
        
        print("\n💡 使用提示:")
        print("  - 输入 /quit 或 /exit 退出程序")
        print("  - 输入 /reset 重置对话")
        if self.mode == "dst":
            print("  - 输入 /state 查看当前对话状态")
        print("="*60 + "\n")
    
    async def chat_dst_mode(self, user_message: str) -> str:
        """DST模式对话"""
        try:
            # 处理对话轮次 - 使用上一轮的系统回复
            state = await self.dst_tracker.process_turn(
                system_utterance=self.last_system_reply,
                user_utterance=user_message
            )
            
            # 构建回复prompt
            messages = [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": f"用户说：{user_message}\n当前状态：{state}\n请生成合适的回复。"}
            ]
            
            # 生成回复
            reply = await self.llm_client.chat_async(messages=messages)
            
            # 保存这轮的系统回复，供下一轮使用
            self.last_system_reply = reply
            
            return reply
            
        except Exception as e:
            logger.error(f"DST模式处理失败: {e}")
            return f"抱歉，处理您的消息时出现了问题：{str(e)}"
    
    async def chat_evolve_mode(self, user_message: str) -> str:
        """Evolve模式对话"""
        try:
            result = await self.app.process_turn(user_input=user_message, debug=False)
            return result
        except Exception as e:
            logger.error(f"Evolve模式处理失败: {e}")
            return f"抱歉，处理您的消息时出现了问题：{str(e)}"
    
    async def chat(self, user_message: str) -> str:
        """统一的对话接口"""
        if self.mode == "dst":
            return await self.chat_dst_mode(user_message)
        else:
            return await self.chat_evolve_mode(user_message)
    
    def show_state(self):
        """显示当前状态（仅DST模式）"""
        if self.mode != "dst":
            print("⚠️  状态查看功能仅在DST模式下可用")
            return
        
        state = self.dst_tracker.get_current_state()
        print("\n" + "="*60)
        print("📊 当前对话状态:")
        print("="*60)
        for key, value in state.items():
            print(f"  {key}: {value}")
        print("="*60 + "\n")
    
    def reset(self):
        """重置对话"""
        if self.mode == "dst":
            self.dst_tracker.reset_dialogue()
        else:
            # Evolve模式重新初始化
            self._init_evolve_mode()
        print("✓ 对话已重置\n")
        
        # 重置后，机器人主动发起对话
        welcome_msg = self._get_welcome_message()
        print(f"\n助手: {welcome_msg}\n")
        print("-" * 60 + "\n")
    
    async def run(self):
        """运行交互循环"""
        self.print_welcome()
        
        # 机器人主动发起对话 - 显示欢迎消息
        welcome_msg = self._get_welcome_message()
        print(f"\n助手: {welcome_msg}\n")
        print("-" * 60 + "\n")
        
        turn = 0
        while True:
            try:
                # 获取用户输入
                user_input = input("你: ").strip()
                
                if not user_input:
                    continue
                
                # 处理特殊命令
                if user_input.lower() in ['/quit', '/exit']:
                    print("\n👋 再见！")
                    break
                elif user_input.lower() == '/reset':
                    self.reset()
                    turn = 0
                    continue
                elif user_input.lower() == '/state':
                    self.show_state()
                    continue
                
                # 处理正常对话
                turn += 1
                print(f"\n[轮次 {turn}] 处理中...")
                
                reply = await self.chat(user_input)
                print(f"\n助手: {reply}\n")
                print("-" * 60 + "\n")
                
            except KeyboardInterrupt:
                print("\n\n👋 检测到中断信号，退出程序")
                break
            except Exception as e:
                logger.error(f"处理错误: {e}", exc_info=True)
                print(f"\n❌ 错误: {str(e)}\n")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Evolve 统一交互式Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python interactive_demo.py --scenario chat --mode evolve
  python interactive_demo.py --scenario callcenter --mode dst
  python interactive_demo.py --scenario insurance --mode evolve --log-level DEBUG
  python interactive_demo.py --scenario insurance --mode dst --max-history-turns 20
        """
    )
    
    parser.add_argument(
        '--scenario',
        choices=['chat', 'callcenter', 'insurance'],
        default='chat',
        help='选择场景: chat(闲聊) / callcenter(客服) / insurance(保险)'
    )
    
    parser.add_argument(
        '--mode',
        choices=['dst', 'evolve'],
        default='evolve',
        help='选择模式: dst(对话状态追踪) / evolve(基于记忆进化)'
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
        metavar='N',
        help='DST模式的最大历史轮数 (默认: 10)'
    )
    
    parser.add_argument(
        '--enable-summary',
        dest='enable_summary',
        action='store_true',
        default=True,
        help='启用历史摘要 (默认: 启用)'
    )
    
    parser.add_argument(
        '--no-summary',
        dest='enable_summary',
        action='store_false',
        help='禁用历史摘要'
    )
    
    parser.add_argument(
        '--use-llm-summary',
        action='store_true',
        default=False,
        help='使用LLM生成摘要而非模板 (默认: False, 使用模板更快)'
    )
    
    return parser.parse_args()


async def main():
    """主函数"""
    args = parse_args()
    
    # 使用setup_logging配置日志系统
    log_level = LogLevel.DEBUG if args.log_level == "DEBUG" else LogLevel.INFO
    setup_logging(level=log_level, save_to_file=True, log_dir="logs")
    
    # 显示配置信息
    logger.info(f"启动参数: scenario={args.scenario}, mode={args.mode}, log_level={args.log_level}, max_history_turns={args.max_history_turns}")
    
    demo = UnifiedInteractiveDemo(
        scenario=args.scenario,
        mode=args.mode,
        max_history_turns=args.max_history_turns,
        enable_summary=args.enable_summary,
        use_llm_summary=args.use_llm_summary
    )
    
    await demo.run()


if __name__ == "__main__":
    asyncio.run(main())
