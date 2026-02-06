#!/usr/bin/env python3
"""
FnCTOD模式 - TransferTOD数据集测试脚本

使用TransferTOD数据集测试FnCTODTracker的函数调用和槽位提取能力。

使用方式:
    python tests/test_fnctod_transfertod.py
    python tests/test_fnctod_transfertod.py --domain 酒店 --data-type clean --limit 10
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
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.fnctod.data_models import DomainSpec, FunctionParameter, ParameterType
from contextmind.modes.fnctod.function_manager import FunctionManager
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class FnCTODTransferTODTest:
    """
    FnCTOD模式 - TransferTOD测试类
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
            raise
        
        # 获取领域schema并生成DomainSpec
        schema = self.adapter.get_domain_schema(domain)
        domain_spec = self._create_domain_spec_from_schema(domain, schema)
        
        # 创建FunctionManager
        function_manager = FunctionManager()
        function_manager.register_domain(domain_spec)
        
        # 创建FnCTODTracker
        self.tracker = FnCTODTracker(
            llm_client=self.llm_client,
            function_manager=function_manager,
            use_two_stage=True,
            max_history_turns=10
        )
        
        logger.info(f"✅ FnCTOD模式初始化完成 - 领域: {domain}")
        logger.info(f"   注册槽位数: {len(domain_spec.parameters)}")
    
    def _create_domain_spec_from_schema(self, domain: str, schema: Dict) -> DomainSpec:
        """
        从适配器的schema生成DomainSpec
        
        Args:
            domain: 领域名称
            schema: 领域schema
            
        Returns:
            DomainSpec实例
        """
        domain_spec = DomainSpec(
            name=domain,
            description=f"{domain}场景的槽位填充"
        )
        
        for slot_name, slot_info in schema["slots"].items():
            param = FunctionParameter(
                name=slot_name,
                description=slot_info.get("description", slot_name),
                param_type=ParameterType.STRING,
                required=False
            )
            domain_spec.add_parameter(param)
        
        return domain_spec
    
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
            
            # 调用FnCTOD
            try:
                result = await self.tracker.process_turn(
                    system_utterance=turn.system_utterance,
                    user_utterance=turn.user_utterance
                )
                
                # 从function_call中提取参数作为状态
                extracted_state = {}
                if result.function_call:
                    extracted_state = result.function_call.parameters.copy()
                
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
                # 转换为字符串进行比较
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
        
        # 计算评估指标（对齐TransferTOD论文）
        slot_accuracy = matched_slots / total_slots if total_slots > 0 else 0.0
        
        # Joint Accuracy（对话级别，使用最终状态）- 对齐TransferTOD论文
        final_expected = cumulative_expected_state
        final_extracted = extracted_state  # 最后一轮的状态
        
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
        # 转换为slot-value pairs的集合进行比较
        expected_pairs = set()
        for k, v in expected.items():
            # 过滤None和空值
            if v is None or v == '' or v == 'null' or v == 'None':
                continue
            v_str = str(v)
            expected_pairs.add((k, v_str))
        
        extracted_pairs = set()
        for k, v in extracted.items():
            # 过滤None和空值
            if v is None or v == '' or v == 'null' or v == 'None':
                continue
            v_str = str(v)
            extracted_pairs.add((k, v_str))
        
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
        expected_pairs = set()
        for k, v in expected.items():
            # 过滤None和空值
            if v is None or v == '' or v == 'null' or v == 'None':
                continue
            v_str = str(v)
            expected_pairs.add((k, v_str))
        
        extracted_pairs = set()
        for k, v in extracted.items():
            # 过滤None和空值
            if v is None or v == '' or v == 'null' or v == 'None':
                continue
            v_str = str(v)
            extracted_pairs.add((k, v_str))
        
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
                if slot in extracted and extracted[slot] == value:
                    true_positive += 1
                else:
                    false_negative += 1
            
            for slot, value in extracted.items():
                if slot not in expected or expected.get(slot) != value:
                    false_positive += 1
        
        precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) > 0 else 0.0
        recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return precision, recall, f1


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="FnCTOD模式 - TransferTOD数据集测试")
    parser.add_argument("--domain", type=str, default="酒店", help="测试领域")
    parser.add_argument("--data-type", type=str, default="clean", choices=["clean", "noise"], help="数据类型")
    parser.add_argument("--limit", type=int, default=None, help="限制测试数量")
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD", help="数据集根目录")
    parser.add_argument("--verbose", action="store_true", help="输出详细信息")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(LogLevel.INFO)
    
    print("=" * 70)
    print(f"FnCTOD 模式测试 - TransferTOD 数据集 ({args.domain})")
    print("=" * 70)
    
    # 初始化测试
    test = FnCTODTransferTODTest(data_root=args.data_root)
    
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
    
    # 初始化FnCTOD
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
    
    # 输出汇总指标（对齐TransferTOD论文）
    if all_metrics:
        print("\n" + "=" * 70)
        print("📊 测试指标汇总（对齐TransferTOD论文）")
        print("=" * 70)
        
        avg_slot_accuracy = sum(m["slot_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy = sum(m["joint_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy_soft = sum(m["joint_accuracy_soft"] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        print(f"\n测试对话数: {len(all_metrics)}")
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
        print("说明：")
        print("  - Strict JA = 0% 说明模型总是预测了额外的槽位")
        print("  - Soft JA > 0% 说明模型能找到所有期望槽位（但可能过度预测）")
        print("  - 如果 Soft JA 高但 Strict JA 低，说明模型倾向于过度预测")
        print()


if __name__ == "__main__":
    asyncio.run(main())
