"""
Embedding Utilities - 向量嵌入工具

提供文本嵌入生成和相似度计算功能，用于语义检索和去重。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
import math
import os

from ..core.data_models import EmbeddingInfo
from .logger import get_logger

logger = get_logger(__name__)

# 尝试导入 OpenAI，用于生成嵌入向量
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore

# 尝试导入 sentence-transformers，用于本地模型加载
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None  # type: ignore


DEFAULT_EMBEDDING_MODEL = "bge-large-zh-v1.5"


def _first_env(keys: Sequence[str], default: Optional[str] = None) -> Optional[str]:
    """按顺序读取环境变量，返回首个非空值。
    
    支持多个环境变量名，便于适配不同的部署环境（Qwen、DeepSeek、OpenAI 等）。
    """
    for key in keys:
        if value := os.getenv(key):
            return value
    return default


@dataclass
class EmbeddingConfig:
    """Embedding 配置 - 使用专门的 embedding 模型提取向量"""
    
    api_key: str
    model: str = DEFAULT_EMBEDDING_MODEL
    base_url: Optional[str] = None
    access_key: Optional[str] = None
    model_path: Optional[str] = None  # 本地模型路径（用于直接加载）
    use_local: bool = False  # 是否使用本地加载模式
    
    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """从环境变量加载配置 - 支持本地加载和 API 两种方式。"""
        # 优先读取专门的 embedding 模型配置
        embedding_model = os.getenv("EMBEDDING_MODEL")
        embedding_model_path = os.getenv("EMBEDDING_MODEL_PATH")  # 本地路径
        embedding_base_url = os.getenv("EMBEDDING_BASE_URL")  # API URL
        embedding_api_key = os.getenv("EMBEDDING_API_KEY")
        
        # 方式 1：本地模型路径（优先级最高）
        if embedding_model_path:
            logger.info(f"[EmbeddingConfig] 使用本地 embedding 模型: {embedding_model_path}")
            # 从路径提取模型名称
            model_name = embedding_model or os.path.basename(embedding_model_path)
            return cls(
                api_key="",  # 本地模型不需要 API key
                model=model_name,
                model_path=embedding_model_path,
                use_local=True,
            )
        
        # 方式 2：通过 API（vLLM 等）使用 embedding 模型
        if embedding_model and embedding_base_url:
            logger.info(f"[EmbeddingConfig] 使用 API embedding 模型: {embedding_model}")
            api_key = embedding_api_key or "EMPTY"  # vLLM 本地部署可能不需要真实 key
            
            # 读取 Access Key（可选）
            access_key = os.getenv("EMBEDDING_ACCESS_KEY") or _first_env(
                [
                    "QWEN3_ACCESS_KEY",
                    "CONTEXTMIND_ACCESS_KEY",
                    "LLM_ACCESS_KEY",
                    "ACCESS_KEY",
                ]
            )
            
            return cls(
                api_key=api_key,
                model=embedding_model,
                base_url=embedding_base_url,
                access_key=access_key,
                use_local=False,
            )
        
        # 否则回退到使用 LLM 模型（向后兼容）
        logger.info("[EmbeddingConfig] 未配置专门的 embedding 模型，将尝试使用 LLM 模型")
        
        # 读取 API Key（必需）
        api_key = _first_env(
            [
                "QWEN3_API_KEY",
                "CONTEXTMIND_API_KEY",
                "LLM_API_KEY",
                "OPENAI_API_KEY",
                "DEEPSEEK_API_KEY",
                "QWEN_API_KEY",
            ]
        )
        if not api_key:
            raise ValueError(
                "缺少 API key。请在 .env 文件中设置以下变量之一: "
                "EMBEDDING_API_KEY (用于 embedding 模型) 或 "
                "QWEN3_API_KEY, CONTEXTMIND_API_KEY, LLM_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, QWEN_API_KEY"
            )
        
        # 读取 Base URL（可选）
        base_url = _first_env(
            [
                "QWEN3_BASE_URL",
                "CONTEXTMIND_BASE_URL",
                "LLM_BASE_URL",
                "OPENAI_BASE_URL",
                "DEEPSEEK_BASE_URL",
                "QWEN_BASE_URL",
            ]
        )
        
        # 读取模型名称（使用 .env 中的 LLM 模型）
        model = _first_env(
            [
                "QWEN3_MODEL",
                "CONTEXTMIND_MODEL",
                "LLM_MODEL",
                "OPENAI_MODEL",
                "DEEPSEEK_MODEL",
                "QWEN_MODEL",
            ],
            default=DEFAULT_EMBEDDING_MODEL,
        )
        
        # 读取 Access Key（可选，某些网关需要）
        access_key = _first_env(
            [
                "QWEN3_ACCESS_KEY",
                "CONTEXTMIND_ACCESS_KEY",
                "LLM_ACCESS_KEY",
                "ACCESS_KEY",
            ]
        )
        
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            access_key=access_key,
        )


class EmbeddingClient:
    """
    Embedding 客户端
    
    支持两种方式：
    1. 本地加载模型（使用 sentence-transformers）
    2. 通过 API 调用（如 vLLM 部署的模型）
    """
    
    def __init__(self, config: Optional[EmbeddingConfig] = None):
        """
        初始化 Embedding 客户端
        
        Args:
            config: Embedding 配置，若为 None 则从环境变量加载
        """
        # 从环境变量或参数加载配置
        try:
            self.config = config or EmbeddingConfig.from_env()
        except ValueError as e:
            logger.warning(f"[EmbeddingClient] 配置加载失败: {e}")
            self.client = None
            self.local_model = None
            self.config = None
            self.embedding_supported = False
            return
        
        self.client = None
        self.local_model = None
        self.embedding_supported = False
        
        # 方式 1：本地加载模型
        if self.config.use_local:
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.error("[EmbeddingClient] sentence-transformers 未安装，无法加载本地模型")
                logger.info("[EmbeddingClient] 请安装: pip install sentence-transformers")
                self.embedding_supported = False
                return
            
            try:
                logger.info(f"[EmbeddingClient] 正在加载本地模型: {self.config.model_path}")
                self.local_model = SentenceTransformer(self.config.model_path)
                logger.info(f"[EmbeddingClient] 本地模型加载成功 - {self.config.model}")
                self.embedding_supported = True
            except Exception as e:
                logger.error(f"[EmbeddingClient] 本地模型加载失败: {e}")
                self.embedding_supported = False
            return
        
        # 方式 2：API 调用
        if not OPENAI_AVAILABLE:
            logger.warning("[EmbeddingClient] OpenAI 未安装，embedding 功能不可用")
            self.embedding_supported = False
            return
        
        # 构造 headers，如果需要 Access Key
        headers = {}
        if self.config.access_key:
            headers["access-key"] = self.config.access_key
        
        # 创建客户端
        try:
            self.client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                default_headers=headers if headers else None,
            )
            logger.info(f"[EmbeddingClient] API 客户端初始化成功 - 使用模型: {self.config.model}")
            # 标记为支持，但在首次调用时会验证
            self.embedding_supported = True
        except Exception as e:
            logger.error(f"[EmbeddingClient] API 客户端初始化失败: {e}")
            self.embedding_supported = False
    
    def generate_embedding(self, text: str) -> Optional[EmbeddingInfo]:
        """
        生成文本的 embedding 向量
        
        支持两种方式：
        1. 本地模型加载（sentence-transformers）
        2. API 调用（vLLM 等）
        
        Args:
            text: 输入文本
            
        Returns:
            EmbeddingInfo 对象，如果失败则返回 None
        """
        if not self.config:
            return None
        
        # 如果已知不支持 embedding，直接返回 None
        if not self.embedding_supported:
            return None
        
        if not text or not text.strip():
            logger.warning("[EmbeddingClient] 输入文本为空，跳过 embedding 生成")
            return None
        
        # 方式 1：本地模型
        if self.config.use_local and self.local_model:
            try:
                # 使用 sentence-transformers 生成向量（禁用进度条）
                vector = self.local_model.encode(text, convert_to_tensor=False, show_progress_bar=False).tolist()
                dimension = len(vector)
                
                logger.debug(f"[EmbeddingClient] 成功生成 embedding (本地) - model: {self.config.model}, dim: {dimension}, text: {text[:50]}...")
                
                return EmbeddingInfo(
                    model=self.config.model,
                    vector=vector,
                    dimension=dimension
                )
            except Exception as e:
                logger.error(f"[EmbeddingClient] 本地模型生成 embedding 失败: {e}")
                return None
        
        # 方式 2：API 调用
        if not self.client:
            return None
        
        try:
            # 使用 embeddings API（OpenAI 兼容）
            response = self.client.embeddings.create(
                model=self.config.model,
                input=text
            )
            
            # 检查响应数据
            if not response or not hasattr(response, 'data'):
                logger.warning("[EmbeddingClient] API 响应格式错误：缺少 data 字段")
                return None
            
            if not response.data or len(response.data) == 0:
                logger.warning("[EmbeddingClient] API 返回空数据")
                return None
            
            # 检查第一个数据项
            first_data = response.data[0]
            if not hasattr(first_data, 'embedding'):
                logger.warning("[EmbeddingClient] API 数据缺少 embedding 字段")
                return None
            
            # 提取向量
            vector = first_data.embedding
            if not vector or len(vector) == 0:
                logger.warning("[EmbeddingClient] embedding 向量为空")
                return None
            
            dimension = len(vector)
            
            logger.debug(f"[EmbeddingClient] 成功生成 embedding (API) - model: {self.config.model}, dim: {dimension}, text: {text[:50]}...")
            
            return EmbeddingInfo(
                model=self.config.model,
                vector=vector,
                dimension=dimension
            )
            
        except AttributeError as e:
            logger.error(f"[EmbeddingClient] API 响应格式错误: {e}")
            return None
        except Exception as e:
            error_str = str(e)
            # 检查是否是模型不支持 embedding 的错误
            if "does not appear to be an embedding model" in error_str or "BadRequestError" in error_str:
                logger.error(f"[EmbeddingClient] 模型 {self.config.model} 不支持 embedding 生成")
                logger.error("[EmbeddingClient] 请配置专门的 embedding 模型（如 bge-large-zh-v1.5）")
                logger.info("[EmbeddingClient] 配置示例：")
                logger.info("  方式1 - 本地加载: EMBEDDING_MODEL_PATH=/path/to/model")
                logger.info("  方式2 - API调用: EMBEDDING_MODEL=bge-large-zh-v1.5, EMBEDDING_BASE_URL=http://localhost:8001/v1")
                # 标记为不支持，避免后续重复尝试
                self.embedding_supported = False
            else:
                logger.error(f"[EmbeddingClient] 生成 embedding 失败: {e}")
            return None


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
    
    # 计算余弦相似度
    similarity = cosine_similarity(emb1.vector, emb2.vector)
    return similarity, True


# 全局单例客户端（延迟初始化）
_global_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> Optional[EmbeddingClient]:
    """
    获取全局 Embedding 客户端（单例模式）
    
    Returns:
        EmbeddingClient 实例，如果配置不可用则返回 None
    """
    global _global_client
    
    if _global_client is None:
        _global_client = EmbeddingClient()
    
    return _global_client
