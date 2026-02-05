#!/usr/bin/env python3
"""
DST模式 - TransferTOD数据集测试脚本

使用TransferTOD数据集测试DialogueStateTracker的槽位提取能力。

使用方式:
    python tests/test_dst_transfertod.py
    python tests/test_dst_transfertod.py --domain 酒店 --data-type clean --limit 10
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.adapters import TransferTODAdapter
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
            
            if verbose:
                print(f"期望状态: {expected}")
                print(f"提取状态: {extracted_state}")
                print(f"匹配数: {turn_matched}/{turn_total}")
        
        # 计算评估指标
        slot_accuracy = matched_slots / total_slots if total_slots > 0 else 0.0
        joint_goal_accuracy = perfect_turns / total_turns if total_turns > 0 else 0.0
        
        # 计算Precision/Recall/F1
        precision, recall, f1 = self._calculate_prf(all_expected, all_extracted)
        
        metrics = {
            "dialogue_id": dialogue_id,
            "slot_accuracy": slot_accuracy,
            "joint_goal_accuracy": joint_goal_accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total_slots": total_slots,
            "matched_slots": matched_slots,
            "total_turns": total_turns,
            "perfect_turns": perfect_turns
        }
        
        if verbose:
            print("\n--- 测试结果 ---")
            print(f"槽位准确率: {slot_accuracy * 100:.2f}%")
            print(f"Joint Goal Accuracy: {joint_goal_accuracy * 100:.2f}%")
            print(f"Precision: {precision * 100:.2f}%")
            print(f"Recall: {recall * 100:.2f}%")
            print(f"F1 Score: {f1 * 100:.2f}%")
        
        return metrics
    
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
    parser.add_argument("--domain", type=str, default="酒店", help="测试领域")
    parser.add_argument("--data-type", type=str, default="clean", choices=["clean", "noise"], help="数据类型")
    parser.add_argument("--limit", type=int, default=None, help="限制测试数量")
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD", help="数据集根目录")
    parser.add_argument("--verbose", action="store_true", help="输出详细信息")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(LogLevel.INFO)
    
    print("=" * 70)
    print(f"DST 模式测试 - TransferTOD 数据集 ({args.domain})")
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
        print(f"\n未找到领域 '{args.domain}' 的对话数据")
        return
    
    print(f"\n找到 {len(dialogue_ids)} 个对话实例")
    
    # 限制测试数量
    if args.limit:
        dialogue_ids = dialogue_ids[:args.limit]
        print(f"限制测试数量: {args.limit}")
    
    # 初始化DST
    test.initialize(args.domain)
    
    # 批量测试
    all_metrics = []
    for dialogue_id in dialogue_ids:
        try:
            metrics = await test.test_dialogue(dialogue_id, verbose=args.verbose)
            all_metrics.append(metrics)
        except Exception as e:
            logger.error(f"测试对话 {dialogue_id} 失败: {e}")
            continue
    
    # 输出汇总指标
    if all_metrics:
        print("\n" + "=" * 70)
        print("📊 测试指标汇总")
        print("=" * 70)
        
        avg_slot_accuracy = sum(m["slot_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_goal = sum(m["joint_goal_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        print(f"\n测试对话数: {len(all_metrics)}")
        print(f"平均槽位准确率: {avg_slot_accuracy * 100:.2f}%")
        print(f"平均 Joint Goal Accuracy: {avg_joint_goal * 100:.2f}%")
        print(f"平均 Precision: {avg_precision * 100:.2f}%")
        print(f"平均 Recall: {avg_recall * 100:.2f}%")
        print(f"平均 F1 Score: {avg_f1 * 100:.2f}%")
        print()


if __name__ == "__main__":
    asyncio.run(main())
