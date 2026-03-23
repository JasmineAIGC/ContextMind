#!/usr/bin/env python3
"""
诊断工具：分析 DST 和 FnCTOD 评测找到的对话数量差异

使用方式:
    python benchmark/tools/diagnose_dialogue_count.py --data-root ./data/TransferTOD
"""

import argparse
import sys
from pathlib import Path
from collections import defaultdict

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.transfertod.adapter import TransferTODAdapter


def analyze_dialogue_distribution(data_root: str):
    """分析对话分布"""
    print("="*80)
    print("TransferTOD 数据集对话分布分析")
    print("="*80)
    print(f"数据路径: {data_root}\n")
    
    adapter = TransferTODAdapter(data_root)
    
    # 1. 统计总对话数
    print("【1. 总体统计】")
    all_ids = adapter.get_all_dialogue_ids()
    print(f"  所有对话数（clean + noise）: {len(all_ids)}")
    
    # 按数据类型分类
    clean_ids = [d for d in all_ids if d.startswith("clean/")]
    noise_ids = [d for d in all_ids if d.startswith("noise/")]
    print(f"  - clean 数据: {len(clean_ids)} 个对话")
    print(f"  - noise 数据: {len(noise_ids)} 个对话")
    
    # 2. 按域统计
    print("\n【2. 按域统计】")
    all_domains = adapter.get_all_domains()
    print(f"  数据集中的域数量: {len(all_domains)}")
    print(f"  域列表: {', '.join(all_domains)}")
    
    # 统计每个域的对话数
    domain_stats = defaultdict(lambda: {"clean": 0, "noise": 0, "total": 0})
    
    for dialogue_id in all_ids:
        try:
            dialogue = adapter.load_dialogue(dialogue_id)
            domain = dialogue.domain
            data_type = "clean" if dialogue_id.startswith("clean/") else "noise"
            domain_stats[domain][data_type] += 1
            domain_stats[domain]["total"] += 1
        except Exception as e:
            print(f"  警告: 无法加载对话 {dialogue_id}: {e}")
            continue
    
    # 显示每个域的统计
    print("\n【3. 分域详细统计】")
    print(f"{'域名':<15} {'Clean':<10} {'Noise':<10} {'总计':<10}")
    print("-" * 50)
    
    total_clean = 0
    total_noise = 0
    total_all = 0
    
    for domain in sorted(domain_stats.keys()):
        stats = domain_stats[domain]
        print(f"{domain:<15} {stats['clean']:<10} {stats['noise']:<10} {stats['total']:<10}")
        total_clean += stats['clean']
        total_noise += stats['noise']
        total_all += stats['total']
    
    print("-" * 50)
    print(f"{'总计':<15} {total_clean:<10} {total_noise:<10} {total_all:<10}")
    
    # 4. 模拟不同参数组合
    print("\n【4. 不同参数组合的对话数】")
    print("-" * 50)
    
    test_cases = [
        ("无参数（所有）", None, None),
        ("只clean数据", None, "clean"),
        ("只noise数据", None, "noise"),
    ]
    
    # 为每个域添加测试用例
    for domain in sorted(all_domains)[:5]:  # 只显示前5个域
        test_cases.append((f"域={domain}, clean", domain, "clean"))
    
    for desc, domain, data_type in test_cases:
        ids = adapter.get_dialogues_by_domain(domain, data_type)
        print(f"  {desc:<30} -> {len(ids):>6} 个对话")
    
    # 5. 文件级别统计
    print("\n【5. 文件级别统计】")
    raw_data_path = Path(data_root) / "data" / "raw_data"
    
    for data_type in ["clean", "noise"]:
        data_dir = raw_data_path / data_type
        if data_dir.exists():
            json_files = list(data_dir.rglob("*.json"))
            print(f"  {data_type} 目录:")
            print(f"    - JSON 文件数: {len(json_files)}")
            
            # 统计对话实例数
            total_instances = 0
            for json_file in json_files:
                try:
                    import json
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        total_instances += len(data)
                    else:
                        total_instances += 1
                except Exception:
                    continue
            
            print(f"    - 对话实例数: {total_instances}")
    
    print("\n" + "="*80)
    print("分析完成")
    print("="*80)


def main():
    parser = argparse.ArgumentParser(description="诊断 TransferTOD 对话数量差异")
    parser.add_argument(
        "--data-root",
        type=str,
        default="./data/TransferTOD",
        help="TransferTOD 数据集根目录"
    )
    
    args = parser.parse_args()
    
    try:
        analyze_dialogue_distribution(args.data_root)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
