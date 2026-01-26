"""
基于LLM的知识提取器
"""

from typing import List, Optional
import json
import re

from .base import BaseExtractor
from .rule import RuleBasedExtractor
from ...core.models import Message, ExtractionConfig, DEFAULT_MEMORY_CONFIG, get_logger
from ...core.types import Knowledge, KnowledgeType, ScoreInfo
from ...utils.embedding import get_embedding_client

logger = get_logger(__name__)


class LLMBasedExtractor(BaseExtractor):
    """
    基于LLM的知识提取器（推荐使用）
    
    ✨ 使用LLM的语义理解能力从对话中提取结构化知识
    📊 支持全部40种知识类型的智能提取
    
    相比规则提取（RuleBasedExtractor），LLM提取器能够：
    1. ✅ 理解语义和上下文（不依赖关键词匹配）
    2. ✅ 识别隐含知识和意图
    3. ✅ 处理同义词和不同表达方式
    4. ✅ 自动分类到40种知识类型
    5. ✅ 提取复杂的关系和模式
    6. ✅ 更高的准确率和召回率
    
    支持的40种知识类型分10大类：
    - 用户画像（4种）：user_info, personality, values, lifestyle
    - 认知（4种）：opinion, belief, attitude, value_judgment
    - 行为（6种）：event, habit, experience, skill, achievement
    - 意图（6种）：intent, need, goal, plan, expectation
    - 关系（3种）：relationship, emotional_connection, influence
    - 知识（4种）：fact, procedural, domain_knowledge, common_sense
    - 情感（3种）：preference, emotion, sentiment
    - 策略（4种）：solution, strategy, best_practice, lesson_learned
    - 上下文（4种）：constraint, interest, topic, scenario
    - 多轮（4种）：conversation_pattern, topic_evolution, problem_solution_sequence, causality
    """
    
    # 静态类型映射表（优化查找性能）
    _TYPE_MAPPING = {
        kt.value.lower(): kt for kt in KnowledgeType
    }
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        config: Optional[ExtractionConfig] = None
    ):
        """
        初始化LLM知识提取器
        
        Args:
            llm_client: LLM客户端（需要有generate方法）
            config: 提取配置
        """
        self.llm_client = llm_client
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
        
        if llm_client:
            logger.info("[LLMBasedExtractor] 初始化完成 - 使用LLM自动提取")
        else:
            logger.warning("[LLMBasedExtractor] 未提供LLM客户端 - 将回退到规则提取")
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        使用LLM提取知识
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识列表
        """
        # 如果没有LLM客户端，回退到规则提取
        if not self.llm_client:
            logger.debug("[LLMBasedExtractor] 回退到规则提取 (无LLM客户端)")
            fallback = RuleBasedExtractor(self.config)
            return await fallback.extract(messages)
        
        logger.info(f"[LLMBasedExtractor] 开始LLM知识提取 - 处理 {len(messages)} 条消息")
        
        # 构建对话文本
        conversation_text = self._build_conversation_text(messages)
        
        if not conversation_text:
            logger.warning("[LLMBasedExtractor] 对话文本为空，跳过提取")
            return []
        
        # 使用LLM提取知识
        try:
            extracted_data = await self._extract_with_llm(conversation_text)
            knowledge_list = self._parse_llm_response(extracted_data, messages)
            
            # 过滤低置信度知识
            before_filter = len(knowledge_list)
            knowledge_list = [k for k in knowledge_list if k.confidence >= self.config.min_confidence]
            filtered_count = before_filter - len(knowledge_list)
            
            if filtered_count > 0:
                logger.debug(f"[LLMBasedExtractor] 过滤低置信度知识: {filtered_count} 条")
            
            logger.info(f"[LLMBasedExtractor] ✓ 知识提取完成 - 总计 {len(knowledge_list)} 条有效知识")
            
            if knowledge_list:
                logger.debug(f"[LLMBasedExtractor] 提取的知识详情:")
                for i, k in enumerate(knowledge_list[:5], 1):
                    logger.debug(f"  {i}. [{k.knowledge_type.value}] {k.content[:60]}... (置信度: {k.confidence:.2f})")
                if len(knowledge_list) > 5:
                    logger.debug(f"  ... 以及其他 {len(knowledge_list) - 5} 条知识")
            
            return knowledge_list
            
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] LLM提取失败: {e}, 回退到规则提取")
            fallback = RuleBasedExtractor(self.config)
            return await fallback.extract(messages)
    
    def _build_conversation_text(self, messages: List[Message]) -> str:
        """构建对话文本"""
        lines = []
        for msg in messages:
            role = "用户" if msg.role.value == "user" else "助手"
            lines.append(f"{role}: {msg.content}")
        return "\n".join(lines)
    
    async def _extract_with_llm(self, conversation_text: str) -> str:
        """
        使用LLM提取知识
        
        Args:
            conversation_text: 对话文本
            
        Returns:
            LLM返回的结构化知识（JSON格式字符串）
        """
        # 构建提取提示词 - 支持40种知识类型
        system_prompt = """你是一个专业的知识提取助手。你的任务是从对话中提取结构化的知识信息。

**关键要求**:
1. **总结提炼**：不要直接复制对话原文，而是总结归纳成简洁的知识点
2. **准确分类**：必须使用下面40种类型之一，不要使用UNKNOWN或其他类型
3. **合理置信度**：根据信息的明确程度合理评分（0.7-1.0之间，严格筛选）
4. **精选重要信息**：只提取真正有价值的核心知识
5. **完整整合**：将分散在多轮对话中的相关信息整合成完整的知识点
6. **避免重复**：不要提取已经在之前对话中提到过的相同或相似信息

**支持的40种知识类型**:

**1. 用户画像类(4种)**:
- user_info: 用户基本信息（年龄、职业、姓名、居住地）
- personality: 性格特征（外向/内向、乐观/悲观）
- values: 价值观和人生观
- lifestyle: 生活方式和日常习惯

**2. 认知类(4种)**:
- opinion: 观点和看法
- belief: 信念和信仰
- attitude: 态度和立场
- value_judgment: 价值判断

**3. 行为类(6种)**:
- event: 发生的事件和活动
- habit: 习惯和常规行为
- experience: 过往经历
- skill: 技能和能力
- achievement: 成就和里程碑

**4. 意图类(6种)**:
- intent: 意图和打算
- need: 需求和要求
- goal: 目标和追求
- plan: 具体计划和安排（含时间/地点）
- expectation: 期望和预期

**5. 关系类(3种)**:
- relationship: 社交关系
- emotional_connection: 情感连接
- influence: 影响因素

**6. 知识类(4种)**:
- fact: 客观事实
- procedural: 程序性知识（如何做某事）
- domain_knowledge: 领域专业知识
- common_sense: 常识

**7. 情感类(3种)**:
- preference: 偏好和喜好
- emotion: 情绪状态
- sentiment: 情感倾向

**8. 策略类(4种)**:
- solution: 解决方案
- strategy: 策略方法
- best_practice: 最佳实践
- lesson_learned: 经验教训

**9. 上下文类(4种)**:
- constraint: 约束条件
- interest: 兴趣爱好（长期的）
- topic: 讨论话题
- scenario: 场景和情境

**10. 多轮对话分析(4种)**:
- conversation_pattern: 对话模式
- topic_evolution: 话题演变
- problem_solution_sequence: 问题解决序列
- causality: 因果关系

**输出格式**:
```json
{
  "knowledge": [
    {
      "content": "用户是软件工程师，25岁",
      "type": "user_info",
      "confidence": 0.95
    }
  ]
}
```

**置信度评分标准（严格筛选）**:
- 0.90-1.00: 用户明确陈述的核心事实信息
- 0.75-0.89: 从对话中可以合理推断的重要信息
- 0.70-0.74: 需要一定推理但仍重要的信息
- <0.70: 不要提取，质量不够高

**提取原则**:
- 只提取真正有价值的核心知识点
- 优先提取用户的核心信息（user_info, plan, preference, goal等）
- 不要提取次要的、模糊的、重复的信息

**提取示例**:

❌ **错误示例**（直接复制对话、类型错误）:
对话:
用户: 想去丽江
助手: 什么时候去呢？
用户: 过两个月

错误提取:
- {"content": "想去丽江", "type": "UNKNOWN", "confidence": 0.5}  ← 类型错误、置信度过低
- {"content": "过两个月", "type": "event", "confidence": 0.3}  ← 分类错误、信息不完整

✅ **正确示例**（总结归纳、准确分类）:
- {"content": "用户想去丽江旅行", "type": "intent", "confidence": 0.85}
- {"content": "用户计划两个月后去丽江", "type": "plan", "confidence": 0.85}

**不要提取的内容**:
- 助手的回复（只提取用户信息）
- 简单的确认回复（"好的"、"嗯"、"没有"）
- 问候语（"你好"、"再见"）
- 无实际信息内容的对话

请严格按照要求提取知识，返回有效的JSON格式。"""
        
        user_prompt = f"""请从以下对话中提取结构化知识：

{conversation_text}

请返回JSON格式的提取结果。"""
        
        # 合并system_prompt和user_prompt为完整的prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # 调用LLM（SimpleLLMClient只接受单个prompt参数）
        try:
            if hasattr(self.llm_client, 'generate_async'):
                # 异步调用
                _, response = await self.llm_client.generate_async(full_prompt)
            elif hasattr(self.llm_client, 'generate'):
                # 同步调用（返回 reasoning, content 元组）
                _, response = self.llm_client.generate(full_prompt)
            else:
                raise ValueError("LLM客户端缺少generate或generate_async方法")
            
            return response
            
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] LLM调用失败: {e}")
            raise
    
    def _parse_llm_response(self, llm_response: str, messages: List[Message]) -> List[Knowledge]:
        """
        解析LLM返回的JSON格式知识
        
        Args:
            llm_response: LLM返回的文本
            messages: 原始消息列表（用于获取消息ID）
            
        Returns:
            Knowledge对象列表
        """
        knowledge_list = []
        
        try:
            # 尝试提取JSON部分（LLM可能返回带有markdown代码块的文本）
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析整个响应
                json_str = llm_response.strip()
            
            # 解析JSON
            data = json.loads(json_str)
            
            # 提取knowledge列表
            if 'knowledge' in data:
                for item in data['knowledge']:
                    try:
                        # 获取内容和类型
                        content = item.get('content', '').strip()
                        type_str = item.get('type', '').lower()
                        confidence = float(item.get('confidence', 0.8))
                        
                        # **验证1**: 跳过无效类型（UNKNOWN等）
                        if not type_str or type_str in ['unknown', 'none', '']:
                            logger.debug(f"[LLMBasedExtractor] 跳过无效类型的知识: type={type_str}, content={content[:50]}")
                            continue
                        
                        # **验证2**: 内容不能为空或过短（至少5个字符）
                        if not content or len(content) < 5:
                            logger.debug(f"[LLMBasedExtractor] 跳过内容过短的知识: {content}")
                            continue
                        
                        # **验证3**: 跳过无意义的简短回复和过于简单的描述
                        meaningless_phrases = {'好的', '嗯', '哦', '没有', '是的', '不是', '可以', '不可以', '你好', '再见', '谢谢', '不客气'}
                        if content in meaningless_phrases or content.strip() in meaningless_phrases:
                            logger.debug(f"[LLMBasedExtractor] 跳过无意义短语: {content}")
                            continue
                        
                        # **验证3.5**: 跳过过于简短且信息量低的内容（少于8个汉字且不含实体信息）
                        if len(content) < 8 and not any(char.isdigit() or char in '年月日时' for char in content):
                            logger.debug(f"[LLMBasedExtractor] 跳过信息量过低的短内容: {content}")
                            continue
                        
                        # **验证4**: 置信度必须合理（0.72-1.0）- 再次提高阈值
                        if confidence < 0.72:
                            logger.debug(f"[LLMBasedExtractor] 跳过低置信度知识: confidence={confidence}, content={content[:50]}")
                            continue
                        if confidence > 1.0:
                            logger.warning(f"[LLMBasedExtractor] 置信度>1.0，调整为1.0: {confidence}")
                            confidence = 1.0
                        
                        # 使用静态映射表进行O(1)查找
                        knowledge_type = self._TYPE_MAPPING.get(type_str)
                        
                        # 如果没找到匹配，跳过（不再使用默认值）
                        if knowledge_type is None:
                            logger.warning(f"[LLMBasedExtractor] 未知知识类型 '{type_str}'，跳过该知识: {content[:50]}")
                            continue
                        
                        # 创建Knowledge对象
                        knowledge = Knowledge(
                            content=content,
                            knowledge_type=knowledge_type,
                            scores=ScoreInfo(confidence=confidence),
                            extraction_method='llm',
                            source_message_ids=[getattr(msg, 'id', '') for msg in messages],
                            metadata={
                                'category': item.get('category', ''),
                                'entities': item.get('entities', []),
                                'keywords': item.get('keywords', []),
                                'llm_extracted': True
                            }
                        )
                        
                        # 生成 embedding
                        embedding_client = get_embedding_client()
                        if embedding_client:
                            embedding_info = embedding_client.generate_embedding(content)
                            if embedding_info:
                                knowledge.embeddings['default'] = embedding_info
                        
                        knowledge_list.append(knowledge)
                        
                    except Exception as e:
                        logger.warning(f"[LLMBasedExtractor] 解析知识项失败: {e}, 项: {item}")
                        continue
            
            logger.debug(f"[LLMBasedExtractor] 成功解析 {len(knowledge_list)} 条知识")
            
        except json.JSONDecodeError as e:
            logger.error(f"[LLMBasedExtractor] JSON解析失败: {e}")
            logger.debug(f"[LLMBasedExtractor] LLM响应: {llm_response[:200]}...")
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] 解析LLM响应失败: {e}")
        
        return knowledge_list
