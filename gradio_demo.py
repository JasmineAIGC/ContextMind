#!/usr/bin/env python3
"""
ContextMind 统一Gradio Web Demo

支持三个场景：chat（闲聊）、callcenter（客服）、insurance（保险）
支持两种模式：DST基础模式、ContextMind完整模式

使用方式:
    python gradio_demo.py
"""

import asyncio
import gradio as gr
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

# 设置日志
setup_logging()
logger = get_logger(__name__)


class UnifiedGradioDemo:
    """统一的Gradio Demo类"""
    
    def __init__(self):
        """初始化Demo（延迟模式）"""
        self.current_scenario = None
        self.current_mode = None
        self.llm_client = None
        self.config = None
        self.dst_tracker = None
        self.app = None
        self.initialized = False
    
    def initialize_scenario(self, scenario: str, mode: str):
        """初始化场景和模式"""
        self.current_scenario = scenario
        self.current_mode = mode
        
        # 加载配置
        if scenario == "chat":
            self.config = get_chat_scenario()
        elif scenario == "callcenter":
            self.config = get_callcenter_scenario()
        elif scenario == "insurance":
            self.config = get_insurance_scenario()
        
        # 根据模式初始化
        if mode == "DST基础模式":
            self._init_dst_mode()
        else:
            self._init_contextmind_mode()
        
        logger.info(f"已初始化: {scenario} - {mode}")
    
    def _init_dst_mode(self):
        """初始化DST模式"""
        # 创建LLM客户端（如果还没有）
        if self.llm_client is None:
            try:
                self.llm_client = SimpleLLMClient()
            except RuntimeError as e:
                logger.error(f"LLM客户端初始化失败: {e}")
                raise
        
        # 创建PromptManager
        pm = PromptManager(
            domain=self.config.name,
            enable_dynamic_slots=(self.current_scenario == "chat")
        )
        
        # 添加槽位
        for slot_name, slot_desc in self.config.dst_slots.items():
            pm.add_slot(slot_name, slot_desc)
        
        if self.config.dst_categorical_slots:
            for slot_name, categories in self.config.dst_categorical_slots.items():
                pm.add_categorical_slot(slot_name, categories)
        
        # 创建DST追踪器
        self.dst_tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            use_llm_summary=False,
            max_history_turns=10
        )
        
        self.app = None
    
    def _init_contextmind_mode(self):
        """初始化ContextMind模式"""
        # 创建LLM客户端（如果还没有）
        if self.llm_client is None:
            try:
                self.llm_client = SimpleLLMClient()
            except RuntimeError as e:
                logger.error(f"LLM客户端初始化失败: {e}")
                raise
        
        engine = ContextEngine(
            system_prompt=self.config.system_prompt,
            enable_memory=self.config.enable_memory,
            enable_evolution=self.config.enable_evolution
        )
        
        if self.current_scenario == "chat":
            self.app = ChatApplication(engine=engine)
        elif self.current_scenario == "callcenter":
            self.app = CallCenterApplication(engine=engine)
        elif self.current_scenario == "insurance":
            self.app = InsuranceApplication(engine=engine)
        
        self.dst_tracker = None
    
    async def chat(self, message: str, history: List[Tuple[str, str]]) -> Tuple[str, List[Tuple[str, str]]]:
        """处理对话"""
        try:
            # 首次使用时初始化
            if not self.initialized:
                self.initialize_scenario("chat", "ContextMind完整模式")
                self.initialized = True
            
            if not message or not message.strip():
                return "", history
            
            # 生成回复
            if self.current_mode == "DST基础模式":
                reply = await self._chat_dst_mode(message)
            else:
                reply = await self._chat_contextmind_mode(message)
            
            # 更新历史
            history.append((message, reply))
            return "", history
            
        except Exception as e:
            logger.error(f"处理失败: {e}", exc_info=True)
            error_msg = f"❌ 处理失败: {str(e)}"
            history.append((message, error_msg))
            return "", history
    
    async def _chat_dst_mode(self, user_message: str) -> str:
        """DST模式处理"""
        # 提取状态
        state = await self.dst_tracker.process_turn(
            agent_message="",
            user_message=user_message
        )
        
        # 生成回复
        messages = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": f"用户说：{user_message}\n当前状态：{state}\n请生成合适的回复。"}
        ]
        
        reply = await self.llm_client.chat_async(messages=messages)
        return reply
    
    async def _chat_contextmind_mode(self, user_message: str) -> str:
        """ContextMind模式处理"""
        result = await self.app.process_turn(user_input=user_message, debug=False)
        return result
    
    def get_state_display(self) -> str:
        """获取状态显示"""
        if self.current_mode != "DST基础模式":
            return "⚠️ 状态查看功能仅在DST模式下可用"
        
        if not self.dst_tracker:
            return "⚠️ DST追踪器未初始化"
        
        state = self.dst_tracker.get_current_state()
        
        if not state:
            return "📊 当前状态: 空"
        
        state_str = "📊 当前对话状态:\n\n"
        for key, value in state.items():
            state_str += f"**{key}**: {value}\n"
        
        return state_str
    
    def reset_conversation(self) -> Tuple[List, str]:
        """重置对话"""
        if self.current_mode == "DST基础模式" and self.dst_tracker:
            self.dst_tracker.reset_dialogue()
        else:
            # 重新初始化ContextMind模式
            self.initialize_scenario(self.current_scenario, self.current_mode)
        
        return [], "✅ 对话已重置"
    
    def change_scenario_or_mode(self, scenario: str, mode: str) -> Tuple[List, str]:
        """切换场景或模式"""
        if scenario != self.current_scenario or mode != self.current_mode:
            self.initialize_scenario(scenario, mode)
            self.initialized = True
            return [], f"✅ 已切换到: {scenario} - {mode}"
        return [], f"当前已是: {scenario} - {mode}"


# 创建全局Demo实例
demo_instance = UnifiedGradioDemo()


async def chat_wrapper(message, history):
    """Gradio聊天包装函数"""
    return await demo_instance.chat(message, history)


def get_state_wrapper():
    """获取状态包装函数"""
    return demo_instance.get_state_display()


def reset_wrapper():
    """重置对话包装函数"""
    return demo_instance.reset_conversation()


def change_scenario_wrapper(scenario, mode):
    """切换场景包装函数"""
    return demo_instance.change_scenario_or_mode(scenario, mode)


# 创建Gradio界面
with gr.Blocks(title="ContextMind 统一Demo v0.4.0", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🤖 ContextMind 统一对话系统 v0.4.0")
    gr.Markdown("支持三个场景（闲聊、客服、保险）和两种模式（DST、ContextMind）")
    
    with gr.Row():
        with gr.Column(scale=2):
            # 场景选择
            scenario_selector = gr.Radio(
                choices=["chat", "callcenter", "insurance"],
                value="chat",
                label="📋 选择场景",
                info="chat=闲聊 | callcenter=客服 | insurance=保险"
            )
            
            # 模式选择
            mode_selector = gr.Radio(
                choices=["ContextMind完整模式", "DST基础模式"],
                value="ContextMind完整模式",
                label="⚙️ 选择模式"
            )
            
            # 应用按钮
            apply_btn = gr.Button("🔄 应用设置", variant="primary")
            status_output = gr.Textbox(label="状态", interactive=False)
        
        with gr.Column(scale=3):
            # 聊天界面
            chatbot = gr.Chatbot(
                label="对话窗口",
                height=400,
                show_label=True
            )
            
            with gr.Row():
                msg_input = gr.Textbox(
                    label="输入消息",
                    placeholder="在这里输入您的消息...",
                    scale=4
                )
                send_btn = gr.Button("发送", variant="primary", scale=1)
            
            with gr.Row():
                reset_btn = gr.Button("🔄 重置对话")
                state_btn = gr.Button("📊 查看状态")
            
            state_display = gr.Markdown("", label="对话状态")
    
    # 使用提示
    with gr.Accordion("💡 使用提示", open=False):
        gr.Markdown("""
        ### 场景说明
        - **chat（闲聊）**: 日常闲聊对话，动态槽位提取
        - **callcenter（客服）**: 智能客服场景，问题追踪和解决
        - **insurance（保险）**: 共荣保险客服，癌症保险咨询
        
        ### 模式说明
        - **ContextMind完整模式**: 五层架构（感知、记忆、上下文、生成、进化）
        - **DST基础模式**: 对话状态追踪，基于预定义意图和槽位
        
        ### 使用步骤
        1. 选择场景和模式
        2. 点击"应用设置"
        3. 在输入框中输入消息
        4. 点击"发送"开始对话
        5. 可随时切换场景和模式
        """)
    
    # 事件绑定
    apply_btn.click(
        fn=change_scenario_wrapper,
        inputs=[scenario_selector, mode_selector],
        outputs=[chatbot, status_output]
    )
    
    msg_input.submit(
        fn=chat_wrapper,
        inputs=[msg_input, chatbot],
        outputs=[msg_input, chatbot]
    )
    
    send_btn.click(
        fn=chat_wrapper,
        inputs=[msg_input, chatbot],
        outputs=[msg_input, chatbot]
    )
    
    reset_btn.click(
        fn=reset_wrapper,
        outputs=[chatbot, status_output]
    )
    
    state_btn.click(
        fn=get_state_wrapper,
        outputs=state_display
    )


if __name__ == "__main__":
    logger.info("启动ContextMind统一Gradio Demo")
    app.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False
    )
