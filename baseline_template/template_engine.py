"""
Template Engine - 模板引擎（基线版本）

核心功能：
1. 接收对话历史
2. 提取意图和主题
3. 填充模板槽位
4. 生成最终提示词

特点：
- 不使用记忆库
- 只基于对话历史
- 作为最简单的 baseline 实现
"""

from __future__ import annotations

from typing import List, Optional
import sys
import os

# 添加父目录到路径，以便导入 prompts 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .prompt_template import PromptTemplate, DEFAULT_TEMPLATE
from .intent_extractor import IntentExtractor, Message


class TemplateEngine:
    """
    模板引擎 - 基线版本
    
    工作流程：
    1. 接收对话历史
    2. 使用意图提取器提取意图、主题和上下文
    3. 使用提示词模板填充槽位
    4. 返回最终的提示词
    
    这是一个完全独立的实现，不依赖 contextmind 框架。
    """
    
    def __init__(
        self,
        template: Optional[PromptTemplate] = None,
        system_prompt: str = ""
    ):
        """
        初始化模板引擎
        
        Args:
            template: 提示词模板（默认使用 DEFAULT_TEMPLATE）
            system_prompt: 系统提示词（可选）
        """
        self.template = template or DEFAULT_TEMPLATE
        self.system_prompt = system_prompt
        self.intent_extractor = IntentExtractor()
    
    async def generate_prompt(
        self,
        conversation_history: List[Message],
        include_system_prompt: bool = True
    ) -> str:
        """
        生成提示词
        
        Args:
            conversation_history: 对话历史列表
            include_system_prompt: 是否包含系统提示词
            
        Returns:
            最终的提示词文本
        """
        # 1. 提取意图、主题和上下文
        intent_info = await self.intent_extractor.extract_intent(conversation_history)
        topic = await self.intent_extractor.extract_topic(conversation_history)
        context_summary = await self.intent_extractor.extract_context_summary(conversation_history)
        
        # 2. 填充模板槽位
        slot_values = {
            'intent': intent_info.description,
            'topic': topic,
            'context': context_summary,
        }
        
        filled_template = self.template.fill_slots(slot_values, strict=False)
        
        # 3. 组合最终提示词
        prompt_parts = []
        
        if include_system_prompt and self.system_prompt:
            prompt_parts.append(self.system_prompt)
        
        prompt_parts.append(filled_template)
        
        # 4. 添加最新的用户输入
        if conversation_history:
            # 找到最新的用户消息
            user_messages = [msg for msg in conversation_history if msg.role == "user"]
            if user_messages:
                latest_user_msg = user_messages[-1].content
                prompt_parts.append(f"\n## 当前用户输入\n{latest_user_msg}")
        
        return "\n\n".join(prompt_parts)
    
    def get_statistics(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return {
            'template_id': self.template.template_id,
            'template_name': self.template.name,
            'num_slots': len(self.template.slots),
            'slot_names': self.template.get_slot_names(),
            'has_system_prompt': bool(self.system_prompt),
        }


class SimpleTemplateEngine:
    """
    简化版模板引擎 - 用于快速实验
    
    与 TemplateEngine 相比，这个版本更简单：
    - 同步接口（不需要 async）
    - 更少的配置选项
    - 适合快速原型和实验
    """
    
    def __init__(self, system_prompt: str = ""):
        """
        初始化简化版引擎
        
        Args:
            system_prompt: 系统提示词
        """
        self.system_prompt = system_prompt
        self.template = DEFAULT_TEMPLATE
        self.intent_extractor = IntentExtractor()
    
    def generate_prompt_sync(
        self,
        user_message: str,
        conversation_history: Optional[List[Message]] = None
    ) -> str:
        """
        同步生成提示词（简化版）
        
        Args:
            user_message: 用户当前消息
            conversation_history: 对话历史（可选）
            
        Returns:
            最终提示词
        """
        # 构建完整的对话历史
        if conversation_history is None:
            conversation_history = []
        
        # 添加当前用户消息
        full_history = conversation_history + [Message(role="user", content=user_message)]
        
        # 简单实现：提取关键信息
        topic = user_message[:30] if len(user_message) > 30 else user_message
        
        # 填充模板
        slot_values = {
            'intent': "用户提问",
            'topic': topic,
            'context': f"共 {len(full_history)} 轮对话",
        }
        
        filled_template = self.template.fill_slots(slot_values, strict=False)
        
        # 组合提示词
        prompt_parts = []
        if self.system_prompt:
            prompt_parts.append(self.system_prompt)
        
        prompt_parts.append(filled_template)
        prompt_parts.append(f"\n## 当前用户输入\n{user_message}")
        
        return "\n\n".join(prompt_parts)


__all__ = [
    'TemplateEngine',
    'SimpleTemplateEngine',
]
