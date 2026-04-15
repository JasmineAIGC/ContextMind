#!/usr/bin/env python3
"""
docs/check_docs.py — 文档与代码路径一致性检查工具

检查架构文档（docs/reference/architecture.md）中引用的关键目录和类名是否实际存在于代码库中，
防止文档随代码重构而逐步漂移。

用法：
    python scripts/check_docs.py
    python scripts/check_docs.py --verbose
    python scripts/check_docs.py --root /path/to/repo

退出码：
    0 — 所有检查通过
    1 — 存在缺失项（CI 中用于阻断合并）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 预期存在的关键路径（相对于项目根目录）
# 来源：docs/reference/architecture.md "项目目录结构" 章节
# ---------------------------------------------------------------------------
EXPECTED_PATHS: list[str] = [
    # 核心包
    "contextmind/__init__.py",
    "contextmind/pipeline.py",
    # 基础设施
    "contextmind/infra/llm_client.py",
    "contextmind/infra/embedding.py",
    "contextmind/infra/logger.py",
    "contextmind/infra/data_models.py",
    # 知识库构建（第一步）
    "contextmind/knowledge/builder.py",
    "contextmind/knowledge/discoverer.py",
    "contextmind/knowledge/synthesizer.py",
    "contextmind/knowledge/normalizer.py",
    # Schema 数据生成（第二步）
    "contextmind/schema_builder/builder.py",
    "contextmind/schema_builder/pytod",
    "contextmind/schema_builder/fnctod",
    # 算法执行层（第三步）
    "contextmind/modes/base.py",
    "contextmind/modes/pytod/tracker.py",
    "contextmind/modes/pytod/execution_engine.py",
    "contextmind/modes/pytod/prompts.py",
    "contextmind/modes/pytod/schemas.py",
    "contextmind/modes/dst/tracker.py",
    "contextmind/modes/fnctod/tracker.py",
    "contextmind/modes/fnctod/function_manager.py",
    "contextmind/modes/evolve",
    # 场景与 UI
    "contextmind/scenarios",
    "contextmind/ui",
    # Benchmark
    "benchmark/run_benchmark.py",
    "benchmark/evaluators",
    "benchmark/datasets",
    # 示例
    "examples/build_kb.py",
    "examples/build_schema_data.py",
    "examples/context_pipeline_demo.py",
]

# ---------------------------------------------------------------------------
# 预期可 import 的关键类/函数（module.ClassName 格式，使用纯文本 grep 验证）
# ---------------------------------------------------------------------------
EXPECTED_SYMBOLS: dict[str, str] = {
    # 文件路径 → 类/函数名（验证源码中是否存在该符号定义）
    "contextmind/pipeline.py": "class ContextPipeline",
    "contextmind/infra/llm_client.py": "class AdkLLMClient",
    "contextmind/infra/embedding.py": "class EmbeddingClient",
    "contextmind/knowledge/builder.py": "class KnowledgeBaseBuilder",
    "contextmind/knowledge/discoverer.py": "class GenericDialogueDiscoverer",
    "contextmind/knowledge/synthesizer.py": "class SchemaSynthesizer",
    "contextmind/knowledge/normalizer.py": "def normalize_dialogues",
    "contextmind/schema_builder/builder.py": "class SchemaDataBuilder",
    "contextmind/modes/base.py": "class BaseTracker",
    "contextmind/modes/pytod/tracker.py": "class AdkPyTODTracker",
    "contextmind/modes/pytod/execution_engine.py": "class ExecutionEngine",
    "contextmind/modes/pytod/schemas.py": "class ServiceSchema",
    "contextmind/modes/dst/tracker.py": "class DialogueStateTracker",
    "contextmind/modes/fnctod/tracker.py": "class FnCTODTracker",
    "contextmind/modes/fnctod/function_manager.py": "class FunctionManager",
    "contextmind/modes/__init__.py": "def build_tracker",
    "contextmind/scenarios/registry.py": "class ScenarioRegistry",
}


def check_paths(root: Path, verbose: bool) -> list[str]:
    """验证预期路径是否存在，返回缺失项列表。"""
    missing: list[str] = []
    for rel in EXPECTED_PATHS:
        p = root / rel
        if not p.exists():
            missing.append(f"[path]   {rel}")
            if verbose:
                print(f"  ✗ 路径不存在: {rel}")
        elif verbose:
            print(f"  ✓ {rel}")
    return missing


def check_symbols(root: Path, verbose: bool) -> list[str]:
    """验证预期符号是否存在于对应源文件中，返回缺失项列表。"""
    missing: list[str] = []
    for rel_file, symbol in EXPECTED_SYMBOLS.items():
        file_path = root / rel_file
        if not file_path.is_file():
            missing.append(f"[symbol] {symbol!r} in {rel_file} (文件不存在)")
            if verbose:
                print(f"  ✗ 文件不存在，无法检查符号 {symbol!r}: {rel_file}")
            continue
        source = file_path.read_text(encoding="utf-8", errors="replace")
        if symbol not in source:
            missing.append(f"[symbol] {symbol!r} in {rel_file}")
            if verbose:
                print(f"  ✗ 符号未找到 {symbol!r} in {rel_file}")
        elif verbose:
            print(f"  ✓ {symbol!r} in {rel_file}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description="文档与代码路径一致性检查")
    parser.add_argument(
        "--root",
        default=None,
        help="项目根目录（默认：本脚本所在目录的上级）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出每个检查项的详细结果",
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    print(f"项目根目录: {root}")
    print()

    if args.verbose:
        print("=== 路径检查 ===")
    path_issues = check_paths(root, args.verbose)

    if args.verbose:
        print()
        print("=== 符号检查 ===")
    symbol_issues = check_symbols(root, args.verbose)

    all_issues = path_issues + symbol_issues

    if all_issues:
        print()
        print(f"✗ 发现 {len(all_issues)} 个文档漂移问题：")
        for issue in all_issues:
            print(f"  {issue}")
        print()
        print("请更新文档（docs/reference/architecture.md）或修复代码路径/类名。")
        return 1

    print(f"✓ 全部 {len(EXPECTED_PATHS)} 个路径 + {len(EXPECTED_SYMBOLS)} 个符号检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
