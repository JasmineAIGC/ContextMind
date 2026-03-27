"""
FnCTOD 算法的 schema 数据构建子包（待实现）。

本子包将包含将 ``*_schema.json`` 文件转换为 FnCTOD 算法所需 companion 文件的代码。

当前状态：**占位符，功能尚未实现。**

待实现内容
----------
- ``builder.py`` — ``build_fnctod_domain()`` 实现：
  生成标准 OpenAI Function Calling JSON Schema 格式的 ``*_fnctod_domain.json`` 文件。
  对应 ``DomainSpec.to_json_schema()`` 的输出格式，可通过
  ``load_fnctod_domain_spec(path)`` 直接重建 ``DomainSpec`` 对象。
"""
