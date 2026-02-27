"""
安逸花外呼促活服务 · PyTOD 批量质检流水线

对 chat_test_100.json 中的 100 条安逸花外呼对话数据集执行离线质检，
预测每条会话的质量标签，并与人工校验标签对比输出 P/R/F1 报告。

用法:
    cd /path/to/ContextMind
    python examples/anyihua_qc_pipeline.py

    # 只看预测错误的条目（verbose 模式）：
    python examples/anyihua_qc_pipeline.py --verbose

    # 只扫描坐席回复（不扫历史，速度更快）：
    python examples/anyihua_qc_pipeline.py --no-full-history

    # 将结果保存到 JSON：
    python examples/anyihua_qc_pipeline.py --output /tmp/qc_results.json

检测优先级（高 → 低）：
    1. 数据错误   — 数值比对，最精确（覆盖率 14/15 = 93%）
    2. 重复询问   — 字符串匹配（覆盖率 13/15 = 87%，L1+L2 可达 15/15）
    3. 不当告别   — 关键词 + 上下文（覆盖率 13/15 = 87%）
    4. 答非所问   — 规则预过滤（召回率约 60%，无需 LLM）
    5. 无标签命中 — 默认

无需配置 API Key，纯规则运行。
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

from contextmind.scenarios.anyihua import PyTODQualityChecker

# 项目根目录（examples/ 的上一级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安逸花外呼对话 PyTOD 批量质检流水线",
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
        help="同时扫描完整对话历史（覆盖率略高，但会增加误报。默认：只扫描坐席回复）",
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

    # ---- 运行质检 ----
    checker = PyTODQualityChecker()
    print(f"\n🔍 开始质检（use_full_history={args.full_history}）…\n")
    results = checker.run_batch(
        data,
        verbose=args.verbose,
        use_full_history=args.full_history,
    )

    # ---- 保存结果（可选）----
    if args.output:
        output_path = Path(args.output)
        # predictions 中的 dict 已是 JSON 可序列化类型
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results["predictions"], f, ensure_ascii=False, indent=2)
        print(f"\n💾 预测结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
