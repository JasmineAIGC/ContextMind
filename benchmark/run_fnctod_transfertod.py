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
    
    def _normalize_value(self, value):
        """
        规范化槽位值以进行比较
        
        处理类型不一致的问题：
        - 字符串形式的数字转为数字
        - 字符串形式的布尔值转为布尔值
        
        Args:
            value: 原始槽位值
            
        Returns:
            规范化后的值
        """
        if value is None:
            return None
        
        # 如果是字符串，尝试转换为其他类型
        if isinstance(value, str):
            # 尝试转为整数
            try:
                return int(value)
            except ValueError:
                pass
            
            # 尝试转为浮点数
            try:
                return float(value)
            except ValueError:
                pass
            
            # 检查布尔值字符串（先确认是字符串类型）
            value_lower = value.lower()
            if value_lower in ('true', 'false'):
                return value_lower == 'true'
            
            # 保持字符串
            return value
        
        return value
    
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
        expected_pairs = set([(k, str(v)) for k, v in expected.items() if v is not None])
        extracted_pairs = set([(k, str(v)) for k, v in extracted.items() if v is not None])
        
        # 根据模式计算
        if mode == 'strict':
            # Strict模式: 完全匹配
            return 1.0 if expected_pairs == extracted_pairs else 0.0
        elif mode == 'soft':
            # Soft模式: 所有期望的槽位都被正确提取（允许额外槽位）
            return 1.0 if expected_pairs.issubset(extracted_pairs) else 0.0
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'strict' or 'soft'")
    
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
        
        # 维护累积的期望状态（用于计算联合准确率）
        cumulative_expected_state = {}
        
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
                
                # 检查是否有数据（用于诊断指标为0的问题）
                # 诊断：只在有数据但为空时警告
                if turn.expected_slots is not None and len(turn.expected_slots) > 0:
                    pass  # 有数据，正常
                elif turn.expected_slots is None:
                    logger.warning(f"⚠️ 轮次 {turn_idx + 1} expected_slots 为 None")
                # 空字典是正常的（该轮没有槽位变化），不需要警告
                
                if not predicted_state:
                    logger.warning(f"⚠️ 轮次 {turn_idx + 1} 没有 predicted_state 数据（LLM可能未正确调用）")
                
                # 从预测状态中提取槽位值（去除域前缀）
                # predicted_state 的键格式：'hotel-酒店星级' (LLM使用英文域名)
                # expected_slots 的键格式：'酒店星级' (数据集使用中文)
                #
                # 问题：dialogue.domain 是中文 "酒店"，但 predicted_state 的键使用英文 "hotel"
                # 解决：动态检测实际使用的域前缀
                predicted_slots_no_prefix = {}
                
                # 动态检测域前缀：从第一个键中提取
                # 键格式：'domain-slotname'，找到第一个连字符前的部分
                detected_domain_prefix = None
                if predicted_state:
                    for key in predicted_state.keys():
                        if '-' in key:
                            detected_domain_prefix = key.split('-', 1)[0] + '-'
                            break
                
                if detected_domain_prefix:
                    domain_prefix = detected_domain_prefix
                else:
                    # 如果无法检测，尝试使用dialogue.domain（可能不准确）
                    domain_prefix = f"{dialogue.domain}-"
                    
                for key, value in predicted_state.items():
                    if key.startswith(domain_prefix):
                        # 去除域前缀
                        slot_name = key[len(domain_prefix):]
                        
                        if isinstance(value, dict):
                            # 如果是字典，展开它的内容（无论是否是域名本身）
                            # 这处理了 LLM 返回嵌套结构的情况，如 'hotel-hotel': {参数...}
                            for nested_key, nested_value in value.items():
                                if nested_key not in predicted_slots_no_prefix:
                                    predicted_slots_no_prefix[nested_key] = nested_value
                                else:
                                    # 记录重复键（顶级和嵌套中都存在的槽位）
                                    # 优先使用顶级值（已存在的值）
                                    logger.debug(f"槽位 '{nested_key}' 在顶级和嵌套字典中都存在，使用顶级值")
                        else:
                            # 非字典值直接添加
                            # 不排除任何槽位，因为域前缀已经被移除
                            predicted_slots_no_prefix[slot_name] = value
                
                # 更新累积的期望状态（合并本轮的变化）
                cumulative_expected_state.update(turn.expected_slots)
                
                # 评估当前轮的槽位准确性（基于累积状态，与DST一致）
                # 这样可以确保 slot_accuracy 不同于 recall
                turn_total = len(cumulative_expected_state)  # 所有累积的槽位
                turn_matched = 0
                total_slots += turn_total
                
                for slot_name, expected_value in cumulative_expected_state.items():
                    predicted_value = predicted_slots_no_prefix.get(slot_name)
                    
                    # 规范化值以进行比较（处理类型不一致问题）
                    normalized_expected = self._normalize_value(expected_value)
                    normalized_pred = self._normalize_value(predicted_value)
                    
                    # 转换为字符串进行比较（与DST一致）
                    expected_str = str(normalized_expected) if normalized_expected is not None else None
                    pred_str = str(normalized_pred) if normalized_pred is not None else None
                    
                    if expected_str == pred_str:
                        turn_matched += 1
                        correct_slots += 1
                
                # 为P/R/F1计算收集slot-value pairs（只基于本轮的expected_slots）
                for slot_name, true_value in turn.expected_slots.items():
                    predicted_value = predicted_slots_no_prefix.get(slot_name)
                    
                    # 规范化值
                    normalized_true_value = self._normalize_value(true_value)
                    normalized_pred_value = self._normalize_value(predicted_value)
                    
                    # 将值转换为可哈希的形式（处理 dict/list 等不可哈希类型）
                    hashable_true_value = self._make_value_hashable(normalized_true_value)
                    hashable_pred_value = self._make_value_hashable(normalized_pred_value)
                    
                    # 添加到集合用于P/R/F1计算
                    all_ground_truth_pairs.add((slot_name, hashable_true_value))
                    if predicted_value is not None:
                        all_predicted_pairs.add((slot_name, hashable_pred_value))
                
                # 检查是否有额外预测的槽位
                for slot_name, pred_value in predicted_slots_no_prefix.items():
                    if slot_name not in turn.expected_slots:
                        normalized_pred_value = self._normalize_value(pred_value)
                        hashable_pred_value = self._make_value_hashable(normalized_pred_value)
                        all_predicted_pairs.add((slot_name, hashable_pred_value))
                
                # 判断整轮是否完全正确（基于累积状态）
                if turn_total > 0 and turn_matched == turn_total:
                    correct_turns += 1
                    
            except Exception as e:
                logger.error(f"处理轮次 {turn_idx + 1} 时出错: {e}")
                continue
        
        # 计算指标
        slot_accuracy = correct_slots / total_slots if total_slots > 0 else 0
        
        # 获取最终的对话状态（FnCTOD tracker维护的累积状态）
        final_extracted = self.tracker.current_state.copy()
        
        # 计算两种联合准确率（基于最终状态）
        # 需要从final_extracted中去除域前缀，以便与cumulative_expected_state比较
        final_extracted_no_prefix = {}
        if final_extracted:
            # 动态检测域前缀
            detected_domain_prefix = None
            for key in final_extracted.keys():
                if '-' in key:
                    detected_domain_prefix = key.split('-', 1)[0] + '-'
                    break
            
            if detected_domain_prefix:
                for key, value in final_extracted.items():
                    if key.startswith(detected_domain_prefix):
                        slot_name = key[len(detected_domain_prefix):]
                        if isinstance(value, dict):
                            # 展开嵌套字典
                            for nested_key, nested_value in value.items():
                                if nested_key not in final_extracted_no_prefix:
                                    final_extracted_no_prefix[nested_key] = nested_value
                        else:
                            final_extracted_no_prefix[slot_name] = value
            else:
                final_extracted_no_prefix = final_extracted
        
        joint_accuracy_strict = self._calculate_joint_accuracy(cumulative_expected_state, final_extracted_no_prefix, mode='strict')
        joint_accuracy_soft = self._calculate_joint_accuracy(cumulative_expected_state, final_extracted_no_prefix, mode='soft')
        
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
                dialogue_slots=final_extracted_no_prefix,  # 使用去除前缀的最终提取槽位
                user_utterances=all_user_utterances
            )
        
        # 输出评测结果（添加分隔线以区分警告和结果）
        if verbose:
            logger.info("  " + "-" * 50)
            logger.info("  评测结果:")
            logger.info(f"    槽位准确率: {slot_accuracy * 100:.2f}%")
            logger.info(f"    联合准确率-严格 (Joint Accuracy Strict): {joint_accuracy_strict * 100:.2f}%")
            logger.info(f"    联合准确率-软匹配 (Joint Accuracy Soft): {joint_accuracy_soft * 100:.2f}%")
            logger.info(f"    精确率: {precision * 100:.2f}%")
            logger.info(f"    召回率: {recall * 100:.2f}%")
            logger.info(f"    F1分数: {f1 * 100:.2f}%")
        
        return {
            "dialogue_id": dialogue_id,
            "slot_accuracy": slot_accuracy,
            "joint_accuracy": joint_accuracy_strict,  # 默认使用严格模式
            "joint_accuracy_strict": joint_accuracy_strict,
            "joint_accuracy_soft": joint_accuracy_soft,
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
                avg_ja_strict = sum(m["joint_accuracy_strict"] for m in metrics_list) / len(metrics_list)
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
        avg_joint_accuracy_strict = sum(m["joint_accuracy_strict"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy_soft = sum(m["joint_accuracy_soft"] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        summary_lines.append("\n【整体汇总统计】")
        summary_lines.append("-" * 70)
        summary_lines.append(f"总测试对话数: {len(all_metrics)}")
        summary_lines.append(f"平均槽位准确率 (Slot Accuracy): {avg_slot_accuracy * 100:.2f}%")
        summary_lines.append(f"平均联合准确率-严格 (Joint Accuracy Strict): {avg_joint_accuracy_strict * 100:.2f}%")
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
            plot_path="fnctod_intent_confusion_matrix.png",
            include_confusion_matrix=False
        )
        summary_lines.append(intent_report)
        summary_lines.append("")
        
        # 输出指标汇总（使用 print）
        for line in summary_lines:
            print(line)
        
        # 保存结果到文件
        output_dir = Path("benchmark_results")
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics_file = output_dir / f"fnctod_transfertod_metrics_{timestamp}.txt"
        
        summary_text = "\n".join(summary_lines)
        
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
        print("=" * 80)
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ 执行失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        print("如果你看到这个错误，说明脚本正确加载但执行时遇到问题")
        sys.exit(1)
