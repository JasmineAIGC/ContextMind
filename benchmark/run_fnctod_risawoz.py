#!/usr/bin/env python3
"""
FnCTOD模式 - RiSAWOZ数据集评测脚本

使用RiSAWOZ数据集测试FnCTODTracker的函数调用能力。

FnCTOD (Function Calling for Task-Oriented Dialogue):
- 将DST任务转化为函数调用
- 每个领域是一个函数
- 槽位作为函数参数
- 更结构化的对话状态追踪

使用方式:
    python benchmark/run_fnctod_risawoz.py
    python benchmark/run_fnctod_risawoz.py --domain 景点 --split val --limit 10
    python benchmark/run_fnctod_risawoz.py --verbose --limit 5
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict, Counter
import datetime

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter
from benchmark.shared.intent_evaluator import IntentEvaluator
from benchmark.shared.intent_label_loader import IntentLabelLoader
from contextmind.modes.fnctod import FnCTODTracker, FunctionManager, DomainSpec, FunctionParameter, ParameterType
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class FnCTODRiSAWOZTest:
    """
    FnCTOD模式 - RiSAWOZ测试类
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
        self.intent_evaluator = IntentEvaluator(intent_label_loader=self.intent_label_loader)
        
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
            print(f"\nFnCTOD 模式需要 LLM 来提取函数调用信息。")
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
        
        # 创建DomainSpec（将RiSAWOZ schema转换为FnCTOD格式）
        domain_spec = self._create_domain_spec_from_schema(domain, schema)
        function_manager.add_domain(domain_spec)
        
        # 创建FnCTODTracker
        self.tracker = FnCTODTracker(
            llm_client=self.llm_client,
            function_manager=function_manager,
            use_two_stage=True,  # 使用两阶段处理
            max_history_turns=10
        )
        
        logger.info(f"✅ FnCTOD追踪器初始化完成 - 领域: {domain}")
    
    def _create_domain_spec_from_schema(self, domain: str, schema: Dict[str, Any]) -> DomainSpec:
        """
        从RiSAWOZ schema创建DomainSpec
        
        Args:
            domain: 领域名称
            schema: RiSAWOZ schema字典
            
        Returns:
            DomainSpec对象
        """
        # 创建函数参数列表
        parameters = []
        
        # RiSAWOZ的槽位在schema中定义
        slots = schema.get('slots', {})
        
        for slot_name, slot_info in slots.items():
            # 确定参数类型
            param_type = ParameterType.STRING  # 默认为字符串
            enum_values = []
            
            # 如果有values列表，将它们存储在enum_values中（但类型还是STRING）
            if isinstance(slot_info, dict):
                values = slot_info.get('values', [])
                if values and len(values) > 0:
                    enum_values = values
            elif isinstance(slot_info, list):
                # slot_info本身就是values列表
                values = slot_info
                if values and len(values) > 0:
                    enum_values = values
                slot_info = {'values': values}
            
            # 创建参数
            param = FunctionParameter(
                name=slot_name,
                param_type=param_type,
                description=f"{domain}领域的{slot_name}槽位",
                required=False,  # RiSAWOZ中槽位通常不是必需的
                enum_values=enum_values
            )
            parameters.append(param)
        
        # 创建DomainSpec
        domain_spec = DomainSpec(
            name=domain,
            description=f"RiSAWOZ - {domain}领域对话",
            parameters=parameters,
            intents=schema.get('intents', ['inform', 'request', 'general'])
        )
        
        return domain_spec
    
    async def test_dialogue(self, dialogue_id: str, split: str = "val", verbose: bool = False) -> Dict[str, Any]:
        """
        测试单个对话
        
        Args:
            dialogue_id: 对话ID
            split: 数据集划分
            verbose: 是否输出详细信息
            
        Returns:
            评测结果字典
        """
        # 加载对话
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"测试对话: {dialogue.dialogue_id}")
            print(f"领域: {dialogue.domain}")
            print(f"{'='*70}")
        
        # 重置追踪器
        self.tracker.reset()
        
        # 逐轮处理
        total_params = 0
        correct_params = 0
        total_turns = len(dialogue.turns)
        correct_function_calls = 0
        
        # 收集所有轮次的意图进行评测
        turn_intents_true = []
        turn_intents_pred = []
        
        for turn_idx, turn in enumerate(dialogue.turns):
            if verbose:
                print(f"\n--- 轮次 {turn.turn_id} ---")
                print(f"系统: {turn.system_utterance}")
                print(f"用户: {turn.user_utterance}")
            
            # 处理轮次
            try:
                response = await self.tracker.process_turn(
                    user_utterance=turn.user_utterance,
                    system_utterance=turn.system_utterance
                )
                
                # 获取函数调用信息
                function_calls = self.tracker.get_current_function_calls()
                
                if verbose and function_calls:
                    print(f"函数调用: {len(function_calls)}个")
                    for fc in function_calls:
                        print(f"  - {fc.function_name}({fc.parameters})")
                
                # 获取提取的状态
                extracted_state = self.tracker.get_current_state()
                
                # 比较参数（槽位）
                expected_params = turn.expected_slots
                
                if verbose:
                    print(f"期望参数: {expected_params}")
                    print(f"提取参数: {extracted_state}")
                
                # 统计参数准确率
                for param_key, expected_value in expected_params.items():
                    total_params += 1
                    extracted_value = extracted_state.get(param_key, "")
                    
                    # 简单的字符串匹配
                    if str(expected_value).lower().strip() == str(extracted_value).lower().strip():
                        correct_params += 1
                        if verbose:
                            print(f"  ✓ {param_key}: {expected_value}")
                    else:
                        if verbose:
                            print(f"  ✗ {param_key}: 期望 '{expected_value}', 得到 '{extracted_value}'")
                
                # 检查函数调用是否正确（是否调用了正确的领域）
                if function_calls:
                    for fc in function_calls:
                        if fc.function_name == dialogue.domain:
                            correct_function_calls += 1
                            break
                
                # 意图评测（使用turn的user_intents）
                if turn.user_intents:
                    # 提取真实意图（从user_acts的第一个元素）
                    true_intent = turn.user_intents[0][0] if turn.user_intents[0] else "General"
                    
                    # 推断意图（基于提取的参数）
                    pred_intent, _ = self.intent_evaluator.infer_intent_from_slots(
                        domain=dialogue.domain,
                        turn_updates=extracted_state,
                        previous_state={},
                        user_utterance=turn.user_utterance,
                        turn_id=turn.turn_id
                    )
                    
                    turn_intents_true.append(true_intent)
                    turn_intents_pred.append(pred_intent)
                    
                    if verbose:
                        match_symbol = "✓" if true_intent == pred_intent else "✗"
                        print(f"轮次意图: {true_intent} -> {pred_intent} {match_symbol}")
                
            except Exception as e:
                logger.error(f"处理轮次 {turn_idx} 时出错: {e}")
                if verbose:
                    print(f"❌ 错误: {e}")
        
        # 计算指标
        param_accuracy = correct_params / total_params if total_params > 0 else 0.0
        function_call_accuracy = correct_function_calls / total_turns if total_turns > 0 else 0.0
        
        # 计算意图准确率
        intent_accuracy = 0.0
        if turn_intents_true:
            correct_intents = sum(1 for t, p in zip(turn_intents_true, turn_intents_pred) if t == p)
            intent_accuracy = correct_intents / len(turn_intents_true)
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"📊 对话评测结果")
            print(f"{'='*70}")
            print(f"参数准确率 (Parameter Accuracy): {param_accuracy * 100:.2f}%")
            print(f"函数调用准确率 (Function Call Accuracy): {function_call_accuracy * 100:.2f}%")
            print(f"意图准确率 (Intent Accuracy): {intent_accuracy * 100:.2f}%")
            print(f"{'='*70}\n")
        
        return {
            "dialogue_id": dialogue.dialogue_id,
            "domain": dialogue.domain,
            "param_accuracy": param_accuracy,
            "function_call_accuracy": function_call_accuracy,
            "intent_accuracy": intent_accuracy,
            "total_params": total_params,
            "correct_params": correct_params,
            "total_turns": total_turns,
            "correct_function_calls": correct_function_calls,
            "total_intents": len(turn_intents_true),
            "correct_intents": sum(1 for t, p in zip(turn_intents_true, turn_intents_pred) if t == p)
        }
    
    async def run_tests(self, domain: str = None, split: str = "val", limit: int = None, verbose: bool = False):
        """
        运行评测
        
        Args:
            domain: 领域过滤 (可选)
            split: 数据集划分
            limit: 限制对话数量
            verbose: 是否输出详细信息
        """
        # 获取对话ID（如果指定domain则过滤，否则获取全部）
        dialogue_ids = self.adapter.get_dialogues_by_domain(domain=domain, split=split)
        
        # 限制数量
        if limit:
            dialogue_ids = dialogue_ids[:limit]
        
        print(f"\n{'='*70}")
        print(f"FnCTOD模式 - RiSAWOZ数据集评测")
        print(f"{'='*70}")
        print(f"数据集划分: {split}")
        print(f"领域过滤: {domain if domain else '全部'}")
        print(f"测试对话数: {len(dialogue_ids)}")
        print(f"{'='*70}\n")
        
        # 初始化追踪器（使用第一个对话的领域，或指定的领域）
        if domain:
            init_domain = domain
        else:
            # 获取第一个对话的领域
            first_dialogue = self.adapter.load_dialogue(dialogue_ids[0], split=split)
            init_domain = first_dialogue.domain
        
        self.initialize(init_domain)
        
        # 收集结果
        all_results = []
        domain_results = defaultdict(list)
        
        for idx, dialogue_id in enumerate(dialogue_ids):
            logger.info(f"测试对话 {idx + 1}/{len(dialogue_ids)}: {dialogue_id}")
            
            try:
                result = await self.test_dialogue(dialogue_id, split=split, verbose=verbose)
                all_results.append(result)
                domain_results[result['domain']].append(result)
                
                if not verbose:
                    print(f"✅ 对话 {idx + 1}/{len(dialogue_ids)} 完成: {dialogue_id}")
            
            except Exception as e:
                logger.error(f"对话 {dialogue_id} 测试失败: {e}")
                print(f"❌ 对话 {idx + 1}/{len(dialogue_ids)} 失败: {dialogue_id} - {e}")
        
        # 打印汇总统计
        self._print_summary(all_results, domain_results)
    
    def _print_summary(self, all_results: List[Dict], domain_results: Dict[str, List[Dict]]):
        """打印汇总统计"""
        if not all_results:
            print("\n⚠️  没有成功评测的对话")
            return
        
        print(f"\n{'='*70}")
        print(f"📊 评测结果汇总")
        print(f"{'='*70}\n")
        
        # 分领域统计
        if len(domain_results) > 1:
            print(f"【分领域统计】")
            print(f"{'-'*70}\n")
            
            for domain, results in sorted(domain_results.items()):
                avg_param_acc = sum(r['param_accuracy'] for r in results) / len(results)
                avg_func_acc = sum(r['function_call_accuracy'] for r in results) / len(results)
                avg_intent_acc = sum(r['intent_accuracy'] for r in results) / len(results)
                
                print(f"{domain}领域 (对话数: {len(results)}):")
                print(f"  参数准确率: {avg_param_acc * 100:.2f}%")
                print(f"  函数调用准确率: {avg_func_acc * 100:.2f}%")
                print(f"  意图准确率: {avg_intent_acc * 100:.2f}%")
                print()
        
        # 整体统计
        print(f"【整体汇总统计】")
        print(f"{'-'*70}")
        
        total_dialogues = len(all_results)
        avg_param_accuracy = sum(r['param_accuracy'] for r in all_results) / total_dialogues
        avg_func_accuracy = sum(r['function_call_accuracy'] for r in all_results) / total_dialogues
        avg_intent_accuracy = sum(r['intent_accuracy'] for r in all_results) / total_dialogues
        
        total_params = sum(r['total_params'] for r in all_results)
        correct_params = sum(r['correct_params'] for r in all_results)
        
        total_calls = sum(r['total_turns'] for r in all_results)
        correct_calls = sum(r['correct_function_calls'] for r in all_results)
        
        total_intents = sum(r.get('total_intents', 0) for r in all_results)
        correct_intents = sum(r.get('correct_intents', 0) for r in all_results)
        
        print(f"总测试对话数: {total_dialogues}")
        print(f"平均参数准确率 (Parameter Accuracy): {avg_param_accuracy * 100:.2f}%")
        print(f"  总参数数: {total_params}, 正确参数数: {correct_params}")
        print(f"平均函数调用准确率 (Function Call Accuracy): {avg_func_accuracy * 100:.2f}%")
        print(f"  总调用数: {total_calls}, 正确调用数: {correct_calls}")
        print(f"平均意图准确率 (Intent Accuracy): {avg_intent_accuracy * 100:.2f}%")
        print(f"  总意图数: {total_intents}, 正确意图数: {correct_intents}")
        print(f"{'-'*70}\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="FnCTOD模式 - RiSAWOZ数据集评测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 测试全部数据
  python benchmark/run_fnctod_risawoz.py

  # 测试特定领域
  python benchmark/run_fnctod_risawoz.py --domain 景点

  # 限制测试数量
  python benchmark/run_fnctod_risawoz.py --limit 10

  # 详细输出
  python benchmark/run_fnctod_risawoz.py --domain 酒店 --limit 5 --verbose

  # 使用测试集
  python benchmark/run_fnctod_risawoz.py --split test --limit 20
        """
    )
    
    parser.add_argument("--domain", type=str, default=None,
                       help="领域名称过滤 (如: 景点, 酒店, 餐厅)")
    parser.add_argument("--split", type=str, default="val",
                       choices=["train", "val", "test"],
                       help="数据集划分 (默认: val)")
    parser.add_argument("--limit", type=int, default=None,
                       help="限制测试对话数量")
    parser.add_argument("--verbose", action="store_true",
                       help="输出详细信息")
    parser.add_argument("--data-root", type=str, default="./data/RiSAWOZ",
                       help="RiSAWOZ数据集根目录 (默认: ./data/RiSAWOZ)")
    parser.add_argument("--log-level", type=str, default="INFO",
                       choices=["DEBUG", "INFO", "WARNING"],
                       help="日志级别 (默认: INFO)")
    
    args = parser.parse_args()
    
    # 设置日志
    log_level_map = {
        "DEBUG": LogLevel.DEBUG,
        "INFO": LogLevel.INFO,
        "WARNING": LogLevel.WARNING
    }
    setup_logging(level=log_level_map[args.log_level])
    
    # 创建测试实例
    test = FnCTODRiSAWOZTest(data_root=args.data_root)
    
    # 运行评测
    try:
        asyncio.run(test.run_tests(
            domain=args.domain,
            split=args.split,
            limit=args.limit,
            verbose=args.verbose
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断测试")
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
