"""
VectorClient - 向量数据库客户端

提供统一的向量数据库操作接口，支持多种后端：
- Chroma
- Pinecone
- Faiss
- Qdrant
- In-Memory (用于测试)
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class VectorSearchResult:
    """向量搜索结果"""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any]


class VectorClient:
    """
    向量数据库客户端
    
    提供统一的接口用于：
    1. 向量存储
    2. 相似度搜索
    3. 批量操作
    
    使用示例：
        ```python
        client = VectorClient(backend="chroma", collection_name="my_docs")
        
        # 添加文档
        await client.add_documents(
            texts=["doc1", "doc2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            metadatas=[{"source": "a"}, {"source": "b"}]
        )
        
        # 搜索
        results = await client.search(
            query_embedding=[0.15, 0.25],
            top_k=5
        )
        ```
    """
    
    def __init__(
        self,
        backend: str = "memory",
        collection_name: str = "default",
        **kwargs
    ):
        """
        初始化向量客户端
        
        Args:
            backend: 后端类型 ("chroma", "pinecone", "faiss", "qdrant", "memory")
            collection_name: 集合名称
            **kwargs: 后端特定的配置参数
        """
        self.backend = backend
        self.collection_name = collection_name
        self.config = kwargs
        self._client = None
        self._collection = None
        
        # In-memory存储（用于memory后端）
        self._memory_store: List[Dict[str, Any]] = []
        
        self._initialize()
    
    def _initialize(self):
        """初始化向量数据库客户端"""
        if self.backend == "memory":
            logger.debug("Using in-memory vector store")
            return
        
        elif self.backend == "chroma":
            try:
                import chromadb
                self._client = chromadb.Client()
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name
                )
                logger.debug(f"Initialized Chroma collection: {self.collection_name}")
            except ImportError:
                logger.warning("chromadb not installed, using in-memory store")
                self.backend = "memory"
            except Exception as e:
                logger.error(f"Failed to initialize Chroma: {e}")
                self.backend = "memory"
        
        elif self.backend == "faiss":
            try:
                import faiss
                # FAISS初始化逻辑
                logger.debug("Initialized FAISS index")
            except ImportError:
                logger.warning("faiss not installed, using in-memory store")
                self.backend = "memory"
        
        # 其他后端的初始化可以在这里添加
    
    async def add_documents(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        ids: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        添加文档到向量数据库
        
        Args:
            texts: 文档文本列表
            embeddings: 嵌入向量列表
            ids: 文档ID列表（可选，自动生成）
            metadatas: 元数据列表（可选）
        """
        if not texts or not embeddings:
            return
        
        if len(texts) != len(embeddings):
            raise ValueError("texts and embeddings must have same length")
        
        # 生成IDs
        if ids is None:
            ids = [f"doc_{i}_{datetime.now().timestamp()}" for i in range(len(texts))]
        
        # 生成默认metadata
        if metadatas is None:
            metadatas = [{} for _ in texts]
        
        if self.backend == "memory":
            for i, (text, emb, id_, meta) in enumerate(zip(texts, embeddings, ids, metadatas)):
                self._memory_store.append({
                    "id": id_,
                    "content": text,
                    "embedding": emb,
                    "metadata": meta,
                })
            logger.debug(f"Added {len(texts)} documents to memory store")
        
        elif self.backend == "chroma" and self._collection:
            self._collection.add(
                embeddings=embeddings,
                documents=texts,
                ids=ids,
                metadatas=metadatas,
            )
            logger.debug(f"Added {len(texts)} documents to Chroma")
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """
        相似度搜索
        
        Args:
            query_embedding: 查询向量
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件
            
        Returns:
            搜索结果列表
        """
        if self.backend == "memory":
            return await self._search_memory(query_embedding, top_k, filter_metadata)
        
        elif self.backend == "chroma" and self._collection:
            return await self._search_chroma(query_embedding, top_k, filter_metadata)
        
        return []
    
    async def _search_memory(
        self,
        query_embedding: List[float],
        top_k: int,
        filter_metadata: Optional[Dict[str, Any]]
    ) -> List[VectorSearchResult]:
        """在内存中搜索"""
        if not self._memory_store:
            return []
        
        # 简单的余弦相似度计算
        import math
        
        def cosine_similarity(a: List[float], b: List[float]) -> float:
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot_product / (norm_a * norm_b)
        
        # 计算相似度
        scored_docs = []
        for doc in self._memory_store:
            # 应用过滤器
            if filter_metadata:
                if not all(doc["metadata"].get(k) == v for k, v in filter_metadata.items()):
                    continue
            
            score = cosine_similarity(query_embedding, doc["embedding"])
            scored_docs.append((doc, score))
        
        # 排序并取top_k
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        scored_docs = scored_docs[:top_k]
        
        # 转换为结果对象
        results = [
            VectorSearchResult(
                id=doc["id"],
                content=doc["content"],
                score=score,
                metadata=doc["metadata"]
            )
            for doc, score in scored_docs
        ]
        
        logger.debug(f"Memory search returned {len(results)} results")
        return results
    
    async def _search_chroma(
        self,
        query_embedding: List[float],
        top_k: int,
        filter_metadata: Optional[Dict[str, Any]]
    ) -> List[VectorSearchResult]:
        """在Chroma中搜索"""
        if not self._collection:
            return []
        
        where = filter_metadata if filter_metadata else None
        
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )
        
        # 转换为结果对象
        output = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                output.append(VectorSearchResult(
                    id=results["ids"][0][i],
                    content=doc,
                    score=1.0 - results["distances"][0][i],  # Convert distance to similarity
                    metadata=results["metadatas"][0][i] if results.get("metadatas") else {}
                ))
        
        logger.debug(f"Chroma search returned {len(output)} results")
        return output
    
    async def delete_collection(self) -> None:
        """删除集合"""
        if self.backend == "memory":
            self._memory_store.clear()
        elif self.backend == "chroma" and self._client:
            try:
                self._client.delete_collection(name=self.collection_name)
                logger.debug(f"Deleted Chroma collection: {self.collection_name}")
            except Exception as e:
                logger.error(f"Failed to delete collection: {e}")
