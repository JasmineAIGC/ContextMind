"""
Embedding Utilities - 向量嵌入工具

提供文本嵌入生成和相似度计算功能，用于语义检索和去重。
"""

from typing import List, Optional, Tuple
import math
import os

from ..models import EmbeddingInfo, get_logger

logger = get_logger(__name__)

# 尝试导入 OpenAI，用于生成 embeddings
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore


class EmbeddingClient:
    """
    Embedding 客户端
    
    使用 OpenAI 兼容的 API 生成文本嵌入向量。
    支持多种 embedding 模型。
    """
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        初始化 Embedding 客户端
        
        Args:
            model: Embedding 模型名称
            api_key: API 密钥（如果为 None，从环境变量读取）
            base_url: API 基础 URL（如果为 None，从环境变量读取）
        """
        if not OPENAI_AVAILABLE:
            logger.warning("[EmbeddingClient] OpenAI 未安装，embedding 功能不可用")
            self.client = None
            self.model = model
            return
        
        # 从环境变量读取配置
        self.api_key = api_key or self._get_api_key()
        self.base_url = base_url or self._get_base_url()
        self.model = model
        
        if not self.api_key:
            logger.warning("[EmbeddingClient] 未配置 API key，embedding 功能不可用")
            self.client = None
            return
        
        # 创建客户端
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            logger.info(f"[EmbeddingClient] 初始化成功 - model: {self.model}")
        except Exception as e:
            logger.error(f"[EmbeddingClient] 初始化失败: {e}")
            self.client = None
    
    def _get_api_key(self) -> Optional[str]:
        """从环境变量获取 API key"""
        keys = [
            "EMBEDDING_API_KEY",
            "QWEN3_API_KEY",
            "CONTEXTMIND_API_KEY",
            "LLM_API_KEY",
            "OPENAI_API_KEY",
        ]
        for key in keys:
            if value := os.getenv(key):
                return value
        return None
    
    def _get_base_url(self) -> Optional[str]:
        """从环境变量获取 base URL"""
        urls = [
            "EMBEDDING_BASE_URL",
            "QWEN3_BASE_URL",
            "CONTEXTMIND_BASE_URL",
            "LLM_BASE_URL",
            "OPENAI_BASE_URL",
        ]
        for url in urls:
            if value := os.getenv(url):
                return value
        return None
    
    def generate_embedding(self, text: str) -> Optional[EmbeddingInfo]:
        """
        生成文本的 embedding 向量
        
        Args:
            text: 输入文本
            
        Returns:
            EmbeddingInfo 对象，如果失败则返回 None
        """
        if not self.client:
            return None
        
        if not text or not text.strip():
            logger.warning("[EmbeddingClient] 输入文本为空，跳过 embedding 生成")
            return None
        
        try:
            # 调用 OpenAI Embeddings API
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            
            if not response.data:
                logger.warning("[EmbeddingClient] API 返回空数据")
                return None
            
            # 提取向量
            vector = response.data[0].embedding
            dimension = len(vector)
            
            logger.debug(f"[EmbeddingClient] 生成 embedding - dim: {dimension}, text: {text[:50]}...")
            
            return EmbeddingInfo(
                model=self.model,
                vector=vector,
                dimension=dimension
            )
            
        except Exception as e:
            logger.error(f"[EmbeddingClient] 生成 embedding 失败: {e}")
            return None
    
    async def generate_embedding_async(self, text: str) -> Optional[EmbeddingInfo]:
        """
        异步生成 embedding（当前简单封装同步版本）
        
        注意: 生产环境应使用 AsyncOpenAI
        """
        return self.generate_embedding(text)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    计算两个向量的余弦相似度
    
    Args:
        vec1: 向量 1
        vec2: 向量 2
        
    Returns:
        余弦相似度 (0-1)，1 表示完全相同
    """
    if not vec1 or not vec2:
        return 0.0
    
    if len(vec1) != len(vec2):
        logger.warning(f"[cosine_similarity] 向量维度不匹配: {len(vec1)} vs {len(vec2)}")
        return 0.0
    
    # 计算点积
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    
    # 计算模长
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    # 余弦相似度
    similarity = dot_product / (norm1 * norm2)
    
    # 归一化到 [0, 1]
    return (similarity + 1) / 2


def calculate_embedding_similarity(
    emb1: Optional[EmbeddingInfo],
    emb2: Optional[EmbeddingInfo]
) -> Tuple[float, bool]:
    """
    计算两个 EmbeddingInfo 的相似度
    
    Args:
        emb1: Embedding 1
        emb2: Embedding 2
        
    Returns:
        (similarity, success) - 相似度和是否成功计算
    """
    if not emb1 or not emb2:
        return 0.0, False
    
    # 检查模型是否匹配（可选）
    if emb1.model != emb2.model:
        logger.debug(f"[calculate_embedding_similarity] 模型不匹配: {emb1.model} vs {emb2.model}")
        # 注意：不同模型的 embedding 也可以比较，但精度可能降低
    
    # 计算余弦相似度
    similarity = cosine_similarity(emb1.vector, emb2.vector)
    return similarity, True


# 全局单例客户端（延迟初始化）
_global_client: Optional[EmbeddingClient] = None


def get_embedding_client(
    model: str = "text-embedding-3-small",
    force_new: bool = False
) -> Optional[EmbeddingClient]:
    """
    获取全局 Embedding 客户端（单例模式）
    
    Args:
        model: Embedding 模型名称
        force_new: 是否强制创建新客户端
        
    Returns:
        EmbeddingClient 实例，如果配置不可用则返回 None
    """
    global _global_client
    
    if force_new or _global_client is None:
        _global_client = EmbeddingClient(model=model)
    
    return _global_client
