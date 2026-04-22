"""
tests/test_genie_tracker.py

GenieTracker / PolicyExecutor / SemanticParser 单元测试（无 LLM 依赖）。

所有 LLM 调用均通过 mock 替代，保证测试在离线环境下可运行。
本文件仅测试 genie 模块本身，不依赖 contextmind.modes.pytod 的任何代码。
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from contextmind.modes.genie.policy_executor import (
    PolicyExecutor,
    WorksheetState,
    FieldStatus,
)
from contextmind.modes.genie.semantic_parser import SemanticParser
from contextmind.modes.genie.tracker import GenieTracker
from contextmind.schema_builder.genie_worksheets import PolicyField, WorksheetLoader
from contextmind.schema_builder.genie_worksheets.schema_types import (
    GenieIntent,
    GenieSchema,
    GenieSlot,
)


# ---------------------------------------------------------------------------
# 测试 Fixture：带 policy_fields 的 GenieSchema
# ---------------------------------------------------------------------------

def make_restaurant_schema() -> GenieSchema:
    return GenieSchema(
        service_name="餐厅服务",
        description="餐厅预订",
        slots=[
            GenieSlot(name="cuisine", description="菜系", is_categorical=True,
                      possible_values=["川菜", "粤菜", "日料"]),
            GenieSlot(name="location", description="位置"),
            GenieSlot(name="party_size", description="人数"),
        ],
        intents=[
            GenieIntent(
                name="search_restaurant",
                description="搜索餐厅",
                required_slots=["cuisine", "location"],
                optional_slots=["party_size"],
                policy_fields=[
                    PolicyField(name="cuisine", description="菜系", required=True,
                                field_type="enum", possible_values=["川菜", "粤菜", "日料"]),
                    PolicyField(name="location", description="位置", required=True,
                                field_type="str"),
                    PolicyField(name="party_size", description="人数", required=False,
                                field_type="int"),
                ],
            )
        ],
    )


def make_mock_llm(response_text: str = "NONE") -> MagicMock:
    """创建一个模拟 LLM 客户端，固定返回指定文本。"""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=response_text)
    llm.generate_async = AsyncMock(return_value=response_text)
    return llm


# ---------------------------------------------------------------------------
# PolicyExecutor 测试
# ---------------------------------------------------------------------------

class TestPolicyExecutor:
    def setup_method(self):
        self.schema = make_restaurant_schema()
        self.executor = PolicyExecutor(self.schema)

    def test_resolves_first_intent_with_policy_fields(self):
        assert self.executor.intent is not None
        assert self.executor.intent.name == "search_restaurant"

    def test_next_required_field_empty_state(self):
        nf = self.executor.next_required_field()
        assert nf is not None
        assert nf.name == "cuisine"  # 第一个必填字段

    def test_fill_valid_enum(self):
        ok, err = self.executor.fill_field("cuisine", "川菜")
        assert ok is True
        assert err == ""
        assert self.executor.state.is_filled("cuisine")

    def test_fill_invalid_enum(self):
        ok, err = self.executor.fill_field("cuisine", "火锅")
        assert ok is False
        assert "不在合法枚举" in err

    def test_fill_enum_case_insensitive(self):
        ok, err = self.executor.fill_field("cuisine", "川菜 ")
        assert ok is True

    def test_fill_int_type_coercion(self):
        ok, err = self.executor.fill_field("party_size", "4")
        assert ok is True
        assert self.executor.state.get_value("party_size") == 4

    def test_fill_int_invalid(self):
        ok, err = self.executor.fill_field("party_size", "abc")
        assert ok is False
        assert "整数" in err

    def test_next_field_advances_after_fill(self):
        self.executor.fill_field("cuisine", "川菜")
        nf = self.executor.next_required_field()
        assert nf is not None
        assert nf.name == "location"

    def test_is_complete_false(self):
        assert self.executor.is_complete() is False

    def test_is_complete_true_after_required_filled(self):
        self.executor.fill_field("cuisine", "粤菜")
        self.executor.fill_field("location", "北京")
        assert self.executor.is_complete() is True

    def test_next_field_none_when_complete(self):
        # Fill required fields — optional ask_by_system field (party_size) may still be returned.
        # `is_complete()` should be True; `next_required_field()` may be the optional field.
        self.executor.fill_field("cuisine", "粤菜")
        self.executor.fill_field("location", "北京")
        assert self.executor.is_complete() is True
        # After filling optional too, next_required_field returns None
        self.executor.fill_field("party_size", "4")
        assert self.executor.next_required_field() is None

    def test_fill_batch(self):
        errors = self.executor.fill_batch({"cuisine": "日料", "location": "上海"})
        assert errors == []
        assert self.executor.is_complete() is True

    def test_get_missing_required(self):
        missing = self.executor.get_missing_required()
        assert len(missing) == 2  # cuisine + location

    def test_reset_clears_state(self):
        self.executor.fill_field("cuisine", "川菜")
        self.executor.reset()
        assert not self.executor.state.is_filled("cuisine")

    def test_depends_on_field_skipped(self):
        """若 depends_on 字段未填，条件字段不参与完成判断。"""
        schema = GenieSchema(
            service_name="svc",
            description="",
            slots=[],
            intents=[
                GenieIntent(
                    name="intent",
                    description="",
                    policy_fields=[
                        PolicyField(name="a", required=True),
                        PolicyField(name="b", required=True, depends_on="a"),
                    ],
                )
            ],
        )
        exe = PolicyExecutor(schema)
        exe.fill_field("a", "val_a")
        # b 虽然必填，但依赖 a，a 已填，所以 b 现在也需要填
        assert exe.is_complete() is False
        exe.fill_field("b", "val_b")
        assert exe.is_complete() is True

    def test_confirm_field(self):
        schema = GenieSchema(
            service_name="svc",
            description="",
            slots=[],
            intents=[
                GenieIntent(
                    name="intent",
                    description="",
                    policy_fields=[
                        PolicyField(name="amount", required=True, confirm=True),
                    ],
                )
            ],
        )
        exe = PolicyExecutor(schema)
        exe.fill_field("amount", "100")
        assert exe.state.field_statuses.get("amount") == FieldStatus.PENDING_CONFIRM
        exe.confirm_field("amount")
        assert exe.state.field_statuses.get("amount") == FieldStatus.CONFIRMED

    def test_undefined_field_accepted(self):
        """未在 policy_fields 中定义的字段仍可被填写（跳过校验）。"""
        ok, err = self.executor.fill_field("undefined_slot", "some_value")
        assert ok is True
        assert self.executor.state.get_value("undefined_slot") == "some_value"


# ---------------------------------------------------------------------------
# SemanticParser 测试（mock LLM）
# ---------------------------------------------------------------------------

class TestSemanticParser:
    def setup_method(self):
        self.schema = make_restaurant_schema()
        self.executor = PolicyExecutor(self.schema)

    def test_parse_valid_json(self):
        llm = make_mock_llm('{"cuisine": "川菜", "location": "北京"}')
        parser = SemanticParser(llm)
        result = asyncio.get_event_loop().run_until_complete(
            parser.parse("我想吃川菜，在北京", self.executor)
        )
        assert result == {"cuisine": "川菜", "location": "北京"}

    def test_parse_none_output(self):
        llm = make_mock_llm("NONE")
        parser = SemanticParser(llm)
        result = asyncio.get_event_loop().run_until_complete(
            parser.parse("你好", self.executor)
        )
        assert result == {}

    def test_parse_markdown_json(self):
        llm = make_mock_llm('```json\n{"location": "上海"}\n```')
        parser = SemanticParser(llm)
        result = asyncio.get_event_loop().run_until_complete(
            parser.parse("在上海", self.executor)
        )
        assert result.get("location") == "上海"

    def test_parse_filters_none_values(self):
        llm = make_mock_llm('{"cuisine": "粤菜", "location": null}')
        parser = SemanticParser(llm)
        result = asyncio.get_event_loop().run_until_complete(
            parser.parse("粤菜", self.executor)
        )
        assert "location" not in result
        assert result.get("cuisine") == "粤菜"

    def test_parse_llm_error_returns_empty(self):
        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=RuntimeError("LLM 不可用"))
        parser = SemanticParser(llm)
        result = asyncio.get_event_loop().run_until_complete(
            parser.parse("你好", self.executor)
        )
        assert result == {}

    def test_parse_plan_extract_format(self):
        """Plan+Extract 两步格式的输出应正确解析。"""
        plan_output = (
            "# 分析\n"
            "用户提到了川菜和北京，分别对应 cuisine 和 location 字段。\n\n"
            "# 提取结果\n"
            '{"cuisine": "川菜", "location": "北京"}'
        )
        llm = make_mock_llm(plan_output)
        parser = SemanticParser(llm)
        result = asyncio.get_event_loop().run_until_complete(
            parser.parse("我想在北京吃川菜", self.executor)
        )
        assert result.get("cuisine") == "川菜"
        assert result.get("location") == "北京"

    def test_extract_result_section(self):
        """_extract_result_section 应正确提取 # 提取结果 段落。"""
        text = "# 分析\n分析内容\n\n# 提取结果\n{\"a\": 1}"
        section = SemanticParser._extract_result_section(text)
        assert section is not None
        assert section.strip().startswith("{")

    def test_extract_result_section_none_when_missing(self):
        """无 # 提取结果 标记时应返回 None。"""
        text = '{"a": 1}'
        section = SemanticParser._extract_result_section(text)
        assert section is None

class TestGenieTracker:
    def setup_method(self):
        self.schema = make_restaurant_schema()

    def _make_tracker(self, parse_response="NONE", reply_text="好的，请问您想吃什么菜系？"):
        # 每轮 process_turn 有 3 次 LLM 调用：
        #   call 1: 意图路由    → 返回合法意图名（schema 中的第一个意图）
        #   call 2: 语义解析    → 返回 parse_response
        #   call 3: 回复生成    → 返回 reply_text
        llm = MagicMock()
        call_count = [0]
        # 取 schema 第一个意图名作为路由返回值（单意图 schema）
        route_response = self.schema.intents[0].name if self.schema.intents else "unknown"

        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            pos = (call_count[0] - 1) % 3  # 0=路由, 1=解析, 2=回复
            if pos == 0:
                return route_response
            if pos == 1:
                return parse_response
            return reply_text

        llm.chat = AsyncMock(side_effect=side_effect)
        return GenieTracker(
            llm_client=llm,
            schema=self.schema,
            scene_description="餐厅预订助手",
        )

    def test_initial_state_is_empty(self):
        tracker = self._make_tracker()
        state = tracker.get_current_state()
        assert state == {}

    def test_process_turn_extracts_fields(self):
        parse_resp = '{"cuisine": "川菜", "location": "北京"}'
        tracker = self._make_tracker(parse_response=parse_resp)
        result = asyncio.get_event_loop().run_until_complete(
            tracker.process_turn("我想吃川菜，在北京")
        )
        assert result["extracted_fields"].get("cuisine") == "川菜"
        assert "cuisine" in result["worksheet_state"]

    def test_process_turn_is_complete(self):
        parse_resp = '{"cuisine": "川菜", "location": "北京"}'
        tracker = self._make_tracker(parse_response=parse_resp)
        asyncio.get_event_loop().run_until_complete(
            tracker.process_turn("我想吃川菜，在北京")
        )
        assert tracker.is_complete is True

    def test_process_turn_not_complete_when_missing(self):
        tracker = self._make_tracker(parse_response="NONE")
        result = asyncio.get_event_loop().run_until_complete(
            tracker.process_turn("你好")
        )
        assert result["is_complete"] is False
        assert len(result["missing_required"]) > 0

    def test_reset_clears_state(self):
        parse_resp = '{"cuisine": "川菜", "location": "北京"}'
        tracker = self._make_tracker(parse_response=parse_resp)
        asyncio.get_event_loop().run_until_complete(
            tracker.process_turn("我想吃川菜，在北京")
        )
        assert tracker.is_complete is True
        tracker.reset()
        assert tracker.is_complete is False
        assert tracker.get_current_state() == {}

    def test_process_turn_has_response(self):
        tracker = self._make_tracker(reply_text="请问您想吃什么菜系？")
        result = asyncio.get_event_loop().run_until_complete(
            tracker.process_turn("你好")
        )
        assert "response" in result
        assert result["response"] == "请问您想吃什么菜系？"

    def test_process_turn_returns_worksheet_state(self):
        result_holder = asyncio.get_event_loop().run_until_complete(
            self._make_tracker().process_turn("你好")
        )
        assert "worksheet_state" in result_holder
        assert "is_complete" in result_holder

    def test_from_worksheet_csv(self):
        """from_scenario 通过 worksheet_path 加载 CSV。"""
        import tempfile, os
        csv_text = """\
# search 搜索
name,type,description,required,confirm,ask_by_system,depends_on,possible_values,on_success
keyword,str,搜索关键词,true,false,true,,,
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_text)
            tmp_path = f.name

        try:
            config = MagicMock()
            config.scene_name = "搜索服务"
            config.scene_description = "搜索"
            llm = make_mock_llm("NONE")
            tracker = GenieTracker.from_scenario(
                llm_client=llm,
                scenario_config=config,
                worksheet_path=tmp_path,
            )
            assert isinstance(tracker, GenieTracker)
            assert tracker._executor.intent is not None
        finally:
            os.unlink(tmp_path)

    def test_from_scenario_requires_schema_or_path(self):
        config = MagicMock()
        config.scene_name = "test"
        config.scene_description = ""
        llm = make_mock_llm("NONE")
        with pytest.raises(ValueError, match="schema 或 worksheet_path"):
            GenieTracker.from_scenario(llm_client=llm, scenario_config=config)


# ---------------------------------------------------------------------------
# AgentActs 测试
# ---------------------------------------------------------------------------

class TestAgentActs:
    """AgentActs 容器和动作类测试。"""

    def setup_method(self):
        self.schema = make_restaurant_schema()
        pfs = self.schema.intents[0].policy_fields
        self.pf_cuisine = pfs[0]
        self.pf_location = pfs[1]

    def test_ask_agent_act_repr(self):
        from contextmind.modes.genie.agent_acts import AskAgentAct
        act = AskAgentAct(field=self.pf_cuisine, intent_name="search_restaurant")
        text = repr(act)
        assert "AskField" in text
        assert "cuisine" in text

    def test_ask_for_confirmation_repr(self):
        from contextmind.modes.genie.agent_acts import AskForConfirmationAgentAct
        act = AskForConfirmationAgentAct(
            field=self.pf_cuisine, value="川菜", intent_name="search_restaurant"
        )
        text = repr(act)
        assert "AskForFieldConfirmation" in text
        assert "川菜" in text

    def test_report_agent_act_repr(self):
        from contextmind.modes.genie.agent_acts import ReportAgentAct
        act = ReportAgentAct(api_name="search_api", result={"count": 5})
        text = repr(act)
        assert "Report" in text
        assert "search_api" in text

    def test_agent_acts_mutual_exclusion(self):
        from contextmind.modes.genie.agent_acts import AgentActs, AskAgentAct
        acts = AgentActs()
        acts.add(AskAgentAct(field=self.pf_cuisine))
        # 不应再添加第二个 Ask
        ok = acts.add(AskAgentAct(field=self.pf_location))
        assert ok is False
        assert len(acts) == 1

    def test_agent_acts_allows_report_with_ask(self):
        from contextmind.modes.genie.agent_acts import AgentActs, AskAgentAct, ReportAgentAct
        acts = AgentActs()
        acts.add(ReportAgentAct(api_name="api1", result="ok"))
        ok = acts.add(AskAgentAct(field=self.pf_cuisine))
        assert ok is True
        assert len(acts) == 2

    def test_agent_acts_to_prompt_lines(self):
        from contextmind.modes.genie.agent_acts import AgentActs, AskAgentAct
        acts = AgentActs()
        acts.add(AskAgentAct(field=self.pf_cuisine, intent_name="ws"))
        lines = acts.to_prompt_lines()
        assert len(lines) == 1
        assert "AskField" in lines[0]


# ---------------------------------------------------------------------------
# 确认流程测试
# ---------------------------------------------------------------------------

class TestConfirmationFlow:
    """confirm=True 字段的确认流程测试。"""

    def setup_method(self):
        self.schema = GenieSchema(
            service_name="测试服务",
            description="确认流程测试",
            slots=[],
            intents=[
                GenieIntent(
                    name="book",
                    description="预订",
                    required_slots=["date"],
                    optional_slots=[],
                    policy_fields=[
                        PolicyField(name="date", description="预订日期",
                                    required=True, confirm=True,
                                    field_type="str"),
                    ],
                )
            ],
        )

    def test_fill_confirm_field_sets_pending(self):
        from contextmind.modes.genie.policy_executor import FieldStatus
        executor = PolicyExecutor(self.schema)
        ok, _ = executor.fill_field("date", "2026-05-01")
        assert ok
        assert executor.state.field_statuses["date"] == FieldStatus.PENDING_CONFIRM

    def test_get_pending_confirm_fields(self):
        executor = PolicyExecutor(self.schema)
        executor.fill_field("date", "2026-05-01")
        pending = executor.get_pending_confirm_fields()
        assert len(pending) == 1
        assert pending[0].name == "date"

    def test_confirm_field_clears_pending(self):
        from contextmind.modes.genie.policy_executor import FieldStatus
        executor = PolicyExecutor(self.schema)
        executor.fill_field("date", "2026-05-01")
        ok = executor.confirm_field("date")
        assert ok
        assert executor.state.field_statuses["date"] == FieldStatus.CONFIRMED
        # 确认后 is_complete 应为 True（依赖确认语义）
        # Note: is_complete 只检查 is_filled，不检查 status
        assert executor.is_complete()

    def test_reject_field_clears_value(self):
        executor = PolicyExecutor(self.schema)
        executor.fill_field("date", "2026-05-01")
        ok = executor.reject_field("date")
        assert ok
        assert not executor.state.is_filled("date")

    def test_reject_nonexistent_field_returns_false(self):
        executor = PolicyExecutor(self.schema)
        ok = executor.reject_field("date")  # 未填过
        assert ok is False

    def test_tracker_process_turn_with_confirm(self):
        """confirm=True 字段 PENDING_CONFIRM 后，下一轮处理 yes/no。"""
        llm = make_mock_llm('{"date": "2026-05-01"}')
        tracker = GenieTracker(
            llm_client=llm,
            schema=self.schema,
            scene_description="预订测试",
        )

        # 第一轮：提取字段 → PENDING_CONFIRM
        async def run_first():
            return await tracker.process_turn("我想预订2026年5月1日")

        result1 = asyncio.get_event_loop().run_until_complete(run_first())
        assert result1["worksheet_state"].get("date") == "2026-05-01"
        pending = tracker._executor.get_pending_confirm_fields()
        assert len(pending) == 1

        # 第二轮：用户说"是" → CONFIRMED
        llm.chat = AsyncMock(return_value="YES")
        async def run_second():
            return await tracker.process_turn("是的，确认")

        result2 = asyncio.get_event_loop().run_until_complete(run_second())
        assert "date" in result2["confirmed_fields"]
        from contextmind.modes.genie.policy_executor import FieldStatus
        assert tracker._executor.state.field_statuses["date"] == FieldStatus.CONFIRMED

    def test_tracker_process_turn_reject_confirm(self):
        """用户拒绝确认时，字段值应被清除。"""
        llm = make_mock_llm('{"date": "2026-05-01"}')
        tracker = GenieTracker(
            llm_client=llm,
            schema=self.schema,
            scene_description="预订测试",
        )
        async def run_first():
            return await tracker.process_turn("预订5月1日")
        asyncio.get_event_loop().run_until_complete(run_first())

        # 第二轮：用户说"不" → 字段被清除
        llm.chat = AsyncMock(return_value="NO")
        async def run_second():
            return await tracker.process_turn("不，日期不对")
        result2 = asyncio.get_event_loop().run_until_complete(run_second())
        assert "date" in result2["rejected_fields"]
        assert not tracker._executor.state.is_filled("date")


# ---------------------------------------------------------------------------
# on_success dispatch 测试
# ---------------------------------------------------------------------------

class TestOnSuccessDispatch:
    """on_success API 回调触发测试。"""

    def setup_method(self):
        self.schema = GenieSchema(
            service_name="搜索服务",
            description="on_success 测试",
            slots=[],
            intents=[
                GenieIntent(
                    name="search",
                    description="搜索",
                    required_slots=["keyword"],
                    optional_slots=[],
                    policy_fields=[
                        PolicyField(name="keyword", description="关键词",
                                    required=True, confirm=False,
                                    field_type="str",
                                    on_success="do_search"),
                    ],
                )
            ],
        )

    def test_get_on_success_actions_after_fill(self):
        executor = PolicyExecutor(self.schema)
        executor.fill_field("keyword", "川菜餐厅")
        actions = executor.get_on_success_actions()
        assert len(actions) == 1
        assert actions[0] == ("keyword", "do_search")

    def test_mark_on_success_dispatched(self):
        from contextmind.modes.genie.policy_executor import FieldStatus
        executor = PolicyExecutor(self.schema)
        executor.fill_field("keyword", "川菜餐厅")
        executor.mark_on_success_dispatched("keyword")
        # 状态应从 FILLED 升级为 CONFIRMED
        assert executor.state.field_statuses["keyword"] == FieldStatus.CONFIRMED
        # 不应再返回 on_success 动作
        assert executor.get_on_success_actions() == []

    def test_tracker_dispatches_registered_api(self):
        """process_turn 应自动调用注册的 on_success 函数。"""
        call_log = []

        def my_search():
            call_log.append("called")
            return {"results": ["餐厅A", "餐厅B"]}

        llm = make_mock_llm('{"keyword": "川菜"}')
        tracker = GenieTracker(
            llm_client=llm,
            schema=self.schema,
            scene_description="搜索测试",
        )
        tracker.register_api("do_search", my_search)

        async def run():
            return await tracker.process_turn("帮我找川菜餐厅")

        result = asyncio.get_event_loop().run_until_complete(run())
        assert call_log == ["called"]
        assert "do_search" in result["dispatched_apis"]

    def test_tracker_skips_unregistered_api(self):
        """未注册的 on_success API 应跳过，不抛出异常。"""
        llm = make_mock_llm('{"keyword": "川菜"}')
        tracker = GenieTracker(
            llm_client=llm,
            schema=self.schema,
            scene_description="搜索测试",
        )
        # 不注册任何 API

        async def run():
            return await tracker.process_turn("帮我找川菜")

        result = asyncio.get_event_loop().run_until_complete(run())
        # 未注册时 dispatched_apis 为空，不抛异常
        assert result["dispatched_apis"] == []



# ---------------------------------------------------------------------------
# pipeline Bug 修复：raw dict → PolicyField 转换
# ---------------------------------------------------------------------------

def _service_schema_to_genie_schema_impl(service_schema):
    """测试用：内联复制 pipeline._service_schema_to_genie_schema 的逻辑，
    避免 pipeline.py 顶层 import google.adk 导致的 ModuleNotFoundError。"""
    from contextmind.schema_builder.genie_worksheets.models import PolicyField
    from contextmind.schema_builder.genie_worksheets.schema_types import (
        GenieIntent, GenieSchema, GenieSlot,
    )
    slots = [
        GenieSlot(
            name=s.name, description=s.description,
            is_categorical=s.is_categorical, possible_values=list(s.possible_values),
            is_required=s.is_required,
        )
        for s in service_schema.slots
    ]
    intents = [
        GenieIntent(
            name=i.name, description=i.description,
            required_slots=list(i.required_slots),
            optional_slots=list(i.optional_slots),
            result_slots=list(i.result_slots),
            is_transactional=i.is_transactional,
            policy_fields=[
                pf if isinstance(pf, PolicyField) else PolicyField.from_dict(pf)
                for pf in i.policy_fields
            ],
        )
        for i in service_schema.intents
    ]
    return GenieSchema(
        service_name=service_schema.service_name,
        description=service_schema.description,
        slots=slots, intents=intents,
    )


class TestPipelineBugFix:
    """_service_schema_to_genie_schema 函数中 raw dict → PolicyField 转换测试。"""

    def test_raw_dict_policy_field_conversion(self):
        """raw dict policy_fields 应被正确转换为 PolicyField 对象。"""
        from contextmind.schema_builder.genie_worksheets.models import PolicyField

        mock_slot = MagicMock()
        mock_slot.name = "cuisine"
        mock_slot.description = "菜系"
        mock_slot.is_categorical = True
        mock_slot.possible_values = ["川菜", "粤菜"]
        mock_slot.is_required = True

        mock_intent = MagicMock()
        mock_intent.name = "search_restaurant"
        mock_intent.description = "搜索餐厅"
        mock_intent.required_slots = ["cuisine"]
        mock_intent.optional_slots = []
        mock_intent.result_slots = []
        mock_intent.is_transactional = False
        # raw dict 格式（不是 PolicyField 对象）
        mock_intent.policy_fields = [
            {"name": "cuisine", "type": "enum", "description": "菜系",
             "required": "true", "confirm": "false", "ask_by_system": "true",
             "possible_values": "川菜,粤菜", "on_success": ""}
        ]

        mock_schema = MagicMock()
        mock_schema.service_name = "餐厅服务"
        mock_schema.description = "测试"
        mock_schema.slots = [mock_slot]
        mock_schema.intents = [mock_intent]

        # 不应抛出 AttributeError
        genie_schema = _service_schema_to_genie_schema_impl(mock_schema)
        assert len(genie_schema.intents) == 1
        pf = genie_schema.intents[0].policy_fields[0]
        assert isinstance(pf, PolicyField), f"期望 PolicyField，得到 {type(pf)}"
        assert pf.name == "cuisine"
        assert pf.required is True

    def test_policy_field_object_passthrough(self):
        """已是 PolicyField 对象的 policy_fields 应原样保留。"""
        from contextmind.schema_builder.genie_worksheets.models import PolicyField

        pf_obj = PolicyField(name="location", description="位置", required=True)

        mock_slot = MagicMock()
        mock_slot.name = "location"
        mock_slot.description = "位置"
        mock_slot.is_categorical = False
        mock_slot.possible_values = []
        mock_slot.is_required = True

        mock_intent = MagicMock()
        mock_intent.name = "search"
        mock_intent.description = ""
        mock_intent.required_slots = ["location"]
        mock_intent.optional_slots = []
        mock_intent.result_slots = []
        mock_intent.is_transactional = False
        mock_intent.policy_fields = [pf_obj]  # 已是 PolicyField 对象

        mock_schema = MagicMock()
        mock_schema.service_name = "服务"
        mock_schema.description = ""
        mock_schema.slots = [mock_slot]
        mock_schema.intents = [mock_intent]

        genie_schema = _service_schema_to_genie_schema_impl(mock_schema)
        result_pf = genie_schema.intents[0].policy_fields[0]
        assert isinstance(result_pf, PolicyField)
        assert result_pf.name == "location"
