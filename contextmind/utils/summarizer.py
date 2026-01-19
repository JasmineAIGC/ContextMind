"""
ConversationSummarizer - 对话摘要工具

用于将长对话历史压缩为摘要，减少prompt token使用。
保留最近2-3轮完整对话，其余转为摘要。
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass
from ..data_models import Message


@dataclass
class SummarizedHistory:
    """摘要后的对话历史"""
    summary: str  # 早期对话的摘要
    recent_messages: List[Message]  # 最近的完整消息
    metadata: dict  # 元数据（如摘要的轮数、总轮数等）


class ConversationSummarizer:
    """
    对话摘要器
    
    将长对话历史分为两部分：
    1. 早期对话 → 摘要
    2. 最近2-3轮 → 保留完整内容
    
    这样可以：
    - 减少prompt token使用
    - 保留最新上下文的完整性
    - 提供历史对话的概览
    """
    
    def __init__(
        self,
        recent_turns: int = 3,
        summarize_threshold: int = 5,
        llm_client: Optional[any] = None,
    ):
        """
        初始化摘要器
        
        Args:
            recent_turns: 保留最近几轮完整对话（默认3轮）
            summarize_threshold: 超过多少轮才开始摘要（默认5轮）
            llm_client: LLM客户端，用于生成摘要（可选，不提供则使用规则）
        """
        self.recent_turns = recent_turns
        self.summarize_threshold = summarize_threshold
        self.llm_client = llm_client
    
    def summarize(self, messages: List[Message]) -> SummarizedHistory:
        """
        摘要对话历史
        
        Args:
            messages: 完整的消息列表
            
        Returns:
            摘要后的对话历史
        """
        if len(messages) <= self.summarize_threshold:
            # 对话较短，不需要摘要
            return SummarizedHistory(
                summary="",
                recent_messages=messages,
                metadata={
                    'total_turns': len(messages),
                    'summarized_turns': 0,
                    'recent_turns': len(messages),
                }
            )
        
        # 计算分界点：最近N轮完整保留，其余摘要
        # 每轮 = 1个user + 1个assistant
        split_point = len(messages) - (self.recent_turns * 2)
        split_point = max(0, split_point)
        
        # 分割消息
        to_summarize = messages[:split_point]
        recent = messages[split_point:]
        
        # 生成摘要
        if not to_summarize:
            summary = ""
        elif self.llm_client:
            summary = self._llm_summarize(to_summarize)
        else:
            summary = self._rule_based_summarize(to_summarize)
        
        return SummarizedHistory(
            summary=summary,
            recent_messages=recent,
            metadata={
                'total_turns': len(messages),
                'summarized_turns': len(to_summarize),
                'recent_turns': len(recent),
            }
        )
    
    def _rule_based_summarize(self, messages: List[Message]) -> str:
        """
        基于规则的简单摘要
        
        Args:
            messages: 要摘要的消息列表
            
        Returns:
            摘要文本
        """
        if not messages:
            return ""
        
        # 统计信息
        user_messages = [m for m in messages if m.role.value == "user"]
        assistant_messages = [m for m in messages if m.role.value == "assistant"]
        
        # 提取关键主题词（简单实现）
        all_text = " ".join([m.content for m in user_messages])
        
        # 基础摘要模板
        summary_parts = []
        
        # 对话轮数
        turns = len(user_messages)
        summary_parts.append(f"前{turns}轮对话")
        
        # 提取关键词（简单版本：找出现频率高的词）
        keywords = self._extract_keywords(all_text, top_k=3)
        if keywords:
            summary_parts.append(f"主要讨论: {', '.join(keywords)}")
        
        # 如果有用户的明确拒绝/接受，提取出来
        rejections = []
        acceptances = []
        for msg in user_messages:
            content = msg.content
            if any(word in content for word in ['不需要', '不想', '拒绝', '不要']):
                # 简单提取拒绝对象
                import re
                matches = re.findall(r'不(需要|想|要)(.{2,8})', content)
                for match in matches:
                    obj = match[1].strip('，。！？,.!?')
                    if obj and len(obj) <= 6:
                        rejections.append(obj)
            
            if any(word in content for word in ['我要', '我想', '我需要', '同意', '好的']):
                # 可以提取意向
                pass
        
        if rejections:
            summary_parts.append(f"用户明确不需要: {', '.join(set(rejections[:2]))}")
        
        return "；".join(summary_parts)
    
    def _extract_keywords(self, text: str, top_k: int = 3) -> List[str]:
        """
        提取文本中的关键词
        
        简单实现：找出现频率较高的2-4字词组
        """
        import re
        from collections import Counter
        
        # 停用词
        stopwords = {'不是', '没有', '怎么', '什么', '如果', '可以', '这个', '那个', '就是', '还是'}
        
        # 提取2-4字的短语
        phrases = []
        # 匹配中文词组
        for length in [4, 3, 2]:
            pattern = f'[\u4e00-\u9fa5]{{{length}}}'
            matches = re.findall(pattern, text)
            phrases.extend(matches)
        
        # 过滤停用词，统计频率
        filtered = [p for p in phrases if p not in stopwords and len(p) >= 2]
        if not filtered:
            return []
        
        # 统计并取top_k
        counter = Counter(filtered)
        top_phrases = [phrase for phrase, count in counter.most_common(top_k) if count > 1]
        
        return top_phrases
    
    def _llm_summarize(self, messages: List[Message]) -> str:
        """
        使用LLM生成摘要
        
        Args:
            messages: 要摘要的消息列表
            
        Returns:
            摘要文本
        """
        if not messages:
            return ""
        
        # 构建对话文本
        conversation = "\n".join(
            f"{msg.role.value}: {msg.content}"
            for msg in messages
        )
        
        # 构建摘要prompt
        prompt = f"""请将以下对话摘要为一句话，重点提取：
1. 用户的主要需求或问题
2. 用户的明确拒绝或接受
3. 关键信息

对话:
{conversation}

摘要（一句话，不超过50字）:"""
        
        try:
            # 调用LLM
            _, summary = self.llm_client.generate(prompt)
            summary = summary.strip()
            
            # 限制长度
            if len(summary) > 100:
                summary = summary[:97] + "..."
            
            return summary
        except Exception as e:
            # 回退到规则方法
            return self._rule_based_summarize(messages)
    
    def format_for_prompt(self, summarized: SummarizedHistory) -> str:
        """
        格式化摘要结果用于prompt
        
        Args:
            summarized: 摘要后的对话历史
            
        Returns:
            格式化的文本，可直接用于prompt
        """
        parts = []
        
        # 添加摘要（如果有）
        if summarized.summary:
            parts.append(f"【早期对话摘要】{summarized.summary}")
        
        # 添加最近的完整对话
        if summarized.recent_messages:
            parts.append("【最近对话】")
            for msg in summarized.recent_messages:
                parts.append(f"{msg.role.value}: {msg.content}")
        
        return "\n".join(parts)
