"""
安逸花外呼知识提取演示（langextract 溯源版）

演示如何使用 AnyihuaKnowledgeExtractor 从原始外呼对话中提取带溯源的结构化知识。

运行::

    python examples/anyihua_knowledge_extraction_demo.py

环境要求：
    在 .env 文件中配置 OPENAI_API_KEY / BASE_URL / MODEL 等 LLM 参数。
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

from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.scenarios.anyihua.knowledge_extraction import AnyihuaKnowledgeExtractor


def _print_result(result) -> None:
    """格式化打印单条提取结果。"""
    print(f"\n{'=' * 70}")
    print(f"对话 ID : {result.dialogue_id}")
    print(f"对话文本（前 200 字）:\n{result.source_text[:200]}…")
    print(f"\n── 提取结果 ({len(result.knowledge_items)} 条，对齐率 {result.stats.get('alignment_rate', 0):.1%}) ──")

    for i, item in enumerate(result.knowledge_items, 1):
        status_icon = {
            "match_exact": "✅",
            "match_lesser": "🔶",
            "match_fuzzy": "🔸",
            None: "❌",
        }.get(item.alignment_status, "❓")

        print(f"\n  [{i}] {status_icon} [{item.extraction_class}] {item.label}: {item.value}")
        print(f"      溯源原文: {item.provenance_text!r}")
        if item.is_aligned():
            snippet = result.source_text[item.char_start:item.char_end]  # type: ignore[index]
            print(f"      字符位置: [{item.char_start}:{item.char_end}]  →  {snippet!r}")
        else:
            print(f"      字符位置: 对齐失败（provenance_text 未在原文中找到）")
        print(f"      对齐质量: {item.alignment_status}  置信度: {item.confidence:.2f}")

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

    # 初始化 LLM 客户端（从 .env 读取配置）
    llm = SimpleLLMClient()
    extractor = AnyihuaKnowledgeExtractor(llm_client=llm)

    # 单条提取演示
    print("\n【演示一：单条提取】")
    result = extractor.extract(dialogues[0])
    _print_result(result)

    # 批量提取演示
    print("\n\n【演示二：批量提取（前 2 条）】")
    results = extractor.extract_batch(dialogues[:2])
    for r in results:
        _print_result(r)

    # 保存 JSON 结果
    out_path = _ROOT / "data" / "anyihua_knowledge_extraction_demo.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in results], f, ensure_ascii=False, indent=2)
    print(f"\n\n结果已保存到: {out_path}")


if __name__ == "__main__":
    main()
