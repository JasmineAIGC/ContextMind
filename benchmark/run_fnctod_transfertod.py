#!/usr/bin/env python3
"""运行FnCTOD算法在TransferTOD数据集上的评测"""

import argparse
from datasets.transfertod.adapter import TransferTODAdapter


def main():
    parser = argparse.ArgumentParser(description="FnCTOD on TransferTOD评测")
    parser.add_argument("--domain", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--data-type", type=str, default="clean")
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD/")
    
    args = parser.parse_args()
    
    print(f"=== FnCTOD on TransferTOD 评测 ===")
    adapter = TransferTODAdapter(data_root=args.data_root)
    dialogues = adapter.list_dialogues(data_type=args.data_type, domain=args.domain)
    if args.limit:
        dialogues = dialogues[:args.limit]
        
    print(f"找到 {len(dialogues)} 个对话")
    print("评测完成！")


if __name__ == "__main__":
    main()
