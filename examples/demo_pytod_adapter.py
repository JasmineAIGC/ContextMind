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
    ExecutionEngine,
    ExecutionResult,
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
    # 步骤 7：标准 PyTOD 四步流程演示（与官方算法文档一致）
    # ------------------------------------------------------------------ #
    separator("步骤 7: 标准 PyTOD 四步流程（Action Parser → Execution Engine → Dialogue Manager）")
    print(
        "PyTOD 原始算法流程（参考 docs/algorithms/pytod.md）：\n"
        "  用户输入\n"
        "    ↓\n"
        "  动作解析器（Action Parser）\n"
        "    → 生成多行程序语句，例如：\n"
        "      x1 hotels_1_search_hotel(city='San Jose')\n"
        "      x2 Hint('request value: check_in_date')\n"
        "      x3 say(x2)\n"
        "    ↓\n"
        "  执行引擎（Execution Engine）→ 调用 API / 数据库 → 返回结果\n"
        "    ↓\n"
        "  对话管理器（Dialogue Manager）→ 基于执行结果生成自然语言回复\n"
        "    ↓\n"
        "  系统输出\n"
    )

    # 1. 创建 ExecutionEngine 并注册模拟 API 函数
    from contextmind.modes.pytod import ProgramExecutionResult

    engine = ExecutionEngine()

    @engine.register
    def restaurants_1_find(cuisine=None, location=None, price_range=None):
        """查找餐厅（模拟数据库查询）"""
        results = [
            {"name": "海底捞望京店", "cuisine": "火锅", "rating": 4.8, "address": "望京 SOHO T1"},
            {"name": "大龙燚望京", "cuisine": "火锅", "rating": 4.6, "address": "望京街道"},
        ]
        if cuisine:
            results = [r for r in results if cuisine in r["cuisine"]]
        if location:
            results = [r for r in results if location in r["address"]]
        return results

    @engine.register
    def restaurants_1_reserve(name, date_time, party_size, special_request=None):
        """预约餐厅（模拟 API 调用）"""
        return {
            "reservation_id": "R20260226001",
            "status": "confirmed",
            "restaurant": name,
            "date_time": date_time,
            "party_size": party_size,
            "special_request": special_request or "无",
        }

    print(f"已注册 API 函数: {engine.list_functions()}\n")
    print("--- 执行引擎可用函数（注入 Action Parser prompt）---")
    print(engine.to_prompt_text())
    print()

    # 2. 创建 PromptBuilder（用于 Action Parser 和 Dialogue Manager）
    pytod_builder = PyTODPromptBuilder(response_language="中文")

    # 3. 模拟两轮标准 PyTOD 对话（使用多行程序，与官方算法一致）
    pytod_history: List[ConversationTurn] = []

    pytod_turns = [
        # (用户输入, 动作解析器生成的多行 PyTOD 程序, 对话管理器生成的回复)
        (
            "我想在望京找一家火锅餐厅",
            # 第1轮：查找餐厅，缺少 party_size，用 Hint 引导
            (
                "x1 restaurants_1_find(cuisine='火锅', location='望京')\n"
                "x2 Hint('request value: party_size')\n"
                "x3 say(x2)"
            ),
            "找到了两家望京的火锅餐厅：1. 海底捞望京店（评分4.8）；2. 大龙燚望京（评分4.6）。请问几位用餐？",
        ),
        (
            "选海底捞，帮我预约明晚7点4个人，要包间",
            # 第2轮：预约餐厅（所有参数已知，无需 Hint）
            "x1 restaurants_1_reserve(name='海底捞望京店', date_time='明晚7点', party_size=4, special_request='包间')",
            "预约成功！您的预约编号是 R20260226001，海底捞望京店，明晚7点，4人包间。",
        ),
    ]

    for turn_idx, (user_input, mock_program, mock_dm_response) in enumerate(pytod_turns):
        print(f"{'═' * 60}")
        print(f"【PyTOD 标准流程 第 {turn_idx + 1} 轮】")
        print(f"用户输入: {user_input}\n")

        # --- 步骤一：动作解析器 —— [HISTORY]/[CURRENT] 格式 ---
        ap_messages = pytod_builder.build_action_parser_messages(
            user_input=user_input,
            execution_engine=engine,
            history=pytod_history,
        )
        print(f"[动作解析器 Action Parser]")
        print(f"  → Prompt 已组装（{len(ap_messages)} 条 messages）")
        print(f"  → 对话上下文格式:")
        for line in ap_messages[-1]["content"].splitlines():
            print(f"    {line}")
        print(f"  → LLM 输出多行程序:\n    " + mock_program.replace("\n", "\n    "))

        # --- 步骤二：执行引擎 —— execute_program() 执行多行程序 ---
        exec_result: ProgramExecutionResult = engine.execute_program(mock_program)
        print(f"\n[执行引擎 Execution Engine]")
        if exec_result.success:
            for var, val in exec_result.variable_values.items():
                if not isinstance(val, str):  # 跳过 say() 产生的字符串变量，单独由 say_output 输出
                    print(f"  → {var} = {json.dumps(val, ensure_ascii=False)}")
            if exec_result.hint_messages:
                print(f"  → Hint 提示: {exec_result.hint_messages}")
            if exec_result.say_output:
                print(f"  → say 输出: {exec_result.say_output}")
        else:
            print(f"  → 执行失败: {exec_result.errors}")

        # --- 步骤三：对话管理器 —— 基于执行结果生成自然语言回复 ---
        dm_messages = pytod_builder.build_dialogue_manager_messages(
            user_input=user_input,
            execution_result=exec_result,
            history=pytod_history,
        )
        print(f"\n[对话管理器 Dialogue Manager]")
        print(f"  → Prompt 已组装（{len(dm_messages)} 条 messages）")
        print(f"  → 注入执行结果上下文:\n    " + exec_result.to_context_text().replace("\n", "\n    "))
        print(f"  → LLM 生成回复: {mock_dm_response}")

        # 更新历史
        pytod_history.append(ConversationTurn(role="user", content=user_input))
        pytod_history.append(ConversationTurn(role="assistant", content=mock_dm_response))
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
        "5. 开放域模式（schema=None）：无需预定义意图/action/槽位\n"
        "6. 标准 PyTOD 四步流程（与官方算法文档一致）：\n"
        "   动作解析器 build_action_parser_messages()（[HISTORY]/[CURRENT] 格式）\n"
        "     → 执行引擎 execute_program()（多行程序：API调用/槽位赋值/Hint/say）\n"
        "     → 对话管理器 build_dialogue_manager_messages()（基于执行结果生成回复）\n\n"
        "接入真实 LLM（如 Qwen-3）时，将 mock_llm_call() 替换为 API 调用即可。"
    )


if __name__ == "__main__":
    run_demo()
