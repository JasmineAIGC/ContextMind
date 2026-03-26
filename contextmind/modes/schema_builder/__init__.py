"""
Schema Data Builder — 从 schema.json 预生成各算法所需的结构化数据

这是一个独立的预生成步骤模块。它读取 ``data/`` 路径下的 ``*_schema.json`` 文件，
为每种对话算法生成对应的 companion 数据文件，存放在同一目录下：

- **PyTOD**：``*_pytod_mock.json`` — 每个意图（intent）的 mock 返回值，
  包含 result_slots 字段，使 AP 生成的 ``say(xN.field)`` 能正常解析。

- **FnCTOD**：``*_fnctod_domain.json`` — FunctionManager 可直接加载的
  DomainSpec 序列化 JSON，避免在 web_demo 初始化时重复从 schema 重建。

使用方式::

    # 方式一：命令行（推荐在部署/开发环境中一次性运行）
    python examples/build_schema_data.py

    # 方式二：Python API
    from contextmind.modes.schema_builder import SchemaDataBuilder
    builder = SchemaDataBuilder()
    builder.build_all("data/")   # 处理 data/ 下所有 *_schema.json

    # 方式三：单个文件
    builder.build_pytod_mock("data/anyihua_schema.json")
    builder.build_fnctod_domain("data/anyihua_schema.json")

生成后，PyTOD 追踪器在运行时通过 ``load_pytod_mock_data(schema_path)``
自动加载对应的 companion 文件（无需手动指定），大幅提升 AP 的推理质量——
EE 执行结果包含真实 result_slots 字段，DM 可直接引用 ``xN.field``。
"""

from contextmind.modes.schema_builder.builder import SchemaDataBuilder

__all__ = ["SchemaDataBuilder"]
