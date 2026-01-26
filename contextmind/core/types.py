"""
Knowledge Types Module

Data models for knowledge representation and storage.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class KnowledgeType(str, Enum):
    """
    从对话中提取的知识类型 (40种)
    
    分为10大类：用户画像、认知、行为、意图、关系、知识、情感、策略、上下文、多轮对话
    """
    # 原有9种基础类型
    PREFERENCE = "preference"  # 用户偏好（喜欢/不喜欢）
    FACT = "fact"              # 关于用户或主题的事实
    EVENT = "event"            # 事件或行为
    INTENT = "intent"          # 用户意图（想要做什么）
    NEED = "need"              # 用户需求（需要什么）
    OPINION = "opinion"        # 用户观点/看法
    HABIT = "habit"            # 用户习惯
    CONSTRAINT = "constraint"  # 约束条件（如预算、时间限制）
    INTEREST = "interest"      # 用户兴趣
    
    # 1. 用户画像类 (User Profile) - 4种
    USER_INFO = "user_info"            # 基本信息（年龄、职业、位置、姓名等）
    PERSONALITY = "personality"        # 性格特征
    VALUES = "values"                  # 价值观
    LIFESTYLE = "lifestyle"            # 生活方式
    
    # 2. 认知类 (Cognitive) - 3种新增（opinion已有）
    BELIEF = "belief"                  # 信念
    ATTITUDE = "attitude"              # 态度
    VALUE_JUDGMENT = "value_judgment"  # 价值判断
    
    # 3. 行为类 (Behavioral) - 3种新增（event, habit已有）
    EXPERIENCE = "experience"          # 经验
    SKILL = "skill"                    # 技能
    ACHIEVEMENT = "achievement"        # 成就
    
    # 4. 意图类 (Intentional) - 3种新增（intent, need已有）
    GOAL = "goal"                      # 目标
    PLAN = "plan"                      # 计划
    EXPECTATION = "expectation"        # 期望
    
    # 5. 关系类 (Relational) - 3种
    RELATIONSHIP = "relationship"              # 社交关系
    EMOTIONAL_CONNECTION = "emotional_connection"  # 情感连接
    INFLUENCE = "influence"                    # 影响因素
    
    # 6. 知识类 (Epistemic) - 3种新增（fact已有）
    PROCEDURAL = "procedural"          # 程序性知识（如何做某事）
    DOMAIN_KNOWLEDGE = "domain_knowledge"  # 领域知识
    COMMON_SENSE = "common_sense"      # 常识
    
    # 7. 情感类 (Emotional) - 2种新增（preference已有）
    EMOTION = "emotion"                # 情绪状态
    SENTIMENT = "sentiment"            # 情感倾向
    
    # 8. 策略类 (Strategic) - 4种
    SOLUTION = "solution"              # 解决方案
    STRATEGY = "strategy"              # 策略
    BEST_PRACTICE = "best_practice"    # 最佳实践
    LESSON_LEARNED = "lesson_learned"  # 经验教训
    
    # 9. 上下文类 (Contextual) - 2种新增（constraint, interest已有）
    TOPIC = "topic"                    # 话题
    SCENARIO = "scenario"              # 场景
    
    # 10. 多轮对话类 (Multi-turn) - 4种
    CONVERSATION_PATTERN = "conversation_pattern"        # 对话模式
    TOPIC_EVOLUTION = "topic_evolution"                  # 主题演变
    PROBLEM_SOLUTION_SEQ = "problem_solution_sequence"   # 问题-解决序列
    CAUSALITY = "causality"                              # 因果关系


class MemoryType(str, Enum):
    """记忆存储类型"""
    SEMANTIC = "semantic"      # 语义/向量存储
    KEYWORD = "keyword"        # 关键词存储
    STRUCTURED = "structured"  # 结构化数据存储


@dataclass
class EmbeddingInfo:
    """
    Embedding向量信息
    
    支持多种embedding模型，便于跨模型检索和模型升级
    """
    model: str  # embedding模型名称
    vector: List[float]  # 向量数据
    dimension: int  # 向量维度
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ScoreInfo:
    """
    知识评分信息
    
    四维评分体系用于检索排序和知识淡化
    """
    importance: float = 0.5  # 重要性分数（基于访问频率和知识类型）
    confidence: float = 0.5  # 置信度分数（基于提取方法和验证次数）
    relevance: float = 0.5  # 相关性分数（基于时间衰减和上下文匹配）
    quality: float = 0.5  # 质量分数（基于来源可靠性和内容完整性）


@dataclass
class VersionRecord:
    """
    知识版本记录
    
    追踪知识的演化历史，支持回滚和审计
    """
    version: int
    content: str
    updated_at: datetime
    update_reason: str
    confidence_delta: float = 0.0
    updated_by: str = "system"


@dataclass
class Knowledge:
    """
    优化的知识存储模型
    
    设计目标:
    1. 检索优化 - 多层次索引，支持向量+关键词混合检索
    2. 便于更新 - 版本追踪，冲突检测，智能合并
    3. 多模态支持 - 支持多种embedding算法和模型
    4. 算法驱动 - 动态评分，自动淡化，智能排序
    
    Attributes:
        memory_id: 唯一标识符
        user_id: 所属用户ID
        session_id: 所属会话ID（可选）
        
        knowledge_type: 知识类型 (preference/fact/event)
        content: 核心文本内容
        summary: 简短摘要（可选）
        
        embeddings: 多embedding向量字典 {name: EmbeddingInfo}
        scores: 四维评分信息
        version_history: 版本历史记录
        
        extraction_method: 提取方法 ('rule' 或 'llm')
        source_message_ids: 源消息ID列表（完整追溯）
        
        created_at: 创建时间
        updated_at: 最后更新时间
        last_accessed: 最后访问时间
        access_count: 访问次数
        
        status: 状态 (active/archived/deleted)
        metadata: 扩展元数据
            - category: 细分类别
            - tags: 标签列表
            - keywords: 关键词列表
            - entities: 实体列表 [{text, type, sentiment}]
            - relationships: 关系列表 [{relation_type, target, strength}]
            - context: 上下文信息
            - conflicts: 冲突记录
    
    参考文档: docs/KNOWLEDGE_STORAGE_DESIGN.md
    """
    # 知识内容（无默认值字段必须在前）
    knowledge_type: KnowledgeType  # 保持兼容性
    content: str
    
    # 核心标识
    memory_id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    user_id: str = ""
    session_id: Optional[str] = None
    
    # 其他内容
    summary: Optional[str] = None
    
    # 多模态支持
    embeddings: Dict[str, EmbeddingInfo] = field(default_factory=dict)
    
    # 评分系统
    scores: ScoreInfo = field(default_factory=ScoreInfo)
    
    # 版本历史
    version_history: List[VersionRecord] = field(default_factory=list)
    
    # 提取信息
    extraction_method: str = "rule"  # 'rule' or 'llm'
    source_message_ids: List[str] = field(default_factory=list)
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    
    # 访问统计
    access_count: int = 0
    
    # 状态
    status: str = "active"  # active/archived/deleted
    
    # 扩展元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 兼容性属性
    @property
    def type(self) -> KnowledgeType:
        """兼容性别名: knowledge_type -> type"""
        return self.knowledge_type
    
    @property
    def confidence(self) -> float:
        """兼容性别名: scores.confidence -> confidence"""
        return self.scores.confidence
    
    @property
    def importance_score(self) -> float:
        """兼容性别名: scores.importance -> importance_score"""
        return self.scores.importance
    
    @property
    def timestamp(self) -> datetime:
        """兼容性别名: created_at -> timestamp"""
        return self.created_at
    
    @property
    def source(self) -> str:
        """兼容性别名: metadata中的source"""
        return self.metadata.get("source", "")
    
    def to_storage_dict(self) -> Dict[str, Any]:
        """
        转换为存储格式
        
        完整的JSON Schema参考: docs/KNOWLEDGE_STORAGE_DESIGN.md
        """
        return {
            "memory_id": self.memory_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "type": self.knowledge_type.value,
            "content": self.content,
            "summary": self.summary,
            "embeddings": {
                name: {
                    "model": emb.model,
                    "vector": emb.vector,
                    "dimension": emb.dimension,
                    "created_at": emb.created_at.isoformat()
                }
                for name, emb in self.embeddings.items()
            },
            "metadata": self.metadata,
            "scores": {
                "importance": self.scores.importance,
                "confidence": self.scores.confidence,
                "relevance": self.scores.relevance,
                "quality": self.scores.quality
            },
            "version_history": [
                {
                    "version": v.version,
                    "content": v.content,
                    "updated_at": v.updated_at.isoformat(),
                    "update_reason": v.update_reason,
                    "confidence_delta": v.confidence_delta,
                    "updated_by": v.updated_by
                }
                for v in self.version_history
            ],
            "extraction_method": self.extraction_method,
            "source_message_ids": self.source_message_ids,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
            "status": self.status
        }
