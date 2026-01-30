#!/usr/bin/env python3
"""
ContextMind 统一Gradio Web Demo

支持三个场景：chat（闲聊）、callcenter（客服）、insurance（保险）
支持两种模式：DST基础模式、ContextMind完整模式

使用方式:
    python gradio_demo.py
    python gradio_demo.py --log-level DEBUG --port 8080
    python gradio_demo.py --max-history-turns 20 --share
"""

import argparse
import asyncio
import logging
from typing import List, Tuple, Optional
from datetime import datetime

from utils.logger import get_logger, setup_logging
from utils.llm_client import SimpleLLMClient
from dst import DialogueStateTracker, PromptManager
from contextmind import ContextEngine
from scenarios import get_chat_scenario, get_callcenter_scenario, get_insurance_scenario
from apps.chat_app import ChatApplication
from apps.callcenter_app import CallCenterApplication
from apps.insurance_app import InsuranceApplication
from ui_components import create_gradio_ui, CUSTOM_CSS

# 初始设置日志（稍后会根据参数调整）
setup_logging()
logger = get_logger(__name__)


class UnifiedGradioDemo:
    """统一的Gradio Demo类"""
    
    def __init__(self, max_history_turns: int = 10):
        """
        初始化Demo
        
        Args:
            max_history_turns: DST模式的最大历史轮数
        """
        self.current_scenario = None
        self.current_mode = None
        self.config = None
        self.llm_client = None
        self.tracker = None
        self.max_history_turns = max_history_turns
        self.app = None
        self.initialized = False
        self.history = []
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
        else:
            raise ValueError(f"未知场景: {scenario}")
        
        # 根据模式初始化
        if mode == "dst":
            self._init_dst_mode()
        else:
            self._init_contextmind_mode()
        
        logger.info(f"✅ 场景初始化完成: {scenario}, 模式: {mode}")
    
    def _init_dst_mode(self):
        """初始化DST模式"""
        try:
            if self.llm_client is None:
                self.llm_client = SimpleLLMClient()
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
        
        # 创建PromptManager
        pm = PromptManager(domain=self.config.name)
        
        # 添加预定义槽位
        for slot_name, slot_desc in self.config.dst_slots.items():
            pm.add_slot(slot_name, slot_desc)
        
        # 创建DialogueStateTracker
        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=10,
            enable_history_summary=True,
            use_llm_summary=False
        )
        
        logger.info("DST模式初始化完成")
    
    def _init_contextmind_mode(self):
        """初始化ContextMind模式"""
        try:
            if self.llm_client is None:
                self.llm_client = SimpleLLMClient()
                logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            error_msg = f"❌ LLM客户端初始化失败: {str(e)}\n\n"
            if "API" in str(e).upper() or "KEY" in str(e).upper():
                error_msg += "📝 请检查.env配置文件\n"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # 创建ContextEngine
        engine = ContextEngine(
            llm_client=self.llm_client,
            system_prompt=self.config.system_prompt,
            enable_memory=self.config.enable_memory,
            enable_evolution=self.config.enable_evolution
        )
        
        # 创建对应的Application
        if self.current_scenario == "chat":
            self.app = ChatApplication(engine)
        elif self.current_scenario == "callcenter":
            self.app = CallCenterApplication(engine)
        elif self.current_scenario == "insurance":
            self.app = InsuranceApplication(engine)
        
        logger.info("ContextMind模式初始化完成")
    
    async def chat(self, message: str, history: List) -> List:
        """处理对话"""
        try:
            # 首次使用时初始化
            if not self.initialized:
                self.initialize_scenario("chat", "contextmind")
                self.initialized = True
            
            if not message or not message.strip():
                return history
            
            # 处理对话
            if self.current_mode == "dst":
                # DST模式
                state = await self.tracker.process_turn(
                    agent_message=history[-1][1] if history else "你好！",
                    user_message=message
                )
                
                # 生成回复
                system_prompt = self.config.system_prompt
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ]
                
                response = await self.llm_client.chat_async(messages=messages)
                reply = response.get("content", "抱歉，我没有理解您的意思。")
                
            else:
                # ContextMind模式
                result = await self.app.process_turn(message)
                reply = result.get("reply", "抱歉，处理出错了。")
            
            # 更新历史
            return history + [[message, reply]]
            
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
                return history + [[message, error_msg]]
            else:
                return history + [[message, f"❌ 错误: {str(e)}"]]
        except Exception as e:
            logger.error(f"对话处理错误: {e}", exc_info=True)
            return history + [[message, f"❌ 系统错误: {str(e)}"]]
    
    def get_state(self) -> dict:
        """获取当前状态"""
        if self.current_mode == "dst" and self.tracker:
            return {
                "模式": "DST",
                "场景": self.current_scenario,
                "当前状态": self.tracker.current_state,
                "对话轮数": len(self.tracker.dialogue_history)
            }
        elif self.current_mode == "contextmind" and self.app:
            return {
                "模式": "ContextMind",
                "场景": self.current_scenario,
                "状态": "运行中"
            }
        else:
            return {"状态": "未初始化"}
    
    def reset_conversation(self):
        """重置对话"""
        if self.current_mode == "dst" and self.tracker:
            self.tracker.current_state = {}
            self.tracker.dialogue_history = []
        elif self.current_mode == "contextmind" and self.app:
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
            "insurance": "保险咨询"
        }
        
        status = f"📌 当前配置: 场景={scenario_names.get(scenario, scenario)}, 模式={mode}"
        logger.info(f"配置已更新: {scenario}, {mode}")
        return [], status


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="ContextMind Gradio Web Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python gradio_demo.py
  python gradio_demo.py --log-level DEBUG
  python gradio_demo.py --port 8080 --share
  python gradio_demo.py --max-history-turns 20 --log-level INFO
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
        help='DST模式的最大历史轮数 (默认: 10)'
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
    
    return parser.parse_args()


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    # 设置日志级别
    logger.setLevel(getattr(logging, args.log_level))
    
    logger.info("[__main__] 启动ContextMind统一Gradio Demo")
    logger.info(f"参数配置: 日志级别={args.log_level}, 最大历史轮数={args.max_history_turns}, 端口={args.port}, 分享={args.share}")
    
    # 创建Demo实例
    try:
        demo_instance = UnifiedGradioDemo(max_history_turns=args.max_history_turns)
        logger.info("✅ Demo实例创建成功")
    except Exception as e:
        logger.error(f"❌ Demo初始化失败: {e}")
        print(f"\n{'='*60}")
        print(f"❌ 错误: {e}")
        print(f"{'='*60}\n")
        raise
    
    # 创建UI
    try:
        app, components = create_gradio_ui()
        logger.info("✅ UI创建成功")
    except Exception as e:
        logger.error(f"❌ UI创建失败: {e}", exc_info=True)
        print(f"\n{'='*60}")
        print(f"❌ UI创建错误: {e}")
        print(f"请检查是否安装了gradio包: pip install gradio")
        print(f"{'='*60}\n")
        raise
    
    # 绑定事件
    # 发送消息
    components["send_btn"].click(
        fn=demo_instance.chat,
        inputs=[components["msg"], components["chatbot"]],
        outputs=[components["chatbot"]]
    ).then(
        fn=lambda: "",
        outputs=[components["msg"]]
    )
    
    components["msg"].submit(
        fn=demo_instance.chat,
        inputs=[components["msg"], components["chatbot"]],
        outputs=[components["chatbot"]]
    ).then(
        fn=lambda: "",
        outputs=[components["msg"]]
    )
    
    # 查看状态
    components["view_state_btn"].click(
        fn=demo_instance.get_state,
        outputs=[components["state_display"]]
    )
    
    # 重置对话
    components["reset_btn"].click(
        fn=demo_instance.reset_conversation,
        outputs=[components["chatbot"]]
    )
    
    # 清空历史
    components["clear_btn"].click(
        fn=lambda: [],
        outputs=[components["chatbot"]]
    )
    
    # 应用配置
    components["apply_btn"].click(
        fn=demo_instance.change_scenario_or_mode,
        inputs=[components["scenario_selector"], components["mode_selector"]],
        outputs=[components["chatbot"], components["config_status"]]
    )
    
    # 启动应用（CSS参数移到这里，兼容Gradio 6.0）
    # 启动应用
    logger.info(f"启动Gradio应用... (端口: {args.port}, 分享: {args.share})")
    app.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share,
        css=CUSTOM_CSS
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
