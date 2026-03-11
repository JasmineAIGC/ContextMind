"""
安逸花外呼知识提取演示（单轮对话 + langextract 溯源版）

演示如何使用 AnyihuaKnowledgeExtractor 从安逸花外呼多轮对话中提取带轮次归属
和字符级溯源的结构化知识。

核心特点：
  · 逐轮解析对话，每轮作为 langextract 的独立文本输入（解决多轮对话对齐问题）
  · LLM 输出包含 turn_idx（来自哪一轮）和 provenance_text（该轮话语的 verbatim 片段）
  · WordAligner 仅对对应轮次的短文本做字符对齐，精度高
  · 提取结果保存为 JSON 文件

LLM 通过 contextmind/infra/llm_client.py 统一初始化，配置从 .env 文件自动加载。

运行::

    python examples/anyihua_knowledge_extraction_demo.py

环境要求：
    在 .env 文件中配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 等参数。
    （参考 .env.example）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from contextmind.scenarios.anyihua.knowledge_extraction import AnyihuaKnowledgeExtractor

# 提取结果默认保存路径
_DEFAULT_SAVE_PATH = _ROOT / "data" / "anyihua_knowledge_extraction_results.json"


def _print_result(result, show_turns: bool = True) -> None:
    """格式化打印单条提取结果。"""
    print(f"\n{'=' * 72}")
    print(f"对话 ID : {result.dialogue_id}")
    n_agent = sum(1 for _, sp, _ in result.turns if sp == "坐席")
    n_user = sum(1 for _, sp, _ in result.turns if sp == "用户")
    print(f"对话轮次: 共 {len(result.turns)} 轮（坐席 {n_agent} 轮 / 用户 {n_user} 轮）")

    if show_turns and result.turns:
        print("\n── 对话内容（前 6 轮）──")
        for idx, sp, utt in result.turns[:6]:
            print(f"  [第{idx+1}轮({sp})] {utt[:60]}{'…' if len(utt) > 60 else ''}")
        if len(result.turns) > 6:
            print(f"  … 还有 {len(result.turns) - 6} 轮")

    print(
        f"\n── 提取结果 {len(result.knowledge_items)} 条 "
        f"（溯源率 {result.stats.get('alignment_rate', 0):.1%}） ──"
    )

    # 按类别分组显示
    for cls_label, cls_key in [("槽位值 slot_value", "slot_value"), ("用户意图 intent", "intent"), ("关键事实 fact", "fact")]:
        items = [it for it in result.knowledge_items if it.extraction_class == cls_key]
        if not items:
            continue
        print(f"\n  【{cls_label}】")
        for item in items:
            print(f"    · {item.label}: {item.value}")
            print(f"      溯源: {item.provenance}")

    print(f"\n── 统计 ──")
    for k, v in result.stats.items():
        print(f"  {k}: {v}")


def main() -> None:
    data_path = _ROOT / "resources" / "data" / "chat_test_100.json"
    if not data_path.exists():
        print(f"[错误] 数据文件不存在: {data_path}")
        sys.exit(1)

    dialogues = json.loads(data_path.read_text(encoding="utf-8"))
    print(f"已加载 {len(dialogues)} 条对话，选取前 2 条进行演示")
    print(f"提取结果将保存至: {_DEFAULT_SAVE_PATH}")

    # LLM 从 .env 自动加载，无需手动传入
    extractor = AnyihuaKnowledgeExtractor()

    # 单条提取演示
    print("\n【演示一：单条提取（含轮次归属与字符级溯源）】")
    result = extractor.extract(dialogues[0])
    _print_result(result, show_turns=True)

    # 批量提取演示，结果自动保存
    print("\n\n【演示二：批量提取（前 2 条）— 结果自动保存为 JSON 文件】")
    results = extractor.extract_batch(
        dialogues[:2],
        save_path=_DEFAULT_SAVE_PATH,
    )
    for r in results:
        _print_result(r, show_turns=False)

    print(f"\n\n✅ 结果已保存至: {_DEFAULT_SAVE_PATH}")


if __name__ == "__main__":
    main()
