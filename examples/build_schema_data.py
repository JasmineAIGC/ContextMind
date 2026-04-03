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

    # 处理指定输入目录
    python examples/build_schema_data.py --data-dir /path/to/schemas

    # 指定输出目录（默认与 schema 文件同目录）
    python examples/build_schema_data.py --output-dir output/schema_data

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

    # LLM 模式 + KB 输出目录（自动利用全部 4 个 json，并自动检测 schema.json）
    python examples/build_schema_data.py --with-llm --kb-dir output/kb_output

    # 仅使用第一步生成的 schema.json（不需要其他 KB 文件）
    python examples/build_schema_data.py --with-llm --schema output/kb_output/schema.json

    # 自定义迭代参数
    python examples/build_schema_data.py --with-llm --max-iterations 5 --pass-rate-threshold 0.8

    # 开启详细输出（打印每个阶段的详细进度日志）
    python examples/build_schema_data.py --with-llm --verbose

两种生成模式
------------
1. **规则模式**（默认）：不依赖 LLM，使用语义化规则生成 mock 返回值的 stub 函数。
   速度快，但函数体没有真实业务计算逻辑。

2. **LLM 模式**（--with-llm）：完整运行 plan.md 定义的 5 阶段流程：
   - Phase 2: 为每个意图生成多轮对话复杂度的测试用例（覆盖早期/中期/完整/上下文依赖/边界场景）
   - Phase 3: 逐意图调用 LLM 生成函数体（Prompt 包含 few-shot 测试用例）
   - Phase 4: 批量执行验证 + 迭代修复（通过率低于阈值时调用 LLM 修复）
   - Phase 5: 生成最终文件 + 可选 validation_report.json
   LLM 失败时自动回退到规则模式（保证文件始终生成）。

KB 目录数据利用
--------------
指定 --kb-dir 时，自动充分利用 KnowledgeBaseBuilder 生成的 4 个 json 文件：
   - schema.json              自动用作 --schema（若未单独指定）
   - dialogues_001.json       真实对话样本（含多轮槽位积累快照）
   - discovery_raw.json       逐轮槽位/意图/事实提取示例（覆盖全部提取类型）
   - conversion_summary.json  发现的意图/槽位统计，提供业务全貌背景

这是一个 **一次性预生成步骤**，生成的文件应加入版本控制（git），
这样运行时无需重新生成，PyTOD 追踪器在初始化时直接加载 companion 文件。

当 schema.json 内容更新后，需重新运行本脚本以同步 companion 文件。
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

# LLM 选项默认值常量（同时用于 argparse 默认值与后置警告检查，保持一致）
_DEFAULT_MAX_ITERATIONS = 10
_DEFAULT_PASS_RATE_THRESHOLD = 0.9
_DEFAULT_MAX_TEST_CASES = 10


# ---------------------------------------------------------------------------
# argparse 类型验证器
# ---------------------------------------------------------------------------

def _positive_int(value: str) -> int:
    """argparse 类型：正整数（>= 1）。"""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是整数，收到: {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError(f"必须 ≥ 1，收到: {n}")
    return n


def _pass_rate(value: str) -> float:
    """argparse 类型：通过率（0.0–1.0）。"""
    try:
        f = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是浮点数，收到: {value!r}")
    if not 0.0 <= f <= 1.0:
        raise argparse.ArgumentTypeError(f"必须在 0.0–1.0 范围内，收到: {f}")
    return f


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _print_llm_mode_summary(
    dialogue_data_path: Optional[Path],
    kb_dir: Optional[Path],
    max_iterations: int,
    pass_rate_threshold: float,
    max_test_cases: int,
    generator: str = "pytod",
) -> None:
    """以结构化多行格式打印 LLM 模式状态摘要，便于用户快速确认数据来源和参数。"""
    gen_label = {
        "pytod": "pytod（原始 5 阶段流水线）",
        "alpha": "alpha（ACIA：反思 + 骨架约束 + 失败分析 + 收敛重启）",
    }.get(generator, generator)
    print(f"🤖 LLM 模式已启用  生成器: {gen_label}")
    print("   数据来源:")

    if dialogue_data_path:
        print(f"     ● 对话样本: {dialogue_data_path}（Phase 2 测试用例业务背景）")
    else:
        print("     ● 对话样本: 未指定（可用 --dialogue-data 提供）")

    if kb_dir:
        kb_files = []
        for fname in ("discovery_raw.json", "conversion_summary.json"):
            if (kb_dir / fname).exists():
                kb_files.append(fname)
        if kb_files:
            print(f"     ● KB 目录 ({kb_dir.name}): {', '.join(kb_files)}")
        dlg_in_kb = kb_dir / "dialogues_001.json"
        if dlg_in_kb.exists():
            if dialogue_data_path:
                print(f"     ● KB 对话 ({dlg_in_kb.name}): 已跳过（--dialogue-data 优先）")
            else:
                print(f"     ● KB 对话: {dlg_in_kb}")
    else:
        print("     ● KB 目录: 未指定（可用 --kb-dir 提供 discovery_raw.json 等上下文）")

    print(
        f"   生成参数: 最大迭代 {max_iterations} 轮 | "
        f"通过率阈值 {pass_rate_threshold:.0%} | "
        f"每意图 {max_test_cases} 条测试用例"
    )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 schema.json 预生成 PyTOD / FnCTOD companion 数据文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── 输入参数 ──────────────────────────────────────────────────────────
    input_group = parser.add_argument_group("输入参数")
    input_group.add_argument(
        "--data-dir",
        default=None,   # None 表示"未显式提供"；main() 内部会回退到 _DEFAULT_DATA_DIR
        metavar="DIR",
        help=f"包含 *_schema.json 文件的目录（默认: {_DEFAULT_DATA_DIR}）",
    )
    input_group.add_argument(
        "--schema",
        default=None,
        metavar="FILE",
        help="处理单个 schema.json 文件（与 --data-dir 互斥）",
    )
    input_group.add_argument(
        "--kb-dir",
        default=None,
        metavar="DIR",
        help=(
            "可选：KB 输出目录路径（与 --with-llm 配合使用）。"
            "由 KnowledgeBaseBuilder.save_dataset() 生成，包含 "
            "dialogues_001.json、discovery_raw.json、conversion_summary.json、schema.json。"
            "提供后 PyTOD 生成器自动加载这些文件作为补充上下文，生成更贴近真实业务逻辑的函数。"
            "与 --dialogue-data 同时指定时，--dialogue-data 优先级更高。"
            "示例: --kb-dir output/kb_output"
        ),
    )

    # ── 输出参数 ──────────────────────────────────────────────────────────
    output_group = parser.add_argument_group("输出参数")
    output_group.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help=(
            "可选：输出目录。指定时所有生成的 companion 文件写入该目录，"
            "否则与对应的 schema 文件同目录。目录不存在时自动创建。"
            "示例: --output-dir output/schema_data"
        ),
    )
    output_group.add_argument(
        "--no-overwrite",
        action="store_true",
        help="跳过已存在的文件，不覆盖",
    )
    output_group.add_argument(
        "--generate-report",
        action="store_true",
        help=(
            "Phase 5 生成 *_validation_report.json 验证报告，记录每个意图的通过率、"
            "迭代次数等信息。仅在 --with-llm 时生效。"
        ),
    )

    # ── 生成模式 ──────────────────────────────────────────────────────────
    mode_group = parser.add_argument_group("生成模式")
    output_mode_group = mode_group.add_mutually_exclusive_group()
    output_mode_group.add_argument(
        "--pytod-only",
        action="store_true",
        help="仅生成 PyTOD APIs .py 文件，跳过 FnCTOD domain 文件",
    )
    output_mode_group.add_argument(
        "--fnctod-only",
        action="store_true",
        help="仅生成 FnCTOD domain 文件，跳过 PyTOD mock 文件",
    )
    mode_group.add_argument(
        "--with-llm",
        action="store_true",
        help=(
            "使用 LLM 完整运行 5 阶段生成流程（Phase 2: 测试用例生成，Phase 3: 逐函数 LLM 生成，"
            "Phase 4: 验证+迭代修复，Phase 5: 文件组装）。"
            "需要在 .env 中配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL。"
            "未指定时使用规则引擎生成（含共享工具函数调用，无需 LLM）。"
        ),
    )

    # ── LLM 选项（仅 --with-llm 时生效）─────────────────────────────────
    llm_group = parser.add_argument_group("LLM 选项（仅 --with-llm 时生效）")
    llm_group.add_argument(
        "--generator",
        choices=["pytod", "alpha"],
        default="pytod",
        metavar="NAME",
        help=(
            "PyTOD API 代码生成算法选择（默认: pytod）。\n"
            "  pytod — 原始 5 阶段流水线（Phase 2 测试用例 → Phase 3 LLM 生成 → Phase 4 迭代修复）\n"
            "  alpha — ACIA 算法（AlphaCodium 风格）：\n"
            "           · Phase R 反思：生成前分析业务语义，提供更准确的上下文\n"
            "           · Phase G 骨架约束生成：预指定 result_slots 返回骨架，消除键缺失失败\n"
            "           · Phase A 失败分析：按类型分类失败原因，为定向修复提供依据\n"
            "           · Phase F 定向修复 + 收敛重启：无改善时全新重启，避免 docstring 累积\n"
            "示例: --with-llm --generator alpha"
        ),
    )
    llm_group.add_argument(
        "--dialogue-data",
        default=None,
        metavar="FILE",
        help=(
            "可选：真实对话数据文件路径。"
            "支持 chat_test_100.json / chat_test_500.json 格式。"
            "Phase 2 生成测试用例时 LLM 将参考这些对话样本提炼业务细节，"
            "生成更贴近真实流程的槽位值和函数实现。"
            "与 --kb-dir 同时指定时，此文件的对话样本优先于 kb-dir/dialogues_001.json。"
            "示例: --dialogue-data resources/data/chat_test_100.json"
        ),
    )
    llm_group.add_argument(
        "--max-iterations",
        type=_positive_int,
        default=_DEFAULT_MAX_ITERATIONS,
        metavar="N",
        help=(
            f"Phase 4 迭代优化最大轮次（默认: {_DEFAULT_MAX_ITERATIONS}，必须 ≥ 1）。"
            "每个意图函数通过率低于阈值时最多修复 N 轮。"
        ),
    )
    llm_group.add_argument(
        "--pass-rate-threshold",
        type=_pass_rate,
        default=_DEFAULT_PASS_RATE_THRESHOLD,
        metavar="RATE",
        help=(
            f"Phase 4 通过率阈值（默认: {_DEFAULT_PASS_RATE_THRESHOLD:.0%}，取值范围 0.0–1.0）。"
            "函数通过率达到阈值后停止迭代修复。"
        ),
    )
    llm_group.add_argument(
        "--max-test-cases",
        type=_positive_int,
        default=_DEFAULT_MAX_TEST_CASES,
        metavar="N",
        help=f"Phase 2 每个意图最多生成的测试用例数（默认: {_DEFAULT_MAX_TEST_CASES}，必须 ≥ 1）。",
    )

    # ── 其他 ──────────────────────────────────────────────────────────────
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help=(
            "开启详细进度输出。启用后将把底层生成器的每阶段日志（Phase 1~5 进度、"
            "每意图通过率、LLM 调用结果等）打印到终端，方便调试和监控生成过程。"
            "不指定时仅显示摘要信息。"
        ),
    )
    args = parser.parse_args()

    # ── 参数一致性检查（后置验证）──────────────────────────────────────
    # 1. --schema 和 --data-dir 同时指定时，--data-dir 会被忽略。
    #    通过 default=None 的哨兵值精确判断用户是否显式提供了 --data-dir。
    if args.schema and args.data_dir is not None:
        print(
            f"⚠️  --schema 与 --data-dir 同时指定，将以 --schema 为准，"
            f"--data-dir ({args.data_dir}) 被忽略。",
            file=sys.stderr,
        )
    # 未显式提供时回退到默认目录
    if args.data_dir is None:
        args.data_dir = str(_DEFAULT_DATA_DIR)

    # 2. LLM 专属选项在未指定 --with-llm 时无效。
    if not args.with_llm:
        _llm_only_flags: list[tuple[bool, str]] = [
            (bool(args.kb_dir), "--kb-dir"),
            (bool(args.dialogue_data), "--dialogue-data"),
            (args.generate_report, "--generate-report"),
            (args.max_iterations != _DEFAULT_MAX_ITERATIONS,
             f"--max-iterations {args.max_iterations}"),
            (args.pass_rate_threshold != _DEFAULT_PASS_RATE_THRESHOLD,
             f"--pass-rate-threshold {args.pass_rate_threshold}"),
            (args.max_test_cases != _DEFAULT_MAX_TEST_CASES,
             f"--max-test-cases {args.max_test_cases}"),
            (args.generator != "pytod", f"--generator {args.generator}"),
        ]
        active_llm_flags = [name for active, name in _llm_only_flags if active]
        if active_llm_flags:
            print(
                f"⚠️  以下参数仅在 --with-llm 模式下生效，当前未指定 --with-llm，"
                f"这些参数将被忽略: {', '.join(active_llm_flags)}",
                file=sys.stderr,
            )

    # 3. --fnctod-only 与 --with-llm 同时指定时，LLM 仅用于 PyTOD 生成，
    #    但 --fnctod-only 会跳过 PyTOD，导致 LLM 被初始化后完全未使用。
    if args.fnctod_only and args.with_llm:
        print(
            "⚠️  --fnctod-only 跳过 PyTOD 生成，--with-llm 的 LLM 流程将不会被执行。",
            file=sys.stderr,
        )

    # --verbose 模式：路由底层 logger.info / logger.debug 到 stdout
    if args.verbose:
        from contextmind.infra.logger import setup_logging, LogLevel
        setup_logging(level=LogLevel.INFO, save_to_file=False)
        print("🔍 详细输出模式已开启 — 底层阶段日志将实时打印到终端")
        print()

    # Optionally initialize LLM client for real business logic generation
    llm_client = None
    dialogue_data_path = None
    kb_dir = None
    if args.with_llm:
        try:
            from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
            llm_client = AdkLLMClient(config=LLMConfig.from_env())
            if args.dialogue_data:
                dialogue_data_path = Path(args.dialogue_data)
                if not dialogue_data_path.exists():
                    print(
                        f"⚠️  对话数据文件不存在，将忽略: {dialogue_data_path}",
                        file=sys.stderr,
                    )
                    dialogue_data_path = None
            if args.kb_dir:
                kb_dir_candidate = Path(args.kb_dir)
                if kb_dir_candidate.is_dir():
                    kb_dir = kb_dir_candidate
                else:
                    print(
                        f"⚠️  KB 目录不存在，将忽略: {kb_dir_candidate}",
                        file=sys.stderr,
                    )
            # 打印结构化的 LLM 模式状态摘要
            _print_llm_mode_summary(
                dialogue_data_path=dialogue_data_path,
                kb_dir=kb_dir,
                max_iterations=args.max_iterations,
                pass_rate_threshold=args.pass_rate_threshold,
                max_test_cases=args.max_test_cases,
                generator=args.generator,
            )
        except Exception as exc:
            print(f"⚠️  LLM 初始化失败，回退到规则生成模式: {exc}", file=sys.stderr)

    # 当 --kb-dir 指定且 --schema 未指定时，自动从 kb-dir 中检测 schema.json。
    # 此处修改 args.schema 相当于模拟用户未显式指定时的默认行为：
    # "用 kb_output 里的 schema.json 作为处理源"，使 --kb-dir 成为自洽的单一入口。
    if kb_dir is not None and not args.schema:
        kb_schema_candidate = kb_dir / "schema.json"
        if kb_schema_candidate.exists():
            args.schema = str(kb_schema_candidate)
            print(f"💡 自动从 --kb-dir 检测到 schema: {kb_schema_candidate}")

    output_dir = Path(args.output_dir) if args.output_dir else None

    builder = SchemaDataBuilder(
        overwrite=not args.no_overwrite,
        llm_client=llm_client,
        dialogue_data_path=dialogue_data_path,
        kb_dir=kb_dir,
        output_dir=output_dir,
        max_iterations=args.max_iterations,
        pass_rate_threshold=args.pass_rate_threshold,
        max_test_cases_per_intent=args.max_test_cases,
        generate_report=args.generate_report,
        verbose=args.verbose,
        generator=args.generator,
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
    import json
    from contextmind.modes.pytod.schemas import load_schema_from_dict
    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = load_schema_from_dict(json.load(fh))
    except Exception as exc:
        print(f"❌ 加载失败: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"📋 处理 schema: {schema_path}"
        f"（服务: {schema.service_name}，{len(schema.intents)} 个意图，{len(schema.slots)} 个槽位）"
    )

    # 如果 --kb-dir 已提供，检查 schema 意图数是否与 KB 发现结果一致
    if args.kb_dir:
        _check_schema_vs_discovery(schema_path, Path(args.kb_dir), len(schema.intents))

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


def _check_schema_vs_discovery(
    schema_path: Path,
    kb_dir: Path,
    schema_intent_count: int,
) -> None:
    """若 KB 目录中 conversion_summary.json 显示发现的意图数多于 schema，打印提醒。"""
    import json as _json
    summary_path = kb_dir / "conversion_summary.json"
    if not summary_path.exists():
        return
    try:
        with open(summary_path, encoding="utf-8") as fh:
            summary = _json.load(fh)
        coverage = summary.get("schema_coverage", {})
        extracted = coverage.get("extracted_intents", [])
        discovered_count = len(extracted) if isinstance(extracted, list) else int(extracted or 0)
        if discovered_count > schema_intent_count:
            print(
                f"💡 提示：KB 共发现 {discovered_count} 个意图，"
                f"但 schema.json 中仅有 {schema_intent_count} 个。"
                f"如需完整覆盖，请重新运行 KB 构建步骤（build_kb.py）"
                f"以生成包含全部意图的 schema.json。"
            )
    except Exception:
        pass  # 读取失败时静默忽略，不影响主流程


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
    if args.output_dir:
        print(f"💡 提示：输出目录: {args.output_dir}")
    else:
        print("💡 提示：请将生成的文件加入版本控制（git add schema/*_pytod_apis.py schema/*_fnctod_domain.json）")
    print("💡 当 schema.json 更新后，重新运行本脚本以同步 companion 文件")


if __name__ == "__main__":
    main()
