"""
提示词管理器（Prompt Manager）

管理槽位本体定义、分类约束和提示词生成，
完全基于LLM理解，支持动态槽位提取。

版本: v0.4.0
"""

from typing import Dict, List, Set, Optional
from enum import Enum
from utils.logger import get_logger

logger = get_logger(__name__)


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
        instruction = """你是一个通用的对话信息提取系统。你的任务是理解对话内容，提取关键信息。

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

返回JSON对象，结构要求：
1. **必须包含** "intent" 字段 - 描述用户的核心意图
2. **灵活添加**其他字段 - 根据实际提取的信息自由命名和组织

**通用模式示例**：

```json
{
  "intent": "<意图描述>",
  "<信息类型1>": "<提取的值>",
  "<信息类型2>": "<提取的值>",
  ...
}
```

**具体场景参考**（适用于任何领域）：

**场景A：请求帮助**
```json
{
  "intent": "寻求帮助",
  "问题类型": "技术问题",
  "具体内容": "配置环境",
  "期望结果": "详细步骤"
}
```

**场景B：信息查询**
```json
{
  "intent": "查询信息",
  "目标对象": "产品",
  "查询维度": ["价格", "功能"],
  "限定条件": {"预算": "中等"}
}
```

**场景C：多步骤任务**
```json
{
  "intent": "计划+执行",
  "阶段1": "准备材料",
  "阶段2": "开始制作",
  "当前状态": "待开始"
}
```

**输出要求**：只返回JSON，不要任何解释文字！
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
