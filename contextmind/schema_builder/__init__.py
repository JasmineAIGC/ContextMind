"""
Schema Data Builder — 从 schema.json 预生成各算法所需的结构化数据

本包是一个独立的预生成步骤模块，读取 ``data/`` 路径下的 ``*_schema.json`` 文件，
为每种对话算法生成对应的 companion 数据文件，存放在同一目录下。

包结构
------
::

    contextmind/schema_builder/
      __init__.py        — 顶层包，导出公开 API
      builder.py         — SchemaDataBuilder 顶层协调器
      utils.py           — 通用工具（companion_path）
      pytod/             — PyTOD 算法专用代码
        __init__.py      — 导出 PyTOD 子包公开符号
        models.py        — 数据类（TestCaseItem、FuncValidation）
        helpers.py       — SHARED_HELPERS 嵌入式工具函数模板
        prompts.py       — LLM 提示词常量
        generator.py     — PyTODApiCodeGenerator（LLM 驱动）
        validator.py     — validate_function、write_validation_report
        builder.py       — build_pytod_apis() 5 阶段生成流程
      fnctod/            — FnCTOD 算法专用代码（待实现）
        __init__.py
        builder.py       — build_fnctod_domain() 占位符
      genie_worksheets/  — Genie Worksheets 算法专用 schema（独立，与 PyTOD 无关）
        __init__.py      — 导出 PolicyField、WorksheetLoader
        models.py        — PolicyField 数据模型及辅助函数
        loader.py        — WorksheetLoader（CSV / JSON 导入/导出）

已实现的 companion 文件
-----------------------
- **PyTOD** (``*_pytod_apis.py``)：每个意图（intent）对应一个 Python 函数定义，
  函数签名来自 required_slots + optional_slots，返回值同时包含 result_slots 字段
  和所有输入参数（供 AP 通过 ``say(xN.slot_name)`` 引用）。
  运行时通过 ``load_pytod_api_module(schema_path)`` 加载注册到 ExecutionEngine。

使用方式::

    # 方式一：命令行
    python examples/build_schema_data.py

    # 方式二：带 LLM 生成真实业务逻辑
    python examples/build_schema_data.py --with-llm

    # 方式三：Python API（基础规则模式）
    from contextmind.schema_builder import SchemaDataBuilder
    builder = SchemaDataBuilder()
    builder.build_all("schema/")

    # 方式四：Python API（LLM 模式）
    from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
    from contextmind.schema_builder import SchemaDataBuilder
    llm = AdkLLMClient(config=LLMConfig.from_env())
    builder = SchemaDataBuilder(llm_client=llm)
    builder.build_pytod_apis("schema/anyihua_schema.json")

    # Genie Worksheets schema 加载（独立模块）
    from contextmind.schema_builder.genie_worksheets import WorksheetLoader
    schema = WorksheetLoader.from_csv("worksheets/restaurant.csv")
"""

# 顶层公开 API：保持与调用方兼容
from contextmind.schema_builder.builder import SchemaDataBuilder
from contextmind.schema_builder.pytod.codegen.shared.generator import PyTODApiCodeGenerator
from contextmind.schema_builder.pytod.testcase.models import FuncValidation, TestCaseItem

__all__ = [
    "SchemaDataBuilder",
    "PyTODApiCodeGenerator",
    "TestCaseItem",
    "FuncValidation",
]
