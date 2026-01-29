"""
Template-based Optimization Strategy - 基于模板的优化策略

通过提示词模板和意图提取实现上下文优化。
"""

from typing import Optional, List, Dict, Any

from ..core.strategies import OptimizationStrategy
from ..core.data_models import ProcessedContext, ContextResult, ContextItem, Message
from ..core.types import ContextSource, MessageRole
from ..core.prompt_template import PromptTemplate, DEFAULT_CHAT_TEMPLATE
from ..pipeline.intent_extractor import IntentExtractor, LLMIntentExtractor
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TemplateBasedOptimization(OptimizationStrategy):
    """
    基于模板的优化策略
    
    工作流程：
    1. 从对话历史中提取意图
    2. 提取主题和上下文摘要
    3. 填充提示词模板的槽位
    4. 生成优化后的上下文
    
    这是上下文优化的基础版本实现。
    """
    
    def __init__(
        self,
        template: Optional[PromptTemplate] = None,
        llm_client: Optional[Any] = None,
        use_llm_extraction: bool = False
    ):
        """
        初始化模板优化策略
        
        Args:
            template: 提示词模板（默认使用DEFAULT_CHAT_TEMPLATE）
            llm_client: LLM客户端（用于高级意图提取）
            use_llm_extraction: 是否使用LLM提取意图
        """
        self.template = template or DEFAULT_CHAT_TEMPLATE
        self.llm_client = llm_client
        
        # 初始化意图提取器
        if use_llm_extraction and llm_client:
            self.intent_extractor = LLMIntentExtractor(llm_client)
            logger.info("[TemplateBasedOptimization] 使用LLM意图提取器")
        else:
            self.intent_extractor = IntentExtractor()
            logger.info("[TemplateBasedOptimization] 使用规则意图提取器")
        
        logger.info(
            f"[TemplateBasedOptimization] 初始化完成 "
            f"(模板: {self.template.name}, 槽位数: {len(self.template.slots)})"
        )
    
    async def optimize(self, context: ProcessedContext) -> ContextResult:
        """
        执行基于模板的优化
        
        Args:
            context: 待优化的上下文
            
        Returns:
            优化后的上下文结果
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[TemplateBasedOptimization] ========== 开始模板优化 ==========")
        logger.info("=" * 100)
        logger.info("")
        
        # 1. 从上下文中提取对话历史
        history_items = [item for item in context.items if item.source == ContextSource.HISTORY]
        messages = self._convert_items_to_messages(history_items)
        
        logger.info(f"[TemplateBasedOptimization] 📝 提取到 {len(messages)} 条对话消息")
        
        # 2. 提取意图、主题和上下文摘要
        logger.info(f"[TemplateBasedOptimization] 🔍 步骤 1/3: 提取意图信息")
        
        intent_info = await self.intent_extractor.extract_intent(messages)
        topic = await self.intent_extractor.extract_topic(messages)
        context_summary = await self.intent_extractor.extract_context_summary(messages)
        
        logger.info(f"[TemplateBasedOptimization]   - 意图: {intent_info.description} (置信度: {intent_info.confidence:.2f})")
        logger.info(f"[TemplateBasedOptimization]   - 主题: {topic}")
        logger.info(f"[TemplateBasedOptimization]   - 上下文: {context_summary[:50]}...")
        logger.info("")
        
        # 3. 填充模板槽位
        logger.info(f"[TemplateBasedOptimization] 📋 步骤 2/3: 填充模板槽位")
        
        slot_values = {
            'intent': intent_info.description,
            'topic': topic,
            'context': context_summary,
        }
        
        # 记录填充的槽位
        for slot_name, value in slot_values.items():
            logger.debug(f"[TemplateBasedOptimization]   - {slot_name}: {value[:50]}...")
        
        try:
            filled_template = self.template.fill_slots(slot_values, strict=False)
            logger.info(f"[TemplateBasedOptimization] ✓ 模板填充完成 (长度: {len(filled_template)} 字符)")
        except Exception as e:
            logger.error(f"[TemplateBasedOptimization] ❌ 模板填充失败: {e}")
            # 回退：返回原始上下文
            return context.to_context_result()
        
        logger.info("")
        
        # 4. 构建优化后的上下文
        logger.info(f"[TemplateBasedOptimization] 🎯 步骤 3/3: 构建优化后的上下文")
        
        # 创建一个新的上下文项，包含填充后的模板
        template_item = ContextItem(
            content=filled_template,
            source=ContextSource.MEMORY,  # 使用MEMORY源标识这是优化后的内容
            score=intent_info.confidence,
            metadata={
                'type': 'template_optimization',
                'template_id': self.template.template_id,
                'intent_type': intent_info.intent_type,
                'intent_description': intent_info.description,
                'topic': topic,
                'slot_values': slot_values,
            }
        )
        
        # 构建结果
        optimized_items = [template_item]
        
        # 可选：保留一些原始上下文项（长期记忆）
        memory_items = [item for item in context.items if item.source == ContextSource.MEMORY]
        optimized_items.extend(memory_items[:5])  # 最多保留5条记忆
        
        result = ContextResult(
            items=optimized_items,
            total_tokens=0,  # TODO: 计算实际token数
            compressed=True,
            metadata={
                'optimization_method': 'template_based',
                'template_id': self.template.template_id,
                'original_items_count': len(context.items),
                'optimized_items_count': len(optimized_items),
                'intent_confidence': intent_info.confidence,
            }
        )
        
        logger.info(
            f"[TemplateBasedOptimization] ✓ 优化完成 "
            f"(原始: {len(context.items)} 项 → 优化后: {len(optimized_items)} 项)"
        )
        logger.info("")
        logger.info("-" * 100)
        logger.info("[TemplateBasedOptimization] ========== 模板优化结束 ==========")
        logger.info("")
        
        return result
    
    def _convert_items_to_messages(self, items: List[ContextItem]) -> List[Message]:
        """
        将上下文项转换为消息列表
        
        Args:
            items: 上下文项列表
            
        Returns:
            消息列表
        """
        messages = []
        
        for item in items:
            # 解析内容格式: "role: content"
            content = item.content
            
            # 尝试解析角色和内容
            if ': ' in content:
                parts = content.split(': ', 1)
                role_str = parts[0].lower()
                message_content = parts[1]
                
                # 识别角色
                if role_str == 'user':
                    role = MessageRole.USER
                elif role_str == 'assistant':
                    role = MessageRole.ASSISTANT
                else:
                    role = MessageRole.SYSTEM
                
                messages.append(Message(
                    role=role,
                    content=message_content,
                    timestamp=item.timestamp,
                    metadata=item.metadata
                ))
            else:
                # 如果无法解析，默认为系统消息
                messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content=content,
                    timestamp=item.timestamp,
                    metadata=item.metadata
                ))
        
        return messages
    
    def set_template(self, template: PromptTemplate):
        """更新使用的模板"""
        self.template = template
        logger.info(f"[TemplateBasedOptimization] 模板已更新: {template.name}")
    
    def get_template_info(self) -> Dict[str, Any]:
        """获取当前模板信息"""
        return {
            'template_id': self.template.template_id,
            'template_name': self.template.name,
            'slots': [
                {
                    'name': slot.name,
                    'type': slot.slot_type,
                    'required': slot.required,
                    'description': slot.description,
                }
                for slot in self.template.slots
            ],
            'metadata': self.template.metadata,
        }


__all__ = [
    'TemplateBasedOptimization',
]
