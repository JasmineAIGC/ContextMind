"""
安逸花外呼场景配置

基于安逸花金融外呼促活服务的对话状态追踪设计。
外呼流程：核实用户身份 → 告知额度/临时提额 → 解答疑问 → 引导借款。

说明：
- 意图来源：安逸花外呼对话分类体系
- 槽位设计：基于安逸花借贷场景的实际信息需求
- 使用预定义槽位模式（enable_dynamic_slots=False）
"""

from ..base import ScenarioConfig, ScenarioType


def get_anyihua_scenario() -> ScenarioConfig:
    """
    获取安逸花外呼场景配置

    场景特点：
    - 外呼方向：坐席主动联系用户进行额度激活或借款引导
    - 核心意图：核实身份、告知额度、解答顾虑、引导借款
    - 槽位体系：涵盖借款金额、利率、还款方式、账户状态等金融信息

    返回:
        ScenarioConfig: 安逸花外呼场景配置对象
    """

    # ===== 意图体系 =====
    dst_intents = {
        # 1. 身份核实
        "身份核实": [
            "确认账户使用状态",
            "确认借款历史",
            "确认是否本人",
        ],

        # 2. 额度告知
        "额度告知": [
            "告知当前额度",
            "告知临时提额",
            "告知可用余额",
        ],

        # 3. 借款咨询
        "借款咨询": [
            "询问借款金额",
            "询问借款利率",
            "询问还款方式",
            "询问借款流程",
            "询问到账时间",
        ],

        # 4. 用户顾虑
        "用户顾虑": [
            "利率偏高",
            "还款压力大",
            "不敢使用额度",
            "担心逾期影响",
            "对金额有疑议",
        ],

        # 5. 投诉质疑
        "投诉质疑": [
            "质疑未申请的贷款",
            "对申请金额与到账不符不满",
            "投诉还款流程繁琐",
            "额度被拒",
        ],

        # 6. 未来意向
        "未来意向": [
            "表达未来借款意向",
            "希望长期合作",
            "建议联系客服",
        ],

        # 7. 接受引导
        "接受引导": [
            "同意了解产品",
            "愿意尝试借款",
            "同意接受回访",
        ],

        # 8. 拒绝
        "拒绝": [
            "明确拒绝",
            "暂时不需要",
            "当前忙，稍后再说",
        ],
    }

    # ===== 槽位定义 =====
    dst_slots = {
        "intent_level1": "一级意图（主意图）",
        "intent_level2": "二级意图（子意图）",
        # 金融信息槽位
        "loan_amount": "借款金额",
        "current_credit_limit": "当前信用额度",
        "temporary_credit_limit": "临时信用额度",
        "available_amount": "当前可用金额",
        "remaining_quota": "剩余可用额度",
        "monthly_payment": "每月还款金额",
        "total_interest": "总利息金额",
        "daily_interest": "每日利息金额",
        "term_years": "贷款期限（年）",
        # 时间信息
        "loan_date": "借款发生日期",
        "borrowing_date": "借款日期",
        "application_date": "申请日期",
        "repayment_status": "还款状态",
        "overdue_days": "逾期天数",
        # 账户信息
        "account_usage_status": "账户使用状态",
        "usage_duration": "账户使用时长",
        "requested_amount": "申请金额",
        "actual_amount": "实际到账金额",
        # 对话状态
        "conversation_stage": "对话阶段",
        "callback_needed": "是否需要回访",
    }

    # ===== 分类槽位（严格约束） =====
    dst_categorical_slots = {
        "intent_level1": ["身份核实", "额度告知", "借款咨询", "用户顾虑", "投诉质疑", "未来意向", "接受引导", "拒绝"],
        "account_usage_status": ["正常使用", "未激活", "已逾期", "已结清", "未知"],
        "repayment_status": ["正常还款", "提前还款", "逾期", "未知"],
        "conversation_stage": ["身份核实", "额度告知", "解答顾虑", "引导借款", "用户拒绝", "完成引导"],
        "callback_needed": ["是", "否", "待定"],
    }

    # ===== DST 提示词模板 =====
    dst_prompt_template = """你是安逸花金融外呼服务的对话状态追踪系统。

## 核心任务
从用户回复中准确提取意图和关键金融信息，用于指导坐席的外呼话术。

⚠️ 严格约束：
1. 只能使用预定义槽位名称，不能创建新槽位
2. 对于分类槽位，只能使用预定义值
3. 不确定时槽位留空，不要强行填充
4. 输出纯JSON，不包含任何解释文字

## 意图体系（两层结构）

**一级意图**（intent_level1）—— 从以下8个中选择：
身份核实、额度告知、借款咨询、用户顾虑、投诉质疑、未来意向、接受引导、拒绝

**二级意图**（intent_level2）—— 对应一级意图的子分类：
- 身份核实：确认账户使用状态 / 确认借款历史 / 确认是否本人
- 额度告知：告知当前额度 / 告知临时提额 / 告知可用余额
- 借款咨询：询问借款金额 / 询问借款利率 / 询问还款方式 / 询问借款流程 / 询问到账时间
- 用户顾虑：利率偏高 / 还款压力大 / 不敢使用额度 / 担心逾期影响 / 对金额有疑议
- 投诉质疑：质疑未申请的贷款 / 对申请金额与到账不符不满 / 投诉还款流程繁琐 / 额度被拒
- 未来意向：表达未来借款意向 / 希望长期合作 / 建议联系客服
- 接受引导：同意了解产品 / 愿意尝试借款 / 同意接受回访
- 拒绝：明确拒绝 / 暂时不需要 / 当前忙，稍后再说

## 提取示例

【示例1 - 利率顾虑】
用户："利息太高了，每个月要还这么多"
{{"intent_level1": "用户顾虑", "intent_level2": "利率偏高", "monthly_payment": "该月还款金额"}}

【示例2 - 质疑贷款】
用户："我没有申请过贷款，怎么有这条记录？"
{{"intent_level1": "投诉质疑", "intent_level2": "质疑未申请的贷款"}}

## 输出格式
纯JSON，不含任何解释文字。必须包含 intent_level1 和 intent_level2。
"""

    # ===== 系统提示词 =====
    system_prompt = """你是安逸花金融外呼服务的专业坐席，负责向用户介绍安逸花信用额度并引导激活/借款。

## 外呼目标
1. 核实用户身份和账户状态
2. 告知用户当前信用额度或临时提额信息
3. 解答用户关于利率、还款方式的疑虑
4. 引导用户完成借款或额度激活

## 沟通原则
- 专业、友善、值得信赖
- 先核实身份，再介绍额度信息
- 耐心解答利率和还款相关问题
- 遇到明确拒绝时礼貌结束通话

## 产品信息
- 安逸花信用额度：最高可达数万元
- 支持随借随还，按日计息
- 提前还款不收违约金
- 最快当天到账
"""

    # ===== 欢迎消息 =====
    welcome_message = """您好！我是安逸花客服专员，今天致电是想告知您账户里有可用额度，您最近有资金需求吗？"""

    return ScenarioConfig(
        name="安逸花外呼",
        scenario_type=ScenarioType.CUSTOM,
        description="安逸花外呼促活服务 · 核实身份 → 告知额度 → 解答疑问 → 引导借款",
        dst_intents=dst_intents,
        dst_slots=dst_slots,
        dst_categorical_slots=dst_categorical_slots,
        enable_dynamic_slots=False,
        dst_prompt_template=dst_prompt_template,
        system_prompt=system_prompt,
        ui_title="安逸花外呼 · 智能话术优化",
        ui_description="安逸花外呼 · 对话状态追踪 · 话术优化",
        welcome_message=welcome_message,
        max_history_turns=15,
        temperature=0.7,
        enable_memory=True,
        enable_evolution=True,
    )
