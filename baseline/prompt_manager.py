"""
提示词管理器（Prompt Manager）

管理槽位本体定义、分类约束和提示词生成，
完全基于LLM理解，支持动态槽位提取。

版本: v7.4.0
"""

import logging
from typing import Dict, List, Set, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Language(Enum):
    """支持的语言"""
    ZH_CN = "zh-CN"  # 简体中文
    EN_US = "en-US"  # 英语
    JA_JP = "ja-JP"  # 日语


class LLMFormat(Enum):
    """LLM平台格式"""
    OPENAI = "openai"          # OpenAI GPT系列
    ANTHROPIC = "anthropic"    # Claude系列
    GOOGLE = "google"          # Gemini系列
    QWEN = "qwen"             # 通义千问
    GENERAL = "general"        # 通用格式（默认）


class PromptManager:
    """
    提示词管理器（支持动态槽位提取）
    
    管理本体定义和提示词生成，符合 ACL 2023 论文规范。
    支持完全动态的槽位提取 - LLM自由提取任何相关信息。
    
    核心改进：
    - 不强制预定义槽位
    - LLM自主识别意图和提取信息
    - 支持多意图场景
    
    属性:
        domain: 对话领域（如 "general", "chat", "restaurant"）
        ontology_slots: 槽位名称到描述的映射字典（可选，用于指导）
        categorical_constraints: 槽位名称到允许值的映射字典（可选，用于指导）
        enable_dynamic_slots: 是否启用完全动态槽位（默认True）
    """
    
    def __init__(self, 
                 domain: str = "general",
                 enable_dynamic_slots: bool = True,
                 language: Language = Language.ZH_CN,
                 llm_format: LLMFormat = LLMFormat.GENERAL,
                 template_style: str = "structured",
                 max_context_length: Optional[int] = None):
        """
        初始化提示词管理器
        
        参数:
            domain: 对话领域
            enable_dynamic_slots: 启用动态槽位提取（推荐）
            language: 提示词语言（默认中文）
            llm_format: LLM平台格式（默认通用）
            template_style: 模板风格 - "structured"(详细), "concise"(简洁), "conversational"(对话式)
            max_context_length: 最大上下文长度（自动根据LLM格式设置）
        """
        self.domain = domain
        self.enable_dynamic_slots = enable_dynamic_slots
        self.language = language
        self.llm_format = llm_format
        self.template_style = template_style
        
        # 根据LLM格式设置默认上下文长度
        if max_context_length is None:
            self.max_context_length = self._get_default_context_length()
        else:
            self.max_context_length = max_context_length
        
        # 可选的槽位本体（仅用于指导，不强制）
        self.ontology_slots: Dict[str, str] = {}
        self.categorical_constraints: Dict[str, List[str]] = {}
        
        logger.info(f"初始化PromptManager (领域={domain}, 动态槽位={enable_dynamic_slots})")
    
    def add_slot(self, 
                 name: str, 
                 description: str, 
                 categorical_values: Optional[List[str]] = None) -> None:
        """
        添加槽位定义（可选，用于指导LLM）
        
        参数:
            name: 槽位名称
            description: 槽位描述
            categorical_values: 可选的预定义值列表
        """
        self.ontology_slots[name] = description
        if categorical_values:
            self.categorical_constraints[name] = categorical_values
    
    def get_system_instruction(self, history_summary: Optional[str] = None) -> str:
        """
        生成系统指令提示词（支持动态槽位和多意图）
        
        参数:
            history_summary: 可选的历史对话摘要
            
        返回:
            格式化的系统指令
        """
        # 根据模板风格选择不同的指令
        if self.template_style == "concise":
            return self.get_concise_instruction()
        elif self.template_style == "conversational":
            return self.get_conversational_instruction()
        
        # structured 风格（默认，详细指导）
        # 基础指令
        instruction = """你是一个智能对话状态追踪系统。你的任务是从用户与系统的对话中提取关键信息。

## 核心任务

从用户的**最新回复**中提取所有相关信息，以JSON格式返回。

"""
        
        # 动态槽位指导
        if self.enable_dynamic_slots:
            instruction += """## 信息提取指南

**重要：不限制提取的信息类型，LLM自主判断提取什么信息。**

请提取所有对话相关的关键信息，包括但不限于：

1. **意图识别**（必须包含）：
   - 准确识别用户的具体意图类型
   - 常见意图：作业帮助、餐饮推荐、技术支持、闲聊交流、咨询建议、告别暂停、信息查询、购物咨询等
   - 必须在返回的JSON中包含 "intent" 字段
   - 如果有多个意图，可以用列表或分别列出

2. **具体信息**（根据对话内容灵活提取）：
   - 话题/主题（如：数学、披萨、Python编程等）
   - 实体和对象（如：学科、菜品、产品名称等）
   - 用户需求（如：解题思路、口味推荐、价格查询等）
   - 时间地点（如果提到）
   - 情绪状态（如：焦虑、开心、生气等）
   - 偏好设置（如：价格范围、风格偏好等）
   - 任何其他相关信息

3. **多意图处理**：
   - 如果对话涉及多个意图，都要识别出来
   - 例如："我要先吃饭，然后做作业" → 包含"餐饮"和"作业"两个意图

"""
        else:
            # 如果有预定义槽位，提供指导
            if self.ontology_slots:
                instruction += "\n## 槽位定义\n\n"
                instruction += "以下是可能的槽位（但不限于这些）：\n\n"
                for slot, desc in self.ontology_slots.items():
                    instruction += f"- **{slot}**: {desc}\n"
                    if slot in self.categorical_constraints:
                        values = ", ".join(self.categorical_constraints[slot])
                        instruction += f"  可选值: {values}\n"
                instruction += "\n"
        
        # 特殊值处理
        instruction += """## 特殊值处理

- 如果用户**正在询问**某个信息（而非提供），使用 "?"
- 如果用户**不关心**某个信息，使用 "dontcare"
- 示例：
  - 用户："什么菜系好吃？" → {"food_type": "?"}
  - 用户："什么都行" → {"food_type": "dontcare"}

"""
        
        # 历史摘要
        if history_summary:
            instruction += f"""## 历史对话摘要

{history_summary}

**注意**：提取信息时要考虑历史上下文，但只提取最新回复中的**新增或更新**的信息。

"""
        
        # 输出格式
        instruction += """## 输出格式

返回JSON对象，必须包含：
1. "intent" 字段（必需）- 用户的具体意图
2. 其他提取的信息字段（根据对话内容灵活添加）

**示例1：作业帮助**
```json
{
  "intent": "作业帮助",
  "学科": "数学",
  "难度": "有几道题不会",
  "需求": "解题思路"
}
```

**示例2：餐饮推荐**
```json
{
  "intent": "餐饮推荐",
  "food_type": "披萨",
  "需求": "口味推荐"
}
```

**示例3：多意图**
```json
{
  "intent": "告别+作业提醒",
  "next_action": "吃饭",
  "未完成事项": "数学作业"
}
```

只返回JSON，不要其他解释文字！
"""
        
        return instruction
    
    def get_slot_names(self) -> Set[str]:
        """
        获取所有槽位名称集合
        
        返回:
            槽位名称集合（如果启用动态槽位，返回空集合）
        """
        if self.enable_dynamic_slots:
            # 动态模式下不限制槽位
            return set()
        return set(self.ontology_slots.keys())
    
    def _get_default_context_length(self) -> int:
        """
        根据LLM格式获取默认上下文长度
        
        返回:
            默认上下文长度（tokens）
        """
        context_limits = {
            LLMFormat.OPENAI: 8000,
            LLMFormat.ANTHROPIC: 100000,
            LLMFormat.GOOGLE: 32000,
            LLMFormat.QWEN: 8000,
            LLMFormat.GENERAL: 4000,
        }
        return context_limits.get(self.llm_format, 4000)
    
    def _translate_term(self, term: str, context: str = "") -> str:
        """
        翻译术语到目标语言
        
        参数:
            term: 要翻译的术语
            context: 上下文（可选）
            
        返回:
            翻译后的术语
        """
        if self.language == Language.ZH_CN:
            return term  # 已经是中文
        
        # 简单的术语映射（可以扩展为更复杂的翻译系统）
        translations = {
            Language.EN_US: {
                "意图": "intent",
                "槽位": "slot",
                "提取": "extract",
                "对话": "dialogue",
                "信息": "information",
                "学科": "subject",
                "难度": "difficulty",
                "需求": "requirement",
            },
            Language.JA_JP: {
                "意图": "意図",
                "槽位": "スロット",
                "提取": "抽出",
                "对话": "対話",
                "信息": "情報",
            }
        }
        
        lang_dict = translations.get(self.language, {})
        return lang_dict.get(term, term)
    
    def get_concise_instruction(self) -> str:
        """
        获取简洁版系统指令（节省tokens）
        
        返回:
            简洁的系统指令
        """
        if self.language == Language.EN_US:
            return """Extract key information from user's latest reply in JSON format.
Must include: "intent" field.
Other fields: flexibly extract relevant information.
Return JSON only, no explanations."""
        
        return """从用户最新回复中提取关键信息，返回JSON。
必须包含：intent字段。
其他字段：灵活提取相关信息。
只返回JSON，不要解释！"""
    
    def get_conversational_instruction(self) -> str:
        """
        获取对话式系统指令（更自然）
        
        返回:
            对话式系统指令
        """
        if self.language == Language.EN_US:
            return """Please analyze this conversation and help me understand what the user wants.
Tell me:
- User's intent
- Key information mentioned
Reply in JSON format."""
        
        return """请帮我分析这段对话，理解用户想要什么。
告诉我：
- 用户的意图
- 提到的关键信息
以JSON格式回复。"""
