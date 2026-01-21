"""
对话摘要模块

提供对话历史的摘要功能，支持两种摘要策略：
1. 基于规则的摘要（快速，零成本）
2. LLM生成的摘要（高质量，需要API调用）
"""

from dataclasses import dataclass
from typing import List, Optional
from ..models import ContextItem, MessageRole, get_logger

logger = get_logger(__name__)


@dataclass
class SummarizationConfig:
    """对话摘要配置"""
    
    # 触发条件
    summarize_threshold: int = 15  # 触发摘要的对话轮数阈值
    keep_recent_turns: int = 5  # 摘要后保留的最近对话轮数
    
    # 摘要方式
    method: str = "rule"  # 'rule' 或 'llm'
    
    # 规则摘要配置
    max_summary_length: int = 200  # 最大摘要长度（字符）
    extract_key_points: bool = True  # 是否提取关键点
    
    # LLM摘要配置（如果使用LLM）
    llm_max_tokens: int = 150  # LLM摘要最大token数
    llm_temperature: float = 0.3  # LLM温度（越低越稳定）


class ConversationSummarizer:
    """对话摘要器"""
    
    def __init__(self, config: Optional[SummarizationConfig] = None, llm_client=None):
        """初始化摘要器
        
        Args:
            config: 摘要配置
            llm_client: LLM客户端（仅当使用LLM摘要时需要）
        """
        self.config = config or SummarizationConfig()
        self.llm_client = llm_client
        
        if self.config.method == "llm" and llm_client is None:
            logger.warning("[Summarizer] LLM摘要模式需要llm_client，将降级为规则摘要")
            self.config.method = "rule"
    
    def should_summarize(self, history_length: int) -> bool:
        """判断是否需要生成摘要
        
        Args:
            history_length: 对话历史长度（轮数）
            
        Returns:
            是否需要摘要
        """
        return history_length > self.config.summarize_threshold
    
    def summarize(self, history_items: List[ContextItem]) -> str:
        """生成对话摘要
        
        Args:
            history_items: 需要摘要的对话历史
            
        Returns:
            摘要文本
        """
        if not history_items:
            return ""
        
        logger.info(f"[Summarizer] 开始生成摘要 (方法: {self.config.method}, 对话轮数: {len(history_items)})")
        
        if self.config.method == "llm":
            summary = self._summarize_with_llm(history_items)
        else:
            summary = self._summarize_with_rules(history_items)
        
        logger.info(f"[Summarizer] ✓ 摘要生成完成 (长度: {len(summary)} 字符)")
        logger.debug(f"[Summarizer] 摘要内容: {summary}")
        
        return summary
    
    def _summarize_with_rules(self, history_items: List[ContextItem]) -> str:
        """基于规则的摘要
        
        提取关键信息：
        - 用户的自我介绍和基本信息
        - 用户表达的偏好和需求
        - 重要的事实陈述
        - 话题的转换点
        
        Args:
            history_items: 对话历史
            
        Returns:
            摘要文本
        """
        key_points = []
        
        # 提取关键信息
        for item in history_items:
            content = item.content
            
            # 跳过太短的对话
            if len(content) < 10:
                continue
            
            # 提取用户的重要陈述
            if "user:" in content.lower():
                # 自我介绍相关
                if any(keyword in content for keyword in ["我是", "我叫", "我的", "我在"]):
                    key_points.append(content.replace("user:", "").replace("User:", "").strip())
                
                # 偏好相关
                elif any(keyword in content for keyword in ["喜欢", "不喜欢", "偏好", "想要", "需要", "希望"]):
                    key_points.append(content.replace("user:", "").replace("User:", "").strip())
                
                # 事实陈述
                elif any(keyword in content for keyword in ["是", "有", "没有", "已经", "正在"]):
                    key_points.append(content.replace("user:", "").replace("User:", "").strip())
        
        # 去重并限制长度
        seen = set()
        unique_points = []
        for point in key_points:
            # 简单的去重：检查前30个字符
            key = point[:30]
            if key not in seen:
                seen.add(key)
                unique_points.append(point)
        
        # 拼接摘要
        if unique_points:
            summary = "对话摘要: " + "；".join(unique_points[:8])  # 最多8个要点
        else:
            # 降级方案：提取前几轮对话的主要内容
            summary = "对话摘要: " + " ".join(
                item.content.split(":")[1].strip() if ":" in item.content else item.content
                for item in history_items[:3]
            )
        
        # 截断过长的摘要
        if len(summary) > self.config.max_summary_length:
            summary = summary[:self.config.max_summary_length] + "..."
        
        return summary
    
    async def _summarize_with_llm(self, history_items: List[ContextItem]) -> str:
        """使用LLM生成摘要
        
        Args:
            history_items: 对话历史
            
        Returns:
            摘要文本
        """
        if not self.llm_client:
            logger.warning("[Summarizer] LLM客户端不可用，降级为规则摘要")
            return self._summarize_with_rules(history_items)
        
        # 构建对话文本
        dialogue_text = "\n".join(item.content for item in history_items)
        
        # LLM摘要prompt
        prompt = f"""请简洁地总结以下对话的关键内容，包括：
1. 用户的基本信息和自我介绍
2. 用户表达的偏好、需求和观点
3. 重要的事实和信息
4. 主要话题

要求：
- 简洁明了，不超过150字
- 保留关键信息，去除冗余
- 使用第三人称叙述

对话内容：
{dialogue_text}

摘要："""
        
        try:
            # 调用LLM
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.config.llm_max_tokens,
                temperature=self.config.llm_temperature
            )
            
            summary = response.strip()
            logger.info(f"[Summarizer] ✓ LLM摘要成功")
            return summary
            
        except Exception as e:
            logger.error(f"[Summarizer] LLM摘要失败: {e}")
            logger.info("[Summarizer] 降级为规则摘要")
            return self._summarize_with_rules(history_items)
    
    def get_summary_and_recent(self, all_history: List[ContextItem]) -> tuple[Optional[str], List[ContextItem]]:
        """获取摘要和最近对话
        
        Args:
            all_history: 所有对话历史
            
        Returns:
            (摘要文本, 最近对话列表)
        """
        total_turns = len(all_history)
        
        if not self.should_summarize(total_turns):
            # 不需要摘要，返回所有历史
            return None, all_history
        
        # 需要摘要：对早期对话生成摘要，保留最近对话
        summary_turns = total_turns - self.config.keep_recent_turns
        
        # 生成摘要
        summary = self.summarize(all_history[:summary_turns])
        
        # 保留最近对话
        recent_history = all_history[-self.config.keep_recent_turns:]
        
        logger.info(f"[Summarizer] 对话分层: 前{summary_turns}轮已摘要，保留最近{len(recent_history)}轮")
        
        return summary, recent_history
