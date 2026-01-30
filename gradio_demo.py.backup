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

# 自定义CSS样式
CUSTOM_CSS = """
/* 全局样式优化 */
.gradio-container {
    font-family: 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif !important;
    max-width: 1200px !important;
    margin: 0 auto !important;
}

/* 美化标题 */
.main-title {
    text-align: center !important;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
    font-size: 2.2em !important;
    font-weight: 700 !important;
    margin-bottom: 0.3em !important;
}

/* 配置区域美化 */
.config-section {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%) !important;
    padding: 20px !important;
    border-radius: 15px !important;
    margin: 15px 0 !important;
    box-shadow: 0 4px 15px rgba(0,0,0,0.08) !important;
}

/* 输入框美化 */
textarea {
    border-radius: 10px !important;
    border: 2px solid #e1e8ed !important;
    font-size: 15px !important;
    padding: 12px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

textarea:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.15) !important;
    transform: translateY(-1px) !important;
}

/* 主按钮美化 */
.primary-button button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    padding: 12px 28px !important;
    font-size: 15px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.35) !important;
}

.primary-button button:hover {
    transform: translateY(-3px) !important;
    box-shadow: 0 8px 20px rgba(102, 126, 234, 0.45) !important;
}

.primary-button button:active {
    transform: translateY(-1px) !important;
}

/* 次要按钮美化 */
.secondary-button button {
    background: white !important;
    border: 2px solid #667eea !important;
    color: #667eea !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    padding: 10px 24px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.secondary-button button:hover {
    background: #667eea !important;
    color: white !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3) !important;
}

/* 对话框美化 */
.chatbot {
    border-radius: 15px !important;
    border: 2px solid #e1e8ed !important;
    box-shadow: 0 8px 25px rgba(0,0,0,0.1) !important;
    background: white !important;
}

/* 消息气泡样式 */
.message {
    border-radius: 12px !important;
    padding: 12px 16px !important;
    margin: 8px 0 !important;
}

.message.user {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
}

.message.bot {
    background: #f5f7fa !important;
    border: 1px solid #e1e8ed !important;
}

/* Radio按钮组美化 */
.radio-group label {
    padding: 10px 20px !important;
    border-radius: 10px !important;
    border: 2px solid #e1e8ed !important;
    margin: 5px !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
}

.radio-group label:hover {
    border-color: #667eea !important;
    background: #f5f7fa !important;
}

.radio-group input:checked + label {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    border-color: transparent !important;
}

/* 下拉框美化 */
select, .dropdown {
    border-radius: 10px !important;
    border: 2px solid #e1e8ed !important;
    padding: 10px 15px !important;
    font-size: 15px !important;
    transition: all 0.3s ease !important;
    background: white !important;
}

select:focus, .dropdown:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.15) !important;
}

/* Accordion美化 */
.accordion {
    border-radius: 12px !important;
    border: 2px solid #e1e8ed !important;
    overflow: hidden !important;
    margin: 15px 0 !important;
}

.accordion summary {
    background: linear-gradient(to right, #f5f7fa, #e1e8ed) !important;
    padding: 12px 18px !important;
    font-weight: 600 !important;
    cursor: pointer !important;
    transition: all 0.3s ease !important;
}

.accordion summary:hover {
    background: linear-gradient(to right, #e1e8ed, #d3dce6) !important;
}

/* JSON显示区域美化 */
.json-display {
    background: #2d3748 !important;
    color: #e2e8f0 !important;
    border-radius: 10px !important;
    padding: 16px !important;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
    font-size: 13px !important;
    line-height: 1.6 !important;
    max-height: 350px !important;
    overflow-y: auto !important;
    box-shadow: inset 0 2px 8px rgba(0,0,0,0.3) !important;
}

/* 滚动条美化 */
::-webkit-scrollbar {
    width: 10px !important;
    height: 10px !important;
}

::-webkit-scrollbar-track {
    background: #f1f1f1 !important;
    border-radius: 10px !important;
}

::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border-radius: 10px !important;
}

::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #764ba2 0%, #667eea 100%) !important;
}

/* 加载动画 */
.loading {
    animation: pulse 1.5s ease-in-out infinite !important;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* 响应式设计 */
@media (max-width: 768px) {
    .gradio-container {
        padding: 15px !important;
    }
    
    .main-title {
        font-size: 1.6em !important;
    }
    
    textarea, button, select {
        font-size: 14px !important;
    }
}

/* 添加过渡动画 */
* {
    transition: all 0.2s ease !important;
}

/* 禁用某些元素的过渡 */
.chatbot *, .json-display * {
    transition: none !important;
}
"""


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
with gr.Blocks(title="ContextMind 统一Demo v0.4.0", css=CUSTOM_CSS) as app:
    # 主标题
    gr.Markdown("# 🤖 ContextMind 统一对话系统", elem_classes=["main-title"])
    gr.Markdown("### 智能对话 · 场景灵活 · 模式可选", elem_classes=["subtitle"])
    
    # 配置区域
    with gr.Group(elem_classes=["config-section"]):
        gr.Markdown("#### ⚙️ 场景与模式配置")
        with gr.Row():
            # 场景选择
            scenario_selector = gr.Dropdown(
                choices=[
                    ("💬 闲聊对话", "chat"),
                    ("📞 智能客服", "callcenter"),
                    ("🏥 保险咨询", "insurance")
                ],
                value="chat",
                label="选择场景",
                info="不同场景有不同的提示词和配置",
                scale=2
            )
            
            # 模式选择
            mode_selector = gr.Radio(
                choices=["contextmind", "dst"],
                value="contextmind",
                label="选择模式",
                info="contextmind=完整模式 | dst=基础状态追踪",
                scale=2
            )
            
            # 应用按钮
            apply_btn = gr.Button("✨ 应用配置", variant="primary", scale=1, elem_classes=["primary-button"])
        
        status_output = gr.Textbox(label="📌 配置状态", interactive=False, show_label=True)
    
    # 对话区域
    chatbot = gr.Chatbot(
        label="💬 对话窗口",
        height=500,
        show_label=True,
        avatar_images=(None, "🤖"),
        bubble_full_width=False,
        elem_classes=["chatbot"]
    )
    
    # 输入区域
    with gr.Row(elem_classes=["input-row"]):
        msg_input = gr.Textbox(
            label="",
            placeholder="💭 在这里输入您的消息...",
            scale=5,
            show_label=False,
            container=False
        )
        send_btn = gr.Button("📤 发送", variant="primary", scale=1, elem_classes=["primary-button"])
    
    # 状态和操作区域
    with gr.Accordion("📊 对话状态与操作", open=False, elem_classes=["accordion"]):
        state_display = gr.JSON(label="当前状态", elem_classes=["json-display"])
        
        with gr.Row():
            state_btn = gr.Button("🔍 查看状态", elem_classes=["secondary-button"])
            reset_btn = gr.Button("🔄 重置对话", elem_classes=["secondary-button"])
            clear_btn = gr.Button("🗑️ 清空历史", elem_classes=["secondary-button"])
    
    # 使用提示
    with gr.Accordion("💡 使用指南", open=False, elem_classes=["accordion"]):
        gr.Markdown("""
        ### 📋 场景说明
        
        | 场景 | 说明 | 特点 |
        |------|------|------|
        | 💬 **闲聊对话** | 日常聊天场景 | 动态槽位，开放意图 |
        | 📞 **智能客服** | 专业客服系统 | 问题追踪，工单管理 |
        | 🏥 **保险咨询** | 共荣保险客服 | 双层意图，预定义槽位 |
        
        ### ⚙️ 模式说明
        
        - **contextmind**: 完整的五层架构（感知→记忆→上下文→生成→进化）
        - **dst**: 基础对话状态追踪（意图识别 + 槽位提取）
        
        ### 🎯 使用技巧
        
        1. **选择场景**: 根据对话目的选择合适的场景
        2. **选择模式**: contextmind功能更强，dst更轻量快速
        3. **点击应用**: 修改配置后记得点击"应用配置"按钮
        4. **开始对话**: 在输入框输入消息，点击发送或按Enter
        5. **查看状态**: DST模式下可查看提取的意图和槽位
        6. **重置对话**: 清空对话历史，重新开始
        
        ### ⚠️ 注意事项
        
        - 首次使用需要配置API密钥（.env文件）
        - 支持的API: QWEN3_API_KEY, LLM_API_KEY, OPENAI_API_KEY
        - 状态查看功能仅在DST模式下可用
        """)
    
    # 底部信息
    gr.Markdown("""
    ---
    <div style="text-align: center; color: #666; font-size: 14px;">
        <p>ContextMind v0.4.0 | 基于五层对话架构 | 支持多场景多模式</p>
        <p>💡 Powered by LLM | 🚀 Built with Gradio</p>
    </div>
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
    
    clear_btn.click(
        lambda: ([], "✅ 历史已清空"),
        outputs=[chatbot, status_output]
    )


if __name__ == "__main__":
    logger.info("🚀 启动ContextMind统一Gradio Demo")
    logger.info("📍 访问地址: http://0.0.0.0:7860")
    app.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        quiet=False
    )
