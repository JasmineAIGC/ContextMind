#!/usr/bin/env python3
"""
DST模式 - RiSAWOZ数据集评测脚本

使用RiSAWOZ数据集测试DialogueStateTracker的槽位提取能力。
参考DST模式在TransferTOD的实现，但使用RiSAWOZ一致的评测指标。

使用方式:
    python benchmark/run_dst_risawoz.py
    python benchmark/run_dst_risawoz.py --domain 景点 --split val --limit 10
"""

import asyncio
import argparse
import datetime
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict, Counter

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter
from benchmark.shared.intent_evaluator import IntentEvaluator
from benchmark.shared.intent_label_loader import IntentLabelLoader
from contextmind.modes.dst import DialogueStateTracker, PromptManager
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class DSTRiSAWOZTest:
    """
    DST模式 - RiSAWOZ测试类
    """
    
    def __init__(self, data_root: str = "./data/RiSAWOZ", file_mapping: Dict[str, str] = None):
        """
        初始化测试
        
        Args:
            data_root: RiSAWOZ数据集根目录
            file_mapping: 自定义文件名映射 (可选)
        """
        self.adapter = RiSAWOZAdapter(data_root, file_mapping=file_mapping)
        self.llm_client = None
        self.tracker = None
        
        # 使用RiSAWOZ专用的意图标签配置
        risawoz_intent_config = Path(__file__).parent / "shared" / "configs" / "intent_labels_risawoz.json"
        self.intent_label_loader = IntentLabelLoader(str(risawoz_intent_config))
        self.intent_evaluator = IntentEvaluator(intent_label_loader=self.intent_label_loader)  # 意图评测器
        
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
        
        # 获取领域schema
        schema = self.adapter.get_domain_schema(domain)
        
        # 创建PromptManager（启用动态槽位，使用RiSAWOZ意图配置）
        pm = PromptManager(
            domain=domain,
            enable_dynamic_slots=True,
            intent_label_loader=self.intent_label_loader
        )
        
        # 可选：添加槽位定义作为指导
        for slot_name, slot_info in schema.get("slots", {}).items():
            pm.add_slot(slot_name, slot_info.get("description", slot_name))
        
        # 创建DialogueStateTracker
        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=10,
            enable_history_summary=True,
            use_llm_summary=False
        )
        
        logger.info(f"✅ DST模式初始化完成 - 领域: {domain}")
        logger.info(f"   动态槽位模式: 启用")
    
    def _extract_dialogue_intent(self, dialogue: 'DialogueInstance') -> str:
        """
        从对话的user_acts中提取对话级别的意图
        
        策略：
        1. 优先选择最后一个有实际槽位的Inform意图
        2. 其次选择Request意图
        3. 再选择其他非General/Greeting的意图
        4. 最后使用Greeting或General
        
        Args:
            dialogue: 对话实例
            
        Returns:
            提取的对话意图，如果没有找到返回空字符串
        """
        # 收集所有意图，按优先级分类
        inform_intents = []
        request_intents = []
        other_intents = []
        general_intents = []
        
        for turn in dialogue.turns:
            for intent_info in turn.user_intents:
                if len(intent_info) >= 2:
                    intent = intent_info[0]  # [intent, domain, slot, value]
                    
                    if not intent:  # 跳过空意图
                        continue
                    
                    # 分类
                    if intent == "Inform":
                        inform_intents.append(intent)
                    elif intent == "Request":
                        request_intents.append(intent)
                    elif intent in ["General", "Greeting", "Bye"]:
                        general_intents.append(intent)
                    else:
                        other_intents.append(intent)
        
        # 按优先级选择
        if inform_intents:
            return inform_intents[-1]  # 最后一个Inform
        elif request_intents:
            return request_intents[-1]  # 最后一个Request
        elif other_intents:
            return other_intents[-1]  # 最后一个其他意图
        elif general_intents:
            return general_intents[-1]  # 最后一个通用意图
        else:
            return ""  # 没有找到任何意图
    
    async def test_dialogue(self, dialogue_id: str, split: str = "val", verbose: bool = True) -> Dict[str, Any]:
        """
        测试单个对话
        
        Args:
            dialogue_id: 对话ID
            split: 数据集划分
            verbose: 是否输出详细信息
            
        Returns:
            测试指标
        """
        # 加载对话
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
        
        if verbose:
            print("\n" + "=" * 60)
            print(f"测试对话: {dialogue_id}")
            print(f"领域: {dialogue.domain}")
            print(f"轮次数: {len(dialogue.turns)}")
            print("=" * 60)
        
        # 重置追踪器状态
        self.tracker.current_state = {}
        self.tracker.dialogue_history = []
        
        # RiSAWOZ评测指标（与官方指标一致）
        total_slots = 0
        correct_slots = 0
        total_turns = len(dialogue.turns)
        correct_turns_strict = 0  # Joint Accuracy - 严格匹配
        correct_turns_soft = 0    # Joint Accuracy - 软匹配
        
        # 收集所有轮次的预测和真实状态（用于计算turn-level指标）
        all_turn_predictions = []
        all_turn_ground_truths = []
        
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
            except Exception as e:
                logger.error(f"处理轮次 {turn.turn_id} 时出错: {e}")
                extracted_state = {}
            
            # 获取期望状态（RiSAWOZ使用累积的belief state）
            expected_state = turn.expected_slots
            
            # 计算本轮的槽位准确率
            turn_correct_slots = 0
            turn_total_slots = len(expected_state)
            turn_exact_match_strict = True  # 本轮是否完全匹配（严格）
            turn_exact_match_soft = True    # 本轮是否软匹配（允许额外槽位）
            
            # 比较每个槽位
            for slot_key, expected_value in expected_state.items():
                extracted_value = extracted_state.get(slot_key)
                
                # 值比较（转换为字符串）
                expected_str = str(expected_value) if expected_value is not None else ""
                extracted_str = str(extracted_value) if extracted_value is not None else ""
                
                if expected_str == extracted_str:
                    turn_correct_slots += 1
                else:
                    turn_exact_match_strict = False
                    turn_exact_match_soft = False  # 期望槽位不正确，软匹配也失败
            
            # 检查是否有多余的槽位（只影响严格匹配）
            for slot_key in extracted_state:
                if slot_key not in expected_state:
                    turn_exact_match_strict = False  # 有额外槽位，严格匹配失败
                    # 软匹配不受影响
            
            total_slots += turn_total_slots
            correct_slots += turn_correct_slots
            
            if turn_exact_match_strict:
                correct_turns_strict += 1
            if turn_exact_match_soft:
                correct_turns_soft += 1
            
            # 记录本轮的预测和真实状态
            all_turn_predictions.append(extracted_state)
            all_turn_ground_truths.append(expected_state)
            
            if verbose:
                print(f"期望状态: {expected_state}")
                print(f"提取状态: {extracted_state}")
                print(f"槽位匹配: {turn_correct_slots}/{turn_total_slots}")
                print(f"严格匹配: {'是' if turn_exact_match_strict else '否'}")
                print(f"软匹配: {'是' if turn_exact_match_soft else '否'}")
        
        # 计算RiSAWOZ评测指标（对齐TransferTOD）
        # 1. Slot Accuracy (turn-level)
        slot_accuracy = correct_slots / total_slots if total_slots > 0 else 0.0
        
        # 2. 使用最终状态计算dialogue-level指标（对齐TransferTOD）
        final_extracted = self.tracker.current_state
        final_expected = dialogue.final_state
        
        # 3. Joint Accuracy (dialogue-level) - 对齐TransferTOD论文
        # 使用最终状态而非turn-level统计，与TransferTOD保持一致
        joint_accuracy_strict = self._calculate_joint_accuracy(final_expected, final_extracted, domain=dialogue.domain, mode='strict')
        joint_accuracy_soft = self._calculate_joint_accuracy(final_expected, final_extracted, domain=dialogue.domain, mode='soft')
        
        # 计算Precision/Recall/F1（基于slot-value pairs）
        precision, recall, f1 = self._calculate_prf_pairs(final_expected, final_extracted, domain=dialogue.domain)
        
        # 4. 意图评测（使用从user_acts提取的意图）
        # 从对话中提取实际的用户意图
        dialogue_intent = self._extract_dialogue_intent(dialogue)
        
        # 添加到意图评测器 - 使用提取的槽位而非期望槽位
        self.intent_evaluator.add_dialogue_evaluation(
            dialogue_id=dialogue_id,
            domain=dialogue.domain,
            predicted_intent=dialogue_intent,  # 使用从user_acts提取的意图
            dialogue_slots=final_extracted,  # 修复：使用提取的槽位
            user_utterances=[turn.user_utterance for turn in dialogue.turns]
        )
        
        if verbose:
            print("\n" + "=" * 70)
            print("📊 对话评测结果")
            print("=" * 70)
            
            print("\n【槽位评测结果】")
            print(f"槽位准确率 (Slot Accuracy): {slot_accuracy * 100:.2f}%")
            print(f"联合准确率-严格 (Joint Accuracy Strict): {joint_accuracy_strict * 100:.2f}%")
            print(f"联合准确率-软匹配 (Joint Accuracy Soft): {joint_accuracy_soft * 100:.2f}%")
            print(f"精确率 (Precision): {precision * 100:.2f}%")
            print(f"召回率 (Recall): {recall * 100:.2f}%")
            print(f"F1分数 (F1 Score): {f1 * 100:.2f}%")
            
            print(f"\n【最终状态比较】")
            print(f"期望状态: {final_expected}")
            print(f"提取状态: {final_extracted}")
            
            # 显示标准化后的状态用于调试
            norm_expected = self._normalize_state_dict(final_expected, dialogue.domain)
            norm_extracted = self._normalize_state_dict(final_extracted, dialogue.domain)
            print(f"\n【标准化后状态】（用于比较）")
            print(f"标准化期望: {norm_expected}")
            print(f"标准化提取: {norm_extracted}")
            
            # 显示匹配和未匹配的槽位
            matched = set(norm_expected.items()) & set(norm_extracted.items())
            missing = set(norm_expected.items()) - set(norm_extracted.items())
            extra = set(norm_extracted.items()) - set(norm_expected.items())
            
            if matched:
                print(f"\n✅ 匹配槽位 ({len(matched)}): {dict(matched)}")
            if missing:
                print(f"❌ 缺失槽位 ({len(missing)}): {dict(missing)}")
            if extra:
                print(f"⚠️  额外槽位 ({len(extra)}): {dict(extra)}")
            
            print("=" * 70)
        
        return {
            "dialogue_id": dialogue_id,
            "domain": dialogue.domain,
            "slot_accuracy": slot_accuracy,
            "joint_accuracy": joint_accuracy_strict,  # 主指标（对齐TransferTOD）
            "joint_accuracy_soft": joint_accuracy_soft,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total_slots": total_slots,
            "correct_slots": correct_slots,
            "total_turns": total_turns,
            "matched_slots": correct_slots,  # 添加matched_slots以对齐TransferTOD
        }
    
    def _normalize_slot_key(self, slot_key: str, domain: str) -> str:
        """
        标准化槽位键：确保包含领域前缀
        
        Args:
            slot_key: 原始槽位键
            domain: 领域名称
            
        Returns:
            标准化后的槽位键
        """
        # 如果已经有领域前缀，直接返回
        if '-' in slot_key:
            return slot_key
        # 否则添加领域前缀
        return f"{domain}-{slot_key}"
    
    def _normalize_value(self, value: str) -> str:
        """
        标准化槽位值：去除空格、统一格式
        
        Args:
            value: 原始值
            
        Returns:
            标准化后的值
        """
        if value is None:
            return ""
        # 转换为字符串并去除所有空格
        normalized = str(value).replace(" ", "").replace(" ", "")  # 移除中英文空格
        return normalized.lower()  # 转小写以忽略大小写差异
    
    def _normalize_state_dict(self, state: Dict, domain: str) -> Dict:
        """
        标准化状态字典：统一槽位键和值的格式
        
        Args:
            state: 原始状态字典
            domain: 领域名称
            
        Returns:
            标准化后的状态字典
        """
        normalized = {}
        for key, value in state.items():
            # 标准化键和值
            norm_key = self._normalize_slot_key(key, domain)
            norm_value = self._normalize_value(value)
            if norm_value:  # 只保留非空值
                normalized[norm_key] = norm_value
        return normalized
    
    def _calculate_prf_pairs(self, expected: Dict, extracted: Dict, domain: str = "") -> Tuple[float, float, float]:
        """
        计算Precision/Recall/F1（基于slot-value pairs）
        
        Args:
            expected: 期望状态
            extracted: 提取状态
            domain: 领域名称（用于标准化）
            
        Returns:
            (precision, recall, f1)
        """
        # 标准化状态字典
        if domain:
            expected = self._normalize_state_dict(expected, domain)
            extracted = self._normalize_state_dict(extracted, domain)
        
        # 转换为slot-value pairs集合
        expected_pairs = set()
        for slot, value in expected.items():
            if value:
                expected_pairs.add((slot, value))
        
        extracted_pairs = set()
        for slot, value in extracted.items():
            if value:
                extracted_pairs.add((slot, value))
        
        # 计算TP/FP/FN
        tp = len(expected_pairs & extracted_pairs)
        fp = len(extracted_pairs - expected_pairs)
        fn = len(expected_pairs - extracted_pairs)
        
        # 计算P/R/F1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return precision, recall, f1
    
    def _calculate_joint_accuracy(self, expected: Dict, extracted: Dict, domain: str = "", mode: str = 'strict') -> float:
        """
        计算Joint Accuracy（对话级别）- 对齐TransferTOD论文
        
        Args:
            expected: 期望的最终状态
            extracted: 提取的最终状态
            domain: 领域名称（用于标准化）
            mode: 'strict' (完全匹配) 或 'soft' (期望槽位都存在即可)
            
        Returns:
            1.0 if matched, 0.0 otherwise
        """
        # 标准化状态字典
        if domain:
            expected = self._normalize_state_dict(expected, domain)
            extracted = self._normalize_state_dict(extracted, domain)
        
        # 转换为slot-value pairs的集合进行比较
        expected_pairs = set([(k, v) for k, v in expected.items() if v])
        extracted_pairs = set([(k, v) for k, v in extracted.items() if v])
        
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
    
    async def run_evaluation(self, domain: str = None, split: str = "val", limit: int = None, verbose: bool = True):
        """
        运行完整评测
        
        Args:
            domain: 领域名称（如果为None则评测所有领域）
            split: 数据集划分
            limit: 限制测试数量
            verbose: 是否输出详细信息
        """
        # 获取对话列表
        dialogue_ids = self.adapter.get_dialogues_by_domain(domain, split=split)
        
        if limit:
            dialogue_ids = dialogue_ids[:limit]
        
        logger.info(f"找到 {len(dialogue_ids)} 个对话实例")
        if limit:
            logger.info(f"限制测试数量: {limit}")
        
        # 如果指定了领域，初始化该领域的追踪器
        if domain:
            self.initialize(domain)
        
        # 运行测试
        all_metrics = []
        current_domain = domain  # 跟踪当前初始化的领域
        
        for idx, dialogue_id in enumerate(dialogue_ids):
            logger.info(f"\n处理对话 {idx+1}/{len(dialogue_ids)}: {dialogue_id}")
            
            try:
                # 如果没有指定领域，需要为每个对话的领域动态初始化
                if not domain:
                    # 先加载对话获取其领域
                    dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
                    dialogue_domain = dialogue.domain
                    
                    # 如果领域变化，重新初始化追踪器
                    if dialogue_domain != current_domain:
                        logger.info(f"切换到领域: {dialogue_domain}")
                        self.initialize(dialogue_domain)
                        current_domain = dialogue_domain
                
                metrics = await self.test_dialogue(dialogue_id, split=split, verbose=verbose)
                all_metrics.append(metrics)
            except Exception as e:
                logger.error(f"❌ 对话 {dialogue_id} 评测失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue
            
            logger.info(f"✅ 对话 {dialogue_id} 评测完成")
        
        # 计算总体指标并返回
        summary_text, metrics = self._print_summary(all_metrics, split, domain)
        return summary_text, metrics
    
    def _print_summary(self, all_metrics: List[Dict], split: str, domain: str = None):
        """
        打印评测汇总
        
        Args:
            all_metrics: 所有对话的评测指标
            split: 数据集划分
            domain: 领域名称
        """
        if not all_metrics:
            print("\n⚠️  没有成功评测的对话")
            return "", []
        
        summary_lines = []
        summary_lines.append("")
        summary_lines.append("=" * 70)
        summary_lines.append("📊 测试指标汇总（对齐TransferTOD论文）")
        summary_lines.append("=" * 70)
        summary_lines.append(f"\n数据集划分: {split}")
        summary_lines.append(f"领域: {domain if domain else '所有领域'}")
        summary_lines.append(f"对话数: {len(all_metrics)}")
        
        # 计算平均指标
        avg_slot_accuracy = sum(m["slot_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy = sum(m["joint_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy_soft = sum(m["joint_accuracy_soft"] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        total_slots = sum(m["total_slots"] for m in all_metrics)
        correct_slots = sum(m["matched_slots"] for m in all_metrics)
        total_turns = sum(m["total_turns"] for m in all_metrics)
        
        
        # 按领域统计
        domain_metrics = defaultdict(list)
        for m in all_metrics:
            domain_metrics[m["domain"]].append(m)
        
        if len(domain_metrics) > 1:
            summary_lines.append("\n【分领域统计】")
            summary_lines.append("-" * 70)
            for d, metrics in sorted(domain_metrics.items()):
                d_slot_acc = sum(m["slot_accuracy"] for m in metrics) / len(metrics)
                d_joint_acc = sum(m["joint_accuracy"] for m in metrics) / len(metrics)
                d_joint_acc_soft = sum(m["joint_accuracy_soft"] for m in metrics) / len(metrics)
                d_precision = sum(m["precision"] for m in metrics) / len(metrics)
                d_recall = sum(m["recall"] for m in metrics) / len(metrics)
                d_f1 = sum(m["f1"] for m in metrics) / len(metrics)
                summary_lines.append(f"\n{d}领域 (对话数: {len(metrics)}):")
                summary_lines.append(f"  槽位准确率: {d_slot_acc * 100:.2f}%")
                summary_lines.append(f"  联合准确率-严格: {d_joint_acc * 100:.2f}%")
                summary_lines.append(f"  联合准确率-软匹配: {d_joint_acc_soft * 100:.2f}%")
                summary_lines.append(f"  精确率: {d_precision * 100:.2f}%")
                summary_lines.append(f"  召回率: {d_recall * 100:.2f}%")
                summary_lines.append(f"  F1分数: {d_f1 * 100:.2f}%")
            summary_lines.append("")
        
        # 整体汇总统计
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
        
        # 输出汇总（使用 print）
        for line in summary_lines:
            print(line)
        
        # 输出意图评测结果
        print("\n" + "=" * 70)
        print("🎯 对话级别意图评测报告")
        print("=" * 70)
        print("")
        intent_report = self.intent_evaluator.get_detailed_report(
            save_confusion_plot=False,  # RiSAWOZ不保存混淆矩阵
            include_confusion_matrix=False
        )
        print(intent_report)
        print("")
        
        # 返回汇总数据，用于保存到文件
        summary_text = "\n".join(summary_lines)
        return summary_text, all_metrics


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="DST模式 - RiSAWOZ数据集评测")
    parser.add_argument("--data-root", type=str, default="./data/RiSAWOZ",
                       help="RiSAWOZ数据集根目录")
    parser.add_argument("--domain", type=str, default=None,
                       help="指定评测的领域（如：景点、酒店、餐厅等）")
    parser.add_argument("--split", type=str, default="val", choices=["train", "val", "test"],
                       help="数据集划分")
    parser.add_argument("--limit", type=int, default=None,
                       help="限制测试对话数量")
    parser.add_argument("--verbose", action="store_true",
                       help="输出详细信息")
    parser.add_argument("--log-level", type=str, default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="日志级别")
    
    # 自定义文件名参数
    parser.add_argument("--train-file", type=str, default="train.json",
                       help="训练集文件名（默认：train.json）")
    parser.add_argument("--val-file", type=str, default="val.json",
                       help="验证集文件名（默认：val.json）")
    parser.add_argument("--test-file", type=str, default="test.json",
                       help="测试集文件名（默认：test.json）")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(LogLevel[args.log_level])
    
    # 处理文件路径参数
    # 如果用户提供的是完整路径（包含目录），需要分离目录和文件名
    data_root = args.data_root
    train_file = args.train_file
    val_file = args.val_file
    test_file = args.test_file
    
    # 检查test-file是否包含路径
    test_path = Path(args.test_file)
    train_path = Path(args.train_file)
    val_path = Path(args.val_file)
    
    # 检测哪个文件使用了完整路径
    detected_split = None
    
    if len(test_path.parts) > 1:  # 包含目录
        # 提取目录和文件名
        data_root = str(test_path.parent)
        test_file = test_path.name
        detected_split = "test"
        logger.info(f"检测到完整路径，使用: data_root={data_root}, test_file={test_file}")
    
    # 同样处理 train-file 和 val-file
    if len(train_path.parts) > 1:
        if data_root != args.data_root:
            logger.warning(f"train-file 路径 {args.train_file} 与 test-file 路径不一致，使用 test-file 的目录")
        else:
            data_root = str(train_path.parent)
        train_file = train_path.name
        if not detected_split:
            detected_split = "train"
    
    if len(val_path.parts) > 1:
        if data_root != args.data_root:
            logger.warning(f"val-file 路径 {args.val_file} 与 test-file 路径不一致，使用 test-file 的目录")
        else:
            data_root = str(val_path.parent)
        val_file = val_path.name
        if not detected_split:
            detected_split = "val"
    
    # 如果检测到文件路径且用户没有明确指定 split，自动设置 split
    if detected_split and args.split == "val":  # "val" 是默认值
        args.split = detected_split
        logger.info(f"根据文件路径自动设置 split={detected_split}")
    
    # 创建文件映射
    file_mapping = {
        "train": train_file,
        "val": val_file,
        "test": test_file
    }
    
    # 显示解析后的配置信息
    logger.info(f"数据根目录: {data_root}")
    logger.info(f"数据划分: {args.split}")
    logger.info(f"文件映射: {file_mapping}")
    
    # 验证将要使用的数据文件是否存在
    expected_file = Path(data_root) / file_mapping.get(args.split, f"{args.split}.json")
    logger.info(f"将要加载的数据文件: {expected_file}")
    
    if not expected_file.exists():
        error_msg = (
            f"\n{'='*70}\n"
            f"❌ 错误：数据文件不存在\n"
            f"{'='*70}\n\n"
            f"文件路径: {expected_file.absolute()}\n"
            f"数据根目录: {Path(data_root).absolute()}\n"
            f"文件名: {file_mapping.get(args.split)}\n"
            f"数据划分: {args.split}\n\n"
            f"请检查：\n"
            f"1. 文件路径是否正确\n"
            f"2. 文件是否存在于指定位置\n"
            f"3. 当前工作目录: {Path.cwd()}\n\n"
            f"提示：\n"
            f"- 如果使用相对路径，请确保从正确的目录运行脚本\n"
            f"- 建议使用绝对路径以避免路径问题\n"
            f"- 使用 --val-file 时，请提供完整的文件路径\n"
            f"{'='*70}\n"
        )
        logger.error(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)
    
    # 创建测试实例（使用自定义文件映射）
    test = DSTRiSAWOZTest(data_root=data_root, file_mapping=file_mapping)
    
    # 运行评测
    summary_text, all_metrics = await test.run_evaluation(
        domain=args.domain,
        split=args.split,
        limit=args.limit,
        verbose=args.verbose
    )
    
    # 保存评测结果到文件（对齐TransferTOD）
    if all_metrics:
        output_dir = Path("benchmark_results")
        output_dir.mkdir(exist_ok=True)
        
        # 生成带时间戳的文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics_file = output_dir / f"dst_risawoz_metrics_{timestamp}.txt"
        
        # 保存详细的评测结果
        with open(metrics_file, 'w', encoding='utf-8') as f:
            # 写入命令和参数
            f.write("=" * 70 + "\n")
            f.write("DST RiSAWOZ 评测结果（对齐TransferTOD）\n")
            f.write("=" * 70 + "\n")
            f.write(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"领域: {args.domain if args.domain else '所有领域'}\n")
            f.write(f"数据划分: {args.split}\n")
            f.write(f"测试数量: {len(all_metrics)}\n")
            f.write(f"数据路径: {data_root}\n")
            f.write("\n")
            
            # 写入汇总结果
            f.write(summary_text)
            
            # 写入详细的每个对话的指标
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("详细对话指标\n")
            f.write("=" * 70 + "\n\n")
            for m in all_metrics:
                try:
                    # 安全地获取和格式化指标值
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
    asyncio.run(main())
