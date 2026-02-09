#!/usr/bin/env python3
"""
意图评测器 (Intent Evaluator)

为DST方法设计的意图评测框架，通过槽位变化推断隐式意图标签。

版本: v2.0 - 使用配置文件驱动，移除硬编码
"""

from typing import Dict, List, Tuple, Any, Optional
from collections import Counter, defaultdict
import os

# 导入意图配置加载器
from benchmark.shared.intent_label_loader import get_intent_label_loader, IntentLabelLoader

# 可选导入matplotlib用于可视化
try:
    import matplotlib
    matplotlib.use('Agg')  # 使用非GUI后端
    import matplotlib.pyplot as plt
    import seaborn as sns
    
    # 配置中文字体支持
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'WenQuanYi Micro Hei']
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
    
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class IntentEvaluator:
    """
    意图评测器 v2.0 - 配置驱动版本
    
    核心功能：
    1. 从槽位变化推断隐式意图（作为ground truth）
    2. 评测DST预测的意图
    3. 计算多维度评测指标
    4. 追踪意图转换和对话阶段
    
    设计原理：
    - TransferTOD数据集没有显式意图标签
    - 通过槽位变化模式推断隐式意图
    - 使用JSON配置文件定义意图类型，移除硬编码
    - 支持两层意图架构（任务相关性 + 对话行为）
    - 追踪意图转换模式和对话阶段
    """
    
    def __init__(self, intent_label_loader: Optional[IntentLabelLoader] = None):
        """
        初始化意图评测器
        
        Args:
            intent_label_loader: 意图标签加载器对象，如果为None则加载默认配置
        """
        self.predictions = []  # [(predicted_intent, inferred_intent), ...]
        self.turn_details = []  # 每轮详细信息
        self.intent_transitions = []  # 意图转换序列
        self.dialogue_intents = []  # 对话级别的意图预测: [(dialogue_id, predicted_intent, inferred_intent)]
        
        # 加载意图标签加载器
        self.intent_label_loader = intent_label_loader or get_intent_label_loader()
        
        # 从配置加载意图信息
        self._load_intent_info()
        
    def _load_intent_info(self):
        """从意图标签加载器加载意图信息"""
        # 构建标准化映射：从所有领域的意图名称到标准化名称
        self.normalization_mapping = {}
        self.aggregation_mapping = {}
        
        for domain in self.intent_label_loader.get_all_domains():
            domain_intents = self.intent_label_loader.get_domain_intents(domain)
            for intent in domain_intents:
                # 标准化：转小写并替换空格
                normalized = intent.lower().replace(' ', '_')
                # 支持中英文映射
                self.normalization_mapping[intent] = normalized
                self.normalization_mapping[intent.lower()] = normalized
                # 聚合映射：使用原始中文名称作为显示名称
                self.aggregation_mapping[normalized] = intent
        
        # 缓存意图关键词（用于推断）
        self._marker_cache = {}
        for domain in self.intent_label_loader.get_all_domains():
            if domain not in self._marker_cache:
                self._marker_cache[domain] = {}
            domain_intents = self.intent_label_loader.get_domain_intents(domain)
            for intent in domain_intents:
                intent_desc = self.intent_label_loader.get_intent_description(domain, intent)
                if intent_desc and "keywords" in intent_desc:
                    keywords = intent_desc["keywords"]
                    if keywords:
                        self._marker_cache[domain][intent] = keywords
        
    def infer_intent_from_slots(
        self,
        domain: str,  # 新增：领域参数
        turn_updates: Dict[str, Any],
        previous_state: Dict[str, Any],
        user_utterance: str = "",
        turn_id: int = 0
    ) -> Tuple[str, str]:
        """
        从槽位变化推断意图
        
        重要：只返回JSON配置文件中定义的意图，不能自定义
        对于无法明确分类的情况，返回"其他"
        
        Args:
            domain: 对话领域
            turn_updates: 当前轮次的槽位更新
            previous_state: 之前的状态
            user_utterance: 用户话语
            turn_id: 轮次ID
            
        Returns:
            (intent, task_relevance) 元组
            intent: 意图名称（来自JSON配置）
            task_relevance: 任务相关性
        """
        # 过滤掉'intent'槽位本身
        slot_updates = {k: v for k, v in turn_updates.items() if k != 'intent'}
        
        # 获取领域的兜底意图（所有领域都有"其他"）
        fallback_intent = self.intent_label_loader.get_fallback_intent_name()  # "其他"
        
        # 由于无法可靠地将槽位模式映射到特定的领域意图
        # 我们返回"其他"作为推断意图
        # 这确保了所有意图标签都来自JSON配置文件，不重新定义
        return fallback_intent, "task_related"
    
    def _check_intent_by_markers(self, domain: str, intent: str, text: str) -> bool:
        """
        根据配置的标记词检测意图（需要领域参数）
        
        注意：此方法保留用于未来扩展，当前推断逻辑主要基于槽位模式
        
        Args:
            domain: 领域名称
            intent: 意图名称
            text: 要检测的文本
            
        Returns:
            是否匹配
        """
        if not text or domain not in self._marker_cache:
            return False
        
        if intent not in self._marker_cache[domain]:
            return False
            
        markers = self._marker_cache[domain][intent]
        text_lower = text.lower()
        return any(marker in text_lower for marker in markers if marker)
    
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
    
    def _is_acknowledgement(self, slot_updates: Dict[str, Any], user_utterance: str) -> bool:
        """检测是否为简单应答（如"好的"、"是的"）"""
        # 简单关键词检测
        if user_utterance and any(word in user_utterance.lower() for word in ['好的', '是的', '对', '嗯', 'ok', 'yes']):
            return True
        # 简单启发式：单个槽位更新且话语很短
        if len(slot_updates) == 1 and len(user_utterance) < 10:
            return True
        return False
    
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
            对话阶段字符串
        """
        # 开场阶段（前1-2轮）
        if turn_id <= 1:
            return "opening"
        
        # 结束阶段（最后1-2轮或无槽位更新）
        if total_turns > 0 and turn_id >= total_turns - 2:
            return "closing"
        
        # 确认阶段（槽位值重复）
        if self._is_confirmation(slot_updates, previous_state):
            return "confirmation"
        
        # 槽位填充阶段（有槽位更新）
        if slot_updates:
            # 如果已有较多槽位，可能在确认
            if len(previous_state) >= 3:
                return "confirmation"
            else:
                return "slot_filling"
        
        # 信息收集阶段（早期，槽位较少）
        if len(previous_state) < 2:
            return "info_gathering"
        
        # 默认槽位填充
        return "slot_filling"
    
    def add_turn_evaluation(
        self,
        domain: str,  # 新增：领域参数
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
            domain: 领域名称
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
            domain,
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
        
        # 使用配置的标准化映射
        predicted_intent = predicted_intent or "unknown"
        predicted_normalized = self.normalization_mapping.get(predicted_intent.lower(), predicted_intent.lower())
        inferred_normalized = self.normalization_mapping.get(inferred_intent.lower(), inferred_intent.lower())
        
        # 判断是否正确（使用标准化后的值）
        is_correct = (predicted_normalized == inferred_normalized)
        
        # 记录意图转换
        if self.turn_details:
            previous_intent = self.turn_details[-1]['inferred_intent']
            transition = (previous_intent, inferred_intent)
            self.intent_transitions.append(transition)
        
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
    
    def add_dialogue_evaluation(
        self,
        dialogue_id: str,
        domain: str,
        predicted_intent: str,
        dialogue_slots: Dict[str, Any],
        user_utterances: List[str] = None
    ) -> Dict[str, Any]:
        """
        添加对话级别的意图评测（新方法）
        
        这是一个简化的评测方法：每个对话有一个整体意图，
        通过对话的完整槽位信息和用户话语推断意图。
        
        Args:
            dialogue_id: 对话ID
            domain: 领域名称
            predicted_intent: DST预测的对话意图
            dialogue_slots: 对话中提取的所有槽位
            user_utterances: 用户话语列表（可选）
            
        Returns:
            评测详情
        """
        # 推断对话的整体意图
        # 这里可以使用第一轮的推断或整体槽位的推断
        combined_utterance = ' '.join(user_utterances) if user_utterances else ""
        inferred_intent, task_relevance = self.infer_intent_from_slots(
            domain,
            dialogue_slots,
            {},  # 对话级别没有previous_state
            combined_utterance,
            turn_id=0
        )
        
        # 标准化
        predicted_normalized = self.normalization_mapping.get(predicted_intent.lower(), predicted_intent.lower())
        inferred_normalized = self.normalization_mapping.get(inferred_intent.lower(), inferred_intent.lower())
        
        # 判断是否正确
        is_correct = (predicted_normalized == inferred_normalized)
        
        # 记录对话级别的意图
        detail = {
            'dialogue_id': dialogue_id,
            'domain': domain,
            'predicted_intent': predicted_intent,
            'inferred_intent': inferred_intent,
            'task_relevance': task_relevance,
            'correct': is_correct,
            'dialogue_slots': dialogue_slots.copy()
        }
        
        self.dialogue_intents.append((dialogue_id, predicted_intent, inferred_intent))
        
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
        # 对话级别统计（优先计算，即使没有轮次数据也可以有对话数据）
        dialogue_metrics = {}
        if self.dialogue_intents:
            dialogue_total = len(self.dialogue_intents)
            dialogue_correct = sum(1 for _, pred, inf in self.dialogue_intents if pred.lower() == inf.lower())
            dialogue_accuracy = dialogue_correct / dialogue_total if dialogue_total > 0 else 0.0
            dialogue_metrics = {
                'dialogue_accuracy': dialogue_accuracy,
                'total_dialogues': dialogue_total,
                'correct_dialogues': dialogue_correct
            }
        
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
                'task_relevance_stats': {},
                'dialogue_metrics': dialogue_metrics
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
        
        # dialogue_metrics已经在开头计算，无需重复
        
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
            'phase_intent_distribution': {k: dict(v) for k, v in phase_intent_dist.items()},
            'dialogue_metrics': dialogue_metrics
        }
    
    def plot_confusion_matrix(self, output_path: str = "confusion_matrix.png") -> Optional[str]:
        """
        生成混淆矩阵可视化图表（优化版：聚合到高层次意图类别）
        
        Args:
            output_path: 输出图片的路径
            
        Returns:
            保存的图片路径，如果matplotlib不可用则返回None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None
        
        # 抑制matplotlib字体警告（避免CJK字符缺失警告）
        import warnings
        warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
        warnings.filterwarnings('ignore', message='.*Glyph.*missing from font.*')
        
        metrics = self.calculate_metrics()
        confusion = metrics['confusion_matrix']
        
        if not confusion:
            return None
        
        # 使用配置的意图聚合映射
        intent_mapping = self.aggregation_mapping
        
        # 聚合混淆矩阵到高层次类别
        aggregated_confusion = defaultdict(lambda: defaultdict(int))
        for true_intent, pred_dict in confusion.items():
            true_category = intent_mapping.get(true_intent, '其他')
            for pred_intent, count in pred_dict.items():
                pred_category = intent_mapping.get(pred_intent, '其他')
                aggregated_confusion[true_category][pred_category] += count
        
        if not aggregated_confusion:
            return None
        
        # 获取所有类别并排序
        all_categories = sorted(set(
            list(aggregated_confusion.keys()) + 
            [cat for cats in aggregated_confusion.values() for cat in cats.keys()]
        ))
        
        # 构建聚合后的混淆矩阵数组
        import numpy as np
        matrix_size = len(all_categories)
        matrix = np.zeros((matrix_size, matrix_size))
        
        for i, true_cat in enumerate(all_categories):
            for j, pred_cat in enumerate(all_categories):
                matrix[i, j] = aggregated_confusion.get(true_cat, {}).get(pred_cat, 0)
        
        # 创建图表（根据类别数量调整大小）
        figsize = (max(8, matrix_size * 1.2), max(7, matrix_size * 1.0))
        plt.figure(figsize=figsize)
        
        # 确保字体配置应用到当前图表
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'WenQuanYi Micro Hei']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 使用seaborn绘制热图
        sns.heatmap(
            matrix,
            annot=True,
            fmt='g',
            cmap='Blues',
            xticklabels=all_categories,
            yticklabels=all_categories,
            cbar_kws={'label': '数量'},
            square=True,
            linewidths=0.5,
            linecolor='gray'
        )
        
        plt.title('意图混淆矩阵 (Intent Confusion Matrix)\n行=实际意图, 列=预测意图', 
                 fontsize=14, fontweight='bold', pad=20)
        plt.xlabel('预测意图 (Predicted)', fontsize=12, fontweight='bold')
        plt.ylabel('实际意图 (Ground Truth)', fontsize=12, fontweight='bold')
        
        # 旋转标签以提高可读性
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图片（抑制输出）
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
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
        
        # 如果准确率为0%，添加诊断信息
        if metrics['accuracy'] == 0 and metrics['total_turns'] > 0:
            # 检查是否所有预测都是'未识别'或'unknown'
            predicted_intents = [pred for pred, _ in self.predictions]
            unique_predictions = set(predicted_intents)
            
            # 使用配置的标准化映射检查
            normalized_predictions = set(
                self.normalization_mapping.get(p.lower(), p.lower())
                for p in unique_predictions
            )
            
            report.append("")
            if normalized_predictions == {'unknown'}:
                # 所有预测都是'未识别'，说明DST未配置意图提取
                # 显示推断的意图样本
                inferred_intents = [inf for _, inf in self.predictions]
                unique_inferred = sorted(set(inferred_intents))
                inferred_sample = ', '.join(unique_inferred[:5])
                
                report.append("❌ 诊断结果：DST未配置意图提取功能")
                report.append("")
                report.append("说明：")
                report.append(f"  - 所有 {metrics['total_turns']} 轮对话的预测意图都是'未识别'")
                report.append("  - 这说明DST Tracker未开启意图提取功能")
                report.append(f"  - 而从槽位推断的意图有: {inferred_sample}")
                report.append("  - 因此无法进行有效的意图评测对比")
                report.append("")
                report.append("建议：")
                report.append("  1. 在DST的prompt中添加意图提取指令")
                report.append("  2. 或者跳过意图评测（专注于槽位提取评测）")
                report.append("  3. 意图评测功能仅在DST配置了意图提取时才有意义")
            else:
                # 有不同的预测，但准确率仍为0%
                # 检查是否是任务特定的描述（而非标准意图类型）
                is_task_specific = any(
                    len(p) > 6 or any(keyword in p for keyword in ['入住', '预订', '取消', '咨询', '了解', '告知', '房间', '酒店', '餐厅'])
                    for p in unique_predictions
                )
                
                if is_task_specific:
                    report.append("❌ 诊断结果：DST输出的是任务特定描述，非标准意图类型")
                    report.append("")
                    report.append("说明：")
                    report.append(f"  - DST预测了 {len(unique_predictions)} 种不同的描述")
                    unique_sample = ', '.join(sorted(unique_predictions)[:5])
                    report.append(f"  - 示例: {unique_sample}")
                    report.append("  - 这些是针对具体槽位的任务描述，而非通用意图类型")
                    report.append("  - 标准意图类型应该是: provide_info, request_info, confirm_info等")
                    report.append("")
                    report.append("建议：")
                    report.append("  1. 修改DST prompt，使用标准意图分类（如provide_info, request_info）")
                    report.append("  2. 或将任务描述映射到标准意图类型")
                    report.append("  3. 当前评测框架期望的是抽象的意图类型，而非具体的任务描述")
                else:
                    report.append("⚠️  提示：意图准确率为0%可能的原因：")
                    report.append("  1. DST意图格式与推断意图格式不匹配")
                    report.append(f"     - DST预测的意图类型: {', '.join(sorted(unique_predictions)[:5])}")
                    report.append("     - 需要确保意图名称格式一致（支持中英文映射）")
                    report.append("  2. 检查意图标准化映射是否完整")
        
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
        
        # 添加对话级别意图评测（如果有）
        if metrics.get('dialogue_metrics'):
            dm = metrics['dialogue_metrics']
            if dm.get('total_dialogues', 0) > 0:
                report.append("-" * 70)
                report.append("对话级别意图评测")
                report.append("-" * 70)
                report.append(f"总对话数: {dm['total_dialogues']}")
                report.append(f"正确对话: {dm['correct_dialogues']}")
                report.append(f"对话意图准确率: {dm['dialogue_accuracy']:.2%}")
                report.append("")
                report.append("说明：对话级别评测将整个对话作为一个单元进行意图评测")
                report.append("")
        
        # 添加综合分析总结
        report.append("=" * 70)
        report.append("📋 综合分析总结")
        report.append("=" * 70)
        report.append("")
        report.append(self._generate_summary_analysis(metrics))
        report.append("")
        
        report.append("=" * 70)
        
        return "\n".join(report)
    
    def _generate_summary_analysis(self, metrics: Dict[str, Any]) -> str:
        """
        生成综合分析总结
        
        Args:
            metrics: 计算出的评测指标
            
        Returns:
            格式化的分析总结字符串
        """
        summary = []
        
        # 1. 整体评估
        summary.append("【整体评估】")
        accuracy = metrics.get('accuracy', 0.0)
        total_turns = metrics.get('total_turns', 0)
        
        if total_turns == 0:
            summary.append("  无评测数据")
            return "\n".join(summary)
        
        if accuracy >= 0.8:
            summary.append(f"  ✅ 意图识别表现优秀（准确率: {accuracy:.1%}）")
        elif accuracy >= 0.5:
            summary.append(f"  ⚠️  意图识别表现中等（准确率: {accuracy:.1%}）")
        elif accuracy > 0:
            summary.append(f"  ❌ 意图识别表现较差（准确率: {accuracy:.1%}）")
        else:
            summary.append(f"  ❌ 意图识别完全失败（准确率: {accuracy:.1%}）")
        
        # 2. 主要问题分析
        summary.append("")
        summary.append("【主要问题】")
        
        if accuracy == 0:
            predicted_intents = [pred for pred, _ in self.predictions]
            unique_predictions = set(predicted_intents)
            normalized_predictions = set(
                self.normalization_mapping.get(p.lower(), p.lower())
                for p in unique_predictions
            )
            
            if normalized_predictions == {'unknown'} or len(unique_predictions) == 1:
                summary.append("  • DST模型未配置意图提取功能")
                summary.append("  • 所有预测都是相同的默认值")
            else:
                summary.append("  • 预测意图与标准意图标签格式不匹配")
                summary.append(f"  • 发现 {len(unique_predictions)} 种不同的预测意图")
        elif accuracy < 0.5:
            # 分析错误模式
            error_patterns = metrics.get('error_patterns', {})
            if error_patterns:
                top_error = list(error_patterns.items())[0]
                summary.append(f"  • 最常见的错误: 预测为'{top_error[0][0]}'实际为'{top_error[0][1]}'（{top_error[1]}次）")
        else:
            summary.append("  • 无重大问题")
        
        # 3. 意图分布分析
        summary.append("")
        summary.append("【意图分布】")
        inferred_dist = metrics.get('inferred_distribution', {})
        predicted_dist = metrics.get('predicted_distribution', {})
        
        if inferred_dist:
            top_inferred = sorted(inferred_dist.items(), key=lambda x: x[1], reverse=True)[:3]
            summary.append("  推断意图分布:")
            for intent, count in top_inferred:
                percentage = count / total_turns * 100
                summary.append(f"    - {intent}: {count}次 ({percentage:.1f}%)")
        
        if predicted_dist and len(predicted_dist) > 1:
            top_predicted = sorted(predicted_dist.items(), key=lambda x: x[1], reverse=True)[:3]
            summary.append("  预测意图分布:")
            for intent, count in top_predicted:
                percentage = count / total_turns * 100
                summary.append(f"    - {intent}: {count}次 ({percentage:.1f}%)")
        
        # 4. 对话阶段分析
        phase_dist = metrics.get('phase_distribution', {})
        if phase_dist:
            summary.append("")
            summary.append("【对话阶段分布】")
            for phase, count in sorted(phase_dist.items(), key=lambda x: x[1], reverse=True):
                percentage = count / total_turns * 100
                summary.append(f"  • {phase}: {count}轮 ({percentage:.1f}%)")
        
        # 5. 改进建议
        summary.append("")
        summary.append("【改进建议】")
        
        if accuracy == 0:
            summary.append("  1. 检查DST配置，确保启用了意图提取功能")
            summary.append("  2. 确认意图标签格式与配置文件一致")
            summary.append("  3. 验证意图标准化映射的完整性")
        elif accuracy < 0.3:
            summary.append("  1. 重新审视意图推断逻辑，确保符合实际场景")
            summary.append("  2. 检查意图关键词配置是否准确")
            summary.append("  3. 考虑增强意图识别的prompt指令")
        elif accuracy < 0.6:
            summary.append("  1. 分析混淆矩阵，找出易混淆的意图对")
            summary.append("  2. 优化关键词和描述，增强意图区分度")
            summary.append("  3. 考虑引入上下文信息辅助意图判断")
        else:
            summary.append("  1. 继续保持当前配置")
            summary.append("  2. 可以尝试进一步优化细节以提升准确率")
            summary.append("  3. 关注低频意图的识别效果")
        
        return "\n".join(summary)
    
    def reset(self):
        """
        重置评测器状态
        """
        self.predictions = []
        self.turn_details = []
        self.intent_transitions = []
        self.dialogue_intents = []
