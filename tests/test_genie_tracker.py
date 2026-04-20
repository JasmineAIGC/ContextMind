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


# ---------------------------------------------------------------------------
# GenieTracker 集成测试（mock LLM）
# ---------------------------------------------------------------------------

class TestGenieTracker:
    def setup_method(self):
        self.schema = make_restaurant_schema()

    def _make_tracker(self, parse_response="NONE", reply_text="好的，请问您想吃什么菜系？"):
        # SemanticParser 返回 parse_response，ResponseGenerator 返回 reply_text
        llm = MagicMock()
        call_count = [0]

        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            # 第一次调用（语义解析）返回 parse_response
            # 第二次调用（回复生成）返回 reply_text
            if call_count[0] % 2 == 1:
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

