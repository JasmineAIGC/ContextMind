#!/usr/bin/env python3
"""
Schema 数据预生成脚本

从 schema/ 目录下的 *_schema.json 文件生成各算法所需的 companion 数据文件：

  - schema/*_pytod_apis.py        — PyTOD API 函数代码（每个意图一个 Python 函数定义）
                                    （含 result_slots 字段，供 AP 通过 say(xN.field) 引用）
  - schema/*_fnctod_domain.json   — FnCTOD 域定义数据
                                    （序列化的 DomainSpec，供 FunctionManager 直接加载）
  - schema/*_genie_worksheet.json — Genie Worksheets 策略声明文件（JSON）
                                    （由 schema.json 自动转换，供 GenieTracker 直接加载）
  - schema/*_genie_worksheet.csv  — Genie Worksheets 策略声明文件（CSV）
                                    （人工可编辑格式，可在 Excel / Numbers 中修改策略字段）

使用方式::

    # 处理 schema/ 下所有 schema（规则生成 stub 函数 + Genie Worksheet）
    python examples/build_schema_data.py

    # 使用 LLM 生成真实业务逻辑函数体（需配置 .env 中的 LLM_API_KEY 等）
    python examples/build_schema_data.py --with-llm

    # 处理指定输入目录
    python examples/build_schema_data.py --data-dir /path/to/schemas

    # 指定输出目录（默认与 schema 文件同目录）
    python examples/build_schema_data.py --output-dir output/schema_data

    # 仅生成 PyTOD API 函数代码（跳过 FnCTOD 和 Genie Worksheet）
    python examples/build_schema_data.py --pytod-only

    # 仅生成 Genie Worksheet（跳过 PyTOD 和 FnCTOD，无需 LLM）
    python examples/build_schema_data.py --genie-only

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

    # 指定预构建的测试用例文件路径（配合 prebuild_test_cases.py --output 使用）
    python examples/build_schema_data.py --with-llm --schema schema/foo_schema.json \\
        --test-cases-path output/my_test_cases.json

【推荐评测流程】跨生成器公平对比
----------------------------------
在运行本脚本之前，先用 ``prebuild_test_cases.py`` 预生成测试用例，
确保 loop / alpha / sstar / ctree 4 种生成器使用完全相同的测试集::

    # Step 1: 用专用脚本预生成测试用例（只需运行一次）
    python examples/prebuild_test_cases.py --schema schema/anyihua_schema.json

    # Step 2a: 用 loop 生成代码（自动加载预生成的测试用例）
    python examples/build_schema_data.py --with-llm --generator loop \\
        --schema schema/anyihua_schema.json --output-dir output/loop

    # Step 2b-2d: 同理运行 alpha / sstar / ctree
    # → 4 组 *_validation_report.json 在相同测试集上可直接对比通过率

若跳过 Step 1 直接运行本脚本，Phase 2 仍会自动生成并缓存测试用例，
但运行第一个生成器时会看到提示，建议先完成预生成步骤。

两种生成模式
------------
1. **规则模式**（默认）：不依赖 LLM，使用语义化规则生成 mock 返回值的 stub 函数。
   速度快，但函数体没有真实业务计算逻辑。

2. **LLM 模式**（--with-llm）：完整运行 plan.md 定义的 5 阶段流程：
   - Phase 2: 为每个意图加载预生成测试用例（优先）或实时生成；
              若同目录存在 *_test_cases.json（由 prebuild_test_cases.py 生成），
              自动从文件加载，跳过 LLM 调用
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
import concurrent.futures
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
    generator: str = "loop",
) -> None:
    """以结构化多行格式打印 LLM 模式状态摘要，便于用户快速确认数据来源和参数。"""
    gen_label = {
        "loop": "loop（迭代修复流水线）",
        "alpha": "alpha（ACIA：反思 + 骨架约束 + 失败分析 + 收敛重启）",
        "sstar": "sstar（S*：并行草稿 + 执行追踪修复 + 区分性测试选择，arXiv:2502.14382）",
        "ctree": "ctree（CodeTree：UCB 树搜索 + 逐失败用例扩展，arXiv:2411.04329）",
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
        help="仅生成 PyTOD APIs .py 文件，跳过 FnCTOD domain 文件和 Genie Worksheet 文件",
    )
    output_mode_group.add_argument(
        "--fnctod-only",
        action="store_true",
        help="仅生成 FnCTOD domain 文件，跳过 PyTOD mock 文件和 Genie Worksheet 文件",
    )
    output_mode_group.add_argument(
        "--genie-only",
        action="store_true",
        help="仅生成 Genie Worksheet 文件（*_genie_worksheet.json 和 *_genie_worksheet.csv），跳过 PyTOD 和 FnCTOD",
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
        choices=["loop", "alpha", "sstar", "ctree"],
        default="loop",
        metavar="NAME",
        help=(
            "PyTOD API 代码生成算法选择（默认: loop）。\n"
            "  loop  — 迭代修复流水线（Phase 2 测试用例 → Phase 3 LLM 生成 → Phase 4 迭代修复）\n"
            "  alpha — ACIA 算法（AlphaCodium 风格）：\n"
            "           · Phase R 反思：生成前分析业务语义，提供更准确的上下文\n"
            "           · Phase G 骨架约束生成：预指定 result_slots 返回骨架，消除键缺失失败\n"
            "           · Phase A 失败分析：按类型分类失败原因，为定向修复提供依据\n"
            "           · Phase F 定向修复 + 收敛重启：无改善时全新重启，避免 docstring 累积\n"
            "  sstar — S* 算法（Test Time Scaling，arXiv:2502.14382，2025）：\n"
            "           · Phase P 并行草稿：以 3 种思维模式并行生成候选实现，扩大解空间覆盖\n"
            "           · Phase D 执行追踪修复：基于 execution traces 精准定位 bug（LDB 风格）\n"
            "           · Phase S 区分性测试选择：LLM 生成区分性输入，通过执行行为选最优候选\n"
            "           · Phase R 精炼：对最优候选继续修复直至达到通过率阈值\n"
            "  ctree — CodeTree 算法（树形搜索，arXiv:2411.04329，2024/2025）：\n"
            "           · Phase G 根节点生成：生成初始候选函数\n"
            "           · Phase E 树扩展：对每个失败用例独立生成修复子节点，互不干扰\n"
            "           · Phase S UCB 选择：UCB 评分平衡利用（高通过率）与探索（未访问节点）\n"
            "           · 整棵树保留最优路径，避免线性修复中修好A破坏B的问题\n"
            "示例: --with-llm --generator ctree"
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
        "--test-cases-path",
        default=None,
        metavar="FILE",
        help=(
            "可选：预构建测试用例 JSON 文件路径（*_test_cases.json）。"
            "指定后 Phase 2 直接从该文件加载测试用例，不再通过 schema 路径自动推导。"
            "适用于通过 prebuild_test_cases.py --output 生成到非默认位置的测试用例文件。"
            "示例: --test-cases-path output/my_test_cases.json"
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
    llm_group.add_argument(
        "--workers", "-j",
        type=_positive_int,
        default=1,
        metavar="N",
        help=(
            "并行工作线程数（默认: 1，即顺序处理）。"
            "设置 > 1 时，多个意图的 Phase 2→3→4 同时并发执行；"
            "在 --data-dir 批量模式下，多个 schema 也会同时并发处理，"
            "可显著缩短含多个 schema / 意图的总生成时间。"
            "示例: --with-llm --workers 4"
        ),
    )
    llm_group.add_argument(
        "--prebuild-test-cases",
        action="store_true",
        help=(
            "仅运行 Phase 2（LLM 测试用例生成），将结果保存到 *_test_cases.json，"
            "不执行代码生成。保存后多次运行不同生成器（loop/alpha/sstar/ctree）时，"
            "Phase 2 自动从该文件加载，确保所有生成器在相同测试集上对比评测。\n"
            "若目标文件已存在，跳过重新生成（删除文件后可重新生成）。\n"
            "示例: --with-llm --prebuild-test-cases --schema schema/foo_schema.json"
        ),
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
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别（默认 INFO；--verbose 会自动提升为 INFO 并输出底层细节）",
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
            (args.generator != "loop", f"--generator {args.generator}"),
            (args.prebuild_test_cases, "--prebuild-test-cases"),
            (bool(args.test_cases_path), "--test-cases-path"),
            (args.workers != 1, f"--workers {args.workers}"),
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

    # 4. --genie-only 不使用 LLM，与 --with-llm 同时指定时提示用户。
    if getattr(args, "genie_only", False) and args.with_llm:
        print(
            "⚠️  --genie-only 仅需从 schema 结构生成 Worksheet，不会调用 LLM。--with-llm 参数将被忽略。",
            file=sys.stderr,
        )

    # --verbose 模式：路由底层 logger.info / logger.debug 到 stdout
    # 日志始终保存到 log/build_schema_data_<timestamp>.log
    from contextmind.infra.logger import setup_logging, LogLevel
    log_level = LogLevel.DEBUG if args.log_level == "DEBUG" else (
        LogLevel[args.log_level] if hasattr(LogLevel, args.log_level) else LogLevel.INFO
    )
    setup_logging(level=log_level, save_to_file=True, log_dir="log", log_name="build_schema_data")
    if args.verbose:
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
        generate_report=args.generate_report or bool(args.with_llm),
        verbose=args.verbose,
        generator=args.generator,
        test_cases_path=Path(args.test_cases_path) if args.test_cases_path else None,
        workers=args.workers,
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


def _print_validation_summary(
    schema_path: Path,
    output_dir: Optional[Path],
    pass_rate_threshold: float,
) -> None:
    """读取 *_validation_report.json 并以表格形式打印验证统计。"""
    import json as _json
    from contextmind.schema_builder.utils import companion_path

    report_path = companion_path(schema_path, "validation_report", suffix=".json", output_dir=output_dir)
    if not report_path.exists():
        return

    try:
        with open(report_path, encoding="utf-8") as fh:
            report = _json.load(fh)
    except Exception:
        return

    summary = report.get("summary", {})
    intents = report.get("intents", {})
    if not intents:
        return

    avg_rate = summary.get("avg_pass_rate", 0.0)
    validated = summary.get("validated", 0)
    total_intents = summary.get("total_intents", 0)

    print()
    print("┌─────────────────────────────────────────────────────────────────────┐")
    print("│  📊 验证统计摘要                                                     │")
    print("├──────────────────────────┬────────────┬────────────┬───────────────┤")
    print("│ 意图 (Intent)            │ 通过率     │ 通过/总数  │ 迭代轮次      │")
    print("├──────────────────────────┼────────────┼────────────┼───────────────┤")
    for name, v in intents.items():
        total_c = v.get("total_cases", 0)
        passed = v.get("passed", 0)
        rate = v.get("pass_rate", 0.0)
        iters = v.get("iterations", 0)
        err = v.get("error")
        if total_c == 0:
            status = "—"
            rate_str = "N/A"
            case_str = "—"
            iter_str = "—"
        else:
            status = "✅" if rate >= pass_rate_threshold else "⚠️ "
            rate_str = f"{rate:.1%}"
            case_str = f"{passed}/{total_c}"
            iter_str = str(iters)
        name_display = name[:24] if len(name) <= 24 else name[:21] + "..."
        if err:
            rate_str = "ERR"
        print(f"│ {status} {name_display:<22s} │ {rate_str:<10s} │ {case_str:<10s} │ {iter_str:<13s} │")
    print("├──────────────────────────┴────────────┴────────────┴───────────────┤")
    overall_status = "✅" if avg_rate >= pass_rate_threshold else "⚠️ "
    print(
        f"│  {overall_status} 平均通过率: {avg_rate:.1%}"
        f"  （{validated}/{total_intents} 个意图已验证）"
        f"{' ' * max(0, 34 - len(f'{avg_rate:.1%}') - len(str(validated)) - len(str(total_intents)))}│"
    )
    print(f"│  📁 完整报告: {str(report_path):<56s}│")
    print("└─────────────────────────────────────────────────────────────────────┘")
    print()


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

    # --prebuild-test-cases：仅生成测试用例，跳过代码生成
    if getattr(args, "prebuild_test_cases", False) and args.with_llm:
        p = builder.prebuild_test_cases(schema_path, schema=schema)
        if p:
            print(f"✅ 测试用例已预生成 → {p}")
            print("   下次运行各生成器时将自动加载此文件，确保评测使用相同测试集。")
        else:
            print("⚠️  测试用例预生成失败（无 LLM 或 schema 无意图定义）")
        return

    genie_only = getattr(args, "genie_only", False)

    if not args.fnctod_only and not genie_only:
        # LLM 模式：若测试用例缓存不存在，提示用户先运行预生成脚本
        if args.with_llm:
            from contextmind.schema_builder.pytod.testcase import test_cases_path_for_schema
            # 优先使用用户指定的路径，否则自动推导
            _user_tc = getattr(args, "test_cases_path", None)
            tc_path = Path(_user_tc) if _user_tc else test_cases_path_for_schema(schema_path)
            if not tc_path.exists():
                print()
                print("┌─────────────────────────────────────────────────────────────────┐")
                print("│  ⚠️  测试用例未预生成                                             │")
                print("│                                                                 │")
                print("│  为确保 loop / alpha / sstar / ctree 4 种生成器使用相同的测试    │")
                print("│  用例进行公平对比评测，建议先运行：                               │")
                print("│                                                                 │")
                print(f"│    python examples/prebuild_test_cases.py \\                    │")
                print(f"│        --schema {str(schema_path):<47s} │")
                print("│                                                                 │")
                print("│  本次将自动生成测试用例并缓存，但若并行运行多个生成器，           │")
                print("│  请务必先运行上述命令以保证测试集一致。                           │")
                print("└─────────────────────────────────────────────────────────────────┘")
                print()
        p = builder.build_pytod_apis(schema_path, schema=schema)
        if p:
            print(f"✅ PyTOD APIs → {p}")
        else:
            print(f"⚠️  PyTOD APIs 未写入（已存在且 --no-overwrite）")
        if args.with_llm:
            _print_validation_summary(schema_path, builder.output_dir, args.pass_rate_threshold)

    if not args.pytod_only and not genie_only:
        p = builder.build_fnctod_domain(schema_path, schema=schema)
        if p:
            print(f"✅ FnCTOD domain → {p}")
        else:
            print(f"⚠️  FnCTOD domain 未写入（已存在且 --no-overwrite）")

    if not args.pytod_only and not args.fnctod_only:
        p = builder.build_genie_worksheet(schema_path, schema=schema)
        if p:
            csv_p = p.with_suffix(".csv")
            print(f"✅ Genie Worksheet JSON → {p}")
            print(f"✅ Genie Worksheet CSV  → {csv_p}")
        else:
            print(f"⚠️  Genie Worksheet 未写入（已存在且 --no-overwrite）")


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


def _process_one_schema(
    builder: SchemaDataBuilder,
    schema_path: Path,
    args: argparse.Namespace,
) -> tuple[int, list[str]]:
    """处理单个 schema 文件（供并行调用）。

    Returns:
        (written_count, log_lines) — 写入文件数 和 日志行列表（调用方统一打印）。
    """
    import json
    from contextmind.modes.pytod.schemas import load_schema_from_dict

    logs: list[str] = []
    written = 0
    prebuild_mode = getattr(args, "prebuild_test_cases", False) and args.with_llm

    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = load_schema_from_dict(json.load(fh))
    except Exception as exc:
        logs.append(f"❌ 加载失败 {schema_path.name}: {exc}")
        return written, logs

    logs.append(f"📋 {schema_path.name} → service={schema.service_name}, intents={len(schema.intents)}")

    if prebuild_mode:
        p = builder.prebuild_test_cases(schema_path, schema=schema)
        if p:
            logs.append(f"   ✅ 测试用例 → {p.name}")
            written += 1
        else:
            logs.append("   ⚠️  测试用例预生成失败或已存在")
        return written, logs

    genie_only = getattr(args, "genie_only", False)

    if not args.fnctod_only and not genie_only:
        if args.with_llm:
            from contextmind.schema_builder.pytod.testcase import test_cases_path_for_schema
            _user_tc = getattr(args, "test_cases_path", None)
            tc_path = Path(_user_tc) if _user_tc else test_cases_path_for_schema(schema_path)
            if not tc_path.exists():
                logs.append(
                    f"   ⚠️  {schema_path.name} 的测试用例未预生成 "
                    f"（建议先运行 prebuild_test_cases.py，本次将自动生成并缓存）"
                )
        p = builder.build_pytod_apis(schema_path, schema=schema)
        if p:
            logs.append(f"   ✅ PyTOD APIs  → {p.name}")
            written += 1
        else:
            logs.append("   ⚠️  PyTOD APIs  跳过（已存在）")
        if args.with_llm:
            # 收集验证摘要行而非直接打印
            import json as _json
            from contextmind.schema_builder.utils import companion_path
            report_path = companion_path(
                schema_path, "validation_report", suffix=".json", output_dir=builder.output_dir
            )
            if report_path.exists():
                try:
                    with open(report_path, encoding="utf-8") as fh:
                        report = _json.load(fh)
                    summary = report.get("summary", {})
                    avg_rate = summary.get("avg_pass_rate", 0.0)
                    validated = summary.get("validated", 0)
                    total_intents = summary.get("total_intents", 0)
                    status = "✅" if avg_rate >= args.pass_rate_threshold else "⚠️ "
                    logs.append(
                        f"   {status} 平均通过率: {avg_rate:.1%}"
                        f"（{validated}/{total_intents} 个意图已验证）"
                    )
                except Exception:
                    pass

    if not args.pytod_only and not genie_only:
        p = builder.build_fnctod_domain(schema_path, schema=schema)
        if p:
            logs.append(f"   ✅ FnCTOD domain → {p.name}")
            written += 1
        else:
            logs.append("   ⚠️  FnCTOD domain 跳过（已存在）")

    if not args.pytod_only and not args.fnctod_only:
        p = builder.build_genie_worksheet(schema_path, schema=schema)
        if p:
            csv_p = p.with_suffix(".csv")
            logs.append(f"   ✅ Genie Worksheet JSON → {p.name}")
            logs.append(f"   ✅ Genie Worksheet CSV  → {csv_p.name}")
            written += 1
        else:
            logs.append("   ⚠️  Genie Worksheet 跳过（已存在）")

    return written, logs


def _process_dir(builder: SchemaDataBuilder, data_dir: Path, args: argparse.Namespace) -> None:
    """处理目录下所有 schema 文件（跨 schema 并行）。"""
    schema_files = sorted(data_dir.glob("*_schema.json"))
    if not schema_files:
        print(f"⚠️  {data_dir} 下未找到任何 *_schema.json 文件")
        return

    print(f"📂 数据目录: {data_dir}")
    print(f"📋 找到 {len(schema_files)} 个 schema 文件:")
    for f in schema_files:
        print(f"   - {f.name}")
    print()

    prebuild_mode = getattr(args, "prebuild_test_cases", False) and args.with_llm
    workers = getattr(args, "workers", 1)

    if workers > 1 and len(schema_files) > 1:
        print(f"⚡ 并行处理 {len(schema_files)} 个 schema（--workers {workers}）...")
        print()

    written_total = 0

    def _task(sp: Path) -> tuple[int, list[str]]:
        return _process_one_schema(builder, sp, args)

    if workers > 1 and len(schema_files) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for written, logs in pool.map(_task, schema_files):
                for line in logs:
                    print(line)
                written_total += written
    else:
        for schema_path in schema_files:
            written, logs = _task(schema_path)
            for line in logs:
                print(line)
            if args.with_llm and not prebuild_mode and not args.fnctod_only:
                _print_validation_summary(schema_path, builder.output_dir, args.pass_rate_threshold)
            written_total += written

    print()
    if prebuild_mode:
        print(f"🎉 完成！共预生成 {written_total} 个测试用例文件")
        print("💡 现在可对每个生成器运行代码生成，Phase 2 将自动加载此文件：")
        print("   python examples/build_schema_data.py --with-llm --generator loop  ...")
        print("   python examples/build_schema_data.py --with-llm --generator alpha ...")
        print("   python examples/build_schema_data.py --with-llm --generator sstar ...")
        print("   python examples/build_schema_data.py --with-llm --generator ctree ...")
    else:
        print(f"🎉 完成！共写入 {written_total} 个文件")
        print()
        if args.output_dir:
            print(f"💡 提示：输出目录: {args.output_dir}")
        else:
            print("💡 提示：请将生成的文件加入版本控制（git add schema/*_pytod_apis.py schema/*_fnctod_domain.json）")
        print("💡 当 schema.json 更新后，重新运行本脚本以同步 companion 文件")


if __name__ == "__main__":
    main()
