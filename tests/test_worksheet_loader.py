"""
tests/test_worksheet_loader.py

WorksheetLoader 单元测试：
- CSV 加载（含分节）
- JSON 加载
- ServiceSchema 反向导出 CSV / JSON
- PolicyField 类型校验
- IntentDefinition.policy_fields 序列化/反序列化
"""

import pytest
import json

from contextmind.schema_builder.genie_worksheets import WorksheetLoader
from contextmind.schema_builder.genie_worksheets.models import (
    PolicyField,
    _parse_bool,
    _parse_list,
)
from contextmind.modes.pytod.schemas import (
    IntentDefinition,
    ServiceSchema,
    SlotDefinition,
)


# ---------------------------------------------------------------------------
# _parse_bool / _parse_list
# ---------------------------------------------------------------------------

class TestParseBool:
    def test_true_variants(self):
        for v in (True, 1, "true", "TRUE", "yes", "是", "1"):
            assert _parse_bool(v) is True, f"Expected True for {v!r}"

    def test_false_variants(self):
        for v in (False, 0, "false", "FALSE", "no", "0"):
            assert _parse_bool(v) is False, f"Expected False for {v!r}"


class TestParseList:
    def test_list_input(self):
        assert _parse_list(["a", "b", "c"]) == ["a", "b", "c"]

    def test_csv_string(self):
        assert _parse_list("川菜,粤菜,日料") == ["川菜", "粤菜", "日料"]

    def test_empty(self):
        assert _parse_list("") == []
        assert _parse_list([]) == []


# ---------------------------------------------------------------------------
# PolicyField
# ---------------------------------------------------------------------------

class TestPolicyField:
    def test_from_dict_defaults(self):
        pf = PolicyField.from_dict({"name": "cuisine"})
        assert pf.name == "cuisine"
        assert pf.required is True
        assert pf.confirm is False
        assert pf.ask_by_system is True

    def test_from_dict_full(self):
        pf = PolicyField.from_dict({
            "name": "cuisine",
            "description": "菜系",
            "required": "true",
            "confirm": "false",
            "ask_by_system": "true",
            "type": "enum",
            "possible_values": "川菜,粤菜",
            "on_success": "search_api",
        })
        assert pf.field_type == "enum"
        assert pf.possible_values == ["川菜", "粤菜"]
        assert pf.on_success == "search_api"

    def test_to_dict_roundtrip(self):
        pf = PolicyField(
            name="location",
            description="位置",
            required=True,
            confirm=True,
            field_type="str",
        )
        d = pf.to_dict()
        pf2 = PolicyField.from_dict(d)
        assert pf2.name == pf.name
        assert pf2.confirm == pf.confirm

    def test_to_prompt_text(self):
        pf = PolicyField(
            name="party_size",
            description="就餐人数",
            required=True,
            field_type="int",
        )
        text = pf.to_prompt_text()
        assert "party_size" in text
        assert "必填" in text


# ---------------------------------------------------------------------------
# IntentDefinition with policy_fields
# ---------------------------------------------------------------------------

class TestIntentDefinitionPolicyFields:
    def test_from_dict_with_policy_fields(self):
        data = {
            "name": "search_restaurant",
            "description": "搜索餐厅",
            "required_slots": ["cuisine"],
            "optional_slots": [],
            "policy_fields": [
                {"name": "cuisine", "type": "enum", "description": "菜系",
                 "required": True, "possible_values": ["川菜", "粤菜"]},
                {"name": "location", "description": "位置", "required": True},
            ]
        }
        intent = IntentDefinition.from_dict(data)
        assert len(intent.policy_fields) == 2
        assert intent.policy_fields[0].name == "cuisine"
        assert intent.policy_fields[0].field_type == "enum"

    def test_to_dict_includes_policy_fields(self):
        intent = IntentDefinition(
            name="book",
            description="预订",
            policy_fields=[PolicyField(name="date_time", description="时间", required=True)],
        )
        d = intent.to_dict()
        assert "policy_fields" in d
        assert d["policy_fields"][0]["name"] == "date_time"

    def test_to_dict_omits_empty_policy_fields(self):
        intent = IntentDefinition(name="search", description="搜索")
        d = intent.to_dict()
        assert "policy_fields" not in d

    def test_to_prompt_text_with_policy_fields(self):
        intent = IntentDefinition(
            name="book",
            description="预订",
            policy_fields=[
                PolicyField(name="restaurant_name", description="餐厅名", required=True),
                PolicyField(name="party_size", description="人数", required=False),
            ],
        )
        text = intent.to_prompt_text()
        assert "策略字段" in text
        assert "restaurant_name" in text


# ---------------------------------------------------------------------------
# ServiceSchema.get_intent_by_api_name
# ---------------------------------------------------------------------------

class TestServiceSchemaGetIntentByApiName:
    def _make_schema(self):
        return ServiceSchema(
            service_name="TestService",
            description="",
            slots=[],
            intents=[
                IntentDefinition(name="search_restaurant", description="搜索"),
                IntentDefinition(name="book_restaurant", description="预订"),
            ],
        )

    def test_exact_match(self):
        schema = self._make_schema()
        assert schema.get_intent_by_api_name("search_restaurant") is not None

    def test_suffix_match(self):
        schema = self._make_schema()
        assert schema.get_intent_by_api_name("service_1_book_restaurant") is not None

    def test_no_match(self):
        schema = self._make_schema()
        assert schema.get_intent_by_api_name("unknown_api") is None


# ---------------------------------------------------------------------------
# WorksheetLoader.from_csv_string
# ---------------------------------------------------------------------------

CSV_SAMPLE = """\
# service: 餐厅服务
# description: 中文餐厅预订系统

# search_restaurant 搜索餐厅
name,type,description,required,confirm,ask_by_system,depends_on,possible_values,on_success
cuisine,enum,菜系类型,true,false,true,,"川菜,粤菜,日料",
location,str,餐厅位置,true,false,true,,,
party_size,int,就餐人数,false,false,true,,,

# book_restaurant 预订餐厅
name,type,description,required,confirm,ask_by_system,depends_on,possible_values,on_success
restaurant_name,str,餐厅名称,true,false,true,,,
date_time,str,预订时间,true,true,true,,,book_api
contact_phone,str,联系电话,true,false,true,restaurant_name,,
"""


class TestWorksheetLoaderFromCsv:
    def test_parses_service_name(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        assert schema.service_name == "餐厅服务"

    def test_parses_two_intents(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        assert len(schema.intents) == 2
        names = [i.name for i in schema.intents]
        assert "search_restaurant" in names
        assert "book_restaurant" in names

    def test_parses_policy_fields(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        search = schema.get_intent("search_restaurant")
        assert search is not None
        assert len(search.policy_fields) == 3

    def test_enum_possible_values(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        search = schema.get_intent("search_restaurant")
        cuisine_pf = next(pf for pf in search.policy_fields if pf.name == "cuisine")
        assert "川菜" in cuisine_pf.possible_values

    def test_confirm_flag(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        book = schema.get_intent("book_restaurant")
        date_pf = next(pf for pf in book.policy_fields if pf.name == "date_time")
        assert date_pf.confirm is True

    def test_depends_on(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        book = schema.get_intent("book_restaurant")
        phone_pf = next(pf for pf in book.policy_fields if pf.name == "contact_phone")
        assert phone_pf.depends_on == "restaurant_name"

    def test_required_slots_inferred(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        search = schema.get_intent("search_restaurant")
        assert "cuisine" in search.required_slots
        assert "location" in search.required_slots
        assert "party_size" in search.optional_slots

    def test_slots_populated(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        slot_names = schema.get_slot_names()
        assert "cuisine" in slot_names

    def test_service_name_override(self):
        schema = WorksheetLoader.from_csv_string(CSV_SAMPLE, service_name="覆盖名称")
        assert schema.service_name == "覆盖名称"


# ---------------------------------------------------------------------------
# WorksheetLoader.from_dict
# ---------------------------------------------------------------------------

WORKSHEET_JSON = {
    "service_name": "订单服务",
    "description": "处理订单相关请求",
    "intents": [
        {
            "name": "create_order",
            "description": "创建订单",
            "policy_fields": [
                {"name": "product_id", "type": "str", "description": "商品ID",
                 "required": True, "confirm": False},
                {"name": "quantity", "type": "int", "description": "数量",
                 "required": True, "confirm": True},
            ]
        }
    ]
}


class TestWorksheetLoaderFromDict:
    def test_parses_service_name(self):
        schema = WorksheetLoader.from_dict(WORKSHEET_JSON)
        assert schema.service_name == "订单服务"

    def test_parses_intent(self):
        schema = WorksheetLoader.from_dict(WORKSHEET_JSON)
        assert len(schema.intents) == 1
        assert schema.intents[0].name == "create_order"

    def test_parses_policy_fields(self):
        schema = WorksheetLoader.from_dict(WORKSHEET_JSON)
        intent = schema.intents[0]
        assert len(intent.policy_fields) == 2
        qty_pf = next(pf for pf in intent.policy_fields if pf.name == "quantity")
        assert qty_pf.field_type == "int"
        assert qty_pf.confirm is True

    def test_list_input(self):
        fields = [
            {"name": "color", "description": "颜色", "required": True},
        ]
        schema = WorksheetLoader.from_dict(fields)
        assert len(schema.intents) == 1
        assert len(schema.intents[0].policy_fields) == 1


# ---------------------------------------------------------------------------
# WorksheetLoader.to_csv
# ---------------------------------------------------------------------------

class TestWorksheetLoaderToCsv:
    def test_roundtrip(self):
        """CSV → Schema → CSV → Schema 应保持字段一致。"""
        schema1 = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        csv_out = WorksheetLoader.to_csv(schema1)
        schema2 = WorksheetLoader.from_csv_string(csv_out)

        names1 = sorted(i.name for i in schema1.intents)
        names2 = sorted(i.name for i in schema2.intents)
        assert names1 == names2

        for name in names1:
            i1 = schema1.get_intent(name)
            i2 = schema2.get_intent(name)
            pf_names1 = sorted(pf.name for pf in i1.policy_fields)
            pf_names2 = sorted(pf.name for pf in i2.policy_fields)
            assert pf_names1 == pf_names2

    def test_inferred_policy_fields(self):
        """从无 policy_fields 的标准 schema 导出 CSV，应能从槽位自动推导。"""
        schema = ServiceSchema(
            service_name="简单服务",
            description="",
            slots=[
                SlotDefinition(name="customer_name", description="客户姓名", is_required=True),
                SlotDefinition(name="product", description="产品"),
            ],
            intents=[
                IntentDefinition(
                    name="query",
                    description="查询",
                    required_slots=["customer_name"],
                    optional_slots=["product"],
                )
            ],
        )
        csv_text = WorksheetLoader.to_csv(schema)
        assert "customer_name" in csv_text
        assert "product" in csv_text


# ---------------------------------------------------------------------------
# WorksheetLoader.to_worksheet_json
# ---------------------------------------------------------------------------

class TestWorksheetLoaderToJson:
    def test_json_roundtrip(self):
        schema1 = WorksheetLoader.from_csv_string(CSV_SAMPLE)
        json_text = WorksheetLoader.to_worksheet_json(schema1)
        data = json.loads(json_text)
        schema2 = WorksheetLoader.from_dict(data)

        assert schema1.service_name == schema2.service_name
        assert len(schema1.intents) == len(schema2.intents)
