"""
Schema Data Builder — 从 schema.json 预生成各算法所需的结构化数据

这是一个独立的预生成步骤模块。它读取 ``data/`` 路径下的 ``*_schema.json`` 文件，
为每种对话算法生成对应的 companion 数据文件，存放在同一目录下：

- **PyTOD**：``*_pytod_apis.py`` — 每个意图（intent）对应一个 Python 函数定义，
  函数签名来自 required_slots + optional_slots，返回值包含 result_slots 字段。
  运行时通过 ``load_pytod_api_module(schema_path)`` 加载，直接注册到 ExecutionEngine。

- **FnCTOD**：``*_fnctod_domain.json`` — FunctionManager 可直接加载的
  DomainSpec 序列化 JSON，包含 domain_name / description / slots 等字段。

使用方式::

    # 方式一：命令行（推荐在部署/开发环境中一次性运行）
    python examples/build_schema_data.py

    # 方式二：Python API
    from contextmind.modes.schema_builder import SchemaDataBuilder
    builder = SchemaDataBuilder()
    builder.build_all("data/")   # 处理 data/ 下所有 *_schema.json

    # 方式三：单个文件
    builder.build_pytod_apis("data/anyihua_schema.json")
    builder.build_fnctod_domain("data/anyihua_schema.json")

生成后，PyTOD 追踪器在运行时通过 ``load_pytod_api_module(schema_path)``
自动加载对应的 companion .py 文件并注册真实函数，使 EE 执行结果包含
真实的 result_slots 字段，AP 可正确地通过 ``say(xN.field)`` 引用。
"""

from contextmind.modes.schema_builder.builder import SchemaDataBuilder

__all__ = ["SchemaDataBuilder"]
