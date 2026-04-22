"""
tests/test_pytod_policy.py

ExecutionEngine Worksheet 策略约束测试（纯 pytod 代码，不涉及 genie_worksheets 模块）。

这些测试验证 pytod ExecutionEngine 的 _check_policy_constraints 方法，
使用 pytod ServiceSchema / IntentDefinition 和 genie_worksheets PolicyField（跨层使用）。
"""

import pytest

from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema
from contextmind.schema_builder.genie_worksheets import PolicyField


class TestExecutionEnginePolicyConstraints:
    """确保 EE 的 Worksheet 约束检查不影响无 schema 的正常执行。"""

    def setup_method(self):
        from contextmind.modes.pytod.execution_engine import ExecutionEngine
        self.engine = ExecutionEngine()

        @self.engine.register
        def query_order(order_id: str = None, customer_name: str = None) -> dict:
            return {"status": "success", "order_id": order_id}

    def test_no_schema_no_constraint(self):
        """无 schema 时，约束检查不拦截调用。"""
        result = self.engine._call_registered("query_order", {"order_id": "123"})
        assert isinstance(result, dict)
        assert result.get("order_id") == "123"

    def test_with_schema_passes_when_required_filled(self):
        """schema 已设且必填字段齐全时，正常调用。"""
        schema = ServiceSchema(
            service_name="svc",
            description="",
            slots=[],
            intents=[
                IntentDefinition(
                    name="query_order",
                    description="查询订单",
                    policy_fields=[
                        PolicyField(name="order_id", required=True),
                    ],
                )
            ],
        )
        self.engine.schema = schema
        result = self.engine._call_registered("query_order", {"order_id": "ORD001"})
        from contextmind.modes.pytod.execution_engine import PolicyViolationError
        assert not isinstance(result, PolicyViolationError)

    def test_with_schema_blocks_when_required_missing(self):
        """schema 已设且必填字段缺失时，返回 PolicyViolationError。"""
        schema = ServiceSchema(
            service_name="svc",
            description="",
            slots=[],
            intents=[
                IntentDefinition(
                    name="query_order",
                    description="查询订单",
                    policy_fields=[
                        PolicyField(name="order_id", required=True, description="订单号"),
                    ],
                )
            ],
        )
        self.engine.schema = schema
        result = self.engine._call_registered("query_order", {})
        from contextmind.modes.pytod.execution_engine import PolicyViolationError
        assert isinstance(result, PolicyViolationError)
        assert "order_id" in str(result)

    def test_no_block_for_optional_fields(self):
        """可选字段缺失时不拦截。"""
        schema = ServiceSchema(
            service_name="svc",
            description="",
            slots=[],
            intents=[
                IntentDefinition(
                    name="query_order",
                    description="查询订单",
                    policy_fields=[
                        PolicyField(name="order_id", required=True),
                        PolicyField(name="customer_name", required=False),
                    ],
                )
            ],
        )
        self.engine.schema = schema
        result = self.engine._call_registered("query_order", {"order_id": "ORD001"})
        from contextmind.modes.pytod.execution_engine import PolicyViolationError
        assert not isinstance(result, PolicyViolationError)
