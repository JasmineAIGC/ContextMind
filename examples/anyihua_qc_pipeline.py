"""
安逸花外呼促活服务 · PyTOD 批量质检流水线（LLM 全量质检版）

对 chat_test_100.json 中的 100 条安逸花外呼对话数据集执行离线质检。
所有质量问题检测均由 LLM 完成（无规则），输出五分类标签并与人工校验对比。

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
    python examples/anyihua_qc_pipeline.py

    # 将全部对话历史送入 LLM（默认仅送最近 10 轮，节省 token）：
    python examples/anyihua_qc_pipeline.py --full-history

    # 只看预测错误的条目（verbose 模式）：
    python examples/anyihua_qc_pipeline.py --verbose

    # 将结果保存到 JSON：
    python examples/anyihua_qc_pipeline.py --output /tmp/qc_results.json
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
from contextmind.scenarios.anyihua import PyTODQualityChecker

# 项目根目录（examples/ 的上一级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"


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
        help="逐条打印预测错误的会话信息",
    )
    parser.add_argument(
        "--full-history",
        dest="full_history",
        action="store_true",
        default=False,
        help=(
            "将完整对话历史送入 LLM（默认仅送最近 10 轮以节省 token）。"
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
    mode_desc = f"use_full_history={args.full_history}, model={config.model}"
    print(f"\n🔍 开始质检（{mode_desc}）…\n")
    results = checker.run_batch(
        data,
        verbose=args.verbose,
        use_full_history=args.full_history,
        llm_client=llm_client,
    )

    # ---- 保存结果（可选）----
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results["predictions"], f, ensure_ascii=False, indent=2)
        print(f"\n💾 预测结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
