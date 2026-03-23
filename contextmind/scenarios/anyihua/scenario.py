"""
安逸花外呼促活场景配置

基于 resources/data/chat_test_100.json 数据定义的外呼对话场景。
坐席代表马上消费金融安逸花拨出电话，目标为身份核实、额度介绍、促活借款及问题处理。
"""

from ..base import ScenarioConfig, ScenarioType
from contextmind.scenarios.prompts import ANYIHUA_OUTBOUND_SYSTEM_PROMPT


def get_anyihua_outbound_scenario() -> ScenarioConfig:
    """
    获取安逸花外呼促活场景配置

    场景特点：
    - 坐席主动外呼，需要先核实用户身份
    - 向用户介绍当前可用额度和产品优势
    - 处理用户的投诉（借款记录异常、利率问题等）
    - 处理用户的咨询（额度、利率、还款方式等）

    返回:
        ScenarioConfig: 安逸花外呼场景配置对象
    """

    # 意图体系：对齐 fnctod/schemas.yaml 中的 anyihua schema
    dst_intents = {
        "投诉": [
            "借款记录异常",
            "账单问题",
            "利率问题",
            "其他投诉",
        ],
        "咨询": [
            "咨询额度",
            "咨询利率",
            "咨询还款方式",
            "其他咨询",
        ],
        "拒绝借款": [
            "明确拒绝",
            "委婉拒绝",
            "暂不需要",
        ],
        "配合/接受": [
            "身份核实配合",
            "同意了解产品",
            "有借款意向",
        ],
        "告别": [
            "用户主动挂机",
            "通话结束",
        ],
        "其他": [
            "信号问题",
            "用户忙",
            "其他",
        ],
    }

    # 槽位定义：与 fnctod schemas.yaml 保持一致
    dst_slots = {
        "intent_level1": "用户主要意图（投诉、咨询、拒绝借款、配合/接受、告别、其他）",
        "intent_level2": "二级意图（更详细的子意图）",
        "identity_verified": "用户身份是否已被核实",
        "customer_name": "已确认的客户姓名",
        "phone_tail": "用户手机尾号",
        "complaint_type": "投诉/争议类型",
        "disputed_loan_date": "用户提出争议的借款日期",
        "disputed_loan_amount": "用户提出争议的借款金额",
        "issue_description": "用户对问题的详细描述",
        "borrow_willingness": "用户对借款/提现的意向",
        "user_emotion": "用户当前情绪状态",
        "resolution_status": "问题当前处理状态",
        "call_outcome": "本次通话结果",
        "notes": "其他重要备注",
    }

    dst_categorical_slots = {
        "intent_level1": [
            "投诉_借款记录异常", "投诉_账单问题", "投诉_利率问题", "投诉_其他",
            "咨询_额度", "咨询_利率", "咨询_还款方式", "咨询_其他",
            "拒绝借款", "配合/接受", "告别", "其他",
        ],
        "identity_verified": ["已核实", "部分核实", "未核实"],
        "complaint_type": [
            "借款记录异常", "账单金额有误", "利率不符", "还款问题", "账户信息有误", "其他",
        ],
        "borrow_willingness": ["有意向", "无意向", "考虑中", "未明确"],
        "user_emotion": ["平静", "疑惑", "不满", "愤怒", "焦虑", "配合", "其他"],
        "resolution_status": ["未处理", "查询中", "已解释", "已解决", "需升级"],
        "call_outcome": [
            "待定", "用户有借款意向", "投诉已处理", "用户拒绝借款", "需回调跟进", "通话结束",
        ],
    }

    dst_prompt_template = """你是安逸花外呼对话状态追踪系统。

## 核心任务
从用户（客户）的回复中提取意图和关键信息，用于指导坐席的下一步应对。

## 预定义槽位
- intent_level1: 用户主要意图（见下方枚举）
- intent_level2: 二级意图（详细子分类，自由文本）
- identity_verified: 身份核实状态（已核实、部分核实、未核实）
- customer_name: 已确认姓名（如"高先生"）
- phone_tail: 用户手机尾号
- complaint_type: 投诉类型（借款记录异常/账单金额有误/利率不符/还款问题/账户信息有误/其他）
- disputed_loan_date: 用户提出争议的借款日期
- disputed_loan_amount: 用户提出争议的借款金额
- issue_description: 问题详细描述
- borrow_willingness: 借款意向（有意向/无意向/考虑中/未明确）
- user_emotion: 情绪状态（平静/疑惑/不满/愤怒/焦虑/配合/其他）
- resolution_status: 处理状态（未处理/查询中/已解释/已解决/需升级）
- call_outcome: 通话结果（待定/用户有借款意向/投诉已处理/用户拒绝借款/需回调跟进/通话结束）
- notes: 其他备注

## 一级意图枚举（intent_level1 必须从以下选择）
- 投诉_借款记录异常：用户称某笔借款不是本人操作
- 投诉_账单问题：账单金额或日期有异议
- 投诉_利率问题：对利率有疑问或不满
- 投诉_其他：其他类型投诉
- 咨询_额度：询问可用额度信息
- 咨询_利率：询问借款利率
- 咨询_还款方式：询问还款方式或计划
- 咨询_其他：其他咨询
- 拒绝借款：用户拒绝借款或提现
- 配合/接受：配合核实身份或接受产品介绍
- 告别：通话即将结束
- 其他：以上均不适用

## 提取示例

用户："我没有借这笔钱，七月二十三号我没有借款"
```json
{{"intent_level1": "投诉_借款记录异常", "intent_level2": "质疑借款记录真实性", "disputed_loan_date": "七月二十三号", "user_emotion": "不满"}}
```

用户："对我就是账户本人"
```json
{{"intent_level1": "配合/接受", "intent_level2": "身份核实配合", "identity_verified": "已核实"}}
```

用户："你们利息太高了，我不想借"
```json
{{"intent_level1": "拒绝借款", "intent_level2": "利率太高", "borrow_willingness": "无意向", "user_emotion": "不满"}}
```

用户："我现在额度是多少？"
```json
{{"intent_level1": "咨询_额度", "intent_level2": "询问可用额度"}}
```

## 输出要求
1. 必须返回纯JSON格式，不含任何Markdown标记
2. 必须包含 intent_level1
3. 只提取有明确依据的信息，不猜测
4. 不要添加任何解释文字

只返回JSON，不要其他内容。
"""

    welcome_message = (
        "诶您好，打扰一下，请问您这边是本人吗？"
        "我这边是马上消费安逸花的客户经理，"
        "来电是想跟您确认一下账户额度的相关情况，请问您现在方便接听吗？"
    )

    return ScenarioConfig(
        name="安逸花外呼",
        scenario_type=ScenarioType.ANYIHUA,
        description="安逸花外呼促活场景 · 身份核实 · 额度介绍 · 投诉处理",
        dst_intents=dst_intents,
        dst_slots=dst_slots,
        dst_categorical_slots=dst_categorical_slots,
        enable_dynamic_slots=False,  # 使用预定义槽位，对齐 fnctod schema
        dst_prompt_template=dst_prompt_template,
        system_prompt=ANYIHUA_OUTBOUND_SYSTEM_PROMPT,
        ui_title="安逸花外呼 · 智能坐席助手",
        ui_description="安逸花外呼促活场景 · 对话状态追踪 · 智能坐席辅助",
        welcome_message=welcome_message,
        max_history_turns=15,
        temperature=0.7,
        enable_memory=True,
        enable_evolution=True,
    )
