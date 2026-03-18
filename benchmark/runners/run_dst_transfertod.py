#!/usr/bin/env python3
"""
DST模式 - TransferTOD数据集评测脚本

使用TransferTOD数据集测试DialogueStateTracker的槽位提取能力。

使用方式:
    python benchmark/runners/run_dst_transfertod.py
    python benchmark/runners/run_dst_transfertod.py --domain 酒店 --data-type clean --limit 10
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict, Counter

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.transfertod.adapter import TransferTODAdapter
from benchmark.shared.intent_evaluator import IntentEvaluator
from benchmark.shared.intent_label_loader import IntentLabelLoader
from contextmind.modes.dst import DialogueStateTracker, PromptManager
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class TransferTODEvaluator:
    """TransferTOD 数据集上的 DST 评测器。"""

    def __init__(self, data_root: str = "./data/TransferTOD"):
        """
        初始化评测器。

        Args:
            data_root: TransferTOD 数据集根目录
        """
        self.adapter = TransferTODAdapter(data_root)
        self.llm_client = None
        self.tracker = None
        self.intent_evaluator = IntentEvaluator()
        # TransferTOD 使用默认意图标签配置（不指定路径则加载内置配置）
        self.intent_label_loader = IntentLabelLoader()

    def setup_tracker(self, domain: str):
        """
        为指定领域初始化 LLM 客户端和 DST 追踪器。

        Args:
            domain: 领域名称
        """
        # 创建LLM客户端
        try:
            self.llm_client = AdkLLMClient()
            logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM客户端初始化失败: {e}")
            raise

        # 获取领域schema（可选：用于指导LLM，但在动态模式下非必需）
        schema = self.adapter.get_domain_schema(domain)

        # 动态槽位模式：LLM 可自由提取任何相关信息，不限于预定义槽位；
        # 同时注入 intent_label_loader 以启用意图预测。
        pm = PromptManager(
            domain=domain,
            enable_dynamic_slots=True,
            intent_label_loader=self.intent_label_loader,
        )

        # 添加槽位定义作为指导（动态模式下 LLM 也可提取未预定义的槽位）
        for slot_name, slot_info in schema["slots"].items():
            pm.add_slot(slot_name, slot_info.get("description", slot_name))

        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=10,
            enable_history_summary=True,
            use_llm_summary=False,
        )

        logger.info(f"✅ DST追踪器初始化完成 - 领域: {domain}，预定义槽位数: {len(schema['slots'])}")

    async def evaluate_dialogue(self, dialogue_id: str, verbose: bool = True) -> Dict[str, Any]:
        """
        对单个对话进行 DST 评测。

        Args:
            dialogue_id: 对话ID
            verbose: 是否输出逐轮详细信息

        Returns:
            评测指标字典
        """
        # 加载对话
        dialogue = self.adapter.load_dialogue(dialogue_id)
        
        if verbose:
            print("\n" + "=" * 60)
            print(f"测试对话: {dialogue_id}")
            print(f"领域: {dialogue.domain}")
            print(f"描述: {dialogue.description}")
            print("=" * 60)
        
        # 重置追踪器状态
        self.tracker.current_state = {}
        self.tracker.dialogue_history = []
        
        # 评估指标
        total_slots = 0
        matched_slots = 0
        total_turns = 0
        
        all_expected = []
        all_extracted = []
        
        # 维护累积的期望状态（用于正确比较）
        cumulative_expected_state = {}
        
        # 上一轮状态（用于意图推断）
        previous_state = {}
        
        # 收集对话级别意图评测所需数据
        all_user_utterances = []
        all_predicted_intents = []
        
        # 逐轮测试
        for turn in dialogue.turns:
            if verbose:
                print(f"\n--- 轮次 {turn.turn_id} ---")
                print(f"系统: {turn.system_utterance[:80]}...")
                print(f"用户: {turn.user_utterance[:80]}...")
            
            # 调用DST
            try:
                extracted_state = await self.tracker.process_turn(
                    system_utterance=turn.system_utterance,
                    user_utterance=turn.user_utterance
                )
                
                # 收集用户话语用于对话级别意图推断
                all_user_utterances.append(turn.user_utterance)
                
                # 获取本轮的turn_updates（包含预测的意图）
                if self.tracker.dialogue_history:
                    last_turn = self.tracker.dialogue_history[-1]
                    turn_updates = last_turn.turn_updates
                    predicted_intent = turn_updates.get('intent', '未识别')
                    all_predicted_intents.append(predicted_intent)
                
            except Exception as e:
                logger.error(f"处理轮次 {turn.turn_id} 时出错: {e}")
                extracted_state = {}
            
            # 更新上一轮状态（用于下一轮的意图推断）
            previous_state = cumulative_expected_state.copy()
            
            # 更新累积的期望状态（合并本轮的变化）
            cumulative_expected_state.update(turn.expected_slots)
            
            # 比较累积的期望状态和提取状态
            expected = cumulative_expected_state.copy()
            
            # 计算本轮的匹配度
            turn_total = len(expected)
            turn_matched = 0
            
            for slot, expected_value in expected.items():
                extracted_value = extracted_state.get(slot)
                # 转换为字符串进行比较（因为expected可能是原始类型）
                expected_value_str = str(expected_value) if expected_value is not None else None
                extracted_value_str = str(extracted_value) if extracted_value is not None else None
                if expected_value_str == extracted_value_str:
                    turn_matched += 1
            
            total_slots += turn_total
            matched_slots += turn_matched
            total_turns += 1
            
            all_expected.append(expected)
            all_extracted.append(extracted_state)
            
            if verbose:
                print(f"期望状态: {expected}")
                print(f"提取状态: {extracted_state}")
                print(f"匹配数: {turn_matched}/{turn_total}")
        
        # 使用tracker的current_state作为最终状态
        final_extracted = self.tracker.current_state
        
        # 对话级别意图评测（在所有轮次处理完成后）
        # 提取对话级别的预测意图：使用出现频率最高的意图（排除'未识别'）
        dialogue_predicted_intent = '未识别'
        if all_predicted_intents:
            # 统计意图出现频率
            intent_counter = Counter([intent for intent in all_predicted_intents if intent != '未识别'])
            if intent_counter:
                # 取最常见的意图
                dialogue_predicted_intent = intent_counter.most_common(1)[0][0]
            elif all_predicted_intents:
                # 如果全部都是'未识别'，则使用第一个非'未识别'的，否则使用'未识别'
                dialogue_predicted_intent = all_predicted_intents[0]
        
        # 添加对话级别意图评测
        self.intent_evaluator.add_dialogue_evaluation(
            dialogue_id=dialogue_id,
            domain=dialogue.domain,
            predicted_intent=dialogue_predicted_intent,
            dialogue_slots=final_extracted,  # 使用最终提取的槽位
            user_utterances=all_user_utterances
        )
        
        # 计算评估指标（对齐TransferTOD论文）
        slot_accuracy = matched_slots / total_slots if total_slots > 0 else 0.0
        
        # Joint Accuracy（对话级别，使用最终状态）- 对齐TransferTOD论文
        # 比较最终的累积状态是否完全匹配
        final_expected = cumulative_expected_state
        # final_extracted 已经在上面定义
        
        # 计算两种Joint Accuracy
        joint_accuracy_strict = self._calculate_joint_accuracy(final_expected, final_extracted, mode='strict')
        joint_accuracy_soft = self._calculate_joint_accuracy(final_expected, final_extracted, mode='soft')
        
        # 计算Precision/Recall/F1（基于slot-value pairs）- 对齐TransferTOD论文
        precision, recall, f1 = self._calculate_prf_pairs(final_expected, final_extracted)
        
        # 需求1: 调整输出顺序 - 先输出槽位结果，再输出意图结果
        if verbose:
            print("\n" + "=" * 70)
            print("📊 对话评测结果")
            print("=" * 70)
            
            # 1. 先输出槽位值结果
            print("\n【槽位评测结果】")
            print(f"槽位准确率 (Slot Accuracy): {slot_accuracy * 100:.2f}%")
            print(f"联合准确率-严格 (Joint Accuracy Strict): {joint_accuracy_strict * 100:.2f}%")
            print(f"联合准确率-软匹配 (Joint Accuracy Soft): {joint_accuracy_soft * 100:.2f}%")
            print(f"精确率 (Precision): {precision * 100:.2f}%")
            print(f"召回率 (Recall): {recall * 100:.2f}%")
            print(f"F1分数 (F1 Score): {f1 * 100:.2f}%")
            print(f"\n最终期望状态: {final_expected}")
            print(f"最终提取状态: {final_extracted}")
            
            # 2. 再输出意图结果（包含真值意图）
            # 先获取真值意图（从intent_evaluator推断）
            inferred_intent, _ = self.intent_evaluator.infer_intent_from_slots(
                domain=dialogue.domain,
                turn_updates={},  # 不需要槽位更新
                previous_state={},
                user_utterance=' '.join(all_user_utterances)  # 使用所有用户话语
            )
            
            print("\n【意图评测结果】")
            print(f"预测意图: {dialogue_predicted_intent}")
            print(f"真值意图: {inferred_intent}")
            
            # 使用标准化映射进行比较
            norm_predicted = self.intent_evaluator.normalization_mapping.get(
                dialogue_predicted_intent.lower(), dialogue_predicted_intent.lower()
            )
            norm_inferred = self.intent_evaluator.normalization_mapping.get(
                inferred_intent.lower(), inferred_intent.lower()
            )
            is_correct = norm_predicted == norm_inferred
            result = "✓ 正确" if is_correct else "✗ 错误"
            print(f"评测结果: {result}")
            print("=" * 70)
            print()  # 添加空行分隔不同对话

        
        metrics = {
            "dialogue_id": dialogue_id,
            "slot_accuracy": slot_accuracy,
            "joint_accuracy": joint_accuracy_strict,  # TransferTOD论文指标：对话级别（严格）
            "joint_accuracy_soft": joint_accuracy_soft,  # 软匹配：允许额外槽位
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total_slots": total_slots,
            "matched_slots": matched_slots,
            "total_turns": total_turns,
        }
        
        return metrics
    
    def _calculate_joint_accuracy(self, expected: Dict, extracted: Dict, mode: str = 'strict') -> float:
        """
        计算Joint Accuracy（对话级别）- 支持strict和soft两种模式
        
        Args:
            expected: 期望的最终状态
            extracted: 提取的最终状态
            mode: 'strict' (完全匹配) 或 'soft' (期望槽位都存在即可)
            
        Returns:
            1.0 if匹配, 0.0 otherwise
        """
        # 转换为slot-value pairs的集合进行比较（对齐TransferTOD论文）
        # 注：TransferTOD适配器已确保不含None值，此处不需要额外过滤
        expected_pairs = set([(k, str(v)) for k, v in expected.items()])
        extracted_pairs = set([(k, str(v)) for k, v in extracted.items()])
        
        # DEBUG: Log mismatch details
        if expected_pairs != extracted_pairs:
            logger.debug(f"JA Mismatch - Expected: {expected_pairs}, Extracted: {extracted_pairs}")
            logger.debug(f"  Missing: {expected_pairs - extracted_pairs}")
            logger.debug(f"  Extra: {extracted_pairs - expected_pairs}")
        
        # 根据模式计算
        if mode == 'strict':
            # Strict模式: 完全匹配（对齐TransferTOD论文）
            return 1.0 if expected_pairs == extracted_pairs else 0.0
        elif mode == 'soft':
            # Soft模式: 所有期望的槽位都被正确提取（允许额外槽位）
            # 适用于模型可能过度预测的情况
            return 1.0 if expected_pairs.issubset(extracted_pairs) else 0.0
        else:
            raise ValueError(f"Unknown mode: {mode}. Use 'strict' or 'soft'")
    
    def _calculate_prf_pairs(self, expected: Dict, extracted: Dict) -> Tuple[float, float, float]:
        """
        计算Precision、Recall和F1 Score（基于slot-value pairs）- 对齐TransferTOD论文
        
        与TransferTOD论文的eval.py一致，使用slot-value pairs作为比较单元
        
        Args:
            expected: 期望的最终状态
            extracted: 提取的最终状态
            
        Returns:
            (precision, recall, f1)
        """
        # 转换为slot-value pairs的集合（对齐TransferTOD论文的实现）
        # 注：TransferTOD适配器已确保不含None值，此处不需要额外过滤
        expected_pairs = set([(k, str(v)) for k, v in expected.items()])
        extracted_pairs = set([(k, str(v)) for k, v in extracted.items()])
        
        # 计算TP, FP, FN（对齐TransferTOD论文的f1_calculator）
        TP = len(expected_pairs & extracted_pairs)  # 交集
        FP = len(extracted_pairs - expected_pairs)  # 预测但不在真实中
        FN = len(expected_pairs - extracted_pairs)  # 真实但未预测
        
        # 特殊情况处理（对齐TransferTOD论文）
        if len(expected_pairs) == 0:
            if len(extracted_pairs) == 0:
                return 1.0, 1.0, 1.0
            else:
                return 0.0, 0.0, 0.0
        
        precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
        recall = TP / (TP + FN) if (TP + FN) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return precision, recall, f1
    

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="DST模式 - TransferTOD数据集测试")
    parser.add_argument("--domain", type=str, default=None, help="测试领域（不指定则测试所有领域）")
    parser.add_argument("--data-type", type=str, default=None, choices=["clean", "noise", None], help="数据类型（不指定则测试所有类型）")
    parser.add_argument("--limit", type=int, default=None, help="限制测试数量")
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD", help="数据集根目录")
    parser.add_argument("--no-verbose", action="store_false", dest="verbose", default=True, help="禁用详细信息输出（默认启用）")
    
    args = parser.parse_args()
    
    # 问题2修复：根据 verbose 参数调整日志级别
    if not args.verbose:
        # 在 no-verbose 模式下，只显示 WARNING 及以上级别的日志
        # 这样可以抑制 INFO 日志，但保留重要的警告和错误
        import logging
        logging.getLogger().setLevel(logging.WARNING)
        # 同时抑制第三方库的详细日志
        logging.getLogger('contextmind').setLevel(logging.WARNING)
        setup_logging(LogLevel.WARNING)
    else:
        # 设置日志
        setup_logging(LogLevel.INFO)
    
    # 显示测试范围
    domain_desc = args.domain if args.domain else "所有领域"
    data_type_desc = args.data_type if args.data_type else "所有类型"
    
    print("=" * 70)
    print(f"DST 模式测试 - TransferTOD 数据集")
    print(f"领域: {domain_desc}, 数据类型: {data_type_desc}")
    print("=" * 70)
    
    # 初始化评测器
    test = TransferTODEvaluator(data_root=args.data_root)
    
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
    
    print(f"\n找到 {len(dialogue_ids)} 个对话实例")
    
    # 限制测试数量
    if args.limit:
        dialogue_ids = dialogue_ids[:args.limit]
        print(f"限制测试数量: {args.limit}")
    
    # 如果指定了domain，初始化DST for that domain
    # 如果没有指定domain，需要按对话的domain分组处理
    if args.domain:
        test.setup_tracker(args.domain)
    
    # 批量测试
    all_metrics = []
    domain_metrics = defaultdict(list)  # 按领域分组的指标
    current_domain = None
    
    # 创建新的事件循环（避免 DeprecationWarning）
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        for dialogue_id in dialogue_ids:
            try:
                # 如果没有指定domain，需要为每个对话的domain初始化tracker
                if not args.domain:
                    dialogue = test.adapter.load_dialogue(dialogue_id)
                    if dialogue.domain != current_domain:
                        current_domain = dialogue.domain
                        print(f"\n初始化领域: {current_domain}")
                        test.setup_tracker(current_domain)
                else:
                    current_domain = args.domain
                
                # 使用事件循环运行async函数
                metrics = loop.run_until_complete(test.evaluate_dialogue(dialogue_id, verbose=args.verbose))
                all_metrics.append(metrics)
                domain_metrics[current_domain].append(metrics)
            except Exception as e:
                logger.error(f"测试对话 {dialogue_id} 失败: {e}")
                continue
    finally:
        # 确保事件循环在使用后正确关闭
        if not loop.is_closed():
            loop.close()
    
    # 问题3修复：输出汇总指标（对齐TransferTOD论文）
    # 同时输出到终端和日志文件
    if all_metrics:
        summary_lines = []
        summary_lines.append("\n" + "=" * 70)
        summary_lines.append("📊 测试指标汇总（对齐TransferTOD论文）")
        summary_lines.append("=" * 70)
        
        # 按领域显示指标（即使只有一个领域也显示）
        if domain_metrics:
            summary_lines.append("\n【分领域统计】")
            summary_lines.append("-" * 70)
            for domain, metrics_list in sorted(domain_metrics.items()):
                avg_slot_acc = sum(m["slot_accuracy"] for m in metrics_list) / len(metrics_list)
                avg_ja_strict = sum(m["joint_accuracy"] for m in metrics_list) / len(metrics_list)
                avg_ja_soft = sum(m["joint_accuracy_soft"] for m in metrics_list) / len(metrics_list)
                avg_precision = sum(m["precision"] for m in metrics_list) / len(metrics_list)
                avg_recall = sum(m["recall"] for m in metrics_list) / len(metrics_list)
                avg_f1 = sum(m["f1"] for m in metrics_list) / len(metrics_list)
                
                summary_lines.append(f"\n{domain}领域 (对话数: {len(metrics_list)}):")
                summary_lines.append(f"  槽位准确率: {avg_slot_acc * 100:.2f}%")
                summary_lines.append(f"  联合准确率-严格: {avg_ja_strict * 100:.2f}%")
                summary_lines.append(f"  联合准确率-软匹配: {avg_ja_soft * 100:.2f}%")
                summary_lines.append(f"  精确率: {avg_precision * 100:.2f}%")
                summary_lines.append(f"  召回率: {avg_recall * 100:.2f}%")
                summary_lines.append(f"  F1分数: {avg_f1 * 100:.2f}%")
            summary_lines.append("")
        
        # 汇总统计
        avg_slot_accuracy = sum(m["slot_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy = sum(m["joint_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy_soft = sum(m["joint_accuracy_soft"] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        summary_lines.append("\n【整体汇总统计】")
        summary_lines.append("-" * 70)
        summary_lines.append(f"总测试对话数: {len(all_metrics)}")
        summary_lines.append(f"平均槽位准确率 (Slot Accuracy): {avg_slot_accuracy * 100:.2f}%")
        summary_lines.append(f"平均联合准确率-严格 (Joint Accuracy Strict): {avg_joint_accuracy * 100:.2f}%")
        summary_lines.append(f"平均联合准确率-软匹配 (Joint Accuracy Soft): {avg_joint_accuracy_soft * 100:.2f}%")
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
            plot_path="intent_confusion_matrix.png",
            include_confusion_matrix=False  # 不打印混淆矩阵，只保存为图片
        )
        summary_lines.append(intent_report)
        summary_lines.append("")
        
        # 输出指标汇总（使用 print）
        summary_text = "\n".join(summary_lines)
        print(summary_text)
        
        # 问题5修复：将指标结果保存到文件
        output_dir = Path("benchmark_results")
        output_dir.mkdir(exist_ok=True)
        
        # 生成带时间戳的文件名
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics_file = output_dir / f"dst_transfertod_metrics_{timestamp}.txt"
        
        # 保存详细的评测结果
        with open(metrics_file, 'w', encoding='utf-8') as f:
            # 写入命令和参数
            f.write("=" * 70 + "\n")
            f.write("DST TransferTOD 评测结果\n")
            f.write("=" * 70 + "\n")
            f.write(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"领域: {args.domain if args.domain else '所有领域'}\n")
            f.write(f"数据类型: {args.data_type if args.data_type else '所有类型'}\n")
            f.write(f"测试数量: {len(all_metrics)}\n")
            f.write(f"数据路径: {args.data_root}\n")
            f.write("\n")
            
            # 写入汇总结果
            f.write(summary_text)
            
            # 写入详细的每个对话的指标
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("详细对话指标\n")
            f.write("=" * 70 + "\n\n")
            for m in all_metrics:
                try:
                    # 安全地获取和格式化指标值，避免KeyError和TypeError
                    dialogue_id = m.get('dialogue_id', 'Unknown')
                    slot_acc = m.get('slot_accuracy', 0) or 0
                    joint_acc = m.get('joint_accuracy', 0) or 0
                    joint_acc_soft = m.get('joint_accuracy_soft', 0) or 0
                    precision = m.get('precision', 0) or 0
                    recall = m.get('recall', 0) or 0
                    f1 = m.get('f1', 0) or 0
                    
                    f.write(f"对话ID: {dialogue_id}\n")
                    f.write(f"  槽位准确率: {slot_acc * 100:.2f}%\n")
                    f.write(f"  联合准确率(严格): {joint_acc * 100:.2f}%\n")
                    f.write(f"  联合准确率(软匹配): {joint_acc_soft * 100:.2f}%\n")
                    f.write(f"  精确率: {precision * 100:.2f}%\n")
                    f.write(f"  召回率: {recall * 100:.2f}%\n")
                    f.write(f"  F1分数: {f1 * 100:.2f}%\n")
                except Exception as e:
                    logger.error(f"写入指标时出错: {e}, 指标数据: {m}")
                    continue
                f.write("\n")
        
        print(f"\n✅ 评测结果已保存到: {metrics_file}")
        logger.info(f"评测结果已保存到: {metrics_file}")


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)  # 成功退出
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
        sys.exit(130)  # 标准的中断退出码
    except Exception as e:
        print(f"\n\n❌ 执行失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)  # 错误退出
