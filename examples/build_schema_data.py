#!/usr/bin/env python3
"""
Schema 数据预生成脚本

从 schema/ 目录下的 *_schema.json 文件生成各算法所需的 companion 数据文件：

  - schema/*_pytod_apis.py   — PyTOD API 函数代码（每个意图一个 Python 函数定义）
                               （含 result_slots 字段，供 AP 通过 say(xN.field) 引用）
  - schema/*_fnctod_domain.json — FnCTOD 域定义数据
                               （序列化的 DomainSpec，供 FunctionManager 直接加载）

使用方式::

    # 处理 schema/ 下所有 schema（规则生成 stub 函数）
    python examples/build_schema_data.py

    # 使用 LLM 生成真实业务逻辑函数体（需配置 .env 中的 LLM_API_KEY 等）
    python examples/build_schema_data.py --with-llm

    # 处理指定目录
    python examples/build_schema_data.py --data-dir /path/to/schemas

    # 仅生成 PyTOD API 函数代码（跳过 FnCTOD）
    python examples/build_schema_data.py --pytod-only

    # 不覆盖已存在的文件
    python examples/build_schema_data.py --no-overwrite

    # 处理单个 schema 文件
    python examples/build_schema_data.py --schema schema/anyihua_schema.json

    # 单个文件 + LLM 模式（完整 5 阶段流程）
    python examples/build_schema_data.py --schema schema/anyihua_schema.json --with-llm

    # LLM 模式 + 真实对话数据 + 生成验证报告
    python examples/build_schema_data.py --with-llm \\
        --dialogue-data resources/data/chat_test_100.json --generate-report

    # 自定义迭代参数
    python examples/build_schema_data.py --with-llm --max-iterations 5 --pass-rate-threshold 0.8

两种生成模式
------------
1. **规则模式**（默认）：不依赖 LLM，使用语义化规则生成 mock 返回值的 stub 函数。
   速度快，但函数体没有真实业务计算逻辑。

2. **LLM 模式**（--with-llm）：完整运行 plan.md 定义的 5 阶段流程：
   - Phase 2: 为每个意图生成测试用例（可指定 --dialogue-data 提供业务背景）
   - Phase 3: 逐意图调用 LLM 生成函数体（Prompt 包含 few-shot 测试用例）
   - Phase 4: 批量执行验证 + 迭代修复（通过率低于阈值时调用 LLM 修复）
   - Phase 5: 生成最终文件 + 可选 validation_report.json
   LLM 失败时自动回退到规则模式（保证文件始终生成）。

这是一个 **一次性预生成步骤**，生成的文件应加入版本控制（git），
这样运行时无需重新生成，PyTOD 追踪器在初始化时直接加载 companion 文件。

当 schema.json 内容更新后，需重新运行本脚本以同步 companion 文件。
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，无需安装即可直接运行
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.schema_builder import SchemaDataBuilder

_DEFAULT_DATA_DIR = _PROJECT_ROOT / "schema"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 schema.json 预生成 PyTOD / FnCTOD companion 数据文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-dir",
        default=str(_DEFAULT_DATA_DIR),
        help=f"包含 *_schema.json 文件的目录（默认: {_DEFAULT_DATA_DIR}）",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="处理单个 schema.json 文件（与 --data-dir 互斥）",
    )
    parser.add_argument(
        "--pytod-only",
        action="store_true",
        help="仅生成 PyTOD APIs .py 文件，跳过 FnCTOD domain 文件",
    )
    parser.add_argument(
        "--fnctod-only",
        action="store_true",
        help="仅生成 FnCTOD domain 文件，跳过 PyTOD mock 文件",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="跳过已存在的文件，不覆盖",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help=(
            "使用 LLM 完整运行 5 阶段生成流程（Phase 2: 测试用例生成，Phase 3: 逐函数 LLM 生成，"
            "Phase 4: 验证+迭代修复，Phase 5: 文件组装）。"
            "需要在 .env 中配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL。"
            "未指定时使用规则引擎生成（含共享工具函数调用，无需 LLM）。"
        ),
    )
    parser.add_argument(
        "--dialogue-data",
        default=None,
        metavar="PATH",
        help=(
            "可选：真实对话数据文件路径（与 --with-llm 配合使用）。"
            "支持 chat_test_100.json / chat_test_500.json 格式。"
            "Phase 2 生成测试用例时 LLM 将参考这些对话样本提炼业务细节，"
            "生成更贴近真实流程的槽位值和函数实现。"
            "示例: --dialogue-data resources/data/chat_test_100.json"
        ),
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        metavar="N",
        help=(
            "Phase 4 迭代优化最大轮次（默认: 3）。"
            "每个意图函数通过率低于阈值时最多修复 N 轮。仅在 --with-llm 时生效。"
        ),
    )
    parser.add_argument(
        "--pass-rate-threshold",
        type=float,
        default=0.9,
        metavar="RATE",
        help=(
            "Phase 4 通过率阈值（默认: 0.9，即 90%%）。"
            "函数通过率达到阈值后停止迭代修复。仅在 --with-llm 时生效。"
        ),
    )
    parser.add_argument(
        "--max-test-cases",
        type=int,
        default=5,
        metavar="N",
        help=(
            "Phase 2 每个意图最多生成的测试用例数（默认: 5）。"
            "仅在 --with-llm 时生效。"
        ),
    )
    parser.add_argument(
        "--generate-report",
        action="store_true",
        help=(
            "Phase 5 生成 *_validation_report.json 验证报告，记录每个意图的通过率、"
            "迭代次数等信息。仅在 --with-llm 时生效。"
        ),
    )
    args = parser.parse_args()

    # Optionally initialize LLM client for real business logic generation
    llm_client = None
    dialogue_data_path = None
    if args.with_llm:
        try:
            from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
            llm_client = AdkLLMClient(config=LLMConfig.from_env())
            dialogue_note = ""
            if args.dialogue_data:
                dialogue_data_path = Path(args.dialogue_data)
                if dialogue_data_path.exists():
                    dialogue_note = f"，对话数据: {dialogue_data_path.name}"
                else:
                    print(
                        f"⚠️  对话数据文件不存在，将忽略: {dialogue_data_path}",
                        file=sys.stderr,
                    )
                    dialogue_data_path = None
            print(
                f"🤖 LLM 模式启用：5 阶段生成流程{dialogue_note}"
                f"（最大迭代: {args.max_iterations} 轮，"
                f"通过率阈值: {args.pass_rate_threshold:.0%}，"
                f"每意图测试用例: {args.max_test_cases} 条）"
            )
        except Exception as exc:
            print(f"⚠️  LLM 初始化失败，回退到规则生成模式: {exc}", file=sys.stderr)

    builder = SchemaDataBuilder(
        overwrite=not args.no_overwrite,
        llm_client=llm_client,
        dialogue_data_path=dialogue_data_path,
        max_iterations=args.max_iterations,
        pass_rate_threshold=args.pass_rate_threshold,
        max_test_cases_per_intent=args.max_test_cases,
        generate_report=args.generate_report,
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


def _process_single(builder: SchemaDataBuilder, schema_path: Path, args: argparse.Namespace) -> None:
    """处理单个 schema 文件。"""
    print(f"📋 处理 schema: {schema_path}")
    import json
    from contextmind.modes.pytod.schemas import load_schema_from_dict
    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = load_schema_from_dict(json.load(fh))
    except Exception as exc:
        print(f"❌ 加载失败: {exc}", file=sys.stderr)
        sys.exit(1)

    if not args.fnctod_only:
        p = builder.build_pytod_apis(schema_path, schema=schema)
        if p:
            print(f"✅ PyTOD APIs → {p}")
        else:
            print(f"⚠️  PyTOD APIs 未写入（已存在且 --no-overwrite）")

    if not args.pytod_only:
        p = builder.build_fnctod_domain(schema_path, schema=schema)
        if p:
            print(f"✅ FnCTOD domain → {p}")
        else:
            print(f"⚠️  FnCTOD domain 未写入（已存在且 --no-overwrite）")


def _process_dir(builder: SchemaDataBuilder, data_dir: Path, args: argparse.Namespace) -> None:
    """处理目录下所有 schema 文件。"""
    schema_files = sorted(data_dir.glob("*_schema.json"))
    if not schema_files:
        print(f"⚠️  {data_dir} 下未找到任何 *_schema.json 文件")
        return

    print(f"📂 数据目录: {data_dir}")
    print(f"📋 找到 {len(schema_files)} 个 schema 文件:")
    for f in schema_files:
        print(f"   - {f.name}")
    print()

    import json
    from contextmind.modes.pytod.schemas import load_schema_from_dict

    written_total = 0
    for schema_path in schema_files:
        try:
            with open(schema_path, encoding="utf-8") as fh:
                schema = load_schema_from_dict(json.load(fh))
        except Exception as exc:
            print(f"❌ 加载失败 {schema_path.name}: {exc}", file=sys.stderr)
            continue

        print(f"📋 {schema_path.name} → service={schema.service_name}, intents={len(schema.intents)}")

        if not args.fnctod_only:
            p = builder.build_pytod_apis(schema_path, schema=schema)
            if p:
                print(f"   ✅ PyTOD APIs  → {p.name}")
                written_total += 1
            else:
                print(f"   ⚠️  PyTOD APIs  跳过（已存在）")

        if not args.pytod_only:
            p = builder.build_fnctod_domain(schema_path, schema=schema)
            if p:
                print(f"   ✅ FnCTOD domain → {p.name}")
                written_total += 1
            else:
                print(f"   ⚠️  FnCTOD domain 跳过（已存在）")

    print()
    print(f"🎉 完成！共写入 {written_total} 个文件")
    print()
    print("💡 提示：请将生成的文件加入版本控制（git add schema/*_pytod_apis.py schema/*_fnctod_domain.json）")
    print("💡 当 schema.json 更新后，重新运行本脚本以同步 companion 文件")


if __name__ == "__main__":
    main()
