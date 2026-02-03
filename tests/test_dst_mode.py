#!/usr/bin/env python3
"""
DST 模式测试代码

复用 gradio_demo.py 中的 DST 模式计算流程
对 7 通电话对话进行对话状态追踪测试

使用方式:
    python -m pytest tests/test_dst_mode.py -v
    python tests/test_dst_mode.py  # 直接运行
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

from utils.llm_client import SimpleLLMClient
from dst import DialogueStateTracker, PromptManager
from scenarios import get_insurance_scenario
from utils.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class DSTModeTest:
    """
    DST 模式测试类
    
    复用 gradio_demo.py 中 UnifiedGradioDemo._init_dst_mode() 和 chat_dst_mode() 的计算流程
    """
    
    def __init__(self, max_history_turns: int = 10):
        """
        初始化 DST 测试
        
        Args:
            max_history_turns: 最大历史轮数
        """
        self.max_history_turns = max_history_turns
        self.llm_client = None
        self.tracker = None
        self.config = None
        
    def initialize(self):
        """
        初始化 DST 模式
        
        复用 gradio_demo.py 中 UnifiedGradioDemo._init_dst_mode() 的初始化流程
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
        
        # 创建 PromptManager，使用自定义模板（如果提供）
        # 复用 gradio_demo.py 的初始化逻辑
        pm = PromptManager(
            domain=self.config.name,
            enable_dynamic_slots=self.config.enable_dynamic_slots,
            custom_template=getattr(self.config, 'dst_prompt_template', None)
        )
        
        # 添加预定义槽位
        for slot_name, slot_desc in self.config.dst_slots.items():
            categorical_values = None
            if self.config.dst_categorical_slots and slot_name in self.config.dst_categorical_slots:
                categorical_values = self.config.dst_categorical_slots[slot_name]
            pm.add_slot(slot_name, slot_desc, categorical_values=categorical_values)
        
        # 创建 DialogueStateTracker
        # 复用 gradio_demo.py 的初始化参数
        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=self.max_history_turns,
            enable_history_summary=True,
            use_llm_summary=False
        )
        
        logger.info(f"✅ DST模式初始化完成 - 场景: {self.config.name}")
    
    def reset(self):
        """重置对话状态"""
        if self.tracker:
            self.tracker.current_state = {}
            self.tracker.dialogue_history = []
            logger.info("对话状态已重置")
    
    async def process_turn(self, system_utterance: str, user_utterance: str) -> Dict:
        """
        处理单轮对话
        
        复用 gradio_demo.py 中 chat_dst_mode() 的处理流程
        
        Args:
            system_utterance: 系统话语（销售员）
            user_utterance: 用户话语（客户）
            
        Returns:
            当前对话状态
        """
        # 调用 tracker.process_turn - 与 gradio_demo.py 完全一致
        state = await self.tracker.process_turn(
            system_utterance=system_utterance,
            user_utterance=user_utterance
        )
        return state
    
    def get_current_state(self) -> Dict:
        """获取当前累积状态"""
        return self.tracker.current_state.copy() if self.tracker else {}
    
    def get_dialogue_history(self) -> List:
        """获取对话历史"""
        return self.tracker.dialogue_history if self.tracker else []


def load_dialogue(dialogue_num: int) -> str:
    """加载对话文本"""
    dialogue_path = PROJECT_ROOT / "tests" / "dialogues" / f"dialogue_{dialogue_num}.txt"
    with open(dialogue_path, 'r', encoding='utf-8') as f:
        return f.read()


def load_dst_labels(dialogue_num: int) -> Dict:
    """加载 DST 标签"""
    label_path = PROJECT_ROOT / "tests" / "labels" / f"dialogue_{dialogue_num}_dst.json"
    with open(label_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_dialogue_turns(dialogue_text: str) -> List[Dict]:
    """
    解析对话文本为轮次列表
    
    Args:
        dialogue_text: 对话文本
        
    Returns:
        轮次列表，每个轮次包含 system_utterance 和 user_utterance
    """
    lines = dialogue_text.strip().split('\n')
    turns = []
    current_system = []
    current_user = []
    in_system = False
    in_user = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 跳过背景音和括号内的注释
        if line.startswith('（') and line.endswith('）'):
            continue
        if line.startswith('(') and line.endswith(')'):
            continue
            
        if line.startswith('销售员：') or line.startswith('销售员:'):
            # 如果之前有用户话语，先保存这一轮
            if current_user and current_system:
                turns.append({
                    'system_utterance': ' '.join(current_system),
                    'user_utterance': ' '.join(current_user)
                })
                current_system = []
                current_user = []
            
            # 开始收集销售员话语
            content = line.split('：', 1)[-1].split(':', 1)[-1].strip()
            if content:
                current_system.append(content)
            in_system = True
            in_user = False
            
        elif line.startswith('客户：') or line.startswith('客户:'):
            # 开始收集客户话语
            content = line.split('：', 1)[-1].split(':', 1)[-1].strip()
            if content:
                current_user.append(content)
            in_system = False
            in_user = True
        else:
            # 继续之前的话语
            if in_system and current_system:
                current_system[-1] += ' ' + line
            elif in_user and current_user:
                current_user[-1] += ' ' + line
    
    # 保存最后一轮
    if current_user and current_system:
        turns.append({
            'system_utterance': ' '.join(current_system),
            'user_utterance': ' '.join(current_user)
        })
    
    return turns


async def test_dialogue(tester: DSTModeTest, dialogue_num: int, verbose: bool = True) -> Dict:
    """
    测试单个对话
    
    Args:
        tester: DST测试器
        dialogue_num: 对话编号 (1-7)
        verbose: 是否输出详细信息
        
    Returns:
        测试结果
    """
    # 加载对话和标签
    dialogue_text = load_dialogue(dialogue_num)
    labels = load_dst_labels(dialogue_num)
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"测试对话 {dialogue_num}: {labels.get('description', '')}")
        print(f"{'='*60}")
    
    # 重置对话状态
    tester.reset()
    
    # 解析对话轮次
    turns = parse_dialogue_turns(dialogue_text)
    
    if verbose:
        print(f"解析到 {len(turns)} 轮对话")
    
    # 使用标签中的轮次（如果有的话）
    label_turns = labels.get('turns', [])
    
    results = {
        'dialogue_id': labels.get('dialogue_id', f'对话{dialogue_num}'),
        'total_turns': len(turns),
        'processed_turns': 0,
        'states': [],
        'final_state': None
    }
    
    # 处理每一轮对话
    # 使用标签中的轮次数据（已标注的关键轮次）
    for i, turn_label in enumerate(label_turns):
        system_utterance = turn_label.get('system_utterance', '')
        user_utterance = turn_label.get('user_utterance', '')
        expected_state = turn_label.get('expected_state', {})
        
        if verbose:
            print(f"\n--- 轮次 {i+1} ---")
            print(f"销售员: {system_utterance[:50]}...")
            print(f"客户: {user_utterance}")
        
        # 处理这一轮对话
        state = await tester.process_turn(system_utterance, user_utterance)
        
        if verbose:
            print(f"提取状态: {state}")
            if expected_state:
                print(f"预期状态: {expected_state}")
        
        results['states'].append({
            'turn_id': i + 1,
            'extracted_state': state,
            'expected_state': expected_state
        })
        results['processed_turns'] += 1
    
    # 获取最终累积状态
    results['final_state'] = tester.get_current_state()
    
    if verbose:
        print(f"\n--- 最终状态 ---")
        print(f"提取: {results['final_state']}")
        print(f"预期: {labels.get('final_state', {})}")
    
    return results


async def run_all_tests(verbose: bool = True):
    """运行所有对话测试"""
    print("\n" + "="*70)
    print("DST 模式测试 - 复用 gradio_demo.py 计算流程")
    print("="*70)
    
    # 初始化测试器
    tester = DSTModeTest(max_history_turns=10)
    
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
    
    # 输出总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)
    
    for result in all_results:
        dialogue_id = result.get('dialogue_id', 'Unknown')
        if 'error' in result:
            print(f"❌ {dialogue_id}: 失败 - {result['error']}")
        else:
            turns = result.get('processed_turns', 0)
            final_state = result.get('final_state', {})
            intent1 = final_state.get('intent_level1', 'N/A')
            intent2 = final_state.get('intent_level2', 'N/A')
            print(f"✅ {dialogue_id}: {turns}轮 | 一级意图: {intent1} | 二级意图: {intent2}")
    
    return all_results


# pytest 测试函数
class TestDSTMode:
    """pytest 测试类"""
    
    @classmethod
    def setup_class(cls):
        """测试类初始化"""
        setup_logging(level=LogLevel.INFO, save_to_file=False)
        cls.tester = DSTModeTest(max_history_turns=10)
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
        assert self.tester.tracker is not None
        assert self.tester.config is not None
    
    def test_dialogue_files_exist(self):
        """测试对话文件存在"""
        for i in range(1, 8):
            dialogue_path = PROJECT_ROOT / "tests" / "dialogues" / f"dialogue_{i}.txt"
            assert dialogue_path.exists(), f"对话文件不存在: {dialogue_path}"
    
    def test_label_files_exist(self):
        """测试标签文件存在"""
        for i in range(1, 8):
            label_path = PROJECT_ROOT / "tests" / "labels" / f"dialogue_{i}_dst.json"
            assert label_path.exists(), f"标签文件不存在: {label_path}"
    
    def test_label_format(self):
        """测试标签格式正确"""
        for i in range(1, 8):
            labels = load_dst_labels(i)
            assert 'dialogue_id' in labels, f"对话{i}标签缺少 dialogue_id"
            assert 'turns' in labels, f"对话{i}标签缺少 turns"
            assert 'final_state' in labels, f"对话{i}标签缺少 final_state"


if __name__ == "__main__":
    # 设置日志
    setup_logging(level=LogLevel.INFO, save_to_file=True, log_dir="logs")
    
    # 运行测试
    asyncio.run(run_all_tests(verbose=True))
