#!/usr/bin/env python3
"""
意图评测器 (Intent Evaluator)

为DST方法设计的意图评测框架，通过槽位变化推断隐式意图标签。

版本: v1.0
"""

from typing import Dict, List, Tuple, Any, Optional
from collections import Counter, defaultdict
from enum import Enum
import os

# 可选导入matplotlib用于可视化
try:
    import matplotlib
    matplotlib.use('Agg')  # 使用非GUI后端
    import matplotlib.pyplot as plt
    import seaborn as sns
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class TaskRelevance(Enum):
    """任务相关性"""
    TASK_RELATED = "task_related"           # 与任务相关
    TASK_INDEPENDENT = "task_independent"   # 与任务无关


class IntentType(Enum):
    """
    重新设计的意图类型枚举（两层架构）
    
    设计原则：
    1. 区分任务相关性（第一层）
    2. 明确对话行为（第二层）
    3. 支持意图转换追踪
    
    版本: v2.0
    """
    # === 任务相关意图（Task-Related Intents）===
    PROVIDE_INFO = "provide_info"       # 提供信息 - 用户主动提供槽位值
    REQUEST_INFO = "request_info"       # 请求信息 - 用户询问槽位值
    CONFIRM_INFO = "confirm_info"       # 确认信息 - 用户确认系统提供的信息
    CORRECT_INFO = "correct_info"       # 更正信息 - 用户纠正之前的槽位值
    ACKNOWLEDGE = "acknowledge"         # 应答确认 - 简单的"是"、"好的"等
    
    # === 任务无关意图（Task-Independent Intents）===
    CHITCHAT = "chitchat"              # 闲聊 - 日常对话
    GREETING = "greeting"              # 问候 - 开场问候
    FAREWELL = "farewell"              # 告别 - 结束对话
    THANKING = "thanking"              # 感谢 - 表达感谢
    
    # === 元意图（Meta Intents）===
    CLARIFICATION = "clarification"    # 澄清/反问 - 请求澄清
    UNKNOWN = "unknown"                # 未知 - 无法识别的意图


class DialoguePhase(Enum):
    """
    对话阶段枚举
    
    任务导向对话的典型阶段序列
    """
    OPENING = "opening"                        # 开场阶段
    INFORMATION_GATHERING = "info_gathering"   # 信息收集阶段
    SLOT_FILLING = "slot_filling"             # 槽位填充阶段
    CONFIRMATION = "confirmation"              # 确认阶段
    COMPLETION = "completion"                  # 完成阶段
    CLOSING = "closing"                        # 结束阶段


class IntentEvaluator:
    """
    意图评测器 v2.0
    
    核心功能：
    1. 从槽位变化推断隐式意图（作为ground truth）
    2. 评测DST预测的意图
    3. 计算多维度评测指标
    4. 追踪意图转换和对话阶段
    
    设计原理：
    - TransferTOD数据集没有显式意图标签
    - 通过槽位变化模式推断隐式意图
    - 支持两层意图架构（任务相关性 + 对话行为）
    - 追踪意图转换模式和对话阶段
    """
    
    def __init__(self):
        """
        初始化意图评测器
        """
        self.predictions = []  # [(predicted_intent, inferred_intent), ...]
        self.turn_details = []  # 每轮详细信息
        self.intent_transitions = []  # 意图转换序列
        self.current_phase = DialoguePhase.OPENING  # 当前对话阶段
        
    def infer_intent_from_slots(
        self, 
        turn_updates: Dict[str, Any],
        previous_state: Dict[str, Any],
        user_utterance: str = "",
        turn_id: int = 0
    ) -> Tuple[str, str]:
        """
        从槽位变化推断隐式意图（v2.0）
        
        新版推断规则：
        1. 考虑任务相关性（第一层）
        2. 识别具体对话行为（第二层）
        3. 考虑对话上下文（轮次、历史意图等）
        
        Args:
            turn_updates: 当前轮的槽位更新
            previous_state: 上一轮的对话状态
            user_utterance: 用户话语（可选，用于辅助判断）
            turn_id: 轮次ID（用于判断对话阶段）
            
        Returns:
            (intent_type, task_relevance) - 意图类型和任务相关性
        """
        # 过滤掉'intent'槽位本身
        slot_updates = {k: v for k, v in turn_updates.items() if k != 'intent'}
        
        # === 规则1: 任务无关意图判断 ===
        
        # 1.1 问候（通常在开场）
        if turn_id == 0 and not slot_updates:
            return IntentType.GREETING.value, TaskRelevance.TASK_INDEPENDENT.value
        
        # 1.2 告别（通常在结束）
        if self._is_farewell(user_utterance):
            return IntentType.FAREWELL.value, TaskRelevance.TASK_INDEPENDENT.value
        
        # 1.3 感谢
        if self._is_thanking(user_utterance):
            return IntentType.THANKING.value, TaskRelevance.TASK_INDEPENDENT.value
        
        # 1.4 闲聊（无槽位变化且非特殊场景）
        if not slot_updates and turn_id > 0:
            return IntentType.CHITCHAT.value, TaskRelevance.TASK_INDEPENDENT.value
        
        # === 规则2: 任务相关意图判断 ===
        
        # 2.1 请求信息（槽位值为特殊标记）
        if self._has_request_marker(slot_updates):
            return IntentType.REQUEST_INFO.value, TaskRelevance.TASK_RELATED.value
        
        # 2.2 更正信息（修改已存在的槽位值）
        if self._is_correction(slot_updates, previous_state):
            return IntentType.CORRECT_INFO.value, TaskRelevance.TASK_RELATED.value
        
        # 2.3 确认信息（槽位值与之前相同，表示确认）
        if self._is_confirmation(slot_updates, previous_state):
            return IntentType.CONFIRM_INFO.value, TaskRelevance.TASK_RELATED.value
        
        # 2.4 应答确认（简单的槽位更新，通常是回答系统问题）
        if self._is_acknowledge(slot_updates, user_utterance):
            return IntentType.ACKNOWLEDGE.value, TaskRelevance.TASK_RELATED.value
        
        # 2.5 提供信息（默认，新增或更新槽位）
        if slot_updates:
            return IntentType.PROVIDE_INFO.value, TaskRelevance.TASK_RELATED.value
        
        # === 规则3: 未知意图 ===
        return IntentType.UNKNOWN.value, TaskRelevance.TASK_INDEPENDENT.value
    
    def _has_request_marker(self, slot_updates: Dict[str, Any]) -> bool:
        """检测是否包含请求标记"""
        for slot, value in slot_updates.items():
            value_str = str(value).lower() if value is not None else ""
            if value_str in ['?', 'unknown', 'null', '未知', 'none']:
                return True
        return False
    
    def _is_correction(self, slot_updates: Dict[str, Any], previous_state: Dict[str, Any]) -> bool:
        """检测是否为更正（修改已有槽位）"""
        for slot, value in slot_updates.items():
            if slot in previous_state and previous_state[slot] != value:
                # 槽位值发生变化
                return True
        return False
    
    def _is_confirmation(self, slot_updates: Dict[str, Any], previous_state: Dict[str, Any]) -> bool:
        """检测是否为确认（重复已有槽位值）"""
        for slot, value in slot_updates.items():
            if slot in previous_state and previous_state[slot] == value:
                # 槽位值相同，可能是确认
                return True
        return False
    
    def _is_acknowledge(self, slot_updates: Dict[str, Any], user_utterance: str) -> bool:
        """检测是否为简单应答（如"好的"、"是的"）"""
        # 简单启发式：单个槽位更新且话语很短
        if len(slot_updates) == 1 and len(user_utterance) < 10:
            return True
        return False
    
    def _is_farewell(self, user_utterance: str) -> bool:
        """检测是否为告别"""
        farewell_keywords = ['再见', '谢谢', '拜拜', 'bye', 'goodbye', '结束']
        utterance_lower = user_utterance.lower()
        return any(kw in utterance_lower for kw in farewell_keywords)
    
    def _is_thanking(self, user_utterance: str) -> bool:
        """检测是否为感谢"""
        thank_keywords = ['谢谢', '感谢', 'thanks', 'thank you']
        utterance_lower = user_utterance.lower()
        return any(kw in utterance_lower for kw in thank_keywords)
    
    def infer_dialogue_phase(
        self,
        turn_id: int,
        slot_updates: Dict[str, Any],
        previous_state: Dict[str, Any],
        total_turns: int = 0
    ) -> str:
        """
        推断当前对话阶段
        
        Args:
            turn_id: 当前轮次ID
            slot_updates: 槽位更新
            previous_state: 之前的状态
            total_turns: 总轮次数（如果已知）
            
        Returns:
            对话阶段
        """
        # 开场阶段（前1-2轮）
        if turn_id <= 1:
            return DialoguePhase.OPENING.value
        
        # 结束阶段（最后1-2轮或无槽位更新）
        if total_turns > 0 and turn_id >= total_turns - 2:
            return DialoguePhase.CLOSING.value
        
        # 确认阶段（槽位值重复）
        if self._is_confirmation(slot_updates, previous_state):
            return DialoguePhase.CONFIRMATION.value
        
        # 槽位填充阶段（有槽位更新）
        if slot_updates:
            # 如果已有较多槽位，可能在确认
            if len(previous_state) >= 3:
                return DialoguePhase.CONFIRMATION.value
            else:
                return DialoguePhase.SLOT_FILLING.value
        
        # 信息收集阶段（早期，槽位较少）
        if len(previous_state) < 2:
            return DialoguePhase.INFORMATION_GATHERING.value
        
        # 默认槽位填充
        return DialoguePhase.SLOT_FILLING.value
    
    def add_turn_evaluation(
        self,
        turn_id: int,
        predicted_intent: str,
        turn_updates: Dict[str, Any],
        previous_state: Dict[str, Any],
        user_utterance: str = "",
        dialogue_id: str = "",
        total_turns: int = 0
    ) -> Dict[str, Any]:
        """
        添加一轮对话的意图评测（v2.0）
        
        Args:
            turn_id: 轮次ID
            predicted_intent: DST预测的意图
            turn_updates: 槽位更新
            previous_state: 之前的状态
            user_utterance: 用户话语
            dialogue_id: 对话ID
            total_turns: 总轮次数
            
        Returns:
            评测详情
        """
        # 推断ground truth意图（返回意图类型和任务相关性）
        inferred_intent, task_relevance = self.infer_intent_from_slots(
            turn_updates, 
            previous_state,
            user_utterance,
            turn_id
        )
        
        # 推断对话阶段
        dialogue_phase = self.infer_dialogue_phase(
            turn_id,
            turn_updates,
            previous_state,
            total_turns
        )
        
        # 标准化预测意图
        predicted_intent = predicted_intent or IntentType.UNKNOWN.value
        
        # 判断是否正确
        is_correct = (predicted_intent.lower() == inferred_intent.lower())
        
        # 记录意图转换
        if self.turn_details:
            previous_intent = self.turn_details[-1]['inferred_intent']
            transition = (previous_intent, inferred_intent)
            self.intent_transitions.append(transition)
        
        # 更新当前阶段
        self.current_phase = dialogue_phase
        
        # 记录详情
        detail = {
            'dialogue_id': dialogue_id,
            'turn_id': turn_id,
            'predicted_intent': predicted_intent,
            'inferred_intent': inferred_intent,
            'task_relevance': task_relevance,
            'dialogue_phase': dialogue_phase,
            'correct': is_correct,
            'turn_updates': turn_updates.copy(),
            'user_utterance': user_utterance
        }
        
        self.turn_details.append(detail)
        self.predictions.append((predicted_intent, inferred_intent))
        
        return detail
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """
        计算意图评测指标（v2.0 - 增强版）
        
        Returns:
            评测指标字典，包括：
            - 基础准确率
            - 意图分布
            - 混淆矩阵
            - 错误分析
            - 意图转换分析（新增）
            - 对话阶段分析（新增）
            - 任务相关性统计（新增）
        """
        if not self.predictions:
            return {
                'accuracy': 0.0,
                'total_turns': 0,
                'correct_turns': 0,
                'intent_distribution': {},
                'confusion_matrix': {},
                'error_analysis': {},
                'transition_analysis': {},
                'phase_distribution': {},
                'task_relevance_stats': {}
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
            (d['predicted_intent'], d['inferred_intent']) for d in errors
        )
        
        # 意图转换分析（新增）
        transition_stats = Counter(self.intent_transitions)
        
        # 对话阶段分布（新增）
        phase_dist = Counter(d['dialogue_phase'] for d in self.turn_details)
        
        # 任务相关性统计（新增）
        task_relevance_dist = Counter(d.get('task_relevance', 'unknown') for d in self.turn_details)
        
        # 按阶段的意图分布（新增）
        phase_intent_dist = defaultdict(Counter)
        for d in self.turn_details:
            phase = d['dialogue_phase']
            intent = d['inferred_intent']
            phase_intent_dist[phase][intent] += 1
        
        return {
            'accuracy': accuracy,
            'total_turns': total,
            'correct_turns': correct,
            'predicted_distribution': dict(predicted_dist),
            'inferred_distribution': dict(inferred_dist),
            'confusion_matrix': {k: dict(v) for k, v in confusion.items()},
            'error_patterns': dict(error_patterns.most_common(10)),
            'error_count': len(errors),
            'transition_stats': dict(transition_stats.most_common(15)),
            'transition_count': len(self.intent_transitions),
            'phase_distribution': dict(phase_dist),
            'task_relevance_stats': dict(task_relevance_dist),
            'phase_intent_distribution': {k: dict(v) for k, v in phase_intent_dist.items()}
        }
    
    def plot_confusion_matrix(self, output_path: str = "confusion_matrix.png") -> Optional[str]:
        """
        生成混淆矩阵可视化图表
        
        Args:
            output_path: 输出图片的路径
            
        Returns:
            保存的图片路径，如果matplotlib不可用则返回None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None
        
        metrics = self.calculate_metrics()
        confusion = metrics['confusion_matrix']
        
        if not confusion:
            return None
        
        # 获取所有意图类型
        all_intents = sorted(
            set(metrics['predicted_distribution'].keys()) | 
            set(metrics['inferred_distribution'].keys())
        )
        
        # 构建混淆矩阵数组
        import numpy as np
        matrix_size = len(all_intents)
        matrix = np.zeros((matrix_size, matrix_size))
        
        for i, true_intent in enumerate(all_intents):
            for j, pred_intent in enumerate(all_intents):
                matrix[i, j] = confusion.get(true_intent, {}).get(pred_intent, 0)
        
        # 创建图表
        plt.figure(figsize=(12, 10))
        
        # 使用seaborn绘制热图
        sns.heatmap(
            matrix,
            annot=True,
            fmt='g',
            cmap='Blues',
            xticklabels=all_intents,
            yticklabels=all_intents,
            cbar_kws={'label': '数量'},
            square=True,
            linewidths=0.5,
            linecolor='gray'
        )
        
        plt.title('意图混淆矩阵 (Intent Confusion Matrix)\n行=Ground Truth, 列=Predicted', 
                 fontsize=14, fontweight='bold', pad=20)
        plt.xlabel('预测意图 (Predicted Intent)', fontsize=12, fontweight='bold')
        plt.ylabel('实际意图 (Ground Truth Intent)', fontsize=12, fontweight='bold')
        
        # 旋转标签以提高可读性
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图片
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def get_detailed_report(
        self, 
        save_confusion_plot: bool = True, 
        plot_path: str = "confusion_matrix.png",
        include_confusion_matrix: bool = True
    ) -> str:
        """
        生成简化的评测报告（仅数值结果）
        
        Args:
            save_confusion_plot: 是否保存混淆矩阵图表
            plot_path: 混淆矩阵图表保存路径
            include_confusion_matrix: 是否在报告中包含混淆矩阵文本（默认True）
            
        Returns:
            格式化的报告字符串，仅包括核心数值
        """
        metrics = self.calculate_metrics()
        
        report = []
        report.append("=" * 70)
        report.append("意图评测报告 (Intent Evaluation Report)")
        report.append("=" * 70)
        report.append("")
        
        # 总体准确率（仅核心数值）
        report.append(f"总轮次数: {metrics['total_turns']}")
        report.append(f"正确轮次: {metrics['correct_turns']}")
        report.append(f"意图准确率: {metrics['accuracy']:.2%}")
        report.append("")
        
        # 添加说明
        report.append("说明：")
        report.append("  - 意图准确率: 预测意图与推断意图完全一致的轮次占比")
        
        # 如果准确率为0%，添加提示
        if metrics['accuracy'] == 0 and metrics['total_turns'] > 0:
            report.append("")
            report.append("⚠️  提示：意图准确率为0%可能的原因：")
            report.append("  1. DST未配置意图提取功能（默认意图为'未识别'）")
            report.append("  2. DST意图格式与推断意图格式不匹配")
            report.append("     - DST预测: 中文意图（如'提供信息'）或'未识别'")
            report.append("     - 推断意图: 英文枚举值（如'provide_info'）")
            report.append("  3. 需要在DST配置中启用意图提取，并确保格式一致")
        
        report.append("")
        
        # 混淆矩阵 - 仅保存图表，不打印
        if metrics['confusion_matrix']:
            report.append("-" * 70)
            report.append("混淆矩阵 (Confusion Matrix)")
            report.append("-" * 70)
            
            # 尝试生成可视化图表
            plot_saved = False
            if save_confusion_plot and MATPLOTLIB_AVAILABLE:
                try:
                    saved_path = self.plot_confusion_matrix(plot_path)
                    if saved_path:
                        report.append(f"✅ 混淆矩阵可视化已保存到: {saved_path}")
                        plot_saved = True
                except Exception as e:
                    report.append(f"⚠️  混淆矩阵可视化生成失败: {str(e)}")
            
            if not plot_saved and not MATPLOTLIB_AVAILABLE:
                report.append("ℹ️  提示: 安装matplotlib和seaborn可查看可视化混淆矩阵")
            
            report.append("")
        
        report.append("=" * 70)
        
        return "\n".join(report)
    
    def reset(self):
        """
        重置评测器状态
        """
        self.predictions = []
        self.turn_details = []
        self.intent_transitions = []
        self.current_phase = DialoguePhase.OPENING
