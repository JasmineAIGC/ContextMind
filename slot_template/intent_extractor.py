"""
Intent Extractor - 意图提取器

从对话历史中提取用户意图和关键信息，用于填充槽位
"""

from typing import List, Dict, Optional, Any
import re


class Message:
    """简单的消息对象"""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


class IntentExtractor:
    """意图提取器 - 从对话历史中提取意图和关键信息"""
    
    def __init__(self, llm_client: Optional[Any] = None):
        """初始化意图提取器
        
        Args:
            llm_client: LLM 客户端（可选），如果提供则使用 LLM 进行智能提取
                       如果不提供则使用基于规则的简单提取
        """
        self.llm_client = llm_client
    
    async def extract_from_history(
        self,
        messages: List[Message],
        current_input: str
    ) -> Dict[str, str]:
        """从对话历史中提取槽位信息
        
        Args:
            messages: 对话历史消息列表
            current_input: 当前用户输入
        
        Returns:
            槽位信息字典，包含:
            - user_intent: 用户意图
            - conversation_context: 对话上下文
            - key_info: 关键信息
        """
        if self.llm_client:
            # 使用 LLM 进行智能提取
            return await self._extract_with_llm(messages, current_input)
        else:
            # 使用规则进行简单提取
            return self._extract_with_rules(messages, current_input)
    
    async def _extract_with_llm(
        self,
        messages: List[Message],
        current_input: str
    ) -> Dict[str, str]:
        """使用 LLM 提取意图和关键信息"""
        
        # 构建历史对话文本
        history_text = self._format_history(messages)
        
        # 构建提取提示词
        extraction_prompt = f"""请分析以下对话历史和当前用户输入，提取以下信息：

对话历史：
{history_text}

当前用户输入：{current_input}

请以 JSON 格式返回以下信息：
1. user_intent: 用户当前的主要意图（一句话概括）
2. conversation_context: 对话上下文的简要总结（2-3句话）
3. key_info: 提取到的关键信息，包括实体、偏好、事实等（列表形式）

返回格式示例：
{{
  "user_intent": "用户想要咨询产品信息",
  "conversation_context": "用户之前询问了价格，现在想了解更多细节。",
  "key_info": "用户对价格敏感，关注产品质量"
}}

请直接返回 JSON，不要包含其他内容。"""

        try:
            # 调用 LLM
            response = await self.llm_client.chat_async(
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.3  # 降低温度以获得更确定的输出
            )
            
            # 解析 JSON 响应
            import json
            
            # 提取 JSON 部分
            content = response.strip()
            
            # 尝试找到 JSON 块
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            
            result = json.loads(content)
            
            return {
                "user_intent": result.get("user_intent", "用户正在进行对话"),
                "conversation_context": result.get("conversation_context", "暂无上下文"),
                "key_info": result.get("key_info", "暂无关键信息")
            }
            
        except Exception as e:
            # LLM 调用失败，降级到规则提取
            print(f"LLM 提取失败，使用规则提取: {e}")
            return self._extract_with_rules(messages, current_input)
    
    def _extract_with_rules(
        self,
        messages: List[Message],
        current_input: str
    ) -> Dict[str, str]:
        """使用规则提取意图和关键信息（简单版本）"""
        
        # 提取用户意图（基于当前输入的关键词）
        user_intent = self._extract_intent_by_keywords(current_input)
        
        # 提取对话上下文（最近几轮对话的摘要）
        conversation_context = self._summarize_recent_context(messages)
        
        # 提取关键信息（实体、数字等）
        key_info = self._extract_key_information(messages, current_input)
        
        return {
            "user_intent": user_intent,
            "conversation_context": conversation_context,
            "key_info": key_info
        }
    
    def _extract_intent_by_keywords(self, user_input: str) -> str:
        """基于关键词提取意图"""
        
        # 定义常见意图关键词
        intent_patterns = {
            "咨询": ["什么", "如何", "怎么", "为什么", "哪里", "谁", "吗"],
            "请求帮助": ["帮", "帮忙", "能不能", "可以", "麻烦"],
            "表达观点": ["我觉得", "我认为", "我想", "我希望"],
            "问候": ["你好", "hi", "hello", "早上好", "晚上好"],
            "感谢": ["谢谢", "感谢", "多谢"],
            "确认": ["是的", "对", "没错", "嗯", "好的", "OK"],
            "否定": ["不是", "不对", "不要", "不用"],
        }
        
        for intent, keywords in intent_patterns.items():
            if any(kw in user_input for kw in keywords):
                return f"用户意图：{intent}"
        
        return f"用户正在与系统对话：{user_input[:30]}..."
    
    def _summarize_recent_context(self, messages: List[Message]) -> str:
        """总结最近的对话上下文"""
        if not messages:
            return "这是对话的开始"
        
        # 获取最近 3 轮对话
        recent = messages[-6:] if len(messages) >= 6 else messages
        
        if len(recent) == 0:
            return "暂无对话历史"
        
        # 简单总结
        user_msgs = [m.content for m in recent if m.role == "user"]
        
        if user_msgs:
            summary_parts = []
            summary_parts.append(f"已进行 {len(messages) // 2} 轮对话。")
            
            if len(user_msgs) > 0:
                summary_parts.append(f"用户最近提到：{user_msgs[-1][:50]}...")
            
            return " ".join(summary_parts)
        
        return "对话刚开始"
    
    def _extract_key_information(
        self,
        messages: List[Message],
        current_input: str
    ) -> str:
        """提取关键信息"""
        
        # 提取所有文本
        all_text = current_input + " " + " ".join([m.content for m in messages])
        
        key_items = []
        
        # 提取数字
        numbers = re.findall(r'\d+', all_text)
        if numbers:
            key_items.append(f"涉及数字: {', '.join(numbers[:3])}")
        
        # 提取常见实体（简单版本）
        # 这里可以扩展更复杂的实体识别
        entities = []
        
        # 提取人名（简单规则）
        name_patterns = [r'([张王李赵刘陈杨黄周吴徐孙马朱胡郭何高林罗郑梁宋谢唐韩曹许邓萧冯曾程蔡彭潘袁于董余苏叶吕魏蒋田杜丁沈姜范江傅钟卢汪戴崔任陆廖姚方金邱夏谭韦贾邹石熊孟秦阎薛侯雷白龙段郝孔邵史毛常万顾赖武康贺严尹钱施牛洪龚]\w{1,2})']
        
        for pattern in name_patterns:
            matches = re.findall(pattern, all_text)
            entities.extend(matches[:2])  # 最多2个
        
        if entities:
            key_items.append(f"提到实体: {', '.join(entities)}")
        
        # 如果没有提取到任何信息
        if not key_items:
            return "暂无明显关键信息"
        
        return "; ".join(key_items)
    
    def _format_history(self, messages: List[Message]) -> str:
        """格式化对话历史"""
        if not messages:
            return "（无对话历史）"
        
        formatted = []
        for msg in messages[-10:]:  # 最多显示最近10条
            role_name = "用户" if msg.role == "user" else "助手"
            formatted.append(f"{role_name}: {msg.content}")
        
        return "\n".join(formatted)
