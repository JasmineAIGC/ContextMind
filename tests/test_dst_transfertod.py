#!/usr/bin/env python3
"""
DST模式 - TransferTOD数据集测试脚本

⚠️ 废弃通知 (DEPRECATED)
==========================================
此文件已被废弃，请使用统一的评测脚本：
  benchmark/run_dst_transfertod.py

使用方式:
    python benchmark/run_dst_transfertod.py
    python benchmark/run_dst_transfertod.py --domain 酒店 --data-type clean --limit 10

此文件将在未来版本中移除。
==========================================

使用TransferTOD数据集测试DialogueStateTracker的槽位提取能力。

原使用方式（已废弃）:
    python tests/test_dst_transfertod.py
    python tests/test_dst_transfertod.py --domain 酒店 --data-type clean --limit 10
"""

import sys
import warnings

# 显示废弃警告
warnings.warn(
    "tests/test_dst_transfertod.py 已被废弃，请使用 benchmark/run_dst_transfertod.py",
    DeprecationWarning,
    stacklevel=2
)

print("=" * 70)
print("⚠️  废弃通知")
print("=" * 70)
print()
print("此脚本 (tests/test_dst_transfertod.py) 已被废弃。")
print("请使用统一的评测脚本: benchmark/run_dst_transfertod.py")
print()
print("使用方式:")
print("  python benchmark/run_dst_transfertod.py")
print("  python benchmark/run_dst_transfertod.py --domain 酒店 --limit 10")
print()
print("=" * 70)
print()

# 导入并运行 benchmark 版本
try:
    import subprocess
    import sys
    
    # 传递所有参数到 benchmark 版本
    benchmark_script = "benchmark/run_dst_transfertod.py"
    args = sys.argv[1:]  # 获取除脚本名外的所有参数
    
    print(f"正在重定向到: {benchmark_script}")
    print()
    
    # 调用 benchmark 版本
    result = subprocess.run([sys.executable, benchmark_script] + args)
    sys.exit(result.returncode)
    
except Exception as e:
    print(f"错误: 无法运行 {benchmark_script}")
    print(f"详情: {e}")
    print()
    print("请直接运行: python benchmark/run_dst_transfertod.py")
    sys.exit(1)

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.adapters import TransferTODAdapter
from tests.intent_evaluator import IntentEvaluator
from contextmind.modes.dst import DialogueStateTracker, PromptManager
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class DSTTransferTODTest:
    """
    DST模式 - TransferTOD测试类
    """
    
    def __init__(self, data_root: str = "./data/TransferTOD"):
        """
        初始化测试
        
        Args:
            data_root: TransferTOD数据集根目录
        """
        self.adapter = TransferTODAdapter(data_root)
        self.llm_client = None
        self.tracker = None
        self.intent_evaluator = IntentEvaluator()  # 意图评测器
        
    def initialize(self, domain: str):
        """
        初始化DST追踪器
        
        Args:
            domain: 领域名称
        """
        # 创建LLM客户端
        try:
            self.llm_client = SimpleLLMClient()
            logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM客户端初始化失败: {e}")
            raise
        
        # 获取领域schema（可选：用于指导LLM，但在动态模式下非必需）
        schema = self.adapter.get_domain_schema(domain)
        
        # 创建PromptManager（启用动态槽位）
        # 动态槽位模式：LLM可以自由提取任何相关信息，不限于预定义槽位
        pm = PromptManager(
            domain=domain,
            enable_dynamic_slots=True
        )
        
        # 可选：添加槽位定义作为指导（在动态模式下，即使未预定义的槽位也会被接受）
        for slot_name, slot_info in schema["slots"].items():
            pm.add_slot(slot_name, slot_info.get("description", slot_name))
        
        # 创建DialogueStateTracker
        # 注意：enable_dynamic_slots=True 会自动禁用槽位过滤，接受所有LLM提取的槽位
        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=10,
            enable_history_summary=True,
            use_llm_summary=False
        )
        
        logger.info(f"✅ DST模式初始化完成 - 领域: {domain}")
        logger.info(f"   动态槽位模式: 启用（接受所有LLM提取的槽位）")
        logger.info(f"   预定义槽位数: {len(schema['slots'])}")
    
    async def test_dialogue(self, dialogue_id: str, verbose: bool = True) -> Dict[str, Any]:
        """
        测试单个对话
        
        Args:
            dialogue_id: 对话ID
            verbose: 是否输出详细信息
            
        Returns:
            测试指标
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
        perfect_turns = 0
        
        all_expected = []
        all_extracted = []
        
        # 维护累积的期望状态（用于正确比较）
        cumulative_expected_state = {}
        
        # 初始化最终提取状态（防止空对话情况）
        final_extracted_state = {}
        
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
                    
                    if verbose:
                        # 推断意图用于显示（正确解包tuple）
                        inferred_result = self.intent_evaluator.infer_intent_from_slots(
                            domain=dialogue.domain,  # 添加领域参数
                            turn_updates=turn.expected_slots,
                            previous_state=previous_state,
                            user_utterance=turn.user_utterance,
                            turn_id=turn.turn_id
                        )
                        # infer_intent_from_slots 返回 (intent, task_relevance) 元组
                        if isinstance(inferred_result, tuple):
                            inferred_intent, task_relevance = inferred_result
                        else:
                            inferred_intent = inferred_result
                        print(f"预测意图: {predicted_intent}, 推断意图: {inferred_intent}")
                
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
            
            if turn_total == 0 or turn_matched == turn_total:
                perfect_turns += 1
            
            all_expected.append(expected)
            all_extracted.append(extracted_state)
            
            # 保存最终提取状态
            final_extracted_state = extracted_state
            
            if verbose:
                print(f"期望状态: {expected}")
                print(f"提取状态: {extracted_state}")
                print(f"匹配数: {turn_matched}/{turn_total}")
        
        # 计算最终提取状态（在使用前定义）
        # 使用tracker的current_state作为最终状态（更可靠）
        final_extracted = self.tracker.current_state if hasattr(self, 'tracker') else final_extracted_state
        
        # 对话级别意图评测（在所有轮次处理完成后）
        # 提取对话级别的预测意图：使用出现频率最高的意图（排除'未识别'）
        dialogue_predicted_intent = '未识别'
        if all_predicted_intents:
            # 统计意图出现频率
            from collections import Counter
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
        
        if verbose:
            print(f"\n--- 对话级别意图 ---")
            print(f"对话预测意图: {dialogue_predicted_intent}")
        
        # 计算评估指标（对齐TransferTOD论文）
        slot_accuracy = matched_slots / total_slots if total_slots > 0 else 0.0
        
        # Joint Accuracy（对话级别，使用最终状态）- 对齐TransferTOD论文
        # 比较最终的累积状态是否完全匹配
        final_expected = cumulative_expected_state
        # final_extracted 已经在上面定义
        
        # DEBUG: 添加调试输出
        if verbose:
            print(f"\n--- 最终状态比较（Joint Accuracy）---")
            print(f"最终期望状态: {final_expected}")
            print(f"最终提取状态: {final_extracted}")
        
        # 计算两种Joint Accuracy
        joint_accuracy_strict = self._calculate_joint_accuracy(final_expected, final_extracted, mode='strict')
        joint_accuracy_soft = self._calculate_joint_accuracy(final_expected, final_extracted, mode='soft')
        
        # 计算Precision/Recall/F1（基于slot-value pairs）- 对齐TransferTOD论文
        precision, recall, f1 = self._calculate_prf_pairs(final_expected, final_extracted)
        
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
        
        if verbose:
            print("\n--- 测试结果（对齐TransferTOD论文指标）---")
            print(f"槽位准确率 (Slot Accuracy): {slot_accuracy * 100:.2f}%")
            print(f"联合准确率-严格 (Joint Accuracy Strict): {joint_accuracy_strict * 100:.2f}%")
            print(f"联合准确率-软匹配 (Joint Accuracy Soft): {joint_accuracy_soft * 100:.2f}%")
            print(f"精确率 (Precision): {precision * 100:.2f}%")
            print(f"召回率 (Recall): {recall * 100:.2f}%")
            print(f"F1分数 (F1 Score): {f1 * 100:.2f}%")
        
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
    
    def _calculate_prf(self, expected_list: List[Dict], extracted_list: List[Dict]) -> Tuple[float, float, float]:
        """
        计算Precision、Recall和F1 Score
        
        Args:
            expected_list: 期望槽位列表
            extracted_list: 提取槽位列表
            
        Returns:
            (precision, recall, f1)
        """
        true_positive = 0
        false_positive = 0
        false_negative = 0
        
        for expected, extracted in zip(expected_list, extracted_list):
            for slot, value in expected.items():
                # 转换为字符串进行比较
                expected_value_str = str(value) if value is not None else None
                extracted_value_str = str(extracted.get(slot)) if extracted.get(slot) is not None else None
                
                if slot in extracted and expected_value_str == extracted_value_str:
                    true_positive += 1
                else:
                    false_negative += 1
            
            for slot, value in extracted.items():
                # 转换为字符串进行比较
                expected_value_str = str(expected.get(slot)) if expected.get(slot) is not None else None
                extracted_value_str = str(value) if value is not None else None
                
                if slot not in expected or expected_value_str != extracted_value_str:
                    false_positive += 1
        
        precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) > 0 else 0.0
        recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return precision, recall, f1


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="DST模式 - TransferTOD数据集测试")
    parser.add_argument("--domain", type=str, default=None, help="测试领域（不指定则测试所有领域）")
    parser.add_argument("--data-type", type=str, default=None, choices=["clean", "noise", None], help="数据类型（不指定则测试所有类型）")
    parser.add_argument("--limit", type=int, default=None, help="限制测试数量")
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD", help="数据集根目录")
    parser.add_argument("--verbose", action="store_true", help="输出详细信息")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(LogLevel.INFO)
    
    # 显示测试范围
    domain_desc = args.domain if args.domain else "所有领域"
    data_type_desc = args.data_type if args.data_type else "所有类型"
    
    print("=" * 70)
    print(f"DST 模式测试 - TransferTOD 数据集")
    print(f"领域: {domain_desc}, 数据类型: {data_type_desc}")
    print("=" * 70)
    
    # 初始化测试
    test = DSTTransferTODTest(data_root=args.data_root)
    
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
        test.initialize(args.domain)
    
    # 批量测试
    all_metrics = []
    domain_metrics = defaultdict(list)  # 按领域分组的指标
    current_domain = None
    
    for dialogue_id in dialogue_ids:
        try:
            # 如果没有指定domain，需要为每个对话的domain初始化tracker
            if not args.domain:
                dialogue = test.adapter.load_dialogue(dialogue_id)
                if dialogue.domain != current_domain:
                    current_domain = dialogue.domain
                    print(f"\n初始化领域: {current_domain}")
                    test.initialize(current_domain)
            else:
                current_domain = args.domain
            
            metrics = await test.test_dialogue(dialogue_id, verbose=args.verbose)
            all_metrics.append(metrics)
            domain_metrics[current_domain].append(metrics)
        except Exception as e:
            logger.error(f"测试对话 {dialogue_id} 失败: {e}")
            continue
    
    # 输出汇总指标（对齐TransferTOD论文）
    if all_metrics:
        print("\n" + "=" * 70)
        print("📊 测试指标汇总（对齐TransferTOD论文）")
        print("=" * 70)
        
        # 按领域显示指标（即使只有一个领域也显示）
        if domain_metrics:
            print("\n【分领域统计】")
            print("-" * 70)
            for domain, metrics_list in sorted(domain_metrics.items()):
                avg_slot_acc = sum(m["slot_accuracy"] for m in metrics_list) / len(metrics_list)
                avg_ja_strict = sum(m["joint_accuracy"] for m in metrics_list) / len(metrics_list)
                avg_ja_soft = sum(m["joint_accuracy_soft"] for m in metrics_list) / len(metrics_list)
                avg_precision = sum(m["precision"] for m in metrics_list) / len(metrics_list)
                avg_recall = sum(m["recall"] for m in metrics_list) / len(metrics_list)
                avg_f1 = sum(m["f1"] for m in metrics_list) / len(metrics_list)
                
                print(f"\n{domain}领域 (对话数: {len(metrics_list)}):")
                print(f"  槽位准确率: {avg_slot_acc * 100:.2f}%")
                print(f"  联合准确率-严格: {avg_ja_strict * 100:.2f}%")
                print(f"  联合准确率-软匹配: {avg_ja_soft * 100:.2f}%")
                print(f"  精确率: {avg_precision * 100:.2f}%")
                print(f"  召回率: {avg_recall * 100:.2f}%")
                print(f"  F1分数: {avg_f1 * 100:.2f}%")
            print()
        
        # 汇总统计
        avg_slot_accuracy = sum(m["slot_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy = sum(m["joint_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy_soft = sum(m["joint_accuracy_soft"] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        print("\n【整体汇总统计】")
        print("-" * 70)
        print(f"总测试对话数: {len(all_metrics)}")
        print(f"平均槽位准确率 (Slot Accuracy): {avg_slot_accuracy * 100:.2f}%")
        print(f"平均联合准确率-严格 (Joint Accuracy Strict): {avg_joint_accuracy * 100:.2f}%")
        print(f"平均联合准确率-软匹配 (Joint Accuracy Soft): {avg_joint_accuracy_soft * 100:.2f}%")
        print(f"平均精确率 (Precision): {avg_precision * 100:.2f}%")
        print(f"平均召回率 (Recall): {avg_recall * 100:.2f}%")
        print(f"平均F1分数 (F1 Score): {avg_f1 * 100:.2f}%")
        print()
        print("注：指标计算方法已对齐TransferTOD论文")
        print("  - Joint Accuracy Strict: 对话级别（最终状态完全匹配，对齐论文）")
        print("  - Joint Accuracy Soft: 对话级别（所有期望槽位都存在，允许额外槽位）")
        print("  - F1/Precision/Recall: 基于slot-value pairs计算")
        print()
        
        # 输出意图评测报告
        print("\n" + "=" * 70)
        print("🎯 对话级别意图评测报告")
        print("=" * 70)
        print()
        print("说明：")
        print("  - 评测粒度：对话级别（整个多轮对话作为一个评测单元）")
        print("  - 预测意图提取：取对话中出现最频繁的意图（排除'未识别'）")
        print("  - 标签意图推断：基于用户所有话语的关键词匹配推断对话整体意图")
        print("  - TransferTOD数据集无显式意图标注，推断意图仅供参考")
        print()
        print(test.intent_evaluator.get_detailed_report(
            save_confusion_plot=True,
            plot_path="intent_confusion_matrix.png",
            include_confusion_matrix=False  # 不打印混淆矩阵，只保存为图片
        ))
        
        print()
        print("说明：")
        print("  - 对话级别意图评测聚焦于整个对话的意图识别能力")
        print("  - 不对单个轮次的意图做评测，只评测对话整体意图")
        print()


if __name__ == "__main__":
    asyncio.run(main())
