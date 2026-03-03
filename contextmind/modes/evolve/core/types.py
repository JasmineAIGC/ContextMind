"""Evolve 中使用的枚举类型，用于知识类型、记忆类型和消息角色。"""

from enum import Enum


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
    
    # 1. 用户画像类 (User Profile) - 4 种
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


class MessageRole(str, Enum):
    """对话消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ContextSource(str, Enum):
    """上下文项来源——用于在上下文组装时确定优先级和过滤条件。"""
    MEMORY = "memory"    # 从历史对话中提取的长期知识
    RAG = "rag"          # 从外部文档库检索的内容
    HISTORY = "history"  # 当前会话的近期消息
