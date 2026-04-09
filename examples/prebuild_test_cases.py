#!/usr/bin/env python3
"""
测试用例预生成脚本
=================

在运行 build_schema_data.py 之前，使用本脚本为每个意图（intent）预先生成
测试数据，保存到 ``*_test_cases.json`` 文件中。

**为什么需要此步骤？**

``build_schema_data.py`` 支持 4 种生成器（loop / alpha / sstar / ctree），
每种生成器在运行时都需要测试用例来验证生成的代码（Phase 2/4）。
如果每次运行时独立生成测试用例，由于 LLM 的随机性，4 种生成器拿到的测试集
各不相同，无法进行公平的跨方法对比评测。

本脚本通过"先生成、后共享"的方式解决这一问题：

1. **本脚本**：提前调用 LLM 为每个意图生成测试用例，保存为 ``*_test_cases.json``
2. **build_schema_data.py**：4 种生成器均从同一份文件加载测试用例，Phase 2 不再重新生成

测试用例文件位于 schema 文件同目录::

    schema/foo_schema.json  →  schema/foo_test_cases.json

若文件已存在，默认跳过（不重新生成）。使用 ``--force`` 可强制覆盖。

使用方式::

    # 为单个 schema 预生成测试用例
    python examples/prebuild_test_cases.py --schema schema/foo_schema.json

    # 为目录下所有 schema 预生成测试用例
    python examples/prebuild_test_cases.py --data-dir schema/

    # 使用 KB 输出目录（自动获取对话上下文）
    python examples/prebuild_test_cases.py --kb-dir output/step1_kb_output

    # 强制重新生成（覆盖已存在的测试用例文件）
    python examples/prebuild_test_cases.py --schema schema/foo_schema.json --force

    # 指定每意图最多生成的测试用例数
    python examples/prebuild_test_cases.py --schema schema/foo_schema.json --max-test-cases 8

生成完测试用例后，再运行各生成器进行代码生成与对比评测::

    python examples/build_schema_data.py --with-llm --generator loop  --schema schema/foo_schema.json --output-dir output/loop
    python examples/build_schema_data.py --with-llm --generator alpha --schema schema/foo_schema.json --output-dir output/alpha
    python examples/build_schema_data.py --with-llm --generator sstar --schema schema/foo_schema.json --output-dir output/sstar
    python examples/build_schema_data.py --with-llm --generator ctree --schema schema/foo_schema.json --output-dir output/ctree

以上 4 条命令均会从同一个 ``*_test_cases.json`` 加载测试用例，确保评测公平。

配置要求
--------
需要在项目根目录的 ``.env`` 文件中配置 LLM 访问参数::

    LLM_API_KEY=<your-api-key>
    LLM_BASE_URL=<your-base-url>
    LLM_MODEL=<model-name>
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到 Python 路径，无需安装即可直接运行
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.schema_builder import SchemaDataBuilder

_DEFAULT_DATA_DIR = _PROJECT_ROOT / "schema"
_DEFAULT_MAX_TEST_CASES = 10


def _positive_int(value: str) -> int:
    """argparse 类型：正整数（>= 1）。"""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是整数，收到: {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError(f"必须 ≥ 1，收到: {n}")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(
        description="为 schema 中的每个意图预生成测试用例（build_schema_data.py 的前置步骤）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── 输入参数 ──────────────────────────────────────────────────────────
    input_group = parser.add_argument_group("输入参数")
    input_group.add_argument(
        "--schema",
        default=None,
        metavar="FILE",
        help="处理单个 *_schema.json 文件（与 --data-dir 互斥）",
    )
    input_group.add_argument(
        "--data-dir",
        default=None,
        metavar="DIR",
        help=f"包含 *_schema.json 文件的目录（默认: {_DEFAULT_DATA_DIR}）",
    )
    input_group.add_argument(
        "--kb-dir",
        default=None,
        metavar="DIR",
        help=(
            "可选：KB 输出目录路径（由 build_kb.py / KnowledgeBaseBuilder 生成）。"
            "自动加载其中的 dialogues_001.json、discovery_raw.json、"
            "conversion_summary.json，为 LLM 提供丰富的业务背景。"
            "与 --dialogue-data 同时指定时，--dialogue-data 优先级更高。"
            "示例: --kb-dir output/step1_kb_output"
        ),
    )
    input_group.add_argument(
        "--dialogue-data",
        default=None,
        metavar="FILE",
        help=(
            "可选：真实对话数据文件路径（chat_test_100.json 等格式）。"
            "LLM 生成测试用例时将参考这些样本，生成更贴近真实业务的槽位值。"
        ),
    )

    # ── 生成参数 ──────────────────────────────────────────────────────────
    gen_group = parser.add_argument_group("生成参数")
    gen_group.add_argument(
        "--max-test-cases",
        type=_positive_int,
        default=_DEFAULT_MAX_TEST_CASES,
        metavar="N",
        help=f"每个意图最多生成的测试用例数（默认: {_DEFAULT_MAX_TEST_CASES}，必须 ≥ 1）",
    )
    gen_group.add_argument(
        "--force",
        action="store_true",
        help=(
            "强制重新生成，覆盖已存在的 *_test_cases.json 文件。"
            "默认行为：文件已存在时跳过，不重新生成。"
        ),
    )
    gen_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="开启详细输出（显示底层 LLM 调用日志）",
    )

    args = parser.parse_args()

    # 回退到默认目录
    if args.data_dir is None:
        args.data_dir = str(_DEFAULT_DATA_DIR)

    # --verbose 模式
    if args.verbose:
        from contextmind.infra.logger import setup_logging, LogLevel
        setup_logging(level=LogLevel.INFO, save_to_file=False)
        print("🔍 详细输出模式已开启")
        print()

    # 初始化 LLM 客户端
    try:
        from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
        llm_client = AdkLLMClient(config=LLMConfig.from_env())
    except Exception as exc:
        print(
            f"❌ LLM 初始化失败: {exc}\n"
            "   请检查 .env 文件中的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 配置。",
            file=sys.stderr,
        )
        sys.exit(1)

    # 解析对话数据和 KB 目录
    dialogue_data_path: Optional[Path] = None
    kb_dir: Optional[Path] = None

    if args.dialogue_data:
        p = Path(args.dialogue_data)
        if p.exists():
            dialogue_data_path = p
        else:
            print(f"⚠️  对话数据文件不存在，将忽略: {p}", file=sys.stderr)

    if args.kb_dir:
        p = Path(args.kb_dir)
        if p.is_dir():
            kb_dir = p
            # 若未指定 --schema，自动从 kb-dir 检测 schema.json
            if args.schema is None and (p / "schema.json").exists():
                args.schema = str(p / "schema.json")
                print(f"💡 自动从 --kb-dir 检测到 schema: {args.schema}")
        else:
            print(f"⚠️  KB 目录不存在，将忽略: {p}", file=sys.stderr)

    # SchemaDataBuilder 只用于调用 prebuild_test_cases()，不需要代码生成参数
    builder = SchemaDataBuilder(
        overwrite=True,
        llm_client=llm_client,
        dialogue_data_path=dialogue_data_path,
        kb_dir=kb_dir,
        max_test_cases_per_intent=args.max_test_cases,
    )

    if args.schema:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"❌ 文件不存在: {schema_path}", file=sys.stderr)
            sys.exit(1)
        _process_single(builder, schema_path, args)
    else:
        data_dir = Path(args.data_dir)
        if not data_dir.is_dir():
            print(f"❌ 目录不存在: {data_dir}", file=sys.stderr)
            sys.exit(1)
        _process_dir(builder, data_dir, args)


def _process_single(
    builder: SchemaDataBuilder,
    schema_path: Path,
    args: argparse.Namespace,
) -> None:
    """处理单个 schema 文件的测试用例预生成。"""
    import json
    from contextmind.modes.pytod.schemas import load_schema_from_dict
    from contextmind.schema_builder.pytod.test_cache import test_cases_path_for_schema

    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = load_schema_from_dict(json.load(fh))
    except Exception as exc:
        print(f"❌ 加载 schema 失败: {exc}", file=sys.stderr)
        sys.exit(1)

    tc_path = test_cases_path_for_schema(schema_path)
    print(
        f"📋 schema: {schema_path.name}"
        f"（服务: {schema.service_name}，{len(schema.intents)} 个意图）"
    )

    if tc_path.exists() and not args.force:
        print(f"⏭️  已存在，跳过（使用 --force 强制重新生成）: {tc_path}")
        return

    if tc_path.exists() and args.force:
        tc_path.unlink()
        print(f"🗑️  已删除旧文件: {tc_path}")

    p = builder.prebuild_test_cases(schema_path, schema=schema)
    if p:
        print(f"✅ 测试用例已生成 → {p}")
    else:
        print("⚠️  测试用例生成失败（schema 无意图定义或 LLM 返回空）")


def _process_dir(
    builder: SchemaDataBuilder,
    data_dir: Path,
    args: argparse.Namespace,
) -> None:
    """处理目录下所有 schema 文件的测试用例预生成。"""
    import json
    from contextmind.modes.pytod.schemas import load_schema_from_dict
    from contextmind.schema_builder.pytod.test_cache import test_cases_path_for_schema

    schema_files = sorted(data_dir.glob("*_schema.json"))
    if not schema_files:
        print(f"⚠️  {data_dir} 下未找到任何 *_schema.json 文件")
        return

    print(f"📂 数据目录: {data_dir}")
    print(f"📋 找到 {len(schema_files)} 个 schema 文件:")
    for f in schema_files:
        print(f"   - {f.name}")
    print()

    written_total = 0
    skipped_total = 0
    for schema_path in schema_files:
        tc_path = test_cases_path_for_schema(schema_path)
        try:
            with open(schema_path, encoding="utf-8") as fh:
                schema = load_schema_from_dict(json.load(fh))
        except Exception as exc:
            print(f"❌ 加载失败 {schema_path.name}: {exc}", file=sys.stderr)
            continue

        print(
            f"📋 {schema_path.name} → "
            f"service={schema.service_name}, intents={len(schema.intents)}"
        )

        if tc_path.exists() and not args.force:
            print(f"   ⏭️  已存在，跳过: {tc_path.name}")
            skipped_total += 1
            continue

        if tc_path.exists() and args.force:
            tc_path.unlink()

        p = builder.prebuild_test_cases(schema_path, schema=schema)
        if p:
            print(f"   ✅ 测试用例 → {p.name}")
            written_total += 1
        else:
            print(f"   ⚠️  生成失败（无意图定义或 LLM 返回空）")

    print()
    print(f"🎉 完成！新生成 {written_total} 个，跳过 {skipped_total} 个（已存在）")
    print()
    print("下一步：使用各生成器进行代码生成（测试用例将自动从缓存加载）：")
    print(f"  python examples/build_schema_data.py --with-llm --generator loop  --data-dir {data_dir}")
    print(f"  python examples/build_schema_data.py --with-llm --generator alpha --data-dir {data_dir}")
    print(f"  python examples/build_schema_data.py --with-llm --generator sstar --data-dir {data_dir}")
    print(f"  python examples/build_schema_data.py --with-llm --generator ctree --data-dir {data_dir}")


if __name__ == "__main__":
    main()
