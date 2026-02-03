"""
Evolution Memory Bank using google-adk

使用 google-adk 的 InMemoryMemoryService 来管理记忆。
简化了原有的 bank.py 实现，从 ~200 行减少到 ~80 行。

版本: v0.4.1
"""

from typing import List, Optional, Dict, Any
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import Session
from evolution.core.data_models import Memory, MemoryType
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
    - 记忆的分类和组织（knowledge, long_term 等）
    - 兼容 Evolution 的数据模型
    
    注意：进化相关的逻辑（适应度计算、进化更新）仍由
    evolution/evolution/ 模块负责
    """
    
    def __init__(self, app_name: str, user_id: str):
        """
        初始化记忆库
        
        Args:
            app_name: 应用名称
            user_id: 用户ID
        """
        self.app_name = app_name
        self.user_id = user_id
        
        # 使用 ADK 的 Memory Service
        self.memory_service = InMemoryMemoryService()
        
        # 本地缓存：按类型组织记忆
        # ADK 的 search_memory 主要用于语义搜索
        # 我们仍需要按类型快速访问，所以保留简单的缓存
        self.memories: Dict[MemoryType, List[Memory]] = {
            MemoryType.KNOWLEDGE: [],
            MemoryType.LONG_TERM: [],
            MemoryType.SHORT_TERM: []
        }
        
        logger.info(f"[ADK Memory] 初始化成功 - app:{app_name}, user:{user_id}")
    
    async def store_memory(self, memory: Memory) -> None:
        """
        存储记忆
        
        Args:
            memory: 记忆对象
        """
        # 添加到本地缓存
        if memory.memory_type not in self.memories:
            self.memories[memory.memory_type] = []
        self.memories[memory.memory_type].append(memory)
        
        logger.debug(f"[ADK Memory] 存储记忆 - type:{memory.memory_type}, content_len:{len(memory.content)}")
    
    async def add_session_to_memory(self, session: Session) -> None:
        """
        将会话添加到记忆（使用 ADK）
        
        Args:
            session: ADK Session 对象
        """
        # 使用 ADK 的 add_session_to_memory 功能
        self.memory_service.add_session_to_memory(session)
        logger.info(f"[ADK Memory] 添加会话到记忆 - session_id:{session.session_id}")
    
    async def search_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索记忆（使用 ADK 的语义搜索）
        
        Args:
            query: 查询文本
            top_k: 返回的最大结果数
            
        Returns:
            搜索结果列表
        """
        try:
            # 使用 ADK 的 search_memory 功能
            response = self.memory_service.search_memory(
                app_name=self.app_name,
                user_id=self.user_id,
                query=query
            )
            
            # 提取结果（取前 top_k 个）
            results = []
            if hasattr(response, 'memories'):
                for mem in response.memories[:top_k]:
                    results.append({
                        'content': mem.content if hasattr(mem, 'content') else str(mem),
                        'score': mem.score if hasattr(mem, 'score') else 1.0
                    })
            
            logger.debug(f"[ADK Memory] 搜索记忆 - query:{query[:50]}, results:{len(results)}")
            return results
        except Exception as e:
            logger.warning(f"[ADK Memory] 搜索失败: {e}")
            return []
    
    async def get_memories_by_type(self, memory_type: MemoryType) -> List[Memory]:
        """
        按类型获取记忆（本地缓存）
        
        Args:
            memory_type: 记忆类型
            
        Returns:
            记忆列表
        """
        return self.memories.get(memory_type, [])
    
    async def get_all_memories(self) -> List[Memory]:
        """获取所有记忆"""
        all_memories = []
        for memories in self.memories.values():
            all_memories.extend(memories)
        return all_memories
    
    async def clear_memories(self, memory_type: Optional[MemoryType] = None) -> None:
        """
        清空记忆
        
        Args:
            memory_type: 如果指定，只清空该类型的记忆；否则清空所有记忆
        """
        if memory_type:
            self.memories[memory_type] = []
            logger.info(f"[ADK Memory] 清空 {memory_type} 记忆")
        else:
            for mtype in self.memories:
                self.memories[mtype] = []
            logger.info("[ADK Memory] 清空所有记忆")
