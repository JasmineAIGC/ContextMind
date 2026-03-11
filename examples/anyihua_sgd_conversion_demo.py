"""
安逸花外呼数据 → SGD 格式转换演示

演示如何将安逸花外呼对话数据转换为类似 Google SGD 数据集的格式：

  原始对话数据（chat_test_100.json）
      │
      ▼
  AnyihuaKnowledgeExtractor（单轮提取 + langextract 溯源）
      │
      ▼
  to_sgd_dialogue / save_as_sgd（基于提取结果 + 原始对话数据）
      │
      ▼
  SGD-like 格式（schema.json + dialogues_001.json）

参照资料：
  - benchmark/tools/analyze_chat_test.py   （全量 LLM 版 SGD 转换器，作为参考）
  - resources/anyihua_sgd/schema.json      （服务 Schema：15 个槽位，10 个意图）

与 analyze_chat_test.py 的关系：
  · analyze_chat_test.py 是完整的两阶段工具（本体归纳 + SGD 提取），直接调用 LLM
  · 本脚本通过 AnyihuaKnowledgeExtractor 完成提取（带轮次归属和字符级溯源），
    再将提取结果转换为 SGD 格式，提取粒度更细（每条知识来自哪一轮可追溯）

运行::

    python examples/anyihua_sgd_conversion_demo.py

环境要求：
    在 .env 文件中配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 等参数。

输出（默认保存至 data/anyihua_sgd/）：
    schema.json           - 服务 Schema（来自 resources/anyihua_sgd/schema.json）
    dialogues_001.json    - SGD 格式对话数据
    conversion_summary.json - 转换统计
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from contextmind.scenarios.anyihua.knowledge_extraction import (
    AnyihuaKnowledgeExtractor,
    save_as_sgd,
    to_sgd_dialogue,
)

# 默认路径
_DATA_PATH = _ROOT / "resources" / "data" / "chat_test_100.json"
_SCHEMA_PATH = _ROOT / "resources" / "anyihua_sgd" / "schema.json"
_SGD_OUTPUT_DIR = _ROOT / "data" / "anyihua_sgd"


def _print_sgd_dialogue(sgd: dict, max_turns: int = 4) -> None:
    """格式化打印 SGD 对话（前 N 轮）。"""
    print(f"\n  dialogue_id : {sgd['dialogue_id']}")
    print(f"  services    : {sgd['services']}")
    meta = sgd.get("metadata", {})
    crm = meta.get("user_info_parsed", {})
    if crm:
        print(f"  CRM 姓名    : {crm.get('customer_name', '-')}")
        print(f"  CRM 额度    : {crm.get('available_credit', '-')} 元")
    print(f"  总轮次      : {len(sgd['turns'])}")
    for turn in sgd["turns"][:max_turns]:
        sp = turn["speaker"]
        utt = turn["utterance"][:60]
        frame = turn["frames"][0] if turn["frames"] else {}
        if sp == "USER":
            state = frame.get("state", {})
            print(
                f"    [{sp}] {utt}…\n"
                f"           intent={state.get('active_intent','-')}  "
                f"slots={list(state.get('slot_values',{}).keys())}"
            )
        else:
            sc = frame.get("service_call") or {}
            print(
                f"    [{sp}] {utt}…\n"
                f"           service_call={sc.get('method', '-')}"
            )
    if len(sgd["turns"]) > max_turns:
        print(f"    … 还有 {len(sgd['turns']) - max_turns} 轮")


def main() -> None:
    if not _DATA_PATH.exists():
        print(f"[错误] 数据文件不存在: {_DATA_PATH}")
        sys.exit(1)

    dialogues = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    print(f"已加载 {len(dialogues)} 条对话，选取前 2 条进行演示")
    print(f"SGD Schema 来源: {_SCHEMA_PATH}")
    print(f"SGD 输出目录  : {_SGD_OUTPUT_DIR}")

    # Step 1: 知识提取（含轮次归属与字符级溯源）
    extractor = AnyihuaKnowledgeExtractor()

    print("\n══════════════════════════════════════════════════════")
    print("【步骤 1】单条提取 + 单条 SGD 转换")
    print("══════════════════════════════════════════════════════")

    result = extractor.extract(dialogues[0])
    sgd_single = to_sgd_dialogue(result, dialogues[0])
    print("SGD 对话（单条）：")
    _print_sgd_dialogue(sgd_single)

    print("\n══════════════════════════════════════════════════════")
    print("【步骤 2】批量提取（前 2 条）→ 批量 SGD 转换 → 保存文件")
    print("══════════════════════════════════════════════════════")

    results = extractor.extract_batch(dialogues[:2])

    # 法 A：通过 extractor 方法直接转换 + 保存
    extractor.convert_to_sgd_batch(
        results=results,
        raw_dialogues=dialogues[:2],
        output_dir=_SGD_OUTPUT_DIR,
        schema_source=_SCHEMA_PATH,
    )

    print("\nSGD 格式（前 2 条对话）：")
    for i, (res, raw) in enumerate(zip(results, dialogues[:2])):
        sgd = to_sgd_dialogue(res, raw)
        print(f"\n  ── 对话 {i+1} ──")
        _print_sgd_dialogue(sgd)

    print("\n══════════════════════════════════════════════════════")
    print("【步骤 3】验证输出文件")
    print("══════════════════════════════════════════════════════")

    schema_out = _SGD_OUTPUT_DIR / "schema.json"
    dlg_out = _SGD_OUTPUT_DIR / "dialogues_001.json"
    summary_out = _SGD_OUTPUT_DIR / "conversion_summary.json"

    if schema_out.exists():
        schema_data = json.loads(schema_out.read_text())
        svc = schema_data[0] if isinstance(schema_data, list) else schema_data
        print(f"  schema.json   : service={svc.get('service_name')} "
              f"| slots={len(svc.get('slots',[]))} | intents={len(svc.get('intents',[]))}")
    if dlg_out.exists():
        loaded = json.loads(dlg_out.read_text())
        print(f"  dialogues_001 : {len(loaded)} 条对话")
        if loaded:
            first = loaded[0]
            print(f"    第1条 dialogue_id: {first['dialogue_id']}")
            print(f"    第1条 turns 数量 : {len(first['turns'])}")
    if summary_out.exists():
        summary = json.loads(summary_out.read_text())
        print(f"  conversion_summary: {summary}")

    print(f"\n✅ 输出文件已保存至: {_SGD_OUTPUT_DIR}")
    print(f"   schema.json            ← 服务 Schema（槽位 + 意图）")
    print(f"   dialogues_001.json     ← SGD 格式对话数据")
    print(f"   conversion_summary.json ← 转换统计")


if __name__ == "__main__":
    main()
