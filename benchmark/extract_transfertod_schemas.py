#!/usr/bin/env python3
"""
从 TransferTOD 数据集提取所有域的预定义函数 Schema

这个脚本从 TransferTOD 数据集获取域的槽位定义，用于 FnCTOD 模式的函数预定义。

重要说明:
  - 默认情况下，脚本只提取数据集中实际存在的域
  - 如果数据集不完整（缺少某些域），这些域不会被提取
  - 使用 --use-standard-list 参数可以尝试提取所有30个标准域（会显示"不可用"的域）
  - 使用 --diagnostics 参数可以查看哪些域缺失

使用方法:
    # 提取数据集中实际存在的所有域（推荐）
    python benchmark/extract_transfertod_schemas.py --data-root ./data/TransferTOD
    
    # 尝试提取标准30域（会显示缺失的域）
    python benchmark/extract_transfertod_schemas.py --data-root ./data/TransferTOD --use-standard-list
    
    # 查看诊断信息（找出缺失的域）
    python benchmark/extract_transfertod_schemas.py --data-root ./data/TransferTOD --diagnostics
    
    # 保存到文件
    python benchmark/extract_transfertod_schemas.py --output schemas.json
"""

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.transfertod.adapter import TransferTODAdapter


def extract_all_schemas(data_root: str, output_file: str = None, verbose: bool = True, show_diagnostics: bool = False, use_standard_list: bool = False):
    """
    从 TransferTOD 数据集提取所有域的 Schema
    
    Args:
        data_root: TransferTOD 数据集根目录
        output_file: 输出文件路径（可选）
        verbose: 是否显示详细信息
        show_diagnostics: 是否显示诊断信息（查找缺失域）
        use_standard_list: 是否使用标准30域列表（默认False，只提取实际存在的域）
    """
    adapter = TransferTODAdapter(data_root)
    
    if verbose:
        print("=" * 80)
        print("从 TransferTOD 数据集提取域-槽位预定义信息")
        print("=" * 80)
        print(f"数据路径: {data_root}")
        print()
    
    # 获取实际可用的域
    available_domains = adapter.get_all_domains(verbose=show_diagnostics)
    if verbose:
        print(f"数据集中可用域数量: {len(available_domains)}")
        print()
    
    # 决定使用哪个域列表进行提取
    if use_standard_list:
        # 使用标准的 30 个域列表（可能包含数据集中不存在的域）
        standard_domains = TransferTODAdapter.get_transfertod_30_domains()
        domains_to_extract = standard_domains
        if verbose:
            print(f"使用 TransferTOD 标准域列表 ({len(standard_domains)} 个域)")
            print()
    else:
        # 只提取实际存在的域（推荐，避免显示"不可用"）
        domains_to_extract = available_domains
        if verbose:
            print(f"仅提取数据集中实际存在的域 ({len(available_domains)} 个域)")
            print()
        
    # 显示诊断信息
    if show_diagnostics or use_standard_list:
        # 当使用标准列表时，总是显示对比信息
        standard_domains = TransferTODAdapter.get_transfertod_30_domains()
        print("=" * 80)
        print("诊断信息：域对比分析")
        print("=" * 80)
        print(f"TransferTOD 标准域列表: {len(standard_domains)} 个")
        print(f"数据集中实际发现的域: {len(available_domains)} 个")
        print()
        
        if show_diagnostics:
            print(f"数据集中实际发现的域（共 {len(available_domains)} 个）：")
            for i, domain in enumerate(available_domains, 1):
                print(f"  {i:2d}. {domain}")
            print()
        
        # 找出缺失的域
        missing_domains = set(standard_domains) - set(available_domains)
        if missing_domains:
            print(f"⚠️  标准列表中但数据集中未找到的域（共 {len(missing_domains)} 个）：")
            for domain in sorted(missing_domains):
                print(f"  - {domain}")
            print()
            if not use_standard_list:
                print("💡 提示: 这些域不会被提取（数据集中不存在）")
                print("   如果要在输出中包含这些域，请使用 --use-standard-list 参数")
                print()
        
        # 找出多余的域
        extra_domains = set(available_domains) - set(standard_domains)
        if extra_domains:
            print(f"数据集中有但标准列表中没有的域（共 {len(extra_domains)} 个）：")
            for domain in sorted(extra_domains):
                print(f"  + {domain}")
            print()
        print("=" * 80)
        print()
    
    # 提取所有域的 Schema
    if verbose:
        print("开始提取域 Schema...")
        print("-" * 80)
    
    all_schemas = {}
    for i, domain in enumerate(domains_to_extract, 1):
        if domain in available_domains:
            try:
                schema = adapter.get_domain_schema(domain)
                all_schemas[domain] = schema
                
                if verbose:
                    slot_count = len(schema.get('slots', {}))
                    dialogue_count = schema.get('metadata', {}).get('dialogue_count', 0)
                    print(f"{i:2d}. ✅ {domain:8s} - {slot_count:2d} 个槽位, {dialogue_count:4d} 个对话")
            except Exception as e:
                if verbose:
                    print(f"{i:2d}. ❌ {domain:8s} - 提取失败: {e}")
        else:
            if verbose:
                print(f"{i:2d}. ⚠️  {domain:8s} - 数据集中不可用")
    
    if verbose:
        print("-" * 80)
        print(f"\n成功提取 {len(all_schemas)} 个域的 Schema")
        print()
    
    # 输出统计信息
    if verbose and all_schemas:
        total_slots = sum(len(schema.get('slots', {})) for schema in all_schemas.values())
        total_dialogues = sum(schema.get('metadata', {}).get('dialogue_count', 0) for schema in all_schemas.values())
        
        print("=" * 80)
        print("汇总统计")
        print("=" * 80)
        print(f"总域数:     {len(all_schemas)}")
        print(f"总槽位数:   {total_slots}")
        print(f"总对话数:   {total_dialogues}")
        print()
    
    # 保存到文件
    if output_file:
        output_path = Path(output_file)
        
        # 准备输出数据
        output_data = {
            "dataset": "TransferTOD",
            "source": "https://github.com/KongLongGeFDU/TransferTOD",
            "total_domains": len(all_schemas),
            "domains": all_schemas
        }
        
        # 写入文件
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            if verbose:
                print(f"✅ Schema 已保存到: {output_path}")
                print(f"   文件大小: {output_path.stat().st_size / 1024:.1f} KB")
                print()
        except IOError as e:
            print(f"❌ 无法写入文件: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            raise
    
    return all_schemas


def show_domain_detail(data_root: str, domain: str):
    """
    显示特定域的详细信息
    
    Args:
        data_root: TransferTOD 数据集根目录
        domain: 域名称
    """
    adapter = TransferTODAdapter(data_root)
    
    print("=" * 80)
    print(f"域详细信息: {domain}")
    print("=" * 80)
    
    try:
        schema = adapter.get_domain_schema(domain)
        
        print(f"领域名称:   {schema.get('domain')}")
        print(f"领域描述:   {schema.get('description')}")
        print(f"对话数量:   {schema.get('metadata', {}).get('dialogue_count', 0)}")
        print(f"槽位数量:   {len(schema.get('slots', {}))}")
        print()
        
        print("槽位列表:")
        print("-" * 80)
        for slot_name, slot_info in sorted(schema.get('slots', {}).items()):
            description = slot_info.get('description', '')
            count = slot_info.get('occurrence_count', 0)
            examples = slot_info.get('example_values', [])
            
            print(f"  {slot_name:20s} - {description}")
            if count:
                print(f"    {'':20s}   出现次数: {count}")
            if examples:
                print(f"    {'':20s}   示例值: {', '.join(examples[:5])}")
        
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="从 TransferTOD 数据集提取域-槽位预定义信息"
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default="./data/TransferTOD",
        help="TransferTOD 数据集根目录 (默认: ./data/TransferTOD)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出 JSON 文件路径 (可选)"
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help="显示特定域的详细信息 (可选)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，不显示详细信息"
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="显示诊断信息，帮助查找缺失的域"
    )
    parser.add_argument(
        "--use-standard-list",
        action="store_true",
        help="使用 TransferTOD 标准30域列表（而不是只提取实际存在的域）"
    )
    
    args = parser.parse_args()
    
    # 检查数据集是否存在
    data_path = Path(args.data_root)
    if not data_path.exists():
        print(f"❌ 错误: 数据集路径不存在: {data_path}")
        print()
        print("请确保 TransferTOD 数据集已下载到指定路径。")
        print("数据集结构应为:")
        print("  {data_root}/data/raw_data/clean/...")
        print("  {data_root}/data/raw_data/noise/...")
        print()
        print("数据集来源: https://github.com/KongLongGeFDU/TransferTOD")
        sys.exit(1)
    
    # 显示特定域的详细信息
    if args.domain:
        show_domain_detail(args.data_root, args.domain)
    else:
        # 提取所有域的 Schema
        extract_all_schemas(
            data_root=args.data_root,
            output_file=args.output,
            verbose=not args.quiet,
            show_diagnostics=args.diagnostics,
            use_standard_list=args.use_standard_list
        )


if __name__ == "__main__":
    main()
