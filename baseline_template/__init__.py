"""
Baseline Template Module - 槽位模板基线版本

这是一个独立的基线实现模块，用于对比实验。

特点：
1. 不使用记忆库功能
2. 只基于对话历史进行意图提取和模板填充
3. 作为最简单的 baseline 实现
4. 便于与 contextmind 的上下文工程方式进行对比

核心流程：
对话历史 → 意图提取 → 模板填充 → 生成提示词

使用示例：
```python
from baseline_template import TemplateEngine, DEFAULT_TEMPLATE

engine = TemplateEngine(template=DEFAULT_TEMPLATE)
prompt = await engine.generate_prompt(conversation_history)
```
"""

from .prompt_template import PromptTemplate, TemplateSlot, DEFAULT_TEMPLATE
from .intent_extractor import IntentExtractor, ExtractedIntent, Message
from .template_engine import TemplateEngine, SimpleTemplateEngine

__version__ = '1.0.0'

__all__ = [
    'PromptTemplate',
    'TemplateSlot',
    'DEFAULT_TEMPLATE',
    'IntentExtractor',
    'ExtractedIntent',
    'Message',
    'TemplateEngine',
    'SimpleTemplateEngine',
]
