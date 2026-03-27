"""
Schema Data Builder — 从 schema.json 预生成各算法所需的结构化数据

这是一个独立的预生成步骤模块。它读取 ``data/`` 路径下的 ``*_schema.json`` 文件，
为每种对话算法生成对应的 companion 数据文件，存放在同一目录下：

- **PyTOD**：``*_pytod_apis.py`` — 每个意图（intent）对应一个 Python 函数定义，
  函数签名来自 required_slots + optional_slots，返回值同时包含：
  (1) result_slots 字段（语义化 mock 值，如 ``"order_status": "已发货"``）；
  (2) ALL 输入参数回传（供 AP 通过 ``say(xN.slot_name)`` 引用任意输入值）。
  运行时通过 ``load_pytod_api_module(schema_path)`` 加载，直接注册到 ExecutionEngine。

  **LLM 模式**：传入 ``llm_client`` 时，使用 :class:`PyTODApiCodeGenerator` 为每个
  意图函数生成真实的业务逻辑代码体（包含实际计算、格式化、工单生成等逻辑），
  回退到规则生成（stub）当 LLM 不可用或调用失败时。

- **FnCTOD**：``*_fnctod_domain.json`` — 标准 OpenAI Function Calling JSON Schema 格式，
  对应 ``DomainSpec.to_json_schema()`` 的输出。每个槽位（slot）映射为一个 property，
  含 ``type``、``description``，以及分类槽位的 ``enum`` 可选值列表（槽位-值 数据）。
  运行时通过 ``web_demo._load_external_schemas()`` 重建为 ``DomainSpec`` 对象。

使用方式::

    # 方式一：命令行（推荐在部署/开发环境中一次性运行）
    python examples/build_schema_data.py

    # 方式二：带 LLM 生成真实业务逻辑
    python examples/build_schema_data.py --with-llm

    # 方式三：Python API（基础模式）
    from contextmind.schema_builder import SchemaDataBuilder
    builder = SchemaDataBuilder()
    builder.build_all("schema/")   # 处理 schema/ 下所有 *_schema.json

    # 方式四：Python API（LLM 模式）
    from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
    from contextmind.schema_builder import SchemaDataBuilder
    llm = AdkLLMClient(config=LLMConfig.from_env())
    builder = SchemaDataBuilder(llm_client=llm)
    builder.build_pytod_apis("schema/anyihua_schema.json")

生成后，PyTOD 追踪器在运行时通过 ``load_pytod_api_module(schema_path)``
自动加载对应的 companion .py 文件并注册真实函数，使 EE 执行结果包含
真实的 result_slots 字段，AP 可正确地通过 ``say(xN.field)`` 引用。
"""

from contextmind.schema_builder.builder import PyTODApiCodeGenerator, SchemaDataBuilder, TestCaseItem

__all__ = ["SchemaDataBuilder", "PyTODApiCodeGenerator", "TestCaseItem"]
