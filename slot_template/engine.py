"""
Slot Template Engine - 槽位模板引擎

核心引擎，整合意图提取和模板填充，提供简洁的 API
"""

from typing import List, Dict, Optional, Any
from .intent_extractor import IntentExtractor, Message
from .template_manager import TemplateManager


class SlotTemplateEngine:
    """槽位模板引擎
    
    这是一个简单的上下文优化引擎，作为 ContextMind 的 baseline 对比。
    
    工作流程：
    1. 接收对话历史和当前用户输入
    2. 使用 IntentExtractor 从历史中提取意图和关键信息
    3. 使用 TemplateManager 填充槽位模板
    4. 返回填充后的提示词，用于指导 LLM 生成回复
    
    与 ContextMind 的区别：
    - 不使用记忆库（无长期记忆）
    - 不进行复杂的上下文检索和压缩
    - 仅基于当前会话的对话历史
    - 作为简单的 baseline 方案
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        use_llm_extraction: bool = False
    ):
        """初始化槽位模板引擎
        
        Args:
            llm_client: LLM 客户端（可选），用于智能意图提取
            use_llm_extraction: 是否使用 LLM 进行意图提取
                               True: 使用 LLM 智能提取（更准确但需要 API 调用）
                               False: 使用规则提取（快速但简单）
        """
        self.llm_client = llm_client if use_llm_extraction else None
        
        # 初始化组件
        self.intent_extractor = IntentExtractor(self.llm_client)
        self.template_manager = TemplateManager()
        
        # 对话历史
        self.conversation_history: List[Message] = []
    
    async def process(
        self,
        user_input: str,
        system_prompt_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """处理用户输入，返回填充后的槽位信息
        
        Args:
            user_input: 当前用户输入
            system_prompt_template: 系统提示词模板（可选）
                                   如果提供，将使用此模板进行槽位填充
        
        Returns:
            包含以下信息的字典：
            - slot_values: 所有槽位的值
            - filled_prompt: 填充后的系统提示词（如果提供了模板）
            - user_input: 当前用户输入
        """
        # 1. 从对话历史提取槽位信息
        slot_values = await self.intent_extractor.extract_from_history(
            messages=self.conversation_history,
            current_input=user_input
        )
        
        # 2. 填充槽位
        for slot_name, value in slot_values.items():
            self.template_manager.set_slot_value(slot_name, value)
        
        # 3. 构建结果
        result = {
            "slot_values": self.template_manager.get_all_slot_values(),
            "user_input": user_input
        }
        
        # 4. 如果提供了系统提示词模板，进行填充
        if system_prompt_template:
            result["filled_prompt"] = self.template_manager.fill_template(
                system_prompt_template
            )
        
        return result
    
    def add_message(self, role: str, content: str) -> None:
        """添加消息到对话历史
        
        Args:
            role: 角色（"user" 或 "assistant"）
            content: 消息内容
        """
        self.conversation_history.append(Message(role, content))
    
    def clear_history(self) -> None:
        """清空对话历史"""
        self.conversation_history.clear()
        self.template_manager.clear()
    
    def get_slot_value(self, slot_name: str) -> str:
        """获取指定槽位的值
        
        Args:
            slot_name: 槽位名称
        
        Returns:
            槽位值
        """
        return self.template_manager.get_slot_value(slot_name)
    
    def get_all_slots(self) -> Dict[str, str]:
        """获取所有槽位值
        
        Returns:
            所有槽位值的字典
        """
        return self.template_manager.get_all_slot_values()
    
    async def generate_prompt(
        self,
        user_input: str,
        system_prompt_template: str
    ) -> str:
        """生成完整的提示词
        
        这是一个便捷方法，整合了 process() 和提示词生成
        
        Args:
            user_input: 用户输入
            system_prompt_template: 系统提示词模板
        
        Returns:
            完整的提示词，可直接用于 LLM 调用
        """
        result = await self.process(user_input, system_prompt_template)
        
        # 构建完整提示词
        full_prompt = f"""{result['filled_prompt']}

## 当前用户问题
{user_input}

请基于上述槽位信息给出回复："""
        
        return full_prompt
