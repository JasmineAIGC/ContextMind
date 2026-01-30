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
        "intent": "用户意图",
        "topic": "对话话题",
        "emotion": "情绪状态",
        "user_name": "用户名称",
        "context_info": "上下文信息"
    }
    
    dst_categorical_slots = {
        "emotion": ["开心", "平静", "烦恼", "兴奋", "其他"]
    }
    
    dst_prompt_template = """你是一个对话信息提取系统。

从用户的回复中提取：
1. 意图：用户想要做什么（闲聊、求助、分享、情感表达等）
2. 话题：谈论的主题
3. 情绪：用户的情绪状态
4. 其他关键信息

返回JSON格式，只包含提取到的信息。
"""
    
    return ScenarioConfig(
        name="闲聊",
        scenario_type=ScenarioType.CHAT,
        description="日常闲聊对话场景",
        dst_intents=dst_intents,
        dst_slots=dst_slots,
        dst_categorical_slots=dst_categorical_slots,
        dst_prompt_template=dst_prompt_template,
        system_prompt=CHAT_SYSTEM_PROMPT,
        ui_title="智能对话 · 上下文理解 · 长期记忆",
        ui_description="智能对话 · 上下文理解 · 长期记忆",
        welcome_message="你好！我是你的AI助手，很高兴和你聊天。有什么我可以帮你的吗？",
        max_history_turns=10,
        temperature=0.8,
        enable_memory=True,
        enable_evolution=True
    )
