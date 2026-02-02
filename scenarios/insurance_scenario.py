"""
保险挽回场景配置

基于data/huashu.md中的保险挽回话术设计

重要说明：
- 本场景的意图和槽位是预定义的，基于data/huashu.md梳理
- DST模式不使用LLM动态提取意图和槽位
- 所有意图和槽位都是固定的，确保识别的一致性和准确性
- 共荣保险公司的团体癌症保险产品
"""

from scenarios.config import ScenarioConfig, ScenarioType


def get_insurance_scenario() -> ScenarioConfig:
    """
    获取保险挽回场景配置
    
    关键特性：
    1. 预定义意图：7个一级意图 + 34个二级意图
    2. 预定义槽位：18个固定槽位
    3. 分类约束：8个槽位有预定义的分类值
    4. 不使用LLM：所有意图和槽位都是预先定义的
    5. 公司身份：共荣保险公司
    
    返回:
        ScenarioConfig: 保险场景配置对象
    """
    
    # 定义一级意图和二级意图（基于huashu.md分析，预定义不从LLM提取）
    dst_intents = {
        "拒绝": [
            "明确拒绝",
            "强硬拒绝",
            "委婉拒绝"
        ],
        "无意向": [
            "已有保险",
            "已有癌症保险",
            "犹豫",
            "保费贵",
            "担心长期缴费",
            "不了解抗癌治疗",
            "不满意只保癌症",
            "不喜欢缴费型保险",
            "生活负担大",
            "不想电话买保险",
            "要与家人商量"
        ],
        "用户忙": [
            "工作中",
            "外出中",
            "会议中",
            "不方便接听"
        ],
        "考虑": [
            "表示考虑",
            "希望自己决策",
            "需要时间思考",
            "需要比较方案"
        ],
        "质疑类": [
            "身份质疑",
            "质疑推销原因",
            "质疑理赔能力",
            "之前吃过亏",
            "担心条款复杂"
        ],
        "接受": [
            "有意向",
            "同意了解",
            "愿意购买"
        ],
        "咨询": [
            "询问保障内容",
            "询问保费",
            "询问理赔流程",
            "询问投保条件"
        ]
    }
    
    # 定义槽位
    dst_slots = {
        "intent_level1": "一级意图",
        "intent_level2": "二级意图",
        "customer_age_range": "客户年龄段（30-40岁、40-50岁、50岁以上等）",
        "customer_gender": "客户性别",
        "has_insurance": "是否已有保险",
        "has_cancer_insurance": "是否已有癌症保险",
        "concern_type": "主要关注点（价格、保障范围、理赔等）",
        "objection_reason": "反对原因",
        "callback_needed": "是否需要回访",
        "decision_maker": "决策者（本人/配偶/家人）",
        "conversation_stage": "对话阶段（初次接触、了解产品、处理异议、促成签约）",
        "customer_emotion": "客户情绪状态（友好、中立、抗拒、生气）",
        "insurance_type_interested": "感兴趣的保险类型",
        "budget_range": "预算范围",
        "health_status": "健康状况提及",
        "family_situation": "家庭情况（有子女、单身、已婚等）",
        "competitor_mention": "提及竞争对手",
        "next_action": "下一步行动（发送资料、安排回访、转人工等）"
    }
    
    # 定义分类槽位（只允许特定值）
    dst_categorical_slots = {
        "customer_age_range": ["30岁以下", "30-40岁", "40-50岁", "50岁以上"],
        "customer_gender": ["男", "女", "未知"],
        "has_insurance": ["是", "否", "未知"],
        "has_cancer_insurance": ["是", "否", "未知"],
        "callback_needed": ["是", "否", "待定"],
        "decision_maker": ["本人", "配偶", "家人", "需商量"],
        "conversation_stage": ["初次接触", "了解产品", "处理异议", "促成签约", "客户拒绝"],
        "customer_emotion": ["友好", "中立", "犹豫", "抗拒", "生气"]
    }
    
    # DST提示词模板
    dst_prompt_template = """你是一个专业的保险电话销售对话状态追踪系统。

## 核心任务
从用户的回复中准确提取意图和关键信息，用于指导销售人员的应对策略。

## 意图体系（双层结构）

### 一级意图:
1. 拒绝 - 明确表示不需要
2. 无意向 - 有各种顾虑和理由
3. 用户忙 - 当前不方便
4. 考虑 - 需要时间思考
5. 质疑类 - 对产品或公司有疑虑
6. 接受 - 愿意了解或购买
7. 咨询 - 主动询问信息

### 二级意图（需精确识别）:
- 拒绝: 明确拒绝、强硬拒绝、委婉拒绝
- 无意向: 已有保险、已有癌症保险、犹豫、保费贵、担心长期缴费、不了解抗癌治疗、不满意只保癌症、不喜欢缴费型保险、生活负担大、不想电话买保险、要与家人商量
- 用户忙: 工作中、外出中、会议中、不方便接听
- 考虑: 表示考虑、希望自己决策、需要时间思考、需要比较方案
- 质疑类: 身份质疑、质疑推销原因、质疑理赔能力、之前吃过亏、担心条款复杂
- 接受: 有意向、同意了解、愿意购买
- 咨询: 询问保障内容、询问保费、询问理赔流程、询问投保条件

## 关键信息提取
必须提取以下信息（如果对话中有提及）：
- 客户年龄段和性别
- 是否已有保险/癌症保险
- 主要关注点和顾虑
- 情绪状态
- 家庭和决策情况
- 对话所处阶段
- 建议的下一步行动

## 输出格式
返回JSON格式，包含：
1. intent_level1: 一级意图（必须）
2. intent_level2: 二级意图（必须）
3. 其他相关槽位信息

## 示例
用户："我已经买过癌症保险了，不需要了"
输出:
{
  "intent_level1": "无意向",
  "intent_level2": "已有癌症保险",
  "has_cancer_insurance": "是",
  "customer_emotion": "中立",
  "conversation_stage": "处理异议",
  "next_action": "提供叠加保险的优势说明"
}

只返回JSON，不要其他解释。
"""
    
    # 系统提示词
    system_prompt = """你是一位经验丰富的保险电话销售专员，专门负责癌症保险的挽回销售。

你的目标是：
1. 理解客户的真实顾虑和需求
2. 提供针对性的解决方案
3. 以专业、友善的态度建立信任
4. 适时促成销售或安排后续跟进

沟通原则：
- 保持专业和礼貌
- 善于倾听，理解客户真实需求
- 针对不同顾虑提供定制化解答
- 使用同理心，不强行推销
- 合理使用产品优势和客户案例
- 遇到明确拒绝时优雅退出

你了解的产品信息：
- 这是面向生活协同组合会员的团体癌症保险
- 保费享受30%优惠折扣
- 确诊癌症即可获得一次性赔付
- 对原位癌和白血病同样提供100%赔付
- 可通过电话直接办理，无需复杂手续
"""
    
    # 欢迎消息
    welcome_message = """您好！我是生活协同组合的保险咨询专员。

今天致电是想向您介绍我们专为会员设计的团体癌症保险方案。这是一个享受30%优惠折扣的专属福利，已经有很多会员加入并给予好评。

请问您现在方便简单了解一下吗？"""
    
    return ScenarioConfig(
        name="保险挽回",
        scenario_type=ScenarioType.INSURANCE,
        description="保险电话销售挽回场景 · 专注于癌症保险产品",
        dst_intents=dst_intents,
        dst_slots=dst_slots,
        dst_categorical_slots=dst_categorical_slots,
        enable_dynamic_slots=False,  # 保险场景使用预定义槽位，基于huashu.md
        dst_prompt_template=dst_prompt_template,
        system_prompt=system_prompt,
        ui_title="保险挽回 · 智能话术优化",
        ui_description="保险挽回 · 对话状态追踪 · 话术优化",
        welcome_message=welcome_message,
        max_history_turns=15,  # 保险对话可能较长
        temperature=0.7,
        enable_memory=True,
        enable_evolution=True
    )
