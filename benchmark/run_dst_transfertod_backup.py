#!/usr/bin/env python3
"""
DST on TransferTOD 评测运行器

支持：
- 清晰的指标显示
- 结果保存（JSON, CSV）
- 可视化图表生成
- 详细度控制（--verbose）
- 意图评测
"""

import argparse
import json
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.datasets.transfertod.adapter import TransferTODAdapter
from benchmark.algorithms.dst import DSTEvaluator
from benchmark.shared.intent_evaluator import IntentEvaluator
from benchmark.shared.intent_label_loader import get_intent_label_loader

# Import DST model
from contextmind.modes.dst import DialogueStateTracker, PromptManager
from contextmind.infra.llm_client import SimpleLLMClient


def print_header(title: str):
    """打印标题"""
    width = 60
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width + "\n")


def print_metrics_table(metrics_dict: dict, intent_metrics: dict = None, verbose: int = 1):
    """打印指标表格"""
    if verbose == 0:
        # Quiet mode - only show key metrics
        print(f"Slot Accuracy: {metrics_dict['slot_level']['accuracy']:.4f}")
        print(f"Joint Accuracy: {metrics_dict['dialogue_state_level']['joint_accuracy']:.4f}")
        if intent_metrics:
            print(f"Intent Accuracy: {intent_metrics.get('intent_accuracy', 0.0):.4f}")
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
    
    # Show intent metrics if available
    if intent_metrics and verbose >= 1:
        print("\n╔" + "═" * 58 + "╗")
        print("║" + " 意图评测指标 ".center(58) + "║")
        print("╠" + "═" * 58 + "╣")
        print(f"║   Intent Accuracy:      {intent_metrics.get('intent_accuracy', 0.0):.4f}".ljust(59) + "║")
        print(f"║   Total Turns:          {intent_metrics.get('total_turns', 0)}".ljust(59) + "║")
        print(f"║   Correct Predictions:  {intent_metrics.get('correct_predictions', 0)}".ljust(59) + "║")
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
    parser.add_argument('--use-actual-dst', action='store_true',
                      help='使用实际DST模型进行预测（需要LLM，否则使用ground truth）')
    
    args = parser.parse_args()
    
    # Print header
    if args.verbose >= 1:
        print_header("DST on TransferTOD 评测")
        print(f"领域: {args.domain or '所有'}")
        print(f"数据类型: {args.data_type}")
        print(f"限制数量: {args.limit or '无限制'}")
        if args.use_actual_dst:
            print(f"模式: 使用实际DST模型")
        else:
            print(f"模式: 使用Ground Truth（快速评测）")
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
    
    # Initialize evaluators
    dst_evaluator = DSTEvaluator()
    intent_evaluator = IntentEvaluator()
    intent_label_loader = get_intent_label_loader()
    
    # Initialize DST tracker if using actual model
    dst_tracker = None
    if args.use_actual_dst:
        try:
            # Initialize LLM client
            llm_client = SimpleLLMClient()
            if args.verbose >= 1:
                print("✅ LLM客户端初始化成功\n")
        except Exception as e:
            print(f"⚠️  LLM初始化失败: {e}")
            print("⚠️  将使用Ground Truth模式")
            args.use_actual_dst = False
    
    # Run evaluation with asyncio if using actual DST
    if args.use_actual_dst:
        asyncio.run(evaluate_with_dst_model(
            dialogue_ids, adapter, dst_evaluator, intent_evaluator,
            dst_tracker, llm_client, args
        ))
    else:
        evaluate_with_ground_truth(
            dialogue_ids, adapter, dst_evaluator, intent_evaluator, args
        )
    
    # Calculate metrics
    metrics = dst_evaluator.calculate_metrics()
    metrics_dict = metrics.to_dict()
    
    # Get intent metrics
    intent_metrics_raw = intent_evaluator.calculate_metrics()
    intent_metrics_dict = {
        'intent_accuracy': intent_metrics_raw.get('accuracy', 0.0),
        'total_turns': intent_metrics_raw.get('total_turns', 0),
        'correct_predictions': intent_metrics_raw.get('correct_turns', 0)
    }
    
    # Display metrics
    if args.verbose >= 1:
        print()
        print_header("评测结果")
    
    print_metrics_table(metrics_dict, intent_metrics_dict, args.verbose)
    
    # Save results if output directory specified
    if args.output_dir:
        output_dir = Path(args.output_dir)
        # Merge intent metrics into main metrics
        full_metrics = metrics_dict.copy()
        full_metrics['intent_metrics'] = intent_metrics_dict
        save_results(full_metrics, output_dir, args.verbose)
        
        # Generate plots if requested
        if args.save_plots:
            try:
                import matplotlib
                matplotlib.use('Agg')  # Non-interactive backend
                import matplotlib.pyplot as plt
                
                # Create a simple bar chart of metrics
                fig, ax = plt.subplots(figsize=(12, 6))
                metrics_names = ['Slot\nAccuracy', 'Precision', 'Recall', 'F1', 'Joint\nAccuracy', 'Intent\nAccuracy']
                metrics_values = [
                    metrics_dict['slot_level']['accuracy'],
                    metrics_dict['slot_level']['precision'],
                    metrics_dict['slot_level']['recall'],
                    metrics_dict['slot_level']['f1'],
                    metrics_dict['dialogue_state_level']['joint_accuracy'],
                    intent_metrics_dict.get('intent_accuracy', 0.0)
                ]
                
                bars = ax.bar(metrics_names, metrics_values, 
                            color=['#3498db', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6', '#1abc9c'])
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


async def evaluate_with_dst_model(dialogue_ids, adapter, dst_evaluator, intent_evaluator,
                                   dst_tracker, llm_client, args):
    """使用实际DST模型进行评测"""
    for idx, dialogue_id in enumerate(dialogue_ids, 1):
        try:
            dialogue = adapter.load_dialogue(dialogue_id)
            
            if args.verbose == 2:  # Debug mode
                print(f"[{idx}/{len(dialogue_ids)}] 评测对话: {dialogue_id} ({dialogue.domain})")
            elif args.verbose == 1 and idx % 10 == 0:  # Progress indicator
                print(f"进度: {idx}/{len(dialogue_ids)} 完成")
            
            # Initialize DST tracker for this dialogue
            prompt_manager = PromptManager(
                domain=dialogue.domain,
                enable_dynamic_slots=True,
                enable_intent_prediction=True
            )
            tracker = DialogueStateTracker(
                llm_client=llm_client,
                prompt_manager=prompt_manager,
                enable_dynamic_slots=True
            )
            
            # Process each turn
            current_predicted_state = {}
            for turn_idx, turn in enumerate(dialogue.turns):
                # Run DST model
                predicted_updates = await tracker.process_turn(
                    system_utterance=turn.system_utterance or "",
                    user_utterance=turn.user_utterance
                )
                
                # Update cumulative state
                current_predicted_state.update(predicted_updates)
                
                # Get predicted intent if available
                predicted_intent = predicted_updates.get('intent', '其他')
                
                # Add to intent evaluator
                intent_evaluator.add_turn_evaluation(
                    domain=dialogue.domain,
                    turn_id=turn_idx,
                    predicted_intent=predicted_intent,
                    turn_updates=turn.expected_slots,
                    previous_state=current_predicted_state,
                    user_utterance=turn.user_utterance,
                    dialogue_id=dialogue_id,
                    total_turns=len(dialogue.turns)
                )
            
            # Evaluate final state
            dst_evaluator.add_prediction(
                predicted=current_predicted_state,
                ground_truth=dialogue.final_state,
                domain=dialogue.domain
            )
            
        except Exception as e:
            if args.verbose >= 1:
                print(f"⚠️  评测对话 {dialogue_id} 时出错: {e}")
            continue


def evaluate_with_ground_truth(dialogue_ids, adapter, dst_evaluator, intent_evaluator, args):
    """使用Ground Truth进行快速评测（用于测试评测框架本身）"""
    for idx, dialogue_id in enumerate(dialogue_ids, 1):
        try:
            dialogue = adapter.load_dialogue(dialogue_id)
            
            if args.verbose == 2:  # Debug mode
                print(f"[{idx}/{len(dialogue_ids)}] 评测对话: {dialogue_id} ({dialogue.domain})")
            elif args.verbose == 1 and idx % 10 == 0:  # Progress indicator
                print(f"进度: {idx}/{len(dialogue_ids)} 完成")
            
            # Simulate turn-by-turn tracking
            current_state = {}
            for turn_idx, turn in enumerate(dialogue.turns):
                # Simulate prediction by using ground truth with some noise
                # In reality, this should come from your DST model
                current_state.update(turn.expected_slots)
                
                # For demo: add some random errors (10% of the time)
                import random
                predicted_state = current_state.copy()
                if random.random() < 0.1 and predicted_state:
                    # Randomly corrupt one slot
                    slot_to_corrupt = random.choice(list(predicted_state.keys()))
                    predicted_state[slot_to_corrupt] = predicted_state[slot_to_corrupt] + "_错误"
                
                # Get predicted intent (using ground truth for now)
                predicted_intent = turn.expected_slots.get('intent', '其他')
                
                # Add to intent evaluator  
                intent_evaluator.add_turn_evaluation(
                    domain=dialogue.domain,
                    turn_id=turn_idx,
                    predicted_intent=predicted_intent,
                    turn_updates=turn.expected_slots,
                    previous_state=current_state,
                    user_utterance=turn.user_utterance,
                    dialogue_id=dialogue_id,
                    total_turns=len(dialogue.turns)
                )
            
            # Evaluate final state (with simulated errors)
            dst_evaluator.add_prediction(
                predicted=predicted_state,
                ground_truth=dialogue.final_state,
                domain=dialogue.domain
            )
            
        except Exception as e:
            if args.verbose >= 1:
                print(f"⚠️  评测对话 {dialogue_id} 时出错: {e}")
            continue


if __name__ == '__main__':
    main()
