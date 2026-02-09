#!/usr/bin/env python3
"""
DST on TransferTOD 评测运行器

支持：
- 清晰的指标显示
- 结果保存（JSON, CSV）
- 可视化图表生成
- 详细度控制（--verbose）
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.datasets.transfertod.adapter import TransferTODAdapter
from benchmark.algorithms.dst import DSTEvaluator


def print_header(title: str):
    """打印标题"""
    width = 60
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width + "\n")


def print_metrics_table(metrics_dict: dict, verbose: int = 1):
    """打印指标表格"""
    if verbose == 0:
        # Quiet mode - only show key metrics
        print(f"Slot Accuracy: {metrics_dict['slot_level']['accuracy']:.4f}")
        print(f"Joint Accuracy: {metrics_dict['dialogue_state_level']['joint_accuracy']:.4f}")
        return
    
    # Normal or verbose mode - show detailed table
    print("\n╔" + "═" * 58 + "╗")
    print("║" + " DST 评测指标 ".center(58) + "║")
    print("╠" + "═" * 58 + "╣")
    
    print("║ " + "Slot-Level Metrics".ljust(57) + "║")
    slot_metrics = metrics_dict['slot_level']
    print(f"║   Slot Accuracy:        {slot_metrics['accuracy']:.4f}".ljust(59) + "║")
    print(f"║   Precision:            {slot_metrics['precision']:.4f}".ljust(59) + "║")
    print(f"║   Recall:               {slot_metrics['recall']:.4f}".ljust(59) + "║")
    print(f"║   F1 Score:             {slot_metrics['f1']:.4f}".ljust(59) + "║")
    
    print("║ " + " " * 57 + "║")
    print("║ " + "Dialogue-State-Level Metrics".ljust(57) + "║")
    ds_metrics = metrics_dict['dialogue_state_level']
    print(f"║   Joint Accuracy:       {ds_metrics['joint_accuracy']:.4f}".ljust(59) + "║")
    print(f"║   Joint Accuracy (Strict): {ds_metrics['joint_accuracy_strict']:.4f}".ljust(59) + "║")
    
    print("║ " + " " * 57 + "║")
    print("║ " + "Statistics".ljust(57) + "║")
    stats = metrics_dict['statistics']
    print(f"║   Total Turns:          {stats['total_turns']}".ljust(59) + "║")
    print(f"║   Total Slots:          {stats['total_slots']}".ljust(59) + "║")
    print(f"║   Correct Slots:        {stats['correct_slots']}".ljust(59) + "║")
    print(f"║   Correct Turns:        {stats['correct_turns']}".ljust(59) + "║")
    
    print("╚" + "═" * 58 + "╝\n")
    
    # Show domain breakdown if available and verbose
    if verbose >= 1 and 'domain_breakdown' in metrics_dict and metrics_dict['domain_breakdown']:
        print("\n领域细分指标:")
        print("-" * 60)
        for domain, domain_metrics in metrics_dict['domain_breakdown'].items():
            print(f"  {domain}:")
            print(f"    Slot Accuracy:  {domain_metrics['slot_accuracy']:.4f}")
            print(f"    Joint Accuracy: {domain_metrics['joint_accuracy']:.4f}")
            print(f"    Total Turns:    {domain_metrics['total_turns']}")
        print("-" * 60)


def save_results(metrics_dict: dict, output_dir: Path, verbose: int = 1):
    """保存结果到文件"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save metrics as JSON
    metrics_file = output_dir / "metrics.json"
    with open(metrics_file, 'w', encoding='utf-8') as f:
        json.dump(metrics_dict, f, ensure_ascii=False, indent=2)
    
    if verbose >= 1:
        print(f"✅ 指标已保存到: {metrics_file}")
    
    # Save summary as text
    summary_file = output_dir / "summary.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write(" DST on TransferTOD 评测结果摘要 ".center(60) + "\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"评测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("主要指标:\n")
        f.write(f"  Slot Accuracy:  {metrics_dict['slot_level']['accuracy']:.4f}\n")
        f.write(f"  Joint Accuracy: {metrics_dict['dialogue_state_level']['joint_accuracy']:.4f}\n")
        f.write(f"  F1 Score:       {metrics_dict['slot_level']['f1']:.4f}\n\n")
        
        f.write("统计信息:\n")
        stats = metrics_dict['statistics']
        f.write(f"  Total Turns:    {stats['total_turns']}\n")
        f.write(f"  Total Slots:    {stats['total_slots']}\n")
        f.write(f"  Correct Slots:  {stats['correct_slots']}\n")
        f.write(f"  Correct Turns:  {stats['correct_turns']}\n")
    
    if verbose >= 1:
        print(f"✅ 摘要已保存到: {summary_file}")


def main():
    parser = argparse.ArgumentParser(description='DST on TransferTOD 评测')
    parser.add_argument('--data-root', type=str, default='./data/TransferTOD',
                      help='TransferTOD 数据集根目录 (默认: ./data/TransferTOD)')
    parser.add_argument('--data-type', type=str, default='clean',
                      choices=['clean', 'noise'],
                      help='数据类型：clean 或 noise (默认: clean)')
    parser.add_argument('--domain', type=str, default=None,
                      help='指定领域（可选，不指定则评测所有领域）')
    parser.add_argument('--limit', type=int, default=None,
                      help='限制评测对话数量（用于快速测试）')
    parser.add_argument('--verbose', '-v', type=int, default=1, choices=[0, 1, 2],
                      help='日志详细度: 0=安静, 1=正常, 2=详细 (默认: 1)')
    parser.add_argument('--output-dir', type=str, default=None,
                      help='结果输出目录（可选）')
    parser.add_argument('--save-plots', action='store_true',
                      help='生成并保存可视化图表')
    
    args = parser.parse_args()
    
    # Print header
    if args.verbose >= 1:
        print_header("DST on TransferTOD 评测")
        print(f"领域: {args.domain or '所有'}")
        print(f"数据类型: {args.data_type}")
        print(f"限制数量: {args.limit or '无限制'}")
        print()
    
    # Load adapter
    adapter = TransferTODAdapter(args.data_root)
    
    # List dialogues
    dialogue_ids = adapter.list_dialogues(
        data_type=args.data_type,
        domain=args.domain
    )
    
    if args.limit:
        dialogue_ids = dialogue_ids[:args.limit]
    
    if args.verbose >= 1:
        print(f"找到 {len(dialogue_ids)} 个对话\n")
    
    if not dialogue_ids:
        print("⚠️  未找到对话数据，请检查数据路径")
        return
    
    # Initialize evaluator
    evaluator = DSTEvaluator()
    
    # Evaluate dialogues
    for idx, dialogue_id in enumerate(dialogue_ids, 1):
        try:
            dialogue = adapter.load_dialogue(dialogue_id)
            
            if args.verbose == 2:  # Debug mode
                print(f"[{idx}/{len(dialogue_ids)}] 评测对话: {dialogue_id} ({dialogue.domain})")
            elif args.verbose == 1 and idx % 10 == 0:  # Progress indicator
                print(f"进度: {idx}/{len(dialogue_ids)} 完成")
            
            # For simplicity, we're using final_state as both prediction and ground truth
            # In real scenario, you would run your DST model here
            predicted_state = dialogue.final_state
            ground_truth_state = dialogue.final_state
            
            evaluator.add_prediction(
                predicted=predicted_state,
                ground_truth=ground_truth_state,
                domain=dialogue.domain
            )
            
        except Exception as e:
            if args.verbose >= 1:
                print(f"⚠️  评测对话 {dialogue_id} 时出错: {e}")
            continue
    
    # Calculate metrics
    metrics = evaluator.calculate_metrics()
    metrics_dict = metrics.to_dict()
    
    # Display metrics
    if args.verbose >= 1:
        print()
        print_header("评测结果")
    
    print_metrics_table(metrics_dict, args.verbose)
    
    # Save results if output directory specified
    if args.output_dir:
        output_dir = Path(args.output_dir)
        save_results(metrics_dict, output_dir, args.verbose)
        
        # Generate plots if requested
        if args.save_plots:
            try:
                import matplotlib
                matplotlib.use('Agg')  # Non-interactive backend
                import matplotlib.pyplot as plt
                
                # Create a simple bar chart of metrics
                fig, ax = plt.subplots(figsize=(10, 6))
                metrics_names = ['Slot\nAccuracy', 'Precision', 'Recall', 'F1', 'Joint\nAccuracy']
                metrics_values = [
                    metrics_dict['slot_level']['accuracy'],
                    metrics_dict['slot_level']['precision'],
                    metrics_dict['slot_level']['recall'],
                    metrics_dict['slot_level']['f1'],
                    metrics_dict['dialogue_state_level']['joint_accuracy']
                ]
                
                bars = ax.bar(metrics_names, metrics_values, color=['#3498db', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6'])
                ax.set_ylim(0, 1.0)
                ax.set_ylabel('Score', fontsize=12)
                ax.set_title('DST Evaluation Metrics', fontsize=14, fontweight='bold')
                ax.grid(axis='y', alpha=0.3)
                
                # Add value labels on bars
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{height:.4f}',
                           ha='center', va='bottom', fontsize=10)
                
                plt.tight_layout()
                plot_file = output_dir / "metrics_chart.png"
                plt.savefig(plot_file, dpi=150, bbox_inches='tight')
                plt.close()
                
                if args.verbose >= 1:
                    print(f"✅ 图表已保存到: {plot_file}")
                
            except ImportError:
                if args.verbose >= 1:
                    print("⚠️  matplotlib 未安装，跳过图表生成")
            except Exception as e:
                if args.verbose >= 1:
                    print(f"⚠️  生成图表时出错: {e}")
    
    if args.verbose >= 1:
        print("\n评测完成！\n")


if __name__ == '__main__':
    main()
