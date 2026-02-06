"""
提示词管理器（Prompt Manager）

管理槽位本体定义、分类约束和提示词生成，
完全基于LLM理解，支持动态槽位提取。

版本: v0.2.1
"""

from typing import Dict, List, Set, Optional
from enum import Enum
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# Intent label loader (imported lazily to avoid circular dependencies)
_intent_label_loader = None

def _get_intent_label_loader():
    """Lazy load intent label loader"""
    global _intent_label_loader
    if _intent_label_loader is None:
        try:
            from tests.intent_label_loader import get_intent_label_loader
            _intent_label_loader = get_intent_label_loader()
        except Exception as e:
            logger.warning(f"Failed to load intent labels: {e}")
            _intent_label_loader = None
    return _intent_label_loader


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
                 max_context_length: Optional[int] = None,
                 custom_template: Optional[str] = None,
                 enable_intent_prediction: bool = True):
        """
        初始化提示词管理器
        
        参数:
            domain: 对话领域
            enable_dynamic_slots: 启用动态槽位提取（推荐）
            language: 提示词语言（默认中文）
            llm_format: LLM平台格式（默认通用）
            template_style: 模板风格 - "structured"(详细), "concise"(简洁), "conversational"(对话式)
            max_context_length: 最大上下文长度（自动根据LLM格式设置）
            custom_template: 自定义提示词模板（如果提供，将替代默认生成的模板）
            enable_intent_prediction: 是否启用基于领域的意图预测（默认True）
        """
        self.domain = domain
        self.enable_dynamic_slots = enable_dynamic_slots
        self.language = language
        self.llm_format = llm_format
        self.template_style = template_style
        self.custom_template = custom_template
        self.enable_intent_prediction = enable_intent_prediction
        
        # 根据LLM格式设置默认上下文长度
        if max_context_length is None:
            self.max_context_length = self._get_default_context_length()
        else:
            self.max_context_length = max_context_length
        
        # 可选的槽位本体（仅用于指导，不强制）
        self.ontology_slots: Dict[str, str] = {}
        self.categorical_constraints: Dict[str, List[str]] = {}
        
        # 加载领域特定的意图标签（如果启用）
        self.domain_intents: List[str] = []
        if self.enable_intent_prediction:
            self._load_domain_intents()
        
        logger.info(f"初始化PromptManager (领域={domain}, 动态槽位={enable_dynamic_slots}, 意图预测={enable_intent_prediction})")
    
    def _load_domain_intents(self) -> None:
        """
        从intent_labels配置文件中加载领域特定的意图列表
        """
        loader = _get_intent_label_loader()
        if loader is None:
            logger.warning(f"Intent label loader not available, intent prediction disabled for domain: {self.domain}")
            return
        
        try:
            self.domain_intents = loader.get_domain_intents(self.domain)
            if self.domain_intents:
                logger.info(f"Loaded {len(self.domain_intents)} intents for domain: {self.domain}")
            else:
                logger.warning(f"No intents found for domain: {self.domain}")
        except Exception as e:
            logger.error(f"Failed to load domain intents: {e}")
            self.domain_intents = []
    
    def _get_intent_instructions(self) -> str:
        """
        生成领域特定的意图识别指令
        
        返回:
            意图识别指令字符串
        """
        if not self.enable_intent_prediction or not self.domain_intents:
            return ""
        
        loader = _get_intent_label_loader()
        if loader is None:
            return ""
        
        intent_text = f"""## 意图识别指南（{self.domain}领域）

**重要：必须从以下预定义的意图列表中选择一个最匹配的意图。**

该领域的有效意图包括：

"""
        
        # Add each intent with description and keywords
        for intent in self.domain_intents:
            desc_info = loader.get_intent_description(self.domain, intent)
            description = desc_info.get("description", "")
            keywords = desc_info.get("keywords", [])
            
            intent_text += f"  - **{intent}**"
            if description:
                intent_text += f": {description}"
            if keywords:
                keyword_str = ", ".join(keywords[:5])  # Limit to 5 keywords
                intent_text += f" (关键词: {keyword_str})"
            intent_text += "\n"
        
        intent_text += """
**意图选择要求：**
1. 必须从上述列表中选择一个意图，不能自由创建新意图
2. 分析用户话语，选择最匹配的意图
3. 如果无法匹配任何具体意图，选择"其他"
4. intent字段的值必须完全匹配列表中的意图名称

"""
        
        return intent_text

    
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
        # 如果提供了自定义模板，直接使用
        if self.custom_template:
            return self.custom_template
        
        # 否则根据模板风格选择不同的指令
        if self.template_style == "concise":
            return self.get_concise_instruction()
        elif self.template_style == "conversational":
            return self.get_conversational_instruction()
        
        # structured 风格（默认，详细指导）
        # 基础指令
        instruction = """你是一个专业的对话信息提取系统。

## 重要说明

**你的回复必须是纯JSON格式，不要包含任何其他文字、解释或对话内容！**

## 核心任务

从用户的**最新回复**中智能提取所有相关信息，以JSON格式返回。

"""
        
        # 动态槽位指导
        if self.enable_dynamic_slots:
            instruction += """## 信息提取指南

**核心原则：完全开放式提取，不限制任何信息类型或领域。**

请根据对话内容，灵活提取所有关键信息：

1. **意图理解**（必须包含）：
   - 识别用户在当前对话中的真实意图
   - 不限于特定类型，可以是：请求帮助、获取信息、表达观点、情感交流、执行操作等
   - 必须在返回的JSON中包含 "intent" 字段
   - 支持识别多个并行或顺序的意图

2. **信息实体**（根据对话内容灵活提取）：
   - **核心概念**：对话中涉及的主题、对象、实体
   - **属性特征**：描述、限定条件、偏好、要求
   - **上下文要素**：时间、地点、方式、原因、目标
   - **状态信息**：进展、结果、决策、变化
   - **关系信息**：比较、关联、依赖
   - **情感态度**：情绪、评价、倾向
   - **元信息**：优先级、确定性、重要性

3. **处理复杂情况**：
   - **多意图**：识别所有并存的意图
   - **隐含信息**：推断未明说但重要的信息
   - **关系结构**：信息之间的层次和关联
   - **动态变化**：新增、修改、删除的信息

"""
            # Add domain-specific intent instructions if available
            intent_instructions = self._get_intent_instructions()
            if intent_instructions:
                instruction += intent_instructions
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
        instruction += """## 输出格式（重要！）

**严格要求：**
1. 只返回纯JSON对象，不要任何其他内容
2. 不要写"好的，我来提取信息"等对话内容
3. 不要解释JSON的含义
4. 直接输出JSON，不要用```json```标记

**JSON结构要求：**
1. **必须包含** "intent" 字段 - 描述用户的核心意图
2. **灵活添加**其他字段 - 根据实际提取的信息自由命名和组织

**正确示例1（用户询问身份）：**
{"intent": "询问身份", "问题类型": "身份确认"}

**正确示例2（询问产品）：**
{"intent": "咨询产品", "产品类型": "保险", "具体需求": "癌症保险"}

**正确示例3（表达兴趣）：**
{"intent": "表达兴趣", "感兴趣程度": "中等", "关注点": "价格和保障范围"}

**错误示例（不要这样）：**
❌ "好的，我来提取信息：{"intent": "询问"}"
❌ "根据对话，用户的意图是..."
❌ ```json\n{"intent": "询问"}\n```

**再次强调：只返回纯JSON对象，立即开始，如：{"intent": "...", ...}**
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
    
    def get_all_slots(self) -> Dict[str, str]:
        """
        获取所有已定义的槽位
        
        返回:
            Dict[str, str]: 槽位名称到描述的映射
        """
        return self.ontology_slots
    
    @property
    def categorical_slots(self) -> Dict[str, List[str]]:
        """
        获取分类槽位约束
        
        返回:
            Dict[str, List[str]]: 槽位名称到允许值列表的映射
        """
        return self.categorical_constraints
    
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
            return """Extract all relevant information from the user's latest message as JSON.
Required: "intent" field describing user's purpose.
Optional: any other key information fields.
Output: JSON only, no explanations."""
        
        return """从用户最新消息中提取所有相关信息，返回JSON格式。
必需：intent字段（描述用户意图）。
可选：任何其他关键信息字段。
输出：仅JSON，无解释。"""
    
    def get_conversational_instruction(self) -> str:
        """
        获取对话式系统指令（更自然）
        
        返回:
            对话式系统指令
        """
        if self.language == Language.EN_US:
            return """Please analyze this conversation and extract meaningful information.
Focus on:
- What is the user trying to achieve? (intent)
- What specific information did they provide?
- What context or constraints are relevant?
Provide your analysis as a JSON object."""
        
        return """请分析这段对话并提取有意义的信息。
关注：
- 用户想达成什么目的？（意图）
- 他们提供了哪些具体信息？
- 有哪些相关的上下文或限制？
以JSON对象形式提供分析。"""
