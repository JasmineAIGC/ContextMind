"""
FnCTOD 预定义函数Schema

为三个场景（闲聊、客服、保险）预定义函数调用Schema，确保一致性和可维护性。
每个Schema定义了domain作为函数的完整规格。
"""

from fnctod.data_models import DomainSpec, FunctionParameter, ParameterType


def get_chat_function_schema() -> DomainSpec:
    """
    获取闲聊场景的函数Schema
    
    Returns:
        DomainSpec: 闲聊场景的函数规格
    """
    schema = DomainSpec(
        name="chat",
        description="日常闲聊对话场景，用于提取用户意图、话题和情绪等信息"
    )
    
    # 添加参数（对应DST的槽位）
    schema.add_parameter(FunctionParameter(
        name="intent_level1",
        description="一级意图（主意图）：闲聊、求助、分享、情感、其他",
        param_type=ParameterType.STRING,
        required=True,
        enum_values=["闲聊", "求助", "分享", "情感", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="intent_level2",
        description="二级意图（子意图）：如问候、告别、请求建议、分享经历等",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="topic",
        description="对话话题",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="emotion",
        description="情绪状态",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["开心", "平静", "烦恼", "兴奋", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="user_name",
        description="用户名称（如果用户提及）",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="context_info",
        description="其他上下文信息",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    return schema


def get_callcenter_function_schema() -> DomainSpec:
    """
    获取客服场景的函数Schema
    
    Returns:
        DomainSpec: 客服场景的函数规格
    """
    schema = DomainSpec(
        name="callcenter",
        description="客户服务对话场景，用于提取客户意图、问题类型和解决状态等信息"
    )
    
    # 添加参数（对应DST的槽位）
    schema.add_parameter(FunctionParameter(
        name="intent_level1",
        description="一级意图（主意图）：咨询、投诉、售后、账户、其他",
        param_type=ParameterType.STRING,
        required=True,
        enum_values=["咨询", "投诉", "售后", "账户", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="intent_level2",
        description="二级意图（子意图）：如产品咨询、退换货、登录问题等",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="issue_type",
        description="问题类型描述",
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
        name="product",
        description="相关产品名称",
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
        name="resolution_status",
        description="解决状态",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["未解决", "处理中", "已解决", "需升级"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="urgency",
        description="紧急程度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["低", "中", "高", "紧急"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="satisfaction",
        description="满意度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["满意", "一般", "不满意", "未知"]
    ))
    
    return schema


def get_insurance_function_schema() -> DomainSpec:
    """
    获取保险场景的函数Schema
    
    Returns:
        DomainSpec: 保险场景的函数规格
    """
    schema = DomainSpec(
        name="insurance",
        description="保险销售对话场景，用于提取客户意图、个人信息和保险需求等信息"
    )
    
    # 添加参数（对应DST的槽位）
    schema.add_parameter(FunctionParameter(
        name="intent_level1",
        description="一级意图：拒绝、无意向、用户忙、考虑、质疑类、接受、咨询",
        param_type=ParameterType.STRING,
        required=True,
        enum_values=["拒绝", "无意向", "用户忙", "考虑", "质疑类", "接受", "咨询"]
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
        name="existing_insurance",
        description="已有保险情况",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="insurance_interest",
        description="保险兴趣：是、否、考虑中",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["是", "否", "考虑中"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="budget",
        description="预算",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="family_info",
        description="家庭信息",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="health_concern",
        description="健康关注点",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="rejection_reason",
        description="拒绝原因",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="follow_up_status",
        description="跟进状态：待跟进、已跟进、已成交、已放弃",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["待跟进", "已跟进", "已成交", "已放弃"]
    ))
    
    return schema


# 映射字典：scenario_type -> schema getter
SCHEMA_GETTERS = {
    "chat": get_chat_function_schema,
    "闲聊": get_chat_function_schema,
    "callcenter": get_callcenter_function_schema,
    "客服": get_callcenter_function_schema,
    "insurance": get_insurance_function_schema,
    "保险": get_insurance_function_schema,
    "保险挽回": get_insurance_function_schema,  # 保险场景的完整名称
}


def get_function_schema_for_scenario(scenario_name: str) -> DomainSpec:
    """
    根据场景名称获取对应的函数Schema（通用化版本）
    
    现在使用场景注册表，支持动态添加新场景的Schema。
    
    Args:
        scenario_name: 场景名称（支持中英文别名）
    
    Returns:
        DomainSpec: 对应场景的函数规格
    
    Raises:
        ValueError: 如果场景未注册或没有Schema
    
    Example:
        # 使用内置场景Schema
        schema = get_function_schema_for_scenario("chat")
        
        # 注册并使用自定义Schema
        from scenario_registry import scenario_registry
        scenario_registry.register(
            name="custom",
            schema_getter=get_custom_schema
        )
        schema = get_function_schema_for_scenario("custom")
    """
    from scenario_registry import scenario_registry
    
    # 优先使用注册表
    schema = scenario_registry.get_schema(scenario_name)
    if schema is not None:
        return schema
    
    # 降级：使用旧的硬编码映射（向后兼容）
    getter = SCHEMA_GETTERS.get(scenario_name)
    if getter is not None:
        return getter()
    
    # 两者都没有，抛出错误
    available_scenarios = scenario_registry.list_scenarios()
    raise ValueError(
        f"场景 '{scenario_name}' 没有注册Schema。\n"
        f"已注册场景: {', '.join(available_scenarios)}\n"
        f"提示: 使用 scenario_registry.register(name, schema_getter=...) 注册Schema"
    )
