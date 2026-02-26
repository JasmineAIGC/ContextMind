#!/usr/bin/env python3
"""
PyTOD Schema 适配器演示

展示如何利用 PyTOD schema + prompt 工程进行 zero-shot 推理，
生成 action 推荐、代码执行与自然语言输出，
**完全不依赖 PyTOD 官方代码**。

运行方式:
    python examples/demo_pytod_adapter.py

本示例不需要真实 LLM，使用模拟输出演示完整流程：
1. 定义 PyTOD 风格的 ServiceSchema（餐厅预约）
2. 使用 PyTODPromptBuilder 组装多轮对话 prompt
3. 使用 ActionValidator 校验模型生成的 action
4. 解析反馈并输出自然语言回复
"""

import json
import sys
from pathlib import Path
from typing import List

# 确保可以直接运行（不安装包时）
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextmind.modes.pytod import (
    ActionValidator,
    ConversationTurn,
    FewShotExample,
    PyTODPromptBuilder,
    ServiceSchema,
    ValidationResult,
    load_schema_from_dict,
)


# =========================================================================== #
# 1. 定义 PyTOD 风格 ServiceSchema
# =========================================================================== #


def build_restaurant_schema() -> ServiceSchema:
    """
    构造一个餐厅预约服务的 PyTOD schema。

    等价于从 PyTOD JSON 文件中加载：
        load_schema_from_dict({...})
    """
    schema_data = {
        "service_name": "RestaurantReservation",
        "description": "餐厅预约服务，支持查询餐厅信息、预约座位和取消预约",
        "slots": [
            {
                "name": "restaurant_name",
                "description": "餐厅名称",
                "is_categorical": False,
            },
            {
                "name": "date_time",
                "description": "预约日期和时间，如'明天晚上7点'",
                "is_categorical": False,
            },
            {
                "name": "party_size",
                "description": "就餐人数",
                "is_categorical": True,
                "possible_values": ["1", "2", "3", "4", "5", "6", "7", "8+"],
            },
            {
                "name": "cuisine_type",
                "description": "菜系类型",
                "is_categorical": True,
                "possible_values": ["中餐", "西餐", "日料", "韩餐", "火锅", "其他"],
            },
            {
                "name": "price_range",
                "description": "价格区间（人均）",
                "is_categorical": True,
                "possible_values": ["经济实惠(50元以下)", "中等(50-150元)", "高档(150元以上)"],
            },
            {
                "name": "location",
                "description": "餐厅所在区域或地址",
                "is_categorical": False,
            },
            {
                "name": "special_request",
                "description": "特殊要求，如包间、靠窗位置、生日布置等",
                "is_categorical": False,
            },
            {
                "name": "reservation_id",
                "description": "预约编号（取消或查询时使用）",
                "is_categorical": False,
            },
        ],
        "intents": [
            {
                "name": "FindRestaurant",
                "description": "查找符合条件的餐厅",
                "required_slots": [],
                "optional_slots": [
                    "cuisine_type",
                    "price_range",
                    "location",
                    "party_size",
                ],
            },
            {
                "name": "Reserve",
                "description": "预约餐厅座位",
                "required_slots": ["restaurant_name", "date_time", "party_size"],
                "optional_slots": ["special_request", "cuisine_type"],
            },
            {
                "name": "CancelReservation",
                "description": "取消已有预约",
                "required_slots": ["reservation_id"],
                "optional_slots": [],
            },
            {
                "name": "QueryReservation",
                "description": "查询预约详情",
                "required_slots": [],
                "optional_slots": ["reservation_id", "restaurant_name"],
            },
        ],
    }
    return load_schema_from_dict(schema_data)


# =========================================================================== #
# 2. 构造 Few-shot 示例（可选，zero-shot 时留空）
# =========================================================================== #


def build_few_shot_examples() -> list:
    """
    构造 few-shot 示例，帮助 LLM 理解输出格式。
    """
    return [
        FewShotExample(
            user_input="我想找一家附近的火锅店",
            action={
                "intent": "FindRestaurant",
                "slots": {"cuisine_type": "火锅"},
            },
            response="好的，您希望在哪个区域附近找火锅店？对价格有要求吗？",
            description="查找餐厅示例",
        ),
        FewShotExample(
            user_input="帮我预约明晚8点，2个人",
            action={
                "intent": "Reserve",
                "slots": {
                    "date_time": "明晚8点",
                    "party_size": "2",
                },
            },
            response="好的，请问您想预约哪家餐厅？",
            description="预约示例（缺少餐厅名）",
        ),
    ]


# =========================================================================== #
# 3. 模拟 LLM 响应（实际使用时替换为真实 API 调用）
# =========================================================================== #


def mock_llm_call(messages: list, turn: int) -> str:
    """
    模拟 LLM API 调用，返回预设的 JSON action。

    实际使用时替换为：
        from openai import OpenAI
        client = OpenAI(api_key=..., base_url="https://dashscope.aliyuncs.com/...")
        resp = client.chat.completions.create(model="qwen3-...", messages=messages)
        return resp.choices[0].message.content
    """
    # 模拟多轮对话中不同轮次的输出
    mock_responses = [
        # 第1轮：用户查询火锅餐厅
        json.dumps(
            {
                "intent": "FindRestaurant",
                "slots": {"cuisine_type": "火锅", "location": "望京"},
                "response": "好的，我帮您在望京地区查找火锅餐厅。请问对价格区间有要求吗？",
            },
            ensure_ascii=False,
            indent=2,
        ),
        # 第2轮：用户选择餐厅并预约
        json.dumps(
            {
                "intent": "Reserve",
                "slots": {
                    "restaurant_name": "海底捞望京店",
                    "date_time": "明天晚上7点",
                    "party_size": "4",
                    "special_request": "需要包间",
                },
                "response": "好的，我将为您预约海底捞望京店明天晚上7点，4位就餐，包间。请确认以上信息是否正确？",
            },
            ensure_ascii=False,
            indent=2,
        ),
        # 第3轮：包含错误的输出（用于演示校验）
        json.dumps(
            {
                "intent": "Reserve",
                "slots": {
                    "restaurant_name": "海底捞望京店",
                    "date_time": "明天晚上7点",
                    "party_size": "20",  # 不在枚举值中，触发校验警告
                },
                "response": "预约成功！您的预约编号是 #A12345。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        # 第4轮：意图不在 schema 中（演示校验错误）
        '{"intent": "ModifyReservation", "slots": {}, "response": "正在修改预约..."}',
    ]

    idx = min(turn, len(mock_responses) - 1)
    return mock_responses[idx]


# =========================================================================== #
# 4. 主演示流程
# =========================================================================== #


def separator(title: str = "") -> None:
    line = "=" * 70
    if title:
        print(f"\n{line}")
        print(f"  {title}")
        print(line)
    else:
        print(line)


def run_demo() -> None:
    separator("PyTOD Schema 适配器演示")
    print("（不依赖 PyTOD 官方代码，仅以 schema + prompt 驱动）\n")

    # ------------------------------------------------------------------ #
    # 步骤 1：加载 Schema
    # ------------------------------------------------------------------ #
    separator("步骤 1: 加载 PyTOD ServiceSchema")
    schema = build_restaurant_schema()
    print(f"服务名称: {schema.service_name}")
    print(f"描述:     {schema.description}")
    print(f"意图数量: {len(schema.intents)}")
    print(f"槽位数量: {len(schema.slots)}")

    print("\n--- Schema Prompt 文本 ---")
    print(schema.to_prompt_text())

    # ------------------------------------------------------------------ #
    # 步骤 2：初始化组件
    # ------------------------------------------------------------------ #
    separator("步骤 2: 初始化 PromptBuilder 和 ActionValidator")

    few_shot = build_few_shot_examples()
    builder = PyTODPromptBuilder(
        schema=schema,
        few_shot_examples=few_shot,  # 去掉此参数则为 zero-shot
        max_history_turns=10,
        response_language="中文",
    )
    validator = ActionValidator(
        schema=schema,
        allow_unknown_intent=False,
        strict_enum=False,   # 枚举不合法时仅发出警告
        require_response_field=True,
    )
    print("PromptBuilder 初始化完成（few-shot 模式，2 个示例）")
    print("ActionValidator 初始化完成")

    # ------------------------------------------------------------------ #
    # 步骤 3：多轮对话演示
    # ------------------------------------------------------------------ #
    separator("步骤 3: 多轮对话 zero/few-shot 推理演示")

    user_turns = [
        "我想在望京找一家火锅餐厅",
        "就选海底捞吧，帮我预约明天晚上7点，4个人，要包间",
        "确认预约，人数改为20人",
        "帮我修改一下预约时间",  # 故意触发 intent 校验错误
    ]

    history: List[ConversationTurn] = []

    for turn_idx, user_input in enumerate(user_turns):
        print(f"\n{'─' * 60}")
        print(f"【第 {turn_idx + 1} 轮对话】")
        print(f"用户: {user_input}")

        # 组装 messages
        messages = builder.build_messages(user_input=user_input, history=history)
        print(f"\n[Prompt 已组装，共 {len(messages)} 条 messages]")

        # 展示第一轮的完整 system prompt（后续轮次折叠）
        if turn_idx == 0:
            print("\n--- System Prompt (节选前 20 行) ---")
            system_content = messages[0]["content"]
            for line in system_content.splitlines()[:20]:
                print(line)
            print("... (省略后续内容)")

        # 模拟 LLM 调用
        llm_output = mock_llm_call(messages, turn_idx)
        print(f"\n[LLM 原始输出]")
        print(llm_output)

        # 校验输出
        result: ValidationResult = validator.validate(llm_output)
        print(f"\n[校验结果] {result.summary()}")
        if result.errors or result.warnings:
            print(result.to_feedback_text())

        # 将本轮加入历史
        history.append(ConversationTurn(role="user", content=user_input))
        history.append(
            ConversationTurn(
                role="assistant",
                content=result.response or "(无回复)",
                action={
                    "intent": result.intent,
                    "slots": result.slots,
                },
            )
        )

        if result.is_valid:
            print(f"\n✓ Action 已接受")
            print(f"  intent : {result.intent}")
            print(f"  slots  : {json.dumps(result.slots, ensure_ascii=False)}")
            print(f"  回复   : {result.response}")
        else:
            print(
                "\n✗ Action 校验失败，实际应用中可将反馈文本追加给 LLM 重新生成"
            )

    # ------------------------------------------------------------------ #
    # 步骤 4：zero-shot 单段 prompt 演示
    # ------------------------------------------------------------------ #
    separator("步骤 4: Zero-shot 单段 Prompt 演示")
    zero_shot_builder = PyTODPromptBuilder(schema=schema)  # 无 few-shot 示例
    single_prompt = zero_shot_builder.build_single_prompt(
        user_input="帮我取消预约 #A12345",
        history=[],
    )
    print("--- 生成的单段 Prompt（节选前 30 行）---")
    for line in single_prompt.splitlines()[:30]:
        print(line)
    print("... (省略后续内容)")

    # ------------------------------------------------------------------ #
    # 步骤 5：Schema 序列化 / 反序列化演示
    # ------------------------------------------------------------------ #
    separator("步骤 5: Schema 序列化 / 反序列化")
    schema_json = schema.to_json()
    print("Schema JSON（节选前 20 行）:")
    for line in schema_json.splitlines()[:20]:
        print(line)
    print("...")

    # 从 JSON 重新加载
    schema_reloaded = ServiceSchema.from_json(schema_json)
    print(
        f"\n重新加载成功: {schema_reloaded.service_name}，"
        f"{len(schema_reloaded.intents)} 个意图，"
        f"{len(schema_reloaded.slots)} 个槽位"
    )

    # ------------------------------------------------------------------ #
    # 步骤 6：开放域模式演示（无需预定义 schema）
    # ------------------------------------------------------------------ #
    separator("步骤 6: 开放域模式（schema=None，无需预定义意图/action）")
    print(
        "开放域模式：PyTOD 的 function / action / 意图 / 槽位\n"
        "不需要预先定义，LLM 根据对话上下文自由判断。\n"
    )

    open_builder = PyTODPromptBuilder()          # schema=None → 开放域
    open_validator = ActionValidator()           # schema=None → 开放域
    print(f"PyTODPromptBuilder.is_open_domain = {open_builder.is_open_domain}")
    print(f"ActionValidator.is_open_domain     = {open_validator.is_open_domain}\n")

    # 展示开放域系统提示（节选）
    open_system = open_builder._build_system_prompt()
    print("--- 开放域 System Prompt（节选前 15 行）---")
    for line in open_system.splitlines()[:15]:
        print(line)
    print("... (省略后续内容)\n")

    # 开放域多轮对话：LLM 自由决定 intent 和 slots 名称
    open_turns = [
        (
            "我想买一张下周五从北京到上海的高铁票，靠窗座位",
            json.dumps(
                {
                    "intent": "BookTrain",
                    "slots": {
                        "departure": "北京",
                        "destination": "上海",
                        "date": "下周五",
                        "seat_preference": "靠窗",
                    },
                    "response": "好的，我帮您查询下周五北京→上海的高铁靠窗座位，请问出行人数是几位？",
                },
                ensure_ascii=False,
            ),
        ),
        (
            "两个成人，另外帮我订一家上海外滩附近的酒店",
            json.dumps(
                {
                    "intent": "BookHotel",
                    "slots": {
                        "location": "上海外滩附近",
                        "guests": "2位成人",
                    },
                    "response": "明白，我为您查找外滩附近的酒店，请问入住和退房日期是？",
                },
                ensure_ascii=False,
            ),
        ),
    ]

    open_history: List[ConversationTurn] = []
    for turn_idx, (user_input, llm_output) in enumerate(open_turns):
        print(f"{'─' * 60}")
        print(f"【开放域 第 {turn_idx + 1} 轮】用户: {user_input}")
        print(f"[LLM 原始输出] {llm_output}")

        result: ValidationResult = open_validator.validate(llm_output)
        print(f"[校验结果] {result.summary()}")

        open_history.append(ConversationTurn(role="user", content=user_input))
        open_history.append(
            ConversationTurn(
                role="assistant",
                content=result.response or "(无回复)",
                action={"intent": result.intent, "slots": result.slots},
            )
        )

        if result.is_valid:
            print(f"  intent : {result.intent}")
            print(f"  slots  : {json.dumps(result.slots, ensure_ascii=False)}")
            print(f"  回复   : {result.response}")
        print()

    # ------------------------------------------------------------------ #
    # 结语
    # ------------------------------------------------------------------ #
    separator("演示完成")
    print(
        "以上展示了 PyTOD schema 适配器的完整流程：\n"
        "1. 导入 PyTOD 风格 schema（service/intent/slot）\n"
        "2. 使用 PyTODPromptBuilder 组装 zero/few-shot prompt\n"
        "3. 使用 ActionValidator 对模型输出进行文本级校验\n"
        "4. 解析反馈，驱动多轮对话\n"
        "5. 开放域模式（schema=None）：无需预定义意图/action/槽位\n\n"
        "接入真实 LLM（如 Qwen-3）时，将 mock_llm_call() 替换为 API 调用即可。"
    )


if __name__ == "__main__":
    run_demo()
