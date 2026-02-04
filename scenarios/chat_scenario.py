"""
闲聊场景配置
"""

from scenarios.config import ScenarioConfig, ScenarioType
from prompts import CHAT_SYSTEM_PROMPT


def get_chat_scenario() -> ScenarioConfig:
    """
    获取闲聊场景配置
    
    返回:
        ScenarioConfig: 闲聊场景配置对象
    """
    
    # 闲聊场景的意图（相对开放）
    dst_intents = {
        "闲聊": ["日常交流", "问候", "告别", "感谢"],
        "求助": ["请求建议", "寻求帮助", "咨询问题"],
        "分享": ["分享经历", "表达观点", "讲述故事"],
        "情感": ["表达情绪", "倾诉烦恼", "庆祝喜悦"],
        "其他": ["不确定", "混合意图"]
    }
    
    # 闲聊场景的槽位
    dst_slots = {
        "intent_level1": "一级意图（主意图）",
        "intent_level2": "二级意图（子意图）",
        "topic": "对话话题",
        "emotion": "情绪状态",
        "user_name": "用户名称",
        "context_info": "上下文信息"
    }
    
    dst_categorical_slots = {
        "intent_level1": ["闲聊", "求助", "分享", "情感", "其他"],
        "emotion": ["开心", "平静", "烦恼", "兴奋", "其他"]
    }
    
    dst_prompt_template = """你是一个对话信息提取系统。

## 核心任务
从用户的回复中提取意图和关键信息。

## 预定义槽位
- intent_level1: 一级意图（闲聊、求助、分享、情感、其他）
- intent_level2: 二级意图（详细子意图）
- topic: 对话话题
- emotion: 情绪状态（开心、平静、烦恼、兴奋、其他）
- user_name: 用户名称（如果提及）
- context_info: 其他上下文信息

## 一级意图说明
- **闲聊**: 日常交流、问候、告别、感谢
- **求助**: 请求建议、寻求帮助、咨询问题
- **分享**: 分享经历、表达观点、讲述故事
- **情感**: 表达情绪、倾诉烦恼、庆祝喜悦
- **其他**: 不确定、混合意图

## 提取示例

用户："你好啊，最近怎么样？"
```json
{"intent_level1": "闲聊", "intent_level2": "问候", "emotion": "平静"}
```

用户："我今天心情很好，升职了！"
```json
{"intent_level1": "分享", "intent_level2": "分享经历", "emotion": "开心", "topic": "工作升职"}
```

用户："能给我推荐一些好书吗？"
```json
{"intent_level1": "求助", "intent_level2": "请求建议", "topic": "书籍推荐"}
```

## 输出要求
1. 必须返回纯JSON格式
2. 必须包含 intent_level1
3. 尽量提取 intent_level2、topic、emotion
4. 不要添加任何解释文字

只返回JSON，不要其他内容。
"""
    
    return ScenarioConfig(
        name="闲聊",
        scenario_type=ScenarioType.CHAT,
        description="日常闲聊对话场景",
        dst_intents=dst_intents,
        dst_slots=dst_slots,
        dst_categorical_slots=dst_categorical_slots,
        # 闲聊场景使用动态槽位提取，让 LLM 自动提取对话中的关键信息
        # 闲聊话题多样，难以预定义所有槽位，动态提取更灵活
        enable_dynamic_slots=True,
        dst_prompt_template=dst_prompt_template,
        system_prompt=CHAT_SYSTEM_PROMPT,
        ui_title="智能对话 · 上下文理解 · 长期记忆",
        ui_description="智能对话 · 上下文理解 · 长期记忆",
        welcome_message="你好！我是智能AI助手，拥有长期记忆和上下文理解能力，可以和你进行自然的对话交流。有什么我可以帮你的吗？",
        max_history_turns=10,
        temperature=0.8,
        enable_memory=True,
        enable_evolution=True
    )
