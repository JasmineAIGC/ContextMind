#!/usr/bin/env python3
"""
意图评测器 (Intent Evaluator)

为DST方法设计的意图评测框架，通过槽位变化推断隐式意图标签。

版本: v1.0
"""

from typing import Dict, List, Tuple, Any
from collections import Counter, defaultdict
from enum import Enum


class IntentType(Enum):
    """
    意图类型枚举
    
    基于对话状态追踪的常见意图分类
    """
    INFORM = "inform"          # 提供信息 - 新增/更新槽位
    REQUEST = "request"        # 请求信息 - 查询某个槽位
    CONFIRM = "confirm"        # 确认信息 - 重复已有槽位
    NEGATE = "negate"         # 否定/修改 - 更改之前的槽位值
    CHITCHAT = "chitchat"     # 闲聊 - 无槽位变化
    OTHER = "other"           # 其他


class IntentEvaluator:
    """
    意图评测器
    
    核心功能：
    1. 从槽位变化推断隐式意图（作为ground truth）
    2. 评测DST预测的意图
    3. 计算多维度评测指标
    
    设计原理：
    - TransferTOD数据集没有显式意图标签
    - 通过槽位变化模式推断隐式意图
    - 这种推断虽不完美，但提供了合理的baseline
    """
    
    def __init__(self):
        """
        初始化意图评测器
        """
        self.predictions = []  # [(predicted_intent, inferred_intent), ...]
        self.turn_details = []  # 每轮详细信息
        
    def infer_intent_from_slots(
        self, 
        turn_updates: Dict[str, Any],
        previous_state: Dict[str, Any],
        user_utterance: str = ""
    ) -> str:
        """
        从槽位变化推断隐式意图
        
        推断规则：
        1. 无槽位变化 → chitchat (闲聊)
        2. 槽位值为'?'或UNKNOWN → request (请求信息)
        3. 槽位值改变（之前存在） → negate (否定/修改)
        4. 新增槽位或更新槽位 → inform (提供信息)
        
        Args:
            turn_updates: 当前轮的槽位更新
            previous_state: 上一轮的对话状态
            user_utterance: 用户话语（可选，用于辅助判断）
            
        Returns:
            推断的意图类型
        """
        # 过滤掉'intent'槽位本身
        slot_updates = {k: v for k, v in turn_updates.items() if k != 'intent'}
        
        # 规则1: 无槽位变化
        if not slot_updates:
            return IntentType.CHITCHAT.value
        
        # 规则2: 检测请求意图（槽位值为特殊标记）
        for slot, value in slot_updates.items():
            value_str = str(value).lower() if value is not None else ""
            if value_str in ['?', 'unknown', 'null', '未知']:
                return IntentType.REQUEST.value
        
        # 规则3: 检测否定意图（修改已存在的槽位）
        for slot, value in slot_updates.items():
            if slot in previous_state and previous_state[slot] != value:
                # 槽位值发生变化
                return IntentType.NEGATE.value
        
        # 规则4: 默认为提供信息（新增槽位或首次赋值）
        return IntentType.INFORM.value
    
    def add_turn_evaluation(
        self,
        turn_id: int,
        predicted_intent: str,
        turn_updates: Dict[str, Any],
        previous_state: Dict[str, Any],
        user_utterance: str = "",
        dialogue_id: str = ""
    ) -> Dict[str, Any]:
        """
        添加一轮对话的意图评测
        
        Args:
            turn_id: 轮次ID
            predicted_intent: DST预测的意图
            turn_updates: 槽位更新
            previous_state: 之前的状态
            user_utterance: 用户话语
            dialogue_id: 对话ID
            
        Returns:
            评测详情
        """
        # 推断ground truth意图
        inferred_intent = self.infer_intent_from_slots(
            turn_updates, 
            previous_state,
            user_utterance
        )
        
        # 标准化预测意图
        predicted_intent = predicted_intent or IntentType.OTHER.value
        
        # 判断是否正确
        is_correct = (predicted_intent.lower() == inferred_intent.lower())
        
        # 记录详情
        detail = {
            'dialogue_id': dialogue_id,
            'turn_id': turn_id,
            'predicted': predicted_intent,
            'inferred': inferred_intent,
            'correct': is_correct,
            'turn_updates': turn_updates.copy(),
            'user_utterance': user_utterance
        }
        
        self.turn_details.append(detail)
        self.predictions.append((predicted_intent, inferred_intent))
        
        return detail
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """
        计算意图评测指标
        
        Returns:
            评测指标字典
        """
        if not self.predictions:
            return {
                'accuracy': 0.0,
                'total_turns': 0,
                'correct_turns': 0,
                'intent_distribution': {},
                'confusion_matrix': {},
                'error_analysis': {}
            }
        
        # 基础统计
        total = len(self.predictions)
        correct = sum(1 for pred, inf in self.predictions if pred.lower() == inf.lower())
        accuracy = correct / total if total > 0 else 0.0
        
        # 意图分布
        predicted_dist = Counter(pred for pred, _ in self.predictions)
        inferred_dist = Counter(inf for _, inf in self.predictions)
        
        # 混淆矩阵
        confusion = defaultdict(lambda: defaultdict(int))
        for pred, inf in self.predictions:
            confusion[inf][pred] += 1
        
        # 错误分析
        errors = [d for d in self.turn_details if not d['correct']]
        error_patterns = Counter(
            (d['predicted'], d['inferred']) for d in errors
        )
        
        return {
            'accuracy': accuracy,
            'total_turns': total,
            'correct_turns': correct,
            'predicted_distribution': dict(predicted_dist),
            'inferred_distribution': dict(inferred_dist),
            'confusion_matrix': {k: dict(v) for k, v in confusion.items()},
            'error_patterns': dict(error_patterns.most_common(10)),
            'error_count': len(errors)
        }
    
    def get_detailed_report(self) -> str:
        """
        生成详细的评测报告
        
        Returns:
            格式化的报告字符串
        """
        metrics = self.calculate_metrics()
        
        report = []
        report.append("=" * 70)
        report.append("意图评测报告 (Intent Evaluation Report)")
        report.append("=" * 70)
        report.append("")
        
        # 总体准确率
        report.append(f"总轮次数: {metrics['total_turns']}")
        report.append(f"正确轮次: {metrics['correct_turns']}")
        report.append(f"意图准确率: {metrics['accuracy']:.2%}")
        report.append("")
        
        # 意图分布对比
        report.append("-" * 70)
        report.append("意图分布对比")
        report.append("-" * 70)
        
        all_intents = set(metrics['predicted_distribution'].keys()) | \
                     set(metrics['inferred_distribution'].keys())
        
        report.append(f"{'意图类型':<15} {'预测数量':<12} {'推断数量':<12} {'差异':<10}")
        report.append("-" * 70)
        
        for intent in sorted(all_intents):
            pred_count = metrics['predicted_distribution'].get(intent, 0)
            inf_count = metrics['inferred_distribution'].get(intent, 0)
            diff = pred_count - inf_count
            diff_str = f"{diff:+d}" if diff != 0 else "0"
            report.append(f"{intent:<15} {pred_count:<12} {inf_count:<12} {diff_str:<10}")
        
        report.append("")
        
        # 混淆矩阵
        if metrics['confusion_matrix']:
            report.append("-" * 70)
            report.append("混淆矩阵 (行=Ground Truth, 列=Predicted)")
            report.append("-" * 70)
            
            # 获取所有意图类型
            all_intents_list = sorted(
                set(metrics['predicted_distribution'].keys()) | 
                set(metrics['inferred_distribution'].keys())
            )
            
            # 表头
            header = f"{'GT\\Pred':<12}"
            for intent in all_intents_list:
                header += f"{intent:<12}"
            report.append(header)
            report.append("-" * 70)
            
            # 数据行
            for true_intent in all_intents_list:
                row = f"{true_intent:<12}"
                for pred_intent in all_intents_list:
                    count = metrics['confusion_matrix'].get(true_intent, {}).get(pred_intent, 0)
                    row += f"{count:<12}"
                report.append(row)
            
            report.append("")
        
        # 错误模式分析
        if metrics['error_patterns']:
            report.append("-" * 70)
            report.append(f"常见错误模式 (Top 10) - 总错误数: {metrics['error_count']}")
            report.append("-" * 70)
            report.append(f"{'预测意图':<15} {'实际意图':<15} {'出现次数':<10}")
            report.append("-" * 70)
            
            for (pred, inf), count in metrics['error_patterns'].items():
                report.append(f"{pred:<15} {inf:<15} {count:<10}")
            
            report.append("")
        
        report.append("=" * 70)
        
        return "\n".join(report)
    
    def reset(self):
        """
        重置评测器状态
        """
        self.predictions = []
        self.turn_details = []
