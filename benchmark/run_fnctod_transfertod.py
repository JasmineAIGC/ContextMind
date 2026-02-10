#!/usr/bin/env python3
"""
FnCTOD模式 - TransferTOD数据集评测脚本

使用TransferTOD数据集测试FnCTODTracker的函数调用能力。

使用方式:
    python benchmark/run_fnctod_transfertod.py
    python benchmark/run_fnctod_transfertod.py --domain 酒店 --data-type clean --limit 10
"""

# ============================================================================
# 版本标识 - 如果你看到这行输出，说明你在运行新版本的脚本
# VERSION: 2024-02-10-v3 (Fixed FunctionParameter initialization)
# ============================================================================
print("=" * 80)
print("🔍 FnCTOD Evaluation Script - Version 2024-02-10-v3")
print("=" * 80)
print("✅ 正在加载完整评测实现（已修复FunctionParameter错误）...")
print()

import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict, Counter
import datetime

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.transfertod.adapter import TransferTODAdapter
from benchmark.shared.intent_evaluator import IntentEvaluator
from contextmind.modes.fnctod import FnCTODTracker, FunctionManager, get_function_schema_for_scenario
from contextmind.modes.fnctod.data_models import DomainSpec, FunctionParameter, ParameterType
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class FnCTODTransferTODTest:
    """
    FnCTOD模式 - TransferTOD测试类
    """
    
    def __init__(self, data_root: str = "./data/TransferTOD", schemas_file: str = None):
        """
        初始化测试
        
        Args:
            data_root: TransferTOD数据集根目录
            schemas_file: 可选的预加载schemas JSON文件路径
        """
        self.adapter = TransferTODAdapter(data_root, schemas_file=schemas_file)
        self.llm_client = None
        self.tracker = None
        self.intent_evaluator = IntentEvaluator()  # 意图评测器
        
    def initialize(self, domain: str):
        """
        初始化FnCTOD追踪器
        
        Args:
            domain: 领域名称
        """
        # 创建LLM客户端
        try:
            self.llm_client = SimpleLLMClient()
            logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM客户端初始化失败: {e}")
            print(f"\n{'='*70}")
            print(f"❌ 错误: 无法初始化LLM客户端")
            print(f"{'='*70}")
            print(f"原因: {e}")
            print(f"\nFnCTOD 模式需要 LLM 来提取槽位信息。")
            print(f"请确认:")
            print(f"  1. 已安装 OpenAI 包: pip install openai")
            print(f"  2. 已设置API密钥环境变量 (如 QWEN3_API_KEY 或 OPENAI_API_KEY)")
            print(f"  3. API密钥有效且有足够的配额")
            print(f"\n提示: 如果没有LLM访问权限，所有指标将为 0.00%")
            print(f"{'='*70}\n")
            raise
        
        # 获取领域schema
        schema = self.adapter.get_domain_schema(domain)
        
        # 创建FunctionManager并添加领域函数
        function_manager = FunctionManager()
        
        # 创建DomainSpec（将TransferTOD schema转换为FnCTOD格式）
        domain_spec = self._create_domain_spec_from_schema(domain, schema)
        function_manager.add_domain(domain_spec)
        
        # 创建FnCTODTracker
        self.tracker = FnCTODTracker(
            llm_client=self.llm_client,
            function_manager=function_manager,
            use_two_stage=True,  # 使用两阶段处理
            max_history_turns=10
        )
        
        logger.info(f"✅ FnCTOD模式初始化完成 - 领域: {domain}")
        logger.info(f"   函数调用模式: 两阶段（domain选择 + parameter填充）")
        logger.info(f"   预定义槽位数: {len(schema['slots'])}")
    
    def _create_domain_spec_from_schema(self, domain: str, schema: Dict) -> DomainSpec:
        """
        从TransferTOD schema创建DomainSpec
        
        Args:
            domain: 领域名称
            schema: TransferTOD schema
            
        Returns:
            DomainSpec对象
        """
        # 创建函数参数
        parameters = []
        for slot_name, slot_info in schema["slots"].items():
            param = FunctionParameter(
                name=slot_name,
                description=slot_info.get("description", slot_name),
                param_type=ParameterType.STRING,  # TransferTOD中大多数槽位是字符串
                required=False  # 一般槽位都是可选的
            )
            parameters.append(param)
        
        # 创建DomainSpec
        domain_spec = DomainSpec(
            name=domain,
            description=schema.get("description", f"{domain}领域对话"),
            parameters=parameters
        )
        
        return domain_spec
    
    def _make_value_hashable(self, value):
        """
        将槽位值转换为可哈希的形式
        
        用于处理字典、列表等不可哈希的类型，以便可以添加到集合中。
        
        Args:
            value: 槽位值（可能是任何类型）
            
        Returns:
            可哈希的值（字符串、数字、None等）
        """
        if value is None:
            return None
        elif isinstance(value, (dict, list)):
            # 将字典或列表转换为JSON字符串，保证一致性
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        else:
            # 其他类型（字符串、数字、布尔值等）直接返回
            return value
    
    async def test_dialogue(self, dialogue_id: str, verbose: bool = True) -> Dict[str, Any]:
        """
        测试单个对话
        
        Args:
            dialogue_id: 对话ID
            verbose: 是否输出详细信息
            
        Returns:
            包含评测指标的字典
        """
        # 加载对话数据
        dialogue = self.adapter.load_dialogue(dialogue_id)
        
        if verbose:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"测试对话: {dialogue_id}")
            logger.info(f"领域: {dialogue.domain}")
            logger.info(f"轮次数: {len(dialogue.turns)}")
        
        # 重置tracker状态
        self.tracker.reset()
        
        # 逐轮处理
        correct_slots = 0
        total_slots = 0
        correct_turns = 0
        
        # 收集所有槽位值对（用于计算precision/recall）
        all_predicted_pairs = set()
        all_ground_truth_pairs = set()
        
        # 收集用户话语用于意图评测
        all_user_utterances = []
        
        for turn_idx, turn in enumerate(dialogue.turns):
            user_input = turn.user_utterance
            all_user_utterances.append(user_input)
            
            # 调用FnCTOD进行状态追踪
            try:
                response = await self.tracker.process_turn(user_input)
                predicted_state = response.get("state", {})
                
                if verbose:
                    logger.info(f"\n  轮次 {turn_idx + 1}:")
                    logger.info(f"    用户: {user_input}")
                    logger.info(f"    预测状态: {predicted_state}")
                    logger.info(f"    实际状态: {turn.expected_slots}")
                
                # 评估当前轮的槽位准确性
                turn_correct = 0
                turn_total = 0
                
                # 检查是否有数据（用于诊断指标为0的问题）
                # 这些警告在非verbose模式下也会显示，帮助用户诊断问题
                if not turn.expected_slots:
                    logger.warning(f"⚠️ 轮次 {turn_idx + 1} 没有 expected_slots 数据")
                if not predicted_state:
                    logger.warning(f"⚠️ 轮次 {turn_idx + 1} 没有 predicted_state 数据（LLM可能未正确调用）")
                
                for slot_name, true_value in turn.expected_slots.items():
                    turn_total += 1
                    total_slots += 1
                    predicted_value = predicted_state.get(slot_name)
                    
                    # 将值转换为可哈希的形式（处理 dict/list 等不可哈希类型）
                    hashable_true_value = self._make_value_hashable(true_value)
                    hashable_pred_value = self._make_value_hashable(predicted_value)
                    
                    # 添加到集合用于P/R/F1计算
                    all_ground_truth_pairs.add((slot_name, hashable_true_value))
                    if predicted_value is not None:
                        all_predicted_pairs.add((slot_name, hashable_pred_value))
                    
                    if predicted_value == true_value:
                        turn_correct += 1
                        correct_slots += 1
                
                # 检查是否有额外预测的槽位
                for slot_name, pred_value in predicted_state.items():
                    if slot_name not in turn.expected_slots:
                        hashable_pred_value = self._make_value_hashable(pred_value)
                        all_predicted_pairs.add((slot_name, hashable_pred_value))
                
                # 判断整轮是否完全正确
                if turn_total > 0 and turn_correct == turn_total:
                    correct_turns += 1
                    
            except Exception as e:
                logger.error(f"处理轮次 {turn_idx + 1} 时出错: {e}")
                continue
        
        # 计算指标
        slot_accuracy = correct_slots / total_slots if total_slots > 0 else 0
        
        # 联合准确率（所有轮次都完全正确）
        joint_accuracy = 1.0 if correct_turns == len(dialogue.turns) and len(dialogue.turns) > 0 else 0.0
        
        # 计算 Precision, Recall, F1
        tp = len(all_predicted_pairs & all_ground_truth_pairs)
        fp = len(all_predicted_pairs - all_ground_truth_pairs)
        fn = len(all_ground_truth_pairs - all_predicted_pairs)
        
        # 诊断信息：如果指标为0，记录详细信息帮助排查
        if len(all_ground_truth_pairs) == 0 or len(all_predicted_pairs) == 0:
            logger.warning(f"⚠️ 对话 {dialogue_id} 的集合为空:")
            logger.warning(f"   Ground truth pairs: {len(all_ground_truth_pairs)}")
            logger.warning(f"   Predicted pairs: {len(all_predicted_pairs)}")
            logger.warning(f"   这通常表示 LLM 未正确提取槽位信息")
        else:
            logger.debug(f"Ground truth pairs: {len(all_ground_truth_pairs)}")
            logger.debug(f"Predicted pairs: {len(all_predicted_pairs)}")
            logger.debug(f"TP: {tp}, FP: {fp}, FN: {fn}")
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        # 添加意图评测（对话级别）
        if dialogue.turns:
            # 获取最终的对话状态（FnCTOD tracker维护的累积状态）
            # tracker.current_state 在处理每一轮后累积更新，这里获取的是处理完所有轮次后的最终状态
            final_extracted = self.tracker.current_state.copy()
            
            # 从FnCTOD响应中获取预测的意图
            # 注意：当前 FnCTOD 实现主要关注槽位填充，不直接预测意图
            # 这里使用领域名称作为预测意图的占位符
            # 真实的意图会由 IntentEvaluator 从槽位信息自动推断
            predicted_intent = dialogue.domain
            
            # 调用add_dialogue_evaluation，让它从槽位信息推断真值意图
            # IntentEvaluator 会基于 dialogue_slots 和 user_utterances 推断实际意图
            self.intent_evaluator.add_dialogue_evaluation(
                dialogue_id=dialogue_id,
                domain=dialogue.domain,
                predicted_intent=predicted_intent,
                dialogue_slots=final_extracted,  # 使用最终提取的槽位
                user_utterances=all_user_utterances
            )
        
        if verbose:
            logger.info(f"\n  评测结果:")
            logger.info(f"    槽位准确率: {slot_accuracy * 100:.2f}%")
            logger.info(f"    联合准确率: {joint_accuracy * 100:.2f}%")
            logger.info(f"    精确率: {precision * 100:.2f}%")
            logger.info(f"    召回率: {recall * 100:.2f}%")
            logger.info(f"    F1分数: {f1 * 100:.2f}%")
        
        return {
            "dialogue_id": dialogue_id,
            "slot_accuracy": slot_accuracy,
            "joint_accuracy": joint_accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total_slots": total_slots,
            "correct_slots": correct_slots
        }


def main():
    parser = argparse.ArgumentParser(description="FnCTOD on TransferTOD评测")
    parser.add_argument("--domain", type=str, default=None, help="指定测试领域")
    parser.add_argument("--limit", type=int, default=None, help="限制测试对话数量")
    parser.add_argument("--data-type", type=str, default="clean", choices=["clean", "noise"], help="数据类型")
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD/", help="数据集根目录")
    parser.add_argument("--schemas-file", type=str, default=None, 
                       help="预加载的schemas JSON文件路径（可选）。"
                            "使用此选项可以加速测试并确保schema一致性。"
                            "文件应由 extract_transfertod_schemas.py 生成。")
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    parser.add_argument("--no-verbose", dest="verbose", action="store_false", help="不输出详细日志")
    parser.set_defaults(verbose=False)
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        setup_logging(LogLevel.DEBUG)
    else:
        setup_logging(LogLevel.WARNING)
    
    # 禁用 matplotlib 的 DEBUG 日志以避免字体查找信息污染输出
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)
    
    print(f"\n{'=' * 70}")
    print(f"=== FnCTOD on TransferTOD 评测 ===")
    print(f"{'=' * 70}")
    print(f"脚本版本: 2024-02-10 (完整评测版本)")
    print(f"{'=' * 70}\n")
    
    # 显示schemas文件信息（如果提供）
    if args.schemas_file:
        print(f"📁 使用预加载的schemas文件: {args.schemas_file}\n")
    
    # 初始化测试
    test = FnCTODTransferTODTest(data_root=args.data_root, schemas_file=args.schemas_file)
    
    # 获取对话列表
    try:
        dialogue_ids = test.adapter.get_dialogues_by_domain(args.domain, args.data_type)
    except Exception as e:
        logger.error(f"获取对话列表失败: {e}")
        print(f"\n错误: 无法加载数据集。请确保数据集位于 {args.data_root}")
        print("数据集应包含以下结构: data/raw_data/clean/ 和 data/raw_data/noise/")
        return
    
    if not dialogue_ids:
        print(f"\n未找到符合条件的对话数据")
        return
    
    print(f"找到 {len(dialogue_ids)} 个对话实例")
    
    # 限制测试数量
    if args.limit:
        dialogue_ids = dialogue_ids[:args.limit]
        print(f"限制测试数量: {args.limit}")
    
    # 初始化FnCTOD tracker
    if args.domain:
        print(f"\n初始化领域: {args.domain}")
        try:
            test.initialize(args.domain)
        except Exception as e:
            print(f"❌ 初始化FnCTOD tracker失败: {e}")
            import traceback
            traceback.print_exc()
            return
    
    # 批量测试
    print(f"\n开始评测...")
    all_metrics = []
    domain_metrics = defaultdict(list)
    current_domain = None
    
    # 创建新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        for idx, dialogue_id in enumerate(dialogue_ids, 1):
            print(f"\n处理对话 {idx}/{len(dialogue_ids)}: {dialogue_id}")
            try:
                # 如果没有指定domain，需要为每个对话的domain初始化tracker
                if not args.domain:
                    dialogue = test.adapter.load_dialogue(dialogue_id)
                    if dialogue.domain != current_domain:
                        current_domain = dialogue.domain
                        print(f"\n切换领域: {current_domain}")
                        try:
                            test.initialize(current_domain)
                        except Exception as e:
                            print(f"❌ 初始化领域 {current_domain} 失败: {e}")
                            import traceback
                            traceback.print_exc()
                            continue
                        
                        # 检查tracker是否成功初始化
                        if test.tracker is None:
                            print(f"❌ 由于初始化失败，跳过剩余 {len(dialogue_ids) - i} 个对话")
                            print(f"请检查领域 '{current_domain}' 的schema配置")
                            break
                else:
                    current_domain = args.domain
                
                # 使用事件循环运行async函数
                metrics = loop.run_until_complete(test.test_dialogue(dialogue_id, verbose=args.verbose))
                all_metrics.append(metrics)
                domain_metrics[current_domain].append(metrics)
                print(f"✅ 对话 {dialogue_id} 评测完成")
            except Exception as e:
                logger.error(f"测试对话 {dialogue_id} 失败: {e}")
                print(f"❌ 测试对话 {dialogue_id} 失败: {e}")
                import traceback
                traceback.print_exc()
                continue
    finally:
        if not loop.is_closed():
            loop.close()
    
    print(f"\n{'=' * 70}")
    print(f"评测循环完成，收集到 {len(all_metrics)} 个对话的指标")
    print(f"{'=' * 70}")
    
    # 输出汇总指标
    if all_metrics:
        summary_lines = []
        summary_lines.append("\n" + "=" * 70)
        summary_lines.append("📊 FnCTOD 测试指标汇总")
        summary_lines.append("=" * 70)
        
        # 按领域显示指标
        if domain_metrics:
            summary_lines.append("\n【分领域统计】")
            summary_lines.append("-" * 70)
            for domain, metrics_list in sorted(domain_metrics.items()):
                avg_slot_acc = sum(m["slot_accuracy"] for m in metrics_list) / len(metrics_list)
                avg_ja = sum(m["joint_accuracy"] for m in metrics_list) / len(metrics_list)
                avg_precision = sum(m["precision"] for m in metrics_list) / len(metrics_list)
                avg_recall = sum(m["recall"] for m in metrics_list) / len(metrics_list)
                avg_f1 = sum(m["f1"] for m in metrics_list) / len(metrics_list)
                
                summary_lines.append(f"\n{domain}领域 (对话数: {len(metrics_list)}):")
                summary_lines.append(f"  槽位准确率: {avg_slot_acc * 100:.2f}%")
                summary_lines.append(f"  联合准确率: {avg_ja * 100:.2f}%")
                summary_lines.append(f"  精确率: {avg_precision * 100:.2f}%")
                summary_lines.append(f"  召回率: {avg_recall * 100:.2f}%")
                summary_lines.append(f"  F1分数: {avg_f1 * 100:.2f}%")
            summary_lines.append("")
        
        # 汇总统计
        avg_slot_accuracy = sum(m["slot_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy = sum(m["joint_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        summary_lines.append("\n【整体汇总统计】")
        summary_lines.append("-" * 70)
        summary_lines.append(f"总测试对话数: {len(all_metrics)}")
        summary_lines.append(f"平均槽位准确率 (Slot Accuracy): {avg_slot_accuracy * 100:.2f}%")
        summary_lines.append(f"平均联合准确率 (Joint Accuracy): {avg_joint_accuracy * 100:.2f}%")
        summary_lines.append(f"平均精确率 (Precision): {avg_precision * 100:.2f}%")
        summary_lines.append(f"平均召回率 (Recall): {avg_recall * 100:.2f}%")
        summary_lines.append(f"平均F1分数 (F1 Score): {avg_f1 * 100:.2f}%")
        summary_lines.append("")
        
        # 输出意图评测报告
        summary_lines.append("\n" + "=" * 70)
        summary_lines.append("🎯 对话级别意图评测报告")
        summary_lines.append("=" * 70)
        summary_lines.append("")
        intent_report = test.intent_evaluator.get_detailed_report(
            save_confusion_plot=True,
            plot_path="fnctod_intent_confusion_matrix.png",
            include_confusion_matrix=False
        )
        summary_lines.append(intent_report)
        summary_lines.append("")
        
        # 输出到终端和日志
        summary_text = "\n".join(summary_lines)
        print(summary_text)
        
        for line in summary_lines:
            if line:
                logger.info(line)
        
        # 保存结果到文件
        output_dir = Path("benchmark_results")
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics_file = output_dir / f"fnctod_transfertod_metrics_{timestamp}.txt"
        
        with open(metrics_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("FnCTOD TransferTOD 评测结果\n")
            f.write("=" * 70 + "\n")
            f.write(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"领域: {args.domain if args.domain else '所有领域'}\n")
            f.write(f"数据类型: {args.data_type}\n")
            f.write(f"测试数量: {len(all_metrics)}\n")
            f.write(f"数据路径: {args.data_root}\n")
            f.write("\n")
            f.write(summary_text)
            
            # 写入详细的每个对话的指标
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("详细对话指标\n")
            f.write("=" * 70 + "\n\n")
            for m in all_metrics:
                try:
                    dialogue_id = m.get('dialogue_id', 'Unknown')
                    slot_acc = m.get('slot_accuracy', 0) or 0
                    joint_acc = m.get('joint_accuracy', 0) or 0
                    precision = m.get('precision', 0) or 0
                    recall = m.get('recall', 0) or 0
                    f1 = m.get('f1', 0) or 0
                    
                    f.write(f"对话ID: {dialogue_id}\n")
                    f.write(f"  槽位准确率: {slot_acc * 100:.2f}%\n")
                    f.write(f"  联合准确率: {joint_acc * 100:.2f}%\n")
                    f.write(f"  精确率: {precision * 100:.2f}%\n")
                    f.write(f"  召回率: {recall * 100:.2f}%\n")
                    f.write(f"  F1分数: {f1 * 100:.2f}%\n")
                except Exception as e:
                    logger.error(f"写入指标时出错: {e}, 指标数据: {m}")
                    continue
                f.write("\n")
        
        print(f"\n✅ 评测结果已保存到: {metrics_file}")
        logger.info(f"评测结果已保存到: {metrics_file}")
    else:
        print(f"\n⚠️  警告: 没有收集到任何评测指标")
        print(f"可能的原因:")
        print(f"  1. 所有对话处理都失败了")
        print(f"  2. FnCTOD tracker初始化失败")
        print(f"  3. 数据格式不兼容")
        print(f"\n请使用 --verbose 参数查看详细日志")


if __name__ == "__main__":
    try:
        main()
        print("\n" + "=" * 80)
        print("✅ 脚本执行完成 - Version 2024-02-10-v2")
        print("=" * 80)
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ 执行失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        print("\n💡 提示: 这是新版本的脚本 (2024-02-10-v2)")
        print("如果你看到这个错误，说明脚本正确加载但执行时遇到问题")
        sys.exit(1)
