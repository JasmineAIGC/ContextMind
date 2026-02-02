"""
保险挽回场景配置

基于data/huashu.md中的保险挽回话术设计

⚠️ 重要规则（基于 data/huashu.md 参考文档）：
1. 一级意图和二级意图是固定的，来自 huashu.md，不可修改
2. 可以添加其他槽位（slots），根据实际需要扩展
3. 分类槽位值（categorical values）可以调整
4. 但核心意图体系必须与 huashu.md 保持一致

说明：
- 意图来源：data/huashu.md 表格中定义的一级意图和二级意图（固定）
- 槽位设计：基于保险销售场景的实际需求（可扩展）
- 使用预定义槽位模式（enable_dynamic_slots=False）
- 共荣保险公司的团体癌症保险产品
"""

from scenarios.config import ScenarioConfig, ScenarioType


def get_insurance_scenario() -> ScenarioConfig:
    """
    获取保险挽回场景配置
    
    ⚠️ 重要约束（基于 data/huashu.md 参考文档）：
    1. 一级意图和二级意图是固定的，来自 huashu.md，不可修改
       - 拒绝、无意向、用户忙、考虑、质疑类（固定来自 huashu.md）
       - 接受、咨询（扩展意图，可调整）
    2. 二级意图必须精确匹配 huashu.md 表格中的定义
    3. 槽位（slots）可以根据实际需要添加或修改
    4. 分类槽位值（categorical values）可以调整
    
    关键特性：
    1. 固定意图：一级和二级意图来自 huashu.md（rows 5-29）
    2. 可扩展槽位：从 huashu.md 和实际需求提取的槽位定义
    3. 分类约束：部分槽位有预定义的分类值建议
    4. 预定义模式：使用 enable_dynamic_slots=False
    5. 公司身份：共荣保险公司
    
    返回:
        ScenarioConfig: 保险场景配置对象
    """
    
    # ===== 以下一级意图和二级意图来自 data/huashu.md，为固定参考，不可修改 =====
    # 每个二级意图对应 huashu.md 表格中的具体行
    dst_intents = {
        # 1. 拒绝（huashu.md rows 5-6）
        "拒绝": [
            "明确、强硬拒绝",  # huashu.md row 5
            "委婉拒绝"          # huashu.md row 6
        ],
        
        # 2. 无意向（huashu.md rows 7-21）
        "无意向": [
            "已有保险",                    # huashu.md rows 7-8
            "已有癌症保险",                # huashu.md row 9
            "犹豫",                        # huashu.md rows 10-12
            "保费贵",                      # huashu.md rows 13-14
            "担心长期缴费后面无法负担",    # huashu.md row 15
            "不了解抗癌治疗",              # huashu.md row 16
            "不满意只保癌症",              # huashu.md row 17
            "不喜欢缴费型保险",            # huashu.md row 18
            "生活负担大",                  # huashu.md row 19
            "不想电话买保险",              # huashu.md row 20
            "要与家人商量"                 # huashu.md row 21
        ],
        
        # 3. 用户忙（huashu.md row 22）
        "用户忙": [
            "用户忙"  # huashu.md row 22 - 只有一个二级意图
        ],
        
        # 4. 考虑（huashu.md rows 23-24）
        "考虑": [
            "用户表示考虑一下",                      # huashu.md row 23
            "希望自己决策，不希望听营销话术"        # huashu.md row 24
        ],
        
        # 5. 质疑类（huashu.md rows 25-29）
        "质疑类": [
            "身份质疑",          # huashu.md row 25
            "质疑为什么推销保险",  # huashu.md row 26
            "质疑是否能理赔",    # huashu.md row 27
            "买保险吃过亏",      # huashu.md row 28
            "担心保险条款"       # huashu.md row 29
        ],
        
        # ===== 以下为扩展意图（非 huashu.md 定义，但销售流程需要）=====
        # 这些可以根据实际需要调整
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
    # 意图层级：一级意图（固定）→ 二级意图（固定）→ 三级意图（可扩展）
    dst_slots = {
        "intent_level1": "一级意图（主意图，来自huashu.md）",
        "intent_level2": "二级意图（子意图，来自huashu.md）",
        "intent_level3": "三级意图（详细分类，用于补充一二级意图的具体情况）",
        
        # 以下为事实性信息槽位（非意图层级）
        "customer_age_range": "客户年龄段",
        "customer_gender": "客户性别",
        "has_insurance": "是否已有保险",
        "has_cancer_insurance": "是否已有癌症保险",
        "callback_needed": "是否需要回访",
        "decision_maker": "决策者（本人/配偶/家人）",
        "conversation_stage": "对话阶段（初次接触、了解产品、处理异议、促成签约）",
        "insurance_type_interested": "感兴趣的保险类型",
        "budget_range": "预算范围",
        "health_status": "健康状况提及",
        "family_situation": "家庭情况",
        "competitor_mention": "提及竞争对手",
        "next_action": "下一步行动"
    }
    
    # 定义分类槽位（只允许特定值）
    dst_categorical_slots = {
        # 三级意图分类（5大类，每类5个值）
        "intent_level3": [
            # 1. 特殊情况类（客户的个人情况）
            "健康状况", "家庭情况", "经济状况", "工作性质", "地理位置",
            # 2. 原因类（客户持某种态度的原因）
            "过往经历", "他人影响", "知识不足", "时机不当", "比较结果",
            # 3. 关注点类（客户重点关注的方面）
            "价格因素", "保障范围", "理赔流程", "公司信誉", "条款细节",
            # 4. 行动意向类（客户的下一步打算）
            "立即决定", "需要时间", "需要咨询", "需要比较", "暂不考虑",
            # 5. 情绪状态类（客户的情绪反应）
            "积极开放", "谨慎保守", "抗拒防御", "困惑迷茫", "不满抱怨"
        ],
        
        # 事实性信息的分类槽位
        "customer_age_range": ["30岁以下", "30-40岁", "40-50岁", "50岁以上"],
        "customer_gender": ["男", "女", "未知"],
        "has_insurance": ["是", "否", "未知"],
        "has_cancer_insurance": ["是", "否", "未知"],
        "callback_needed": ["是", "否", "待定"],
        "decision_maker": ["本人", "配偶", "家人", "需商量"],
        "conversation_stage": ["初次接触", "了解产品", "处理异议", "促成签约", "客户拒绝"]
    }
    
    # DST提示词模板
    dst_prompt_template = """你是一个专业的保险电话销售对话状态追踪系统。

## 核心任务
从用户的回复中准确提取意图和关键信息，用于指导销售人员的应对策略。

## 意图体系（三层结构 - 基于 data/huashu.md）

### 一级意图（7个固定类别，来自huashu.md）:
1. 拒绝 - 明确表示不需要
2. 无意向 - 有各种顾虑和理由
3. 用户忙 - 当前不方便
4. 考虑 - 需要时间思考
5. 质疑类 - 对产品或公司有疑虑
6. 接受 - 愿意了解或购买
7. 咨询 - 主动询问信息

### 二级意图（必须精确匹配以下定义，来自huashu.md）:

**拒绝**:
- 明确、强硬拒绝
- 委婉拒绝

**无意向**:
- 已有保险
- 已有癌症保险
- 犹豫
- 保费贵
- 担心长期缴费后面无法负担
- 不了解抗癌治疗
- 不满意只保癌症
- 不喜欢缴费型保险
- 生活负担大
- 不想电话买保险
- 要与家人商量

**用户忙**:
- 用户忙

**考虑**:
- 用户表示考虑一下
- 希望自己决策，不希望听营销话术

**质疑类**:
- 身份质疑
- 质疑为什么推销保险
- 质疑是否能理赔
- 买保险吃过亏
- 担心保险条款

**接受**:
- 有意向
- 同意了解
- 愿意购买

**咨询**:
- 询问保障内容
- 询问保费
- 询问理赔流程
- 询问投保条件

### 三级意图（可选，用于补充一二级意图的详细分类）:

**5大类别，每类5个值**：

1. **特殊情况类**（客户的个人情况）：
   - 健康状况、家庭情况、经济状况、工作性质、地理位置

2. **原因类**（客户持某种态度的原因）：
   - 过往经历、他人影响、知识不足、时机不当、比较结果

3. **关注点类**（客户重点关注的方面）：
   - 价格因素、保障范围、理赔流程、公司信誉、条款细节

4. **行动意向类**（客户的下一步打算）：
   - 立即决定、需要时间、需要咨询、需要比较、暂不考虑

5. **情绪状态类**（客户的情绪反应）：
   - 积极开放、谨慎保守、抗拒防御、困惑迷茫、不满抱怨

## 关键信息提取
必须提取以下信息（如果对话中有提及）：
- 客户年龄段和性别
- 是否已有保险/癌症保险
- 家庭和决策情况
- 对话所处阶段
- 建议的下一步行动

## 输出格式
返回JSON格式，包含：
1. intent_level1: 一级意图（必须从上述7个中选择）
2. intent_level2: 二级意图（必须精确匹配上述定义）
3. intent_level3: 三级意图（可选，用于补充详细信息，从25个值中选择）
4. 其他相关槽位信息

## 示例
用户："我已经买过癌症保险了，不需要了"
输出:
{
  "intent_level1": "无意向",
  "intent_level2": "已有癌症保险",
  "intent_level3": "过往经历",
  "has_cancer_insurance": "是",
  "conversation_stage": "处理异议",
  "next_action": "提供叠加保险的优势说明"
}

用户："保费太贵了，我负担不起"
输出:
{
  "intent_level1": "无意向",
  "intent_level2": "保费贵",
  "intent_level3": "价格因素",
  "budget_range": "不确定",
  "conversation_stage": "处理异议"
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
        enable_dynamic_slots=False,  # 使用预定义槽位（一级和二级意图固定来自huashu.md，不可修改）
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
