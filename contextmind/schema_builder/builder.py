"""
SchemaDataBuilder — 从 schema.json 预生成各算法所需的 companion 数据文件。

本模块是 schema_builder 包的**顶层协调器**。它读取 ``*_schema.json`` 文件，
分别调用各算法子包的构建器，生成对应的 companion 文件：

- **PyTOD**（`pytod/`）：``*_pytod_apis.py`` — 意图函数定义文件，
  供 PyTOD ExecutionEngine 在运行时注册并调用。
- **FnCTOD**（`fnctod/`）：``*_fnctod_domain.json`` — 标准 OpenAI Function
  Calling JSON Schema 格式，符合 FnCTOD 论文原理（ACL 2024），供 FnCTOD 算法使用。

文件命名规则
------------
给定 ``schema/foo_schema.json``：
  - PyTOD companion  → ``schema/foo_pytod_apis.py``
  - FnCTOD companion → ``schema/foo_fnctod_domain.json``

使用方式::

    # 基础规则模式（无需 LLM）
    from contextmind.schema_builder import SchemaDataBuilder
    builder = SchemaDataBuilder()
    builder.build_all("schema/")

    # LLM 模式（生成真实业务逻辑）
    from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
    from contextmind.schema_builder import SchemaDataBuilder
    llm = AdkLLMClient(config=LLMConfig.from_env())
    builder = SchemaDataBuilder(llm_client=llm)
    builder.build_pytod_apis("schema/anyihua_schema.json")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import ServiceSchema, load_schema_from_dict

# 各算法子包构建器
from contextmind.schema_builder.fnctod.builder import build_fnctod_domain as _build_fnctod_domain
from contextmind.schema_builder.pytod.builder import build_pytod_apis as _build_pytod_apis

logger = get_logger(__name__)


class SchemaDataBuilder:
    """从 schema.json 预生成各算法所需的 companion 数据文件。

    顶层协调器，内部委托给各算法子包（``pytod/``、``fnctod/`` 等）完成具体构建工作。

    Args:
        overwrite:                目标文件已存在时是否覆盖（默认 True）。
        llm_client:               可选的 AdkLLMClient 实例。提供时 PyTOD 构建器使用 LLM
                                  生成真实业务逻辑；不提供时回退到基于规则的生成。
        dialogue_data_path:       可选的真实对话数据文件路径（LLM 模式业务背景）。
                                  支持 chat_test_100.json / chat_test_500.json 格式。
        max_iterations:           PyTOD Phase 4 最大修复轮次（默认 3）。
        pass_rate_threshold:      PyTOD Phase 4 通过率阈值（默认 0.9）。
        max_test_cases_per_intent: PyTOD Phase 2 每意图最多测试用例数（默认 5）。
        generate_report:          是否写入 PyTOD ``*_validation_report.json``（默认 False）。
    """

    def __init__(
        self,
        overwrite: bool = True,
        llm_client: Optional[Any] = None,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        max_iterations: int = 3,
        pass_rate_threshold: float = 0.9,
        max_test_cases_per_intent: int = 5,
        generate_report: bool = False,
    ) -> None:
        self.overwrite = overwrite
        self._llm_client = llm_client
        self._dialogue_data_path = Path(dialogue_data_path) if dialogue_data_path else None
        self._max_iterations = max_iterations
        self._pass_rate_threshold = pass_rate_threshold
        self._max_test_cases = max_test_cases_per_intent
        self._generate_report = generate_report

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def build_all(self, data_dir: Union[str, Path]) -> List[Path]:
        """处理目录下所有 ``*_schema.json`` 文件，生成全部算法的 companion 文件。

        Args:
            data_dir: 包含 ``*_schema.json`` 文件的目录路径。

        Returns:
            成功写入的文件路径列表。
        """
        data_dir = Path(data_dir)
        if not data_dir.is_dir():
            raise ValueError(f"data_dir 不是有效目录: {data_dir}")

        schema_files = sorted(data_dir.glob("*_schema.json"))
        if not schema_files:
            logger.warning(f"[SchemaDataBuilder] 未在 {data_dir} 找到任何 *_schema.json 文件")
            return []

        written: List[Path] = []
        for schema_path in schema_files:
            logger.info(f"[SchemaDataBuilder] 处理: {schema_path.name}")
            written.extend(self.build_single(schema_path))

        logger.info(
            f"[SchemaDataBuilder] 全部完成: "
            f"处理 {len(schema_files)} 个 schema，写入 {len(written)} 个文件"
        )
        return written

    def build_single(self, schema_path: Union[str, Path]) -> List[Path]:
        """处理单个 schema.json，为所有已实现的算法生成 companion 文件。

        当前已实现：PyTOD（``*_pytod_apis.py``）。
        待实现：FnCTOD（``*_fnctod_domain.json``）。

        Args:
            schema_path: ``*_schema.json`` 文件路径。

        Returns:
            成功写入的文件路径列表。
        """
        schema_path = Path(schema_path)
        written: List[Path] = []

        # 加载 schema 对象，避免各子构建器重复 IO
        try:
            with open(schema_path, encoding="utf-8") as fh:
                schema = load_schema_from_dict(json.load(fh))
        except Exception as exc:
            logger.error(f"[SchemaDataBuilder] 加载 schema 失败: {schema_path} — {exc}")
            return []

        # PyTOD：生成 *_pytod_apis.py
        p = self.build_pytod_apis(schema_path, schema=schema)
        if p:
            written.append(p)

        # FnCTOD：生成 *_fnctod_domain.json
        p = self.build_fnctod_domain(schema_path, schema=schema)
        if p:
            written.append(p)

        return written

    def build_pytod_apis(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 PyTOD ``*_pytod_apis.py`` companion 文件。

        委托给 :func:`contextmind.schema_builder.pytod.builder.build_pytod_apis`。
        完整实现 plan.md 定义的 5 阶段生成流程（解析 → 测试用例 → 生成 → 验证修复 → 组装）。

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        return _build_pytod_apis(
            schema_path,
            schema=schema,
            overwrite=self.overwrite,
            llm_client=self._llm_client,
            dialogue_data_path=self._dialogue_data_path,
            max_iterations=self._max_iterations,
            pass_rate_threshold=self._pass_rate_threshold,
            max_test_cases_per_intent=self._max_test_cases,
            generate_report=self._generate_report,
        )

    def build_fnctod_domain(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 FnCTOD ``*_fnctod_domain.json`` companion 文件。

        委托给 :func:`contextmind.schema_builder.fnctod.builder.build_fnctod_domain`。

        依据 FnCTOD 原论文将服务/域整体建模为一个 OpenAI Function Calling 函数，
        所有槽位成为参数，分类槽位携带枚举值列表。

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回生成的文件路径，否则返回 None。
        """
        return _build_fnctod_domain(
            schema_path,
            schema=schema,
            overwrite=self.overwrite,
        )
