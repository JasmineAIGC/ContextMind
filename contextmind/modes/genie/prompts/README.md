# prompts 目录 — Genie Worksheets 提示词文件

本目录存放 Genie Worksheets 执行模式的独立提示词文件，
方便业务人员在不修改 Python 代码的前提下调优提示词。

| 文件 | 说明 |
|------|------|
| `semantic_parsing.prompt` | LLM-1 语义解析器系统提示（Plan + Extract 格式） |
| `response_generator.prompt` | LLM-2 回复生成器系统提示（基于 AgentActs） |

这些文件仅供参考/备份用；实际运行时提示词在 `semantic_parser.py` 和 `tracker.py`
的常量中维护，以保证模块独立可测。如需从文件加载，可使用 `Path(__file__).parent / "semantic_parsing.prompt"` 读取。
