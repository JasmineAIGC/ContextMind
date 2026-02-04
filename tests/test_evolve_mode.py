#!/usr/bin/env python3
"""
Evolve 模式测试代码

复用 gradio_demo.py 中的 Evolve 模式计算流程
对 7 通电话对话进行知识提取和记忆进化测试

使用方式:
    python -m pytest tests/test_evolve_mode.py -v
    python tests/test_evolve_mode.py  # 直接运行
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextmind.core.common.utils.llm_client import SimpleLLMClient
from contextmind.modes.evolve import EvolveEngine
from contextmind.scenarios.config import get_insurance_scenario
from contextmind.scenarios.apps.insurance_app import InsuranceApplication
from contextmind.core.common.utils.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class EvolveModeTest:
    """
    Evolve 模式测试类
    
    复用 gradio_demo.py 中 UnifiedGradioDemo._init_evolve_mode() 和 chat_evolve_mode() 的计算流程
    """
    
    def __init__(self):
        """初始化 Evolve 测试"""
        self.llm_client = None
        self.app = None
        self.config = None
        self.engine = None
        
    def initialize(self):
        """
        初始化 Evolve 模式
        
        复用 gradio_demo.py 中 UnifiedGradioDemo._init_evolve_mode() 的初始化流程
        """
        # 加载保险场景配置
        self.config = get_insurance_scenario()
        
        # 创建 LLM 客户端
        try:
            self.llm_client = SimpleLLMClient()
            logger.info("✅ LLM客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM客户端初始化失败: {e}")
            raise
        
        # 创建 EvolveEngine - 复用 gradio_demo.py 的初始化逻辑
        self.engine = EvolveEngine(
            app_name="test_evolve_insurance",
            user_id="test_user",
            llm_client=self.llm_client
        )
        
        # 创建 InsuranceApplication - 复用 gradio_demo.py 的初始化逻辑
        self.app = InsuranceApplication(
            context_engine=self.engine,
            system_prompt=self.config.system_prompt
        )
        
        logger.info(f"✅ Evolve模式初始化完成 - 场景: {self.config.name}")
    
    def reset(self):
        """重置对话和记忆状态"""
        if self.engine:
            # 重新初始化以清除状态
            self.engine = EvolveEngine(
                app_name="test_evolve_insurance",
                user_id="test_user",
                llm_client=self.llm_client
            )
            self.app = InsuranceApplication(
                context_engine=self.engine,
                system_prompt=self.config.system_prompt
            )
            logger.info("Evolve状态已重置")
    
    async def process_turn(self, user_message: str) -> str:
        """
        处理单轮对话
        
        复用 gradio_demo.py 中 chat_evolve_mode() 的处理流程
        
        Args:
            user_message: 用户消息（客户）
            
        Returns:
            助手回复
        """
        # 调用 app.process_turn - 与 gradio_demo.py 完全一致
        reply = await self.app.process_turn(user_message)
        return reply
    
    def get_memory_cache(self) -> List:
        """获取当前记忆库内容"""
        if self.engine and hasattr(self.engine, 'memory_bank'):
            return self.engine.memory_bank.get_memory_cache()
        return []
    
    def get_memory_count(self) -> int:
        """获取记忆数量"""
        return len(self.get_memory_cache())


def load_dialogue(dialogue_num: int) -> str:
    """加载对话文本"""
    dialogue_path = PROJECT_ROOT / "tests" / "dialogues" / f"dialogue_{dialogue_num}.txt"
    with open(dialogue_path, 'r', encoding='utf-8') as f:
        return f.read()


def load_evolve_labels(dialogue_num: int) -> Dict:
    """加载 Evolve 标签"""
    label_path = PROJECT_ROOT / "tests" / "labels" / f"dialogue_{dialogue_num}_evolve.json"
    with open(label_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_customer_messages(dialogue_text: str) -> List[str]:
    """
    解析对话文本，提取客户消息
    
    Args:
        dialogue_text: 对话文本
        
    Returns:
        客户消息列表
    """
    lines = dialogue_text.strip().split('\n')
    messages = []
    current_message = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 跳过背景音和括号内的注释
        if line.startswith('（') and line.endswith('）'):
            continue
        if line.startswith('(') and line.endswith(')'):
            continue
            
        if line.startswith('客户：') or line.startswith('客户:'):
            # 如果有之前的消息，先保存
            if current_message:
                messages.append(' '.join(current_message))
                current_message = []
            
            # 开始收集客户消息
            content = line.split('：', 1)[-1].split(':', 1)[-1].strip()
            if content:
                current_message.append(content)
        elif line.startswith('销售员：') or line.startswith('销售员:'):
            # 保存之前的客户消息
            if current_message:
                messages.append(' '.join(current_message))
                current_message = []
    
    # 保存最后一条消息
    if current_message:
        messages.append(' '.join(current_message))
    
    return messages


async def test_dialogue(tester: EvolveModeTest, dialogue_num: int, verbose: bool = True) -> Dict:
    """
    测试单个对话
    
    Args:
        tester: Evolve测试器
        dialogue_num: 对话编号 (1-7)
        verbose: 是否输出详细信息
        
    Returns:
        测试结果（包含数值指标）
    """
    # 加载对话和标签
    dialogue_text = load_dialogue(dialogue_num)
    labels = load_evolve_labels(dialogue_num)
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"测试对话 {dialogue_num}: {labels.get('dialogue_summary', '')[:50]}...")
        print(f"{'='*60}")
    
    # 重置状态
    tester.reset()
    
    # 解析客户消息
    customer_messages = parse_customer_messages(dialogue_text)
    
    if verbose:
        print(f"解析到 {len(customer_messages)} 条客户消息")
    
    expected_knowledge = labels.get('extracted_knowledge', {})
    expected_memory_items = labels.get('memory_items', [])
    
    results = {
        'dialogue_id': labels.get('dialogue_id', f'对话{dialogue_num}'),
        'total_messages': len(customer_messages),
        'processed_messages': 0,
        'successful_messages': 0,
        'replies': [],
        'memory_count': 0,
        'expected_knowledge': expected_knowledge,
        'expected_memory_items': expected_memory_items,
        # 数值指标
        'metrics': {
            'processing_success_rate': 0.0,    # 处理成功率
            'knowledge_coverage': 0.0,          # 知识覆盖率
            'memory_generation_rate': 0.0,      # 记忆生成率
            'expected_categories': 0,           # 期望知识类别数
            'actual_memory_count': 0            # 实际记忆数量
        }
    }
    
    # 处理每条客户消息
    max_messages = 3
    messages_to_process = customer_messages[:min(max_messages, len(customer_messages))]
    
    for i, message in enumerate(messages_to_process):
        if verbose:
            print(f"\n--- 消息 {i+1}/{len(messages_to_process)} ---")
            print(f"客户: {message}")
        
        try:
            # 处理消息
            reply = await tester.process_turn(message)
            
            if verbose:
                # 截取回复的前100个字符
                print(f"助手: {reply[:100]}..." if len(reply) > 100 else f"助手: {reply}")
            
            results['replies'].append({
                'message_id': i + 1,
                'customer_message': message,
                'assistant_reply': reply,
                'success': True
            })
            results['processed_messages'] += 1
            results['successful_messages'] += 1
            
        except Exception as e:
            if verbose:
                print(f"❌ 处理失败: {e}")
            results['replies'].append({
                'message_id': i + 1,
                'customer_message': message,
                'error': str(e),
                'success': False
            })
            results['processed_messages'] += 1
    
    # 获取记忆库状态
    results['memory_count'] = tester.get_memory_count()
    
    # 计算数值指标
    expected_categories = len(expected_knowledge)
    expected_memory_count = len(expected_memory_items)
    
    # 处理成功率：成功处理的消息数 / 已处理的消息总数
    # processed_messages 包含成功和失败的消息，successful_messages 只计成功的
    results['metrics']['processing_success_rate'] = (
        results['successful_messages'] / results['processed_messages'] * 100
    ) if results['processed_messages'] > 0 else 0.0
    
    # 知识覆盖率：评估系统是否能生成覆盖预期知识类别的记忆
    # 计算方法：min(记忆数量, 期望类别数) / 期望类别数
    # 使用 min 是因为记忆数量可能超过类别数（一个类别可生成多条记忆）
    # 此指标表示系统是否有能力覆盖不同类型的知识，上限为100%
    results['metrics']['knowledge_coverage'] = (
        min(results['memory_count'], expected_categories) / expected_categories * 100
    ) if expected_categories > 0 else 0.0
    
    # 记忆生成率：实际生成的记忆数 / 期望记忆数
    # 此指标可能超过100%（如果生成的记忆比期望多）
    results['metrics']['memory_generation_rate'] = (
        results['memory_count'] / expected_memory_count * 100
    ) if expected_memory_count > 0 else 0.0
    
    results['metrics']['expected_categories'] = expected_categories
    results['metrics']['actual_memory_count'] = results['memory_count']
    
    if verbose:
        print(f"\n--- 记忆库状态 ---")
        print(f"记忆数量: {results['memory_count']}")
        
        # 显示期望的知识提取
        print(f"\n期望知识提取:")
        for category, items in expected_knowledge.items():
            print(f"  {category}: {len(items)} 条")
        
        print(f"\n📊 本对话指标:")
        print(f"  处理成功率: {results['metrics']['processing_success_rate']:.1f}%")
        print(f"  知识覆盖率: {results['metrics']['knowledge_coverage']:.1f}%")
        print(f"  记忆生成率: {results['metrics']['memory_generation_rate']:.1f}%")
    
    return results


async def run_all_tests(verbose: bool = True):
    """运行所有对话测试"""
    print("\n" + "="*70)
    print("Evolve 模式测试 - 复用 gradio_demo.py 计算流程")
    print("="*70)
    
    # 初始化测试器
    tester = EvolveModeTest()
    
    try:
        tester.initialize()
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        print("\n请检查 .env 文件中的 API 配置")
        return
    
    all_results = []
    
    # 测试所有7个对话
    for dialogue_num in range(1, 8):
        try:
            result = await test_dialogue(tester, dialogue_num, verbose=verbose)
            all_results.append(result)
            print(f"\n✅ 对话{dialogue_num} 测试完成")
        except Exception as e:
            print(f"\n❌ 对话{dialogue_num} 测试失败: {e}")
            all_results.append({
                'dialogue_id': f'对话{dialogue_num}',
                'error': str(e)
            })
    
    # 输出指标汇总表
    print("\n" + "="*70)
    print("📊 Evolve 模式测试指标汇总")
    print("="*70)
    
    # 表头
    print(f"\n{'对话ID':<10} {'消息数':<8} {'成功率':<10} {'知识覆盖':<10} {'记忆生成':<10} {'记忆数':<8}")
    print("-" * 70)
    
    # 用于计算平均值
    total_success = 0
    total_coverage = 0
    total_memory_rate = 0
    total_memory_count = 0
    valid_count = 0
    
    for result in all_results:
        dialogue_id = result.get('dialogue_id', 'Unknown')
        if 'error' in result:
            print(f"{dialogue_id:<10} {'错误':<8} {'-':<10} {'-':<10} {'-':<10} {'-':<8}")
        else:
            msgs = result.get('processed_messages', 0)
            mems = result.get('memory_count', 0)
            metrics = result.get('metrics', {})
            success_rate = metrics.get('processing_success_rate', 0)
            coverage = metrics.get('knowledge_coverage', 0)
            memory_rate = metrics.get('memory_generation_rate', 0)
            
            print(f"{dialogue_id:<10} {msgs:<8} {success_rate:>6.1f}%    {coverage:>6.1f}%    {memory_rate:>6.1f}%    {mems:<8}")
            
            total_success += success_rate
            total_coverage += coverage
            total_memory_rate += memory_rate
            total_memory_count += mems
            valid_count += 1
    
    # 输出平均值
    if valid_count > 0:
        print("-" * 70)
        avg_success = total_success / valid_count
        avg_coverage = total_coverage / valid_count
        avg_memory_rate = total_memory_rate / valid_count
        avg_memory = total_memory_count / valid_count
        print(f"{'平均值':<10} {'-':<8} {avg_success:>6.1f}%    {avg_coverage:>6.1f}%    {avg_memory_rate:>6.1f}%    {avg_memory:.1f}")
    
    print("\n" + "="*70)
    print("测试完成!")
    print("="*70)
    
    # 详细结果总结
    print("\n详细结果:")
    for result in all_results:
        dialogue_id = result.get('dialogue_id', 'Unknown')
        if 'error' in result:
            print(f"❌ {dialogue_id}: 失败 - {result['error']}")
        else:
            msgs = result.get('processed_messages', 0)
            mems = result.get('memory_count', 0)
            expected_cats = len(result.get('expected_knowledge', {}))
            print(f"✅ {dialogue_id}: {msgs}条消息 | {mems}条记忆 | {expected_cats}类期望知识")
    
    return all_results


# pytest 测试函数
class TestEvolveMode:
    """pytest 测试类"""
    
    @classmethod
    def setup_class(cls):
        """测试类初始化"""
        setup_logging(level=LogLevel.INFO, save_to_file=False)
        cls.tester = EvolveModeTest()
        try:
            cls.tester.initialize()
            cls.initialized = True
        except Exception as e:
            cls.initialized = False
            cls.init_error = str(e)
    
    def test_initialization(self):
        """测试初始化"""
        if not self.initialized:
            import pytest
            pytest.skip(f"LLM 初始化失败: {self.init_error}")
        assert self.tester.app is not None
        assert self.tester.engine is not None
        assert self.tester.config is not None
    
    def test_dialogue_files_exist(self):
        """测试对话文件存在"""
        for i in range(1, 8):
            dialogue_path = PROJECT_ROOT / "tests" / "dialogues" / f"dialogue_{i}.txt"
            assert dialogue_path.exists(), f"对话文件不存在: {dialogue_path}"
    
    def test_label_files_exist(self):
        """测试标签文件存在"""
        for i in range(1, 8):
            label_path = PROJECT_ROOT / "tests" / "labels" / f"dialogue_{i}_evolve.json"
            assert label_path.exists(), f"标签文件不存在: {label_path}"
    
    def test_label_format(self):
        """测试标签格式正确"""
        for i in range(1, 8):
            labels = load_evolve_labels(i)
            assert 'dialogue_id' in labels, f"对话{i}标签缺少 dialogue_id"
            assert 'dialogue_summary' in labels, f"对话{i}标签缺少 dialogue_summary"
            assert 'extracted_knowledge' in labels, f"对话{i}标签缺少 extracted_knowledge"
            assert 'memory_items' in labels, f"对话{i}标签缺少 memory_items"
    
    def test_knowledge_categories(self):
        """测试知识类别完整"""
        expected_categories = ['user_preferences', 'facts', 'patterns', 'strategies', 'experiences']
        for i in range(1, 8):
            labels = load_evolve_labels(i)
            knowledge = labels.get('extracted_knowledge', {})
            for cat in expected_categories:
                assert cat in knowledge, f"对话{i}缺少知识类别: {cat}"


if __name__ == "__main__":
    # 设置日志
    setup_logging(level=LogLevel.INFO, save_to_file=True, log_dir="logs")
    
    # 运行测试
    asyncio.run(run_all_tests(verbose=True))
