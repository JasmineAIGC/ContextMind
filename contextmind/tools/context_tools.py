"""
上下文相关工具

提供上下文优化、压缩等功能的标准化工具。
"""

from typing import Dict, Any
from .base import BaseTool


class OptimizeContextTool(BaseTool):
    """优化上下文工具。"""
    
    def __init__(self, engine):
        self.engine = engine
    
    @property
    def name(self) -> str:
        return "optimize_context"
    
    @property
    def description(self) -> str:
        return "Optimize and retrieve relevant context for user input"
    
    async def execute(
        self,
        user_input: str,
        include_session: bool = True,
        include_memory: bool = True
    ) -> Dict:
        """优化上下文。
        
        Args:
            user_input: 用户输入
            include_session: 是否包含会话历史
            include_memory: 是否包含长期记忆
        
        Returns:
            优化后的上下文
        """
        result = await self.engine.optimize(
            user_input=user_input,
            include_session=include_session,
            include_memory=include_memory
        )
        
        return {
            "context_items": len(result.items),
            "total_tokens": result.total_tokens,
            "compressed": result.compressed,
            "items": [
                {
                    "content": item.content,
                    "source": item.source.value if hasattr(item.source, 'value') else str(item.source),
                    "score": item.score
                }
                for item in result.items[:10]  # 返回前10个
            ]
        }


class ExtractKnowledgeTool(BaseTool):
    """提取知识工具。"""
    
    def __init__(self, engine):
        self.engine = engine
    
    @property
    def name(self) -> str:
        return "extract_knowledge"
    
    @property
    def description(self) -> str:
        return "Extract knowledge from recent conversations"
    
    async def execute(self, auto_store: bool = True) -> Dict:
        """提取知识。
        
        Args:
            auto_store: 是否自动存储
        
        Returns:
            提取的知识
        """
        knowledge = await self.engine.extract_knowledge(auto_store=auto_store)
        
        return {
            "knowledge_count": len(knowledge),
            "knowledge": [k.content for k in knowledge[:5]],  # 返回前5个
            "stored": auto_store
        }


class ContextTools:
    """上下文工具集合。"""
    
    def __init__(self, engine):
        self.engine = engine
    
    def get_tools(self):
        """获取所有上下文工具。"""
        return [
            OptimizeContextTool(self.engine),
            ExtractKnowledgeTool(self.engine),
        ]
