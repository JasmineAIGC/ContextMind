"""
FnCTOD 预定义函数Schema

为三个场景（闲聊、客服、保险）预定义函数调用Schema，确保一致性和可维护性。
每个Schema定义了domain作为函数的完整规格。
"""

from .data_models import DomainSpec, FunctionParameter, ParameterType


def get_chat_function_schema() -> DomainSpec:
    """
    获取闲聊场景的函数Schema（增强版）
    
    包含更全面的用户信息和对话上下文提取能力。
    
    Returns:
        DomainSpec: 闲聊场景的函数规格
    """
    schema = DomainSpec(
        name="chat",
        description="日常闲聊对话场景，全面提取用户意图、话题、情绪、用户画像等多维度信息"
    )
    
    schema.add_parameter(FunctionParameter(
        name="intent_level1",
        description="一级意图（主意图）",
        param_type=ParameterType.STRING,
        required=True,  # top-level intent is mandatory; all other fields are best-effort
        enum_values=["闲聊", "求助", "分享", "咨询", "情感倾诉", "闲暇活动", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="intent_level2",
        description="二级意图（子意图）：如问候、告别、请求建议、分享经历、征询意见等",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="topic",
        description="对话主题（具体内容）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="topic_category",
        description="话题分类",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["工作", "学习", "生活", "娱乐", "情感", "健康", "科技", "美食", "旅游", "运动", "家庭", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="keywords",
        description="对话关键词（逗号分隔）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="emotion",
        description="用户情绪状态",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["开心", "平静", "烦恼", "焦虑", "兴奋", "失落", "愤怒", "期待", "无聊", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="attitude",
        description="对话态度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["友好", "热情", "冷淡", "敷衍", "认真", "随意", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="user_name",
        description="用户名称或称呼",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="user_age_group",
        description="用户年龄段（根据对话推测）",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["儿童", "青少年", "青年", "中年", "老年", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="user_gender",
        description="用户性别（根据对话推测）",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["男", "女", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="user_occupation",
        description="用户职业或身份",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="user_location",
        description="用户所在地（城市或地区）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="user_interests",
        description="用户兴趣爱好（逗号分隔）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="conversation_style",
        description="对话风格",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["正式", "随意", "幽默", "严肃", "轻松", "专业", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="conversation_depth",
        description="对话深度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["浅层闲聊", "一般交流", "深度讨论", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="time_context",
        description="时间上下文（如早上、晚上、周末等）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="follow_up_needed",
        description="是否需要后续跟进",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["是", "否", "可选"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="follow_up_topic",
        description="后续跟进话题",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="context_info",
        description="其他重要上下文信息",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    return schema


def get_callcenter_function_schema() -> DomainSpec:
    """
    获取客服场景的函数Schema（增强版）
    
    包含全面的问题分类、客户信息、解决方案跟踪等专业客服必需字段。
    
    Returns:
        DomainSpec: 客服场景的函数规格
    """
    schema = DomainSpec(
        name="callcenter",
        description="客户服务对话场景，全面提取客户意图、问题详情、解决方案、服务质量等多维度信息"
    )
    
    schema.add_parameter(FunctionParameter(
        name="intent_level1",
        description="一级意图（主意图）",
        param_type=ParameterType.STRING,
        required=True,
        enum_values=["咨询", "投诉", "售后", "账户", "技术支持", "建议反馈", "预约服务", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="intent_level2",
        description="二级意图（子意图）：如产品咨询、退换货、登录问题、支付问题等",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="issue_category",
        description="问题大类",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["产品问题", "订单问题", "支付问题", "物流问题", "账户问题", "技术问题", "服务问题", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="issue_subcategory",
        description="问题子类（具体问题类型）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="issue_description",
        description="问题详细描述",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="customer_name",
        description="客户姓名",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="customer_id",
        description="客户ID或会员号",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="customer_level",
        description="客户等级",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["普通", "VIP", "黄金", "钻石", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="contact_phone",
        description="联系电话",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="contact_email",
        description="联系邮箱",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="preferred_contact_method",
        description="首选联系方式",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["电话", "短信", "邮件", "微信", "APP推送", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="preferred_contact_time",
        description="首选联系时间",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="order_number",
        description="订单号",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="product_name",
        description="产品名称",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="product_model",
        description="产品型号",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="purchase_date",
        description="购买日期",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="resolution_status",
        description="解决状态",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["未解决", "处理中", "待回复", "已解决", "需升级", "已转接"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="solution_provided",
        description="提供的解决方案",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="follow_up_action",
        description="后续跟进行动",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="estimated_resolution_time",
        description="预计解决时间",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="urgency",
        description="紧急程度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["低", "中", "高", "紧急"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="priority",
        description="处理优先级",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["P1-最高", "P2-高", "P3-中", "P4-低"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="escalation_needed",
        description="是否需要升级",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["是", "否", "待定"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="satisfaction",
        description="客户满意度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["非常满意", "满意", "一般", "不满意", "非常不满意", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="service_quality",
        description="服务质量评价",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="agent_name",
        description="客服代表姓名",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="complaint_reason",
        description="投诉原因（如果是投诉）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="reference_number",
        description="工单号或参考号",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="notes",
        description="备注或其他重要信息",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    return schema


def get_insurance_function_schema() -> DomainSpec:
    """
    获取保险场景的函数Schema（增强专业版）
    
    包含全面的客户信息、保险需求、健康状况、家庭情况等专业保险销售必需字段。
    
    Returns:
        DomainSpec: 保险场景的函数规格
    """
    schema = DomainSpec(
        name="insurance",
        description="保险销售对话场景，全面提取客户意图、个人信息、保险需求、健康状况、家庭情况等专业销售信息"
    )
    
    schema.add_parameter(FunctionParameter(
        name="intent_level1",
        description="一级意图",
        param_type=ParameterType.STRING,
        required=True,
        enum_values=["拒绝", "无意向", "用户忙", "考虑", "质疑类", "接受", "咨询", "购买意向"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="intent_level2",
        description="二级意图：详细子意图",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="intent_level3",
        description="三级意图：更详细的意图描述",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="customer_name",
        description="客户姓名",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="age",
        description="年龄",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="gender",
        description="性别",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["男", "女", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="occupation",
        description="职业",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="work_type",
        description="工作性质",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["企业员工", "个体经营", "自由职业", "公务员", "退休", "学生", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="income_level",
        description="收入水平",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["5千以下", "5千-1万", "1万-2万", "2万-5万", "5万以上", "未透露"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="city",
        description="所在城市",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="marital_status",
        description="婚姻状况",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["未婚", "已婚", "离异", "丧偶", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="has_children",
        description="是否有子女",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["是", "否", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="children_count",
        description="子女数量",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="children_ages",
        description="子女年龄（逗号分隔）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="family_members",
        description="需要保障的家庭成员（逗号分隔）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="main_income_earner",
        description="家庭主要收入来源者",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="health_status",
        description="健康状况",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["健康", "良好", "一般", "较差", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="smoking_status",
        description="吸烟状况",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["不吸烟", "偶尔吸烟", "经常吸烟", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="drinking_status",
        description="饮酒状况",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["不饮酒", "偶尔饮酒", "经常饮酒", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="chronic_disease",
        description="慢性病情况（如高血压、糖尿病等）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="recent_medical_history",
        description="近期就医史或手术史",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="family_medical_history",
        description="家族病史",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="health_concern",
        description="健康关注点或担忧",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="insurance_interest",
        description="保险兴趣度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["很有兴趣", "有一定兴趣", "考虑中", "兴趣不大", "不感兴趣"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="insurance_type",
        description="感兴趣的保险类型",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["重疾险", "医疗险", "寿险", "意外险", "年金险", "理财险", "综合保障", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="insurance_product",
        description="具体保险产品名称",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="coverage_amount",
        description="保额需求",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="premium_budget",
        description="保费预算（年度或月度）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="payment_frequency",
        description="缴费频率偏好",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["年交", "半年交", "季交", "月交", "趸交", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="payment_period",
        description="缴费期限偏好",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["5年", "10年", "15年", "20年", "30年", "终身", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="coverage_period",
        description="保障期限偏好",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["定期（10-30年）", "至70岁", "至80岁", "终身", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="existing_insurance",
        description="已有保险情况描述",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="existing_insurance_types",
        description="已有保险类型（逗号分隔）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="existing_coverage_gap",
        description="现有保障缺口",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="social_security",
        description="社保情况",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["有职工社保", "有居民社保", "有新农合", "无社保", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="decision_maker",
        description="决策人（谁决定买保险）",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["本人", "配偶", "父母", "共同决策", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="decision_stage",
        description="决策阶段",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["初步了解", "对比产品", "深入考虑", "准备购买", "已决定购买", "暂不考虑"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="purchase_timeline",
        description="购买时间计划",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["立即购买", "一周内", "一个月内", "三个月内", "暂不确定"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="risk_awareness",
        description="风险意识",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["风险意识强", "有一定认识", "认识不足", "未知"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="main_concerns",
        description="主要顾虑或关注点（逗号分隔）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="rejection_reason",
        description="拒绝原因（如果拒绝）",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["价格太高", "不需要", "已有保险", "不信任", "要考虑", "时间不合适", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="objections",
        description="客户提出的异议或质疑",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="objection_handled",
        description="异议是否已处理",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["是", "否", "部分处理"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="consultation_channel",
        description="咨询渠道",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["电话", "微信", "APP", "线下", "官网", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="preferred_contact_time",
        description="首选联系时间",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="follow_up_status",
        description="跟进状态",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["待跟进", "已预约", "持续跟进", "已成交", "已放弃"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="next_follow_up_action",
        description="下次跟进行动",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="agent_notes",
        description="坐席备注（重要信息记录）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    return schema


def get_function_schema_for_scenario(scenario_name: str) -> DomainSpec:
    """
    根据场景名称获取对应的函数Schema
    
    Delegates to the scenario registry so new schemas can be added via
    ``scenarios.yaml`` without modifying this file (open/closed principle).
    All built-in schemas (chat, callcenter, insurance) are pre-registered
    there; custom schemas must also be registered in that config.
    
    Args:
        scenario_name: 场景名称（支持中英文别名）
    
    Returns:
        DomainSpec: 对应场景的函数规格
    
    Raises:
        ValueError: 如果场景未注册或没有Schema
    
    Example:
        schema = get_function_schema_for_scenario("chat")
        schema = get_function_schema_for_scenario("闲聊")  # 中文别名
    """
    from contextmind.config.registry import scenario_registry
    
    schema = scenario_registry.get_schema(scenario_name)
    if schema is not None:
        return schema
    
    available_scenarios = scenario_registry.list_scenarios()
    raise ValueError(
        f"场景 '{scenario_name}' 未注册或没有Schema。\n"
        f"已注册场景: {', '.join(available_scenarios)}\n"
        f"请在 scenarios.yaml 中配置该场景的 schema_getter。"
    )
