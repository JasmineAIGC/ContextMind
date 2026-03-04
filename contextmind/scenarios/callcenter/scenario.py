"""
客服场景配置
"""

from ..base import ScenarioConfig, ScenarioType
from contextmind.scenarios.prompts import CALLCENTER_SYSTEM_PROMPT


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
        "intent_level1": "一级意图（主意图）",
        "intent_level2": "二级意图（子意图）",
        "issue_type": "问题类型",
        "customer_name": "客户姓名",
        "product": "相关产品",
        "order_number": "订单号",
        "resolution_status": "解决状态",
        "urgency": "紧急程度",
        "satisfaction": "满意度"
    }
    
    dst_categorical_slots = {
        "intent_level1": ["咨询", "投诉", "售后", "账户", "其他"],
        "resolution_status": ["未解决", "处理中", "已解决", "需升级"],
        "urgency": ["低", "中", "高", "紧急"],
        "satisfaction": ["满意", "一般", "不满意", "未知"]
    }
    
    dst_prompt_template = """你是一个客服对话状态追踪系统。

## 核心任务
从客户的回复中提取意图和关键信息，用于指导客服人员的应对策略。

## 预定义槽位
- intent_level1: 一级意图（咨询、投诉、售后、账户、其他）
- intent_level2: 二级意图（详细子意图）
- issue_type: 问题类型描述
- customer_name: 客户姓名
- product: 相关产品名称
- order_number: 订单号
- resolution_status: 解决状态（未解决、处理中、已解决、需升级）
- urgency: 紧急程度（低、中、高、紧急）
- satisfaction: 满意度（满意、一般、不满意、未知）

## 一级意图说明
- **咨询**: 产品咨询、服务咨询、价格咨询、政策咨询
- **投诉**: 产品问题、服务问题、物流问题、其他投诉
- **售后**: 退换货、维修、质保、使用指导
- **账户**: 登录问题、密码重置、信息修改、账户查询
- **其他**: 建议反馈、一般询问

## 提取示例

客户："我买的手机屏幕碎了，想换一个"
```json
{"intent_level1": "售后", "intent_level2": "退换货", "product": "手机", "issue_type": "屏幕损坏"}
```

客户："你们的客服态度太差了，我要投诉！"
```json
{"intent_level1": "投诉", "intent_level2": "服务问题", "urgency": "高", "satisfaction": "不满意"}
```

客户："请问这个产品多少钱？"
```json
{"intent_level1": "咨询", "intent_level2": "价格咨询"}
```

客户："我的订单123456怎么还没发货？"
```json
{"intent_level1": "咨询", "intent_level2": "服务咨询", "order_number": "123456", "issue_type": "物流查询"}
```

## 输出要求
1. 必须返回纯JSON格式
2. 必须包含 intent_level1
3. 尽量提取 intent_level2 和相关信息
4. 不要添加任何解释文字

只返回JSON，不要其他内容。
"""
    
    return ScenarioConfig(
        name="客服",
        scenario_type=ScenarioType.CALLCENTER,
        description="客户服务对话场景",
        dst_intents=dst_intents,
        dst_slots=dst_slots,
        dst_categorical_slots=dst_categorical_slots,
        # 客服场景使用动态槽位提取，让 LLM 自动提取对话中的关键信息
        # 客服问题多样，难以预定义所有槽位，动态提取更灵活
        enable_dynamic_slots=True,
        dst_prompt_template=dst_prompt_template,
        system_prompt=CALLCENTER_SYSTEM_PROMPT,
        ui_title="智能客服 · 上下文工程 · 专业对话",
        ui_description="智能客服 · 上下文工程 · 专业对话",
        welcome_message="您好！我是智能客服助手，专门负责处理产品咨询、投诉建议和售后服务等业务。我会认真记录您的问题并提供专业的解决方案。请问有什么可以帮您的吗？",
        max_history_turns=10,
        temperature=0.7,
        enable_memory=True,
        enable_evolution=True
    )
