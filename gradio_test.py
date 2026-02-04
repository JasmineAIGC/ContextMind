#!/usr/bin/env python3
"""
ContextMind 批量对话测试 Gradio Demo

与 gradio_demo.py 的区别：
- 对话窗口直接输入预写好的对话内容（而非实时交互）
- 支持单轮对话和多轮对话
- 支持一次性输入和分批多次输入
- 复用 gradio_demo.py 中 DST 和 ContextMind 模式的计算流程

使用方式:
    python gradio_test.py
    python gradio_test.py --port 7861
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gradio as gr

from utils.llm_client import SimpleLLMClient
from dst import DialogueStateTracker, PromptManager
from evolve import EvolveEngine
from scenarios import get_insurance_scenario
from apps.insurance_app import InsuranceApplication
from utils.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class BatchDialogueTest:
    """批量对话测试类"""
    
    def __init__(self, max_history_turns: int = 10):
        """
        初始化测试类
        
        Args:
            max_history_turns: DST模式的最大历史轮数
        """
        self.max_history_turns = max_history_turns
        self.llm_client = None
        self.tracker = None
        self.config = None
        self.app = None
        self.engine = None
        self.current_mode = None
        self.results_history = []
        logger.info("BatchDialogueTest 实例创建完成")
    
    def initialize(self, mode: str = "dst"):
        """
        初始化模式
        
        Args:
            mode: "dst" 或 "evolve"
        """
        self.current_mode = mode
        
        # 加载保险场景配置
        self.config = get_insurance_scenario()
        
        # 创建 LLM 客户端
        try:
            if self.llm_client is None:
                self.llm_client = SimpleLLMClient()
                logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM客户端初始化失败: {e}")
            raise
        
        if mode == "dst":
            self._init_dst_mode()
        else:
            self._init_evolve_mode()
        
        logger.info(f"✅ {mode.upper()} 模式初始化完成")
    
    def _init_dst_mode(self):
        """
        初始化 DST 模式
        
        复用 gradio_demo.py 中的初始化逻辑
        """
        # 创建 PromptManager
        pm = PromptManager(
            domain=self.config.name,
            enable_dynamic_slots=self.config.enable_dynamic_slots,
            custom_template=getattr(self.config, 'dst_prompt_template', None)
        )
        
        # 添加预定义槽位
        for slot_name, slot_desc in self.config.dst_slots.items():
            categorical_values = None
            if self.config.dst_categorical_slots and slot_name in self.config.dst_categorical_slots:
                categorical_values = self.config.dst_categorical_slots[slot_name]
            pm.add_slot(slot_name, slot_desc, categorical_values=categorical_values)
        
        # 创建 DialogueStateTracker
        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=self.max_history_turns,
            enable_history_summary=True,
            use_llm_summary=False
        )
    
    def _init_evolve_mode(self):
        """
        初始化 Evolve 模式
        
        复用 gradio_demo.py 中的初始化逻辑
        """
        # 创建 EvolveEngine
        self.engine = EvolveEngine(
            app_name="gradio_test_insurance",
            user_id="test_user",
            llm_client=self.llm_client
        )
        
        # 创建 InsuranceApplication
        self.app = InsuranceApplication(
            context_engine=self.engine,
            system_prompt=self.config.system_prompt
        )
    
    def reset(self):
        """重置对话状态"""
        if self.current_mode == "dst" and self.tracker:
            self.tracker.current_state = {}
            self.tracker.dialogue_history = []
        elif self.current_mode == "evolve" and self.engine:
            # 重新初始化
            self._init_evolve_mode()
        
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
        import re
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
        
        # 获取最终累积状态
        final_state = self.tracker.current_state.copy()
        
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
    
    async def process_dialogue_evolve(self, turns: List[Dict]) -> Tuple[str, Dict]:
        """
        使用 Evolve 模式处理对话
        
        复用 gradio_demo.py 中的处理逻辑
        
        Args:
            turns: 对话轮次列表
            
        Returns:
            (处理结果文本, 状态信息)
        """
        result_text = ""
        
        for i, turn in enumerate(turns):
            user_utterance = turn.get('user_utterance', '')
            
            # 处理用户消息 - 复用 gradio_demo.py 的流程
            reply = await self.app.process_turn(user_utterance)
            
            # 格式化输出
            result_text += f"\n{'='*50}\n"
            result_text += f"轮次 {i + 1}\n"
            result_text += f"{'='*50}\n"
            result_text += f"用户输入: {user_utterance}\n"
            result_text += f"系统回复: {reply[:200]}{'...' if len(reply) > 200 else ''}\n"
        
        # 获取记忆库状态
        state_info = {}
        if hasattr(self.engine, 'memory_bank'):
            memory_cache = self.engine.memory_bank.get_memory_cache()
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


# 全局测试实例
test_instance = None


def get_test_instance():
    """获取测试实例（延迟初始化）"""
    global test_instance
    if test_instance is None:
        test_instance = BatchDialogueTest()
    return test_instance


async def process_dialogue_async(dialogue_text: str, mode: str) -> Tuple[str, str]:
    """
    异步处理对话
    
    Args:
        dialogue_text: 对话文本
        mode: "dst" 或 "evolve"
        
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
        dialogue_path = Path(__file__).parent / "tests" / "dialogues" / f"dialogue_{dialogue_num}.txt"
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
        gr.Markdown("直接输入对话内容进行 DST 或 ContextMind 模式测试")
        
        with gr.Row():
            # 左侧 - 输入区
            with gr.Column(scale=1):
                gr.Markdown("### 📝 对话输入")
                
                # 模式选择
                mode_selector = gr.Radio(
                    choices=[
                        ("DST 模式 (槽位提取)", "dst"),
                        ("ContextMind 模式 (记忆进化)", "evolve")
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

这是一个批量对话测试界面，与 `gradio_demo.py` 的主要区别：

1. **直接输入对话内容**：不是实时交互，而是直接粘贴完整对话
2. **支持单轮/多轮**：可以输入一轮或多轮对话
3. **支持多次输入**：可以多次运行测试，状态会累积
4. **复用计算流程**：完全复用 `gradio_demo.py` 中的 DST 和 ContextMind 计算逻辑

### 对话格式

```
销售员：你好，我是保险顾问
客户：你好
销售员：请问您有什么需要？
客户：我想了解癌症保险
```

### 模式说明

- **DST 模式**：提取对话中的槽位信息（意图、保险状态等）
- **ContextMind 模式**：基于记忆的对话处理，会积累知识

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
    parser = argparse.ArgumentParser(description="Evolve 批量对话测试")
    parser.add_argument('--port', type=int, default=7861, help='端口号')
    parser.add_argument('--share', action='store_true', help='创建公共链接')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO')
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    # 设置日志
    log_level = LogLevel.DEBUG if args.log_level == "DEBUG" else LogLevel.INFO
    setup_logging(level=log_level, save_to_file=True, log_dir="logs")
    
    logger.info("启动 Evolve 批量对话测试")
    
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
