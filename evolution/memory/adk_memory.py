"""
Evolution Memory Bank using google-adk

使用 google-adk 的 InMemoryMemoryService 来管理记忆。
提供与 EvolutionEngine 兼容的接口。

版本: v0.4.1
"""

from typing import List, Optional, Dict, Any
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import Session

from evolution.core.types import ContextSource, KnowledgeType
from evolution.core.data_models import Knowledge, ContextItem
from utils.logger import get_logger

logger = get_logger("evolution.memory.adk_memory")


class ADKMemoryBank:
    """
    基于 google-adk InMemoryMemoryService 的记忆库
    
    ADK 负责：
    - 记忆的存储和检索
    - 语义搜索
    
    本类负责：
    - 提供简化的记忆管理接口
    - 与 EvolutionEngine 兼容的 API
    - 记忆的分类和组织
    
    注意：进化相关的逻辑（适应度计算、进化更新）仍由
    evolution/evolution/ 模块负责
    """
    
    def __init__(
        self,
        app_name: str,
        user_id: str,
        memory_service: Optional[InMemoryMemoryService] = None,
        session_service: Optional[Any] = None,
        **kwargs
    ):
        """
        初始化记忆库
        
        Args:
            app_name: 应用名称
            user_id: 用户ID
            memory_service: 可选的 ADK 内存服务（如果不提供则创建新的）
            session_service: 可选的会话服务（用于集成）
            **kwargs: 其他参数（向后兼容）
        """
        self.app_name = app_name
        self.user_id = user_id
        
        # 使用提供的或创建新的 ADK Memory Service
        self.memory_service = memory_service or InMemoryMemoryService()
        self.session_service = session_service
        
        # 本地缓存：存储 Knowledge 对象
        # 提供快速访问和简单的内存管理
        self._memory_cache: List[ContextItem] = []
        self._knowledge_store: List[Knowledge] = []
        
        logger.info(f"[ADK Memory] 初始化成功 - app:{app_name}, user:{user_id}")
    
    async def store(self, knowledge_list: List[Knowledge]) -> None:
        """
        存储知识到记忆库
        
        Args:
            knowledge_list: 知识对象列表
        """
        for knowledge in knowledge_list:
            # 添加到知识存储
            self._knowledge_store.append(knowledge)
            
            # 同时创建 ContextItem 用于检索
            context_item = ContextItem(
                content=knowledge.content,
                source=ContextSource.MEMORY,
                score=knowledge.scores.confidence,
                metadata={
                    "type": knowledge.knowledge_type.value,
                    "memory_id": knowledge.memory_id,
                }
            )
            self._memory_cache.append(context_item)
            
            logger.debug(
                f"[ADK Memory] 存储知识 - type:{knowledge.knowledge_type.value}, "
                f"content_len:{len(knowledge.content)}"
            )
        
        logger.info(f"[ADK Memory] 存储 {len(knowledge_list)} 条知识")
    
    async def retrieve(
        self,
        query: str,
        limit: int = 10
    ) -> List[ContextItem]:
        """
        检索相关记忆
        
        Args:
            query: 查询文本
            limit: 返回的最大结果数
            
        Returns:
            ContextItem 列表
        """
        # 简单的基于关键词的检索
        # 未来可以使用 ADK 的语义搜索增强
        results = []
        
        query_lower = query.lower()
        for item in self._memory_cache:
            # 简单的关键词匹配评分
            if query_lower in item.content.lower():
                # 匹配到的项获得较高分数
                item.score = 0.8
                results.append(item)
            elif any(word in item.content.lower() for word in query_lower.split()):
                # 部分匹配
                item.score = 0.5
                results.append(item)
        
        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        # 限制返回数量
        results = results[:limit]
        
        logger.debug(f"[ADK Memory] 检索 - query:{query[:50]}, results:{len(results)}")
        return results
    
    def get_memory_cache(self) -> List[ContextItem]:
        """
        获取记忆缓存
        
        Returns:
            ContextItem 列表
        """
        return self._memory_cache.copy()
    
    async def seed(self, facts: List[str]) -> None:
        """
        植入初始事实
        
        Args:
            facts: 事实字符串列表
        """
        knowledge_list = []
        for fact in facts:
            knowledge = Knowledge(
                knowledge_type=KnowledgeType.FACT,
                content=fact,
                extraction_method="seed"
            )
            knowledge_list.append(knowledge)
        
        await self.store(knowledge_list)
        logger.info(f"[ADK Memory] 植入 {len(facts)} 条初始事实")
    
    async def add_session_to_memory(self, session: Session) -> None:
        """
        将会话添加到记忆（使用 ADK）
        
        Args:
            session: ADK Session 对象
        """
        try:
            self.memory_service.add_session_to_memory(session)
            logger.info(f"[ADK Memory] 添加会话到记忆 - session_id:{session.id}")
        except Exception as e:
            logger.warning(f"[ADK Memory] 添加会话失败: {e}")
    
    async def search_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        使用 ADK 搜索记忆（语义搜索）
        
        Args:
            query: 查询文本
            top_k: 返回的最大结果数
            
        Returns:
            搜索结果列表
        """
        try:
            response = self.memory_service.search_memory(
                app_name=self.app_name,
                user_id=self.user_id,
                query=query
            )
            
            results = []
            if hasattr(response, 'memories'):
                for mem in response.memories[:top_k]:
                    results.append({
                        'content': mem.content if hasattr(mem, 'content') else str(mem),
                        'score': mem.score if hasattr(mem, 'score') else 1.0
                    })
            
            logger.debug(f"[ADK Memory] ADK搜索 - query:{query[:50]}, results:{len(results)}")
            return results
        except Exception as e:
            logger.warning(f"[ADK Memory] ADK搜索失败: {e}")
            return []
    
    async def clear(self) -> None:
        """清空所有记忆"""
        self._memory_cache.clear()
        self._knowledge_store.clear()
        logger.info("[ADK Memory] 清空所有记忆")
