"""
安逸花外呼促活服务 · PyTOD 批量质检流水线（Hybrid 质检版）

对 chat_test_100.json 中的 100 条安逸花外呼对话数据集执行离线质检。
默认启用 Hybrid 模式：规则覆盖的会话（约 40%）直接给出标签（高精度），
其余会话调用 LLM 质检，节省 token 并提升整体准确率。

五个质量标签：
    - 数据错误：坐席引用金额与用户实际信息不符
    - 重复询问：坐席回复与历史发言高度重复
    - 不当告别：用户有未解决问题时坐席执行告别话术
    - 答非所问：用户明确提问但坐席回复完全无关
    - 无标签命中：不存在上述任何质量问题

环境要求（.env 文件）：
    QWEN3_API_KEY=your_key_here
    LLM_BASE_URL=https://your-endpoint/v1

用法:
    cd /path/to/ContextMind
    python examples/anyihua_qc_demo.py

    # 使用纯 LLM 质检（不使用规则预测）：
    python examples/anyihua_qc_demo.py --mode llm

    # 将全部对话历史送入 LLM（默认仅送最近 20 轮，节省 token）：
    python examples/anyihua_qc_demo.py --full-history

    # 逐条打印预测错误的条目：
    python examples/anyihua_qc_demo.py --verbose

    # 逐条打印所有条目（含预测正确的）：
    python examples/anyihua_qc_demo.py --show-all

    # 将结果保存到 JSON：
    python examples/anyihua_qc_demo.py --output /tmp/qc_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，使得可以直接运行而无需安装
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from contextmind.infra.llm_client import LLMConfig, SimpleLLMClient
from contextmind.modes.pytod import ServiceSchema
from contextmind.scenarios.anyihua.qc import ANYIHUA_QC_SCHEMA, PyTODQualityChecker

# 项目根目录（examples/ 的上一级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"


def print_schema_summary(schema: ServiceSchema) -> None:
    """
    显示 QC ServiceSchema 的意图和槽位摘要。

    PyTOD 动作解析器（Action Parser）会根据此 schema 约束意图选择和槽位填充。
    schema 定义了 LLM 可以调用的执行引擎 API 以及每个意图需要的数据槽位。
    """
    print("\n📐 QC Schema — PyTOD 动作解析器约束（contextmind/modes/pytod/schema.py）")
    print(f"   服务名: {schema.service_name}")
    print(f"   意图数: {len(schema.intents)}  槽位数: {len(schema.slots)}")
    print()
    print("   质量检测意图（Action Parser 按需调用对应执行引擎 API）:")
    for intent in schema.intents:
        req = ", ".join(intent.required_slots) or "—"
        opt = ", ".join(intent.optional_slots) if intent.optional_slots else "—"
        print(f"     · {intent.name}")
        print(f"       必填槽位: {req}  可选槽位: {opt}")
    print()
    # 展示 ServiceSchema 渲染为 prompt 文本的片段
    schema_prompt = schema.to_prompt_text()[:400]
    print("   Schema prompt 片段（前 400 字符）:")
    for line in schema_prompt.split("\n"):
        print(f"     {line}")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安逸花外呼对话 PyTOD 批量质检流水线（LLM 全量质检）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data",
        default=str(_DEFAULT_DATA_PATH),
        help=f"数据文件路径（默认: {_DEFAULT_DATA_PATH}）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="将预测结果保存到指定 JSON 文件（可选）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="逐条打印预测错误的会话详情",
    )
    parser.add_argument(
        "--show-all",
        dest="show_all",
        action="store_true",
        default=False,
        help="逐条打印所有会话详情（含预测正确的；与 --verbose 互斥，优先级更高）",
    )
    parser.add_argument(
        "--mode",
        choices=["hybrid", "llm"],
        default="hybrid",
        help=(
            "预测标签方法（默认: hybrid）：\n"
            "  hybrid — 规则优先 + LLM 兜底：规则直接覆盖数据错误/重复询问/不当告别，"
            "其余由 LLM 处理，节省 token 并提升准确率；\n"
            "  llm    — 纯 LLM 质检：所有会话均由 LLM 处理，适用于规则覆盖不足的场景。"
        ),
    )
    parser.add_argument(
        "--full-history",
        dest="full_history",
        action="store_true",
        default=False,
        help=(
            "将完整对话历史送入 LLM（默认仅送最近 20 轮以节省 token）。"
            "历史较长的会话建议开启以提升检测准确率。"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ---- 加载数据 ----
    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"数据文件不存在: {data_path}")

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"✅ 加载数据: {data_path}")
    print(f"   共 {len(data)} 条会话")

    # ---- 显示 QC Schema（PyTOD 动作解析器约束）----
    print_schema_summary(ANYIHUA_QC_SCHEMA)

    # 标签分布
    from collections import Counter
    label_counts = Counter(d.get("人工校验", "") for d in data)
    print("\n人工校验标签分布:")
    for label, count in sorted(label_counts.items()):
        print(f"  {label}: {count} 条")

    # ---- 初始化 LLM 客户端（必须）----
    try:
        config = LLMConfig.from_env()
        llm_client = SimpleLLMClient(config)
        print(f"\n✅ LLM 客户端初始化成功 (model: {config.model})")
    except Exception as exc:
        print(f"\n❌ LLM 客户端初始化失败: {exc}")
        print("   请在 .env 文件中配置 QWEN3_API_KEY / LLM_BASE_URL 等参数")
        sys.exit(1)

    # ---- 运行质检 ----
    checker = PyTODQualityChecker()
    use_pytod_first = args.mode == "hybrid"
    mode_desc = (
        f"mode={args.mode}  full_history={args.full_history}  model={config.model}"
    )
    print(f"\n🔍 开始质检（{mode_desc}）…\n")
    results = checker.run_batch(
        data,
        verbose=args.verbose,
        show_all=args.show_all,
        use_full_history=args.full_history,
        llm_client=llm_client,
        use_pytod_first=use_pytod_first,
    )

    # ---- 保存结果（可选）----
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results["predictions"], f, ensure_ascii=False, indent=2)
        print(f"\n💾 预测结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
