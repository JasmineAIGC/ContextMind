#!/usr/bin/env python3
"""
DST模式 - RiSAWOZ NLU格式数据评测脚本

使用NLU格式的RiSAWOZ数据（resources/data/risawoz_test.json）进行DST评测。
该格式包含每个轮次的意图、领域、槽位、值信息。

使用方式:
    python benchmark/run_dst_risawoz_nlu.py
    python benchmark/run_dst_risawoz_nlu.py --limit 100 --verbose
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

from benchmark.datasets.risawoz.nlu_adapter import NLUFormatAdapter, NLUTurn
from benchmark.shared.intent_evaluator import IntentEvaluator
from contextmind.modes.dst import DialogueStateTracker, PromptManager
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class DSTNLUTest:
    """
    DST模式 - NLU格式测试类
    """
    
    def __init__(self, data_path: str):
        """
        初始化测试
        
        Args:
            data_path: NLU格式数据文件路径
        """
        self.adapter = NLUFormatAdapter(data_path)
        self.llm_client = None
        self.tracker = None
        self.intent_evaluator = IntentEvaluator()
        
    def initialize(self, domain: str = None):
        """
        初始化DST追踪器
        
        Args:
            domain: 领域名称（可选）
        """
        # 创建LLM客户端
        try:
            self.llm_client = SimpleLLMClient()
            logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM客户端初始化失败: {e}")
            raise
        
        # 创建PromptManager（启用动态槽位）
        pm = PromptManager(
            domain=domain or "通用",
            enable_dynamic_slots=True
        )
        
        # 创建DialogueStateTracker
        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=5,
            enable_history_summary=False,
            use_llm_summary=False
        )
        
        logger.info(f"✅ DST模式初始化完成 - 领域: {domain or '通用'}")
    
    async def test_turn(self, turn: NLUTurn, verbose: bool = True) -> Dict[str, Any]:
        """
        测试单个轮次
        
        Args:
            turn: NLU轮次对象
            verbose: 是否输出详细信息
            
        Returns:
            测试指标
        """
        if verbose:
            print(f"\n{'='*70}")
            print(f"测试轮次 {turn.turn_id}: {turn.utterance}")
            print(f"{'='*70}")
        
        # 调用DST（使用空的系统话语）
        try:
            extracted_state = await self.tracker.process_turn(
                system_utterance="",
                user_utterance=turn.utterance
            )
        except Exception as e:
            logger.error(f"处理轮次 {turn.turn_id} 时出错: {e}")
            extracted_state = {}
        
        # 获取期望状态
        expected_state = turn.belief_state
        
        # 获取期望意图
        expected_intents = [intent['intent'] for intent in turn.intents]
        primary_intent = expected_intents[0] if expected_intents else "Unknown"
        
        # 获取预测意图（从tracker历史中提取）
        predicted_intent = "Unknown"
        if self.tracker.dialogue_history:
            last_turn = self.tracker.dialogue_history[-1]
            predicted_intent = last_turn.turn_updates.get('intent', 'Unknown')
        
        # 计算槽位准确率
        total_slots = len(expected_state)
        correct_slots = 0
        
        for slot_key, expected_value in expected_state.items():
            extracted_value = extracted_state.get(slot_key)
            expected_str = str(expected_value) if expected_value is not None else ""
            extracted_str = str(extracted_value) if extracted_value is not None else ""
            
            if expected_str == extracted_str:
                correct_slots += 1
        
        slot_accuracy = correct_slots / total_slots if total_slots > 0 else 1.0
        
        # Joint accuracy（完全匹配）
        joint_accuracy = 1.0 if extracted_state == expected_state else 0.0
        
        # 计算Precision/Recall/F1
        precision, recall, f1 = self._calculate_prf(expected_state, extracted_state)
        
        # 意图准确率
        intent_accuracy = 1.0 if predicted_intent == primary_intent else 0.0
        
        if verbose:
            print(f"\n【期望信息】")
            print(f"意图: {expected_intents}")
            print(f"槽位状态: {expected_state}")
            
            print(f"\n【提取信息】")
            print(f"意图: {predicted_intent}")
            print(f"槽位状态: {extracted_state}")
            
            print(f"\n【评测结果】")
            print(f"槽位准确率: {slot_accuracy*100:.2f}% ({correct_slots}/{total_slots})")
            print(f"Joint Accuracy: {joint_accuracy*100:.2f}%")
            print(f"意图准确率: {intent_accuracy*100:.2f}%")
            print(f"Precision: {precision*100:.2f}%")
            print(f"Recall: {recall*100:.2f}%")
            print(f"F1 Score: {f1*100:.2f}%")
        
        return {
            'turn_id': turn.turn_id,
            'utterance': turn.utterance,
            'slot_accuracy': slot_accuracy,
            'joint_accuracy': joint_accuracy,
            'intent_accuracy': intent_accuracy,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'total_slots': total_slots,
            'correct_slots': correct_slots,
            'expected_intent': primary_intent,
            'predicted_intent': predicted_intent,
            'expected_state': expected_state,
            'extracted_state': extracted_state
        }
    
    def _calculate_prf(self, expected: Dict, extracted: Dict) -> Tuple[float, float, float]:
        """
        计算Precision/Recall/F1
        
        Args:
            expected: 期望状态
            extracted: 提取状态
            
        Returns:
            (precision, recall, f1)
        """
        expected_pairs = set((k, str(v)) for k, v in expected.items() if v is not None)
        extracted_pairs = set((k, str(v)) for k, v in extracted.items() if v is not None)
        
        tp = len(expected_pairs & extracted_pairs)
        fp = len(extracted_pairs - expected_pairs)
        fn = len(expected_pairs - extracted_pairs)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return precision, recall, f1
    
    async def run_evaluation(self, limit: int = None, verbose: bool = False, 
                           domain: str = None):
        """
        运行完整评测
        
        Args:
            limit: 限制测试数量
            verbose: 是否输出详细信息
            domain: 过滤特定领域（可选）
        """
        # 初始化追踪器
        self.initialize(domain)
        
        # 获取测试数据
        if domain:
            turns = self.adapter.get_turns_by_domain(domain)
            logger.info(f"找到 {len(turns)} 个 '{domain}' 领域的轮次")
        else:
            turns = self.adapter.get_all_turns()
            logger.info(f"找到 {len(turns)} 个轮次")
        
        # 只评测有槽位值的轮次
        turns_with_slots = [turn for turn in turns if turn.belief_state]
        logger.info(f"其中 {len(turns_with_slots)} 个轮次包含槽位值")
        
        if limit:
            turns_with_slots = turns_with_slots[:limit]
            logger.info(f"限制测试数量: {limit}")
        
        # 运行评测
        all_metrics = []
        
        for idx, turn in enumerate(turns_with_slots):
            if not verbose:
                logger.info(f"处理轮次 {idx+1}/{len(turns_with_slots)}: {turn.utterance[:50]}...")
            
            try:
                # 重置追踪器状态（每个轮次独立）
                self.tracker.current_state = {}
                self.tracker.dialogue_history = []
                
                metrics = await self.test_turn(turn, verbose=verbose)
                all_metrics.append(metrics)
            except Exception as e:
                logger.error(f"❌ 轮次 {idx} 评测失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue
            
            if not verbose:
                logger.info(f"✅ 轮次 {idx+1} 评测完成")
        
        # 打印总结
        self._print_summary(all_metrics, domain)
        
        return all_metrics
    
    def _print_summary(self, all_metrics: List[Dict], domain: str = None):
        """
        打印评测汇总
        
        Args:
            all_metrics: 所有轮次的评测指标
            domain: 领域名称
        """
        if not all_metrics:
            print("\n⚠️  没有成功评测的轮次")
            return
        
        print("\n" + "="*70)
        print("📊 NLU格式 DST 评测指标汇总")
        print("="*70)
        print(f"\n领域: {domain if domain else '所有领域'}")
        print(f"评测轮次数: {len(all_metrics)}")
        
        # 计算平均指标
        avg_slot_accuracy = sum(m['slot_accuracy'] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy = sum(m['joint_accuracy'] for m in all_metrics) / len(all_metrics)
        avg_intent_accuracy = sum(m['intent_accuracy'] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m['precision'] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m['recall'] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m['f1'] for m in all_metrics) / len(all_metrics)
        
        total_slots = sum(m['total_slots'] for m in all_metrics)
        correct_slots = sum(m['correct_slots'] for m in all_metrics)
        
        print(f"\n【核心指标】")
        print(f"-" * 70)
        print(f"槽位准确率 (Slot Accuracy):       {avg_slot_accuracy*100:.2f}%")
        print(f"联合准确率 (Joint Accuracy):      {avg_joint_accuracy*100:.2f}%")
        print(f"意图准确率 (Intent Accuracy):     {avg_intent_accuracy*100:.2f}%")
        print(f"精确率 (Precision):               {avg_precision*100:.2f}%")
        print(f"召回率 (Recall):                  {avg_recall*100:.2f}%")
        print(f"F1分数 (F1 Score):                {avg_f1*100:.2f}%")
        
        print(f"\n【详细统计】")
        print(f"-" * 70)
        print(f"总槽位数: {total_slots}")
        print(f"正确槽位数: {correct_slots}")
        print(f"槽位级别准确率: {correct_slots/total_slots*100:.2f}%" if total_slots > 0 else "N/A")
        
        # 意图统计
        intent_correct = sum(1 for m in all_metrics if m['intent_accuracy'] == 1.0)
        print(f"\n意图识别:")
        print(f"  正确: {intent_correct}/{len(all_metrics)} ({intent_correct/len(all_metrics)*100:.2f}%)")
        
        print("\n" + "="*70)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="DST模式 - RiSAWOZ NLU格式数据评测"
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="resources/data/risawoz_test.json",
        help="NLU格式数据文件路径"
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help="指定评测的领域"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制测试数量"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出详细信息"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(LogLevel[args.log_level])
    
    # 创建测试实例
    test = DSTNLUTest(data_path=args.data_path)
    
    # 显示数据集统计
    stats = test.adapter.get_statistics()
    print("\n" + "="*70)
    print("📁 数据集信息")
    print("="*70)
    print(f"数据文件: {args.data_path}")
    print(f"总轮次数: {stats['total_turns']}")
    print(f"包含槽位的轮次: {stats['turns_with_slots']}")
    print(f"总槽位-值对: {stats['total_slot_value_pairs']}")
    print(f"唯一意图数: {stats['unique_intents']}")
    print(f"唯一领域数: {stats['unique_domains']}")
    print("="*70)
    
    # 运行评测
    await test.run_evaluation(
        limit=args.limit,
        verbose=args.verbose,
        domain=args.domain
    )


if __name__ == "__main__":
    asyncio.run(main())
