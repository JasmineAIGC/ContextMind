"""
记忆相关工具

提供记忆检索、存储等功能的标准化工具。
"""

from typing import List, Dict, Any, Optional
from .base import BaseTool


class SearchMemoryTool(BaseTool):
    """搜索语义记忆工具。"""
    
    def __init__(self, memory_bank):
        self.memory_bank = memory_bank
    
    @property
    def name(self) -> str:
        return "search_memory"
    
    @property
    def description(self) -> str:
        return "Search semantic memory bank for relevant context"
    
    async def execute(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict]:
        """搜索记忆库。
        
        Args:
            query: 搜索查询
            top_k: 返回结果数量
            filters: 可选过滤器
        
        Returns:
            相关记忆项列表
        """
        results = await self.memory_bank.retrieve(
            query=query,
            limit=top_k
        )
        return [
            {
                "content": r.content,
                "score": r.score,
                "source": r.source.value if hasattr(r.source, 'value') else str(r.source),
            }
            for r in results
        ]


class StoreMemoryTool(BaseTool):
    """存储记忆工具。"""
    
    def __init__(self, memory_bank):
        self.memory_bank = memory_bank
    
    @property
    def name(self) -> str:
        return "store_memory"
    
    @property
    def description(self) -> str:
        return "Store knowledge into long-term memory"
    
    async def execute(
        self,
        knowledge: List[str],
        metadata: Optional[Dict] = None
    ) -> Dict:
        """存储知识到记忆库。
        
        Args:
            knowledge: 知识列表
            metadata: 可选元数据
        
        Returns:
            存储结果
        """
        from contextmind.core.data_models import Knowledge
        
        # 转换为 Knowledge 对象
        knowledge_items = [
            Knowledge(content=k, metadata=metadata or {})
            for k in knowledge
        ]
        
        await self.memory_bank.store(knowledge_items)
        
        return {
            "stored": len(knowledge_items),
            "success": True
        }


class MemoryTools:
    """记忆工具集合。"""
    
    def __init__(self, memory_bank):
        self.memory_bank = memory_bank
    
    def get_tools(self) -> List[BaseTool]:
        """获取所有记忆工具。"""
        return [
            SearchMemoryTool(self.memory_bank),
            StoreMemoryTool(self.memory_bank),
        ]
