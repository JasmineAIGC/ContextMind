"""
客服场景配置
"""

from scenarios.config import ScenarioConfig, ScenarioType
from prompts import CALLCENTER_SYSTEM_PROMPT


def get_callcenter_scenario() -> ScenarioConfig:
    """
    获取客服场景配置
    
    返回:
        ScenarioConfig: 客服场景配置对象
    """
    
    # 客服场景的意图
    dst_intents = {
        "咨询": ["产品咨询", "服务咨询", "价格咨询", "政策咨询"],
        "投诉": ["产品问题", "服务问题", "物流问题", "其他投诉"],
        "售后": ["退换货", "维修", "质保", "使用指导"],
        "账户": ["登录问题", "密码重置", "信息修改", "账户查询"],
        "其他": ["建议反馈", "一般询问"]
    }
    
    # 客服场景的槽位
    dst_slots = {
        "intent": "用户意图",
        "issue_type": "问题类型",
        "customer_name": "客户姓名",
        "product": "相关产品",
        "order_number": "订单号",
        "resolution_status": "解决状态",
        "urgency": "紧急程度",
        "satisfaction": "满意度"
    }
    
    dst_categorical_slots = {
        "resolution_status": ["未解决", "处理中", "已解决", "需升级"],
        "urgency": ["低", "中", "高", "紧急"],
        "satisfaction": ["满意", "一般", "不满意", "未知"]
    }
    
    dst_prompt_template = """你是一个客服对话状态追踪系统。

从客户的回复中提取：
1. 意图：客户的需求类型（咨询、投诉、售后等）
2. 问题：具体的问题描述
3. 相关信息：产品、订单号、客户信息等
4. 状态：问题解决状态、紧急程度

返回JSON格式。
"""
    
    return ScenarioConfig(
        name="客服",
        scenario_type=ScenarioType.CALLCENTER,
        description="客户服务对话场景",
        dst_intents=dst_intents,
        dst_slots=dst_slots,
        dst_categorical_slots=dst_categorical_slots,
        enable_dynamic_slots=True,  # 客服场景使用动态槽位提取，灵活处理各类问题
        dst_prompt_template=dst_prompt_template,
        system_prompt=CALLCENTER_SYSTEM_PROMPT,
        ui_title="智能客服 · 上下文工程 · 专业对话",
        ui_description="智能客服 · 上下文工程 · 专业对话",
        welcome_message="您好！我是智能客服助手，我可以帮您解决各类问题和咨询。请问有什么可以帮到您的？",  # 让用户主动发起对话
        max_history_turns=10,
        temperature=0.7,
        enable_memory=True,
        enable_evolution=True
    )
