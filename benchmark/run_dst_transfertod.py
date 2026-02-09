#!/usr/bin/env python3
"""
运行DST算法在TransferTOD数据集上的评测

使用方法:
    python run_dst_transfertod.py --domain 酒店 --limit 10
"""

import argparse
from datasets.transfertod.adapter import TransferTODAdapter
from algorithms.dst import DSTEvaluator


def main():
    parser = argparse.ArgumentParser(description="DST on TransferTOD评测")
    parser.add_argument("--domain", type=str, default=None, help="评测的领域")
    parser.add_argument("--limit", type=int, default=None, help="限制对话数量")
    parser.add_argument("--data-type", type=str, default="clean", choices=["clean", "noise"])
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD")
    
    args = parser.parse_args()
    
    print(f"=== DST on TransferTOD 评测 ===")
    print(f"领域: {args.domain or '所有'}")
    print(f"数据类型: {args.data_type}")
    print(f"限制数量: {args.limit or '无'}")
    
    # 加载适配器
    adapter = TransferTODAdapter(data_root=args.data_root)
    
    # 获取对话列表
    dialogues = adapter.list_dialogues(data_type=args.data_type, domain=args.domain)
    if args.limit:
        dialogues = dialogues[:args.limit]
        
    print(f"找到 {len(dialogues)} 个对话")
    
    # 评测
    evaluator = DSTEvaluator()
    for dialogue_id in dialogues:
        dialogue = adapter.load_dialogue(dialogue_id, args.data_type)
        # TODO: 运行DST算法并评测
        print(f"评测对话: {dialogue_id} ({dialogue.domain})")
        
    print("评测完成！")


if __name__ == "__main__":
    main()
