#!/usr/bin/env python3
"""
意图评测器 (Intent Evaluator)

为DST方法设计的意图评测框架，通过槽位变化推断隐式意图标签。

版本: v2.0 - 使用配置文件驱动，移除硬编码
"""

from typing import Dict, List, Tuple, Any, Optional
from collections import Counter, defaultdict

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
        
        # 意图标准化映射：将变体统一到标准形式
        # 重要：所有映射的目标必须是配置文件中定义的预定义意图
        # 动态从配置文件构建变体映射，确保目标都是预定义的意图
        self.intent_normalization = self._build_intent_normalization_mapping()
        
        # 构建所有预定义意图的集合（用于验证）
        self.predefined_intents = set()
        for domain in self.intent_label_loader.get_all_domains():
            domain_intents = self.intent_label_loader.get_domain_intents(domain)
            self.predefined_intents.update(domain_intents)
        
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
    
    def _normalize_for_comparison(self, intent: str) -> str:
        """
        标准化意图用于比较
        
        Args:
            intent: 原始意图字符串
            
        Returns:
            标准化后的意图
        """
        return self.normalization_mapping.get(intent.lower(), intent.lower())
    
    def _build_intent_normalization_mapping(self) -> Dict[str, str]:
        """
        从配置文件动态构建意图标准化映射
        
        重要：所有映射的目标必须是配置文件中定义的预定义意图
        确保标准化不会产生配置文件之外的意图
        
        Returns:
            变体到标准意图的映射字典
        """
        mapping = {}
        
        # 只定义必要的变体映射，所有目标必须在配置文件中存在
        # 酒店领域的变体映射
        if self._intent_exists_in_config('酒店', '预订酒店'):
            mapping['预定酒店'] = '预订酒店'
            mapping['预订房间'] = '预订酒店'
            mapping['预定房间'] = '预订酒店'
            mapping['酒店预订'] = '预订酒店'
            mapping['房间预订'] = '预订酒店'
        
        if self._intent_exists_in_config('酒店', '查询酒店信息'):
            mapping['咨询酒店'] = '查询酒店信息'
            mapping['查询酒店'] = '查询酒店信息'
            mapping['酒店咨询'] = '查询酒店信息'
            mapping['咨询酒店信息'] = '查询酒店信息'
        
        if self._intent_exists_in_config('酒店', '确认预订'):
            mapping['确认订单'] = '确认预订'
            mapping['订单确认'] = '确认预订'
            mapping['确认酒店'] = '确认预订'
        
        if self._intent_exists_in_config('酒店', '取消预订'):
            mapping['取消订单'] = '取消预订'
            mapping['订单取消'] = '取消预订'
            mapping['取消酒店'] = '取消预订'
        
        return mapping
    
    def _intent_exists_in_config(self, domain: str, intent: str) -> bool:
        """
        检查意图是否在配置文件的指定领域中存在
        
        Args:
            domain: 领域名称
            intent: 意图名称
            
        Returns:
            是否存在
        """
        domain_intents = self.intent_label_loader.get_domain_intents(domain)
        return intent in domain_intents
        
    def normalize_intent(self, intent: str, domain: str = None) -> str:
        """
        标准化意图名称，将变体统一为标准形式
        
        重要：确保同一含义的意图只有一个标准词语
        更重要：确保返回的意图必须在配置文件的预定义列表中
        
        例如："预定酒店"、"预订房间" → "预订酒店"
        
        Args:
            intent: 原始意图名称
            domain: 领域名称（可选，用于验证）
            
        Returns:
            标准化后的意图名称（保证在预定义列表中）
        """
        if not intent:
            return intent
        
        # 首先尝试直接映射
        if intent in self.intent_normalization:
            normalized = self.intent_normalization[intent]
            # 验证标准化后的意图在预定义集合中
            if normalized in self.predefined_intents:
                return normalized
        
        # 尝试小写匹配
        intent_lower = intent.lower()
        for variant, standard in self.intent_normalization.items():
            if intent_lower == variant.lower():
                # 验证标准化后的意图在预定义集合中
                if standard in self.predefined_intents:
                    return standard
        
        # 检查原始意图是否已在预定义列表中
        if intent in self.predefined_intents:
            return intent
        
        # 如果提供了领域，尝试找到最接近的预定义意图
        if domain:
            domain_intents = self.intent_label_loader.get_domain_intents(domain)
            # 尝试部分匹配
            for predefined_intent in domain_intents:
                if intent.lower() in predefined_intent.lower() or predefined_intent.lower() in intent.lower():
                    return predefined_intent
            # 如果都不匹配，返回领域的第一个非兜底意图
            non_fallback = [i for i in domain_intents if not self.intent_label_loader.is_fallback_intent(domain, i)]
            if non_fallback:
                return non_fallback[0]
        
        # 最后，如果无法标准化且不在预定义列表中，返回"其他"
        return self.intent_label_loader.get_fallback_intent_name()
    
    def infer_intent_from_slots(
        self,
        domain: str,  # 新增：领域参数
        turn_updates: Dict[str, Any],
        previous_state: Dict[str, Any],
        user_utterance: str = "",
        turn_id: int = 0
    ) -> Tuple[str, str]:
        """
        从槽位变化和用户话语推断意图
        
        重要：只返回JSON配置文件中定义的意图，绝不返回"其他"作为意图真值
        意图真值必须是领域定义的具体意图类别（排除"其他"）
        
        优先使用关键词匹配，其次使用槽位模式分析，最后使用领域默认意图
        
        Args:
            domain: 对话领域
            turn_updates: 当前轮次的槽位更新（或完整对话的所有槽位）
            previous_state: 之前的状态
            user_utterance: 用户话语（或所有用户话语的组合）
            turn_id: 轮次ID
            
        Returns:
            (intent, task_relevance) 元组
            intent: 意图名称（来自JSON配置，绝不为"其他"）
            task_relevance: 任务相关性
        """
        # 过滤掉'intent'槽位本身
        slot_updates = {k: v for k, v in turn_updates.items() if k != 'intent'}
        
        # 获取领域的兜底意图（所有领域都有"其他"）
        fallback_intent = self.intent_label_loader.get_fallback_intent_name()  # "其他"
        
        # 获取该领域的所有意图（排除"其他"）
        domain_intents = self.intent_label_loader.get_domain_intents(domain)
        if not domain_intents:
            return fallback_intent, "task_related"
        
        # 获取非兜底的意图列表
        non_fallback_intents = [
            intent for intent in domain_intents 
            if not self.intent_label_loader.is_fallback_intent(domain, intent)
        ]
        
        # 策略1: 基于关键词匹配推断意图
        if user_utterance:
            intent_scores = {}
            for intent in non_fallback_intents:
                keywords = self.intent_label_loader.get_intent_keywords(domain, intent)
                score = 0
                for keyword in keywords:
                    if keyword and keyword in user_utterance:
                        score += 1
                
                if score > 0:
                    intent_scores[intent] = score
            
            # 如果找到匹配的意图，返回分数最高的
            if intent_scores:
                best_intent = max(intent_scores.items(), key=lambda x: x[1])[0]
                return best_intent, "task_related"
        
        # 策略2: 如果有槽位更新但无关键词匹配，使用领域的第一个主要意图
        # 这避免了返回"其他"，而是返回一个合理的默认意图
        if slot_updates and non_fallback_intents:
            # 返回领域的第一个非兜底意图作为默认意图
            # 通常配置文件中第一个意图是该领域最常见的意图
            return non_fallback_intents[0], "task_related"
        
        # 策略3: 即使没有槽位，如果有用户话语，也返回第一个主要意图
        if user_utterance and non_fallback_intents:
            return non_fallback_intents[0], "task_related"
        
        # 策略4: 在所有其他情况下，都返回领域的第一个主要意图
        # 绝不返回"其他"作为推断的意图真值
        # 这确保意图真值总是领域定义的具体意图类别
        if non_fallback_intents:
            return non_fallback_intents[0], "task_related"
        
        # 只有在领域没有定义任何具体意图时才返回兜底（理论上不应发生）
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
        
        # 标准化意图名称（将变体统一为标准形式）
        # 确保所有意图都来自配置文件的预定义列表
        predicted_intent_normalized = self.normalize_intent(predicted_intent, domain)
        inferred_intent_normalized = self.normalize_intent(inferred_intent, domain)
        
        # 验证标准化后的意图在预定义列表中
        if predicted_intent_normalized not in self.predefined_intents:
            # 记录警告并使用领域的兜底意图
            print(f"警告: 预测意图 '{predicted_intent}' (标准化后: '{predicted_intent_normalized}') 不在预定义列表中，使用兜底意图")
            predicted_intent_normalized = self.intent_label_loader.get_fallback_intent_name()
        
        if inferred_intent_normalized not in self.predefined_intents:
            # 记录警告并使用领域的兜底意图
            print(f"警告: 推断意图 '{inferred_intent}' (标准化后: '{inferred_intent_normalized}') 不在预定义列表中，使用兜底意图")
            inferred_intent_normalized = self.intent_label_loader.get_fallback_intent_name()
        
        
        # 判断是否正确（使用标准化后的值）
        is_correct = (predicted_intent_normalized.lower() == inferred_intent_normalized.lower())
        
        # 记录对话级别的意图（使用标准化后的值）
        detail = {
            'dialogue_id': dialogue_id,
            'domain': domain,
            'predicted_intent': predicted_intent_normalized,  # 使用标准化后的值
            'inferred_intent': inferred_intent_normalized,    # 使用标准化后的值
            'predicted_intent_original': predicted_intent,     # 保留原始值用于追溯
            'inferred_intent_original': inferred_intent,       # 保留原始值用于追溯
            'task_relevance': task_relevance,
            'correct': is_correct,
            'dialogue_slots': dialogue_slots.copy()
        }
        
        # 存储标准化后的意图
        self.dialogue_intents.append((dialogue_id, predicted_intent_normalized, inferred_intent_normalized))
        
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
            - 分类指标：精确率、召回率、F1分数（新增）
        """
        # 对话级别统计（优先计算，即使没有轮次数据也可以有对话数据）
        dialogue_metrics = {}
        if self.dialogue_intents:
            dialogue_total = len(self.dialogue_intents)
            # 使用标准化映射进行比较，处理"预定"vs"预订"等变体
            dialogue_correct = sum(
                1 for _, pred, inf in self.dialogue_intents 
                if self.normalization_mapping.get(pred.lower(), pred.lower()) == 
                   self.normalization_mapping.get(inf.lower(), inf.lower())
            )
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
                'dialogue_metrics': dialogue_metrics,
                'per_class_metrics': {},
                'macro_metrics': {
                    'precision': 0.0,
                    'recall': 0.0,
                    'f1': 0.0
                },
                'micro_metrics': {
                    'precision': 0.0,
                    'recall': 0.0,
                    'f1': 0.0
                }
            }
        
        # 基础统计（使用标准化映射进行比较，与turn-level评测一致）
        total = len(self.predictions)
        correct = sum(1 for pred, inf in self.predictions 
                     if self._normalize_for_comparison(pred) == self._normalize_for_comparison(inf))
        accuracy = correct / total if total > 0 else 0.0
        
        # 意图分布
        predicted_dist = Counter(pred for pred, _ in self.predictions)
        inferred_dist = Counter(inf for _, inf in self.predictions)
        
        # 混淆矩阵
        confusion = defaultdict(lambda: defaultdict(int))
        for pred, inf in self.predictions:
            confusion[inf][pred] += 1
        
        # 计算每个类别的精确率、召回率、F1分数
        per_class_metrics = {}
        all_intents = set()
        all_intents.update(pred for pred, _ in self.predictions)
        all_intents.update(inf for _, inf in self.predictions)
        
        for intent in all_intents:
            # 使用标准化映射进行比较（与整体accuracy一致）
            tp = fp = fn = 0
            intent_normalized = self._normalize_for_comparison(intent)
            
            for pred, inf in self.predictions:
                pred_normalized = self._normalize_for_comparison(pred)
                inf_normalized = self._normalize_for_comparison(inf)
                
                pred_match = pred_normalized == intent_normalized
                inf_match = inf_normalized == intent_normalized
                
                if pred_match and inf_match:
                    tp += 1
                elif pred_match and not inf_match:
                    fp += 1
                elif not pred_match and inf_match:
                    fn += 1
            
            # 支持数（真值中该类别的数量）
            support = tp + fn
            
            # 计算指标
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            
            per_class_metrics[intent] = {
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'support': support,
                'tp': tp,
                'fp': fp,
                'fn': fn
            }
        
        # 计算宏平均（每个类别等权重）
        if per_class_metrics:
            macro_precision = sum(m['precision'] for m in per_class_metrics.values()) / len(per_class_metrics)
            macro_recall = sum(m['recall'] for m in per_class_metrics.values()) / len(per_class_metrics)
            macro_f1 = sum(m['f1'] for m in per_class_metrics.values()) / len(per_class_metrics)
        else:
            macro_precision = macro_recall = macro_f1 = 0.0
        
        # 计算微平均（所有样本等权重）
        total_tp = sum(m['tp'] for m in per_class_metrics.values())
        total_fp = sum(m['fp'] for m in per_class_metrics.values())
        total_fn = sum(m['fn'] for m in per_class_metrics.values())
        
        micro_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        micro_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall) if (micro_precision + micro_recall) > 0 else 0.0
        
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
            'dialogue_metrics': dialogue_metrics,
            'per_class_metrics': per_class_metrics,
            'macro_metrics': {
                'precision': macro_precision,
                'recall': macro_recall,
                'f1': macro_f1
            },
            'micro_metrics': {
                'precision': micro_precision,
                'recall': micro_recall,
                'f1': micro_f1
            }
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
        
        # 检查是否只有对话级别数据（没有轮次数据）
        has_dialogue_only = (metrics['total_turns'] == 0 and 
                            metrics.get('dialogue_metrics', {}).get('total_dialogues', 0) > 0)
        
        # 如果只有对话级别数据，跳过轮次统计
        if not has_dialogue_only:
            # 总体指标（核心数值）
            report.append(f"总轮次数: {metrics['total_turns']}")
            report.append(f"正确轮次: {metrics['correct_turns']}")
            report.append("")
            
            # 核心评测指标
            report.append("【核心指标】")
            report.append(f"  准确率 (Accuracy):   {metrics['accuracy']:.2%}")
            
            # 添加宏平均和微平均指标
            macro = metrics.get('macro_metrics', {})
            micro = metrics.get('micro_metrics', {})
            
            # Always show P/R/F1 if macro metrics exist
            if macro:
                report.append(f"  精确率 (Precision):  {macro.get('precision', 0):.2%}")
                report.append(f"  召回率 (Recall):     {macro.get('recall', 0):.2%}")
                report.append(f"  F1分数 (F1 Score):   {macro.get('f1', 0):.2%}")
            
            report.append("")
        
        # 如果准确率为0%，添加诊断信息（简化版）
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
                # 所有预测都是'未识别'
                report.append("❌ 诊断: DST未配置意图提取功能（所有预测都是'未识别'）")
            else:
                # 有不同的预测，但准确率仍为0%
                report.append(f"⚠️  诊断: 意图格式不匹配（发现{len(unique_predictions)}种预测意图，但无匹配）")
            
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
        
        # 分类评测指标（精简版）
        dialogue_metrics_exist = metrics.get('dialogue_metrics', {}).get('total_dialogues', 0) > 0
        if metrics.get('per_class_metrics') and (metrics['total_turns'] > 0 or dialogue_metrics_exist):
            report.append("-" * 70)
            report.append("分类评测指标")
            report.append("-" * 70)
            
            # 宏平均和微平均
            macro = metrics.get('macro_metrics', {})
            micro = metrics.get('micro_metrics', {})
            
            report.append("【宏平均指标】")
            report.append(f"  精确率 (Precision):  {macro.get('precision', 0):.2%}")
            report.append(f"  召回率 (Recall):     {macro.get('recall', 0):.2%}")
            report.append(f"  F1分数 (F1 Score):   {macro.get('f1', 0):.2%}")
            report.append("")
            
            report.append("【微平均指标】")
            report.append(f"  精确率 (Precision):  {micro.get('precision', 0):.2%}")
            report.append(f"  召回率 (Recall):     {micro.get('recall', 0):.2%}")
            report.append(f"  F1分数 (F1 Score):   {micro.get('f1', 0):.2%}")
            report.append("")
            
            # 各意图类别的详细指标
            per_class = metrics.get('per_class_metrics', {})
            if per_class:
                report.append("【各意图类别指标】")
                report.append("")
                report.append(f"{'意图类别':<20} {'精确率':<10} {'召回率':<10} {'F1分数':<10} {'支持数':<10}")
                report.append("-" * 70)
                
                # 按支持数排序显示
                sorted_intents = sorted(per_class.items(), key=lambda x: x[1]['support'], reverse=True)
                for intent, metrics_data in sorted_intents:
                    precision = metrics_data['precision']
                    recall = metrics_data['recall']
                    f1 = metrics_data['f1']
                    support = metrics_data['support']
                    report.append(f"{intent:<20} {precision:<10.2%} {recall:<10.2%} {f1:<10.2%} {support:<10}")
                
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
        
        # 检查是否有对话级别评测数据
        dialogue_metrics = metrics.get('dialogue_metrics', {})
        has_dialogue_data = dialogue_metrics.get('total_dialogues', 0) > 0
        
        # 如果既没有轮次数据也没有对话数据，返回无评测数据
        if total_turns == 0 and not has_dialogue_data:
            summary.append("  无评测数据")
            return "\n".join(summary)
        
        # 使用对话级别准确率（如果有）
        if has_dialogue_data:
            dialogue_accuracy = dialogue_metrics.get('dialogue_accuracy', 0.0)
            total_dialogues = dialogue_metrics.get('total_dialogues', 0)
            
            if dialogue_accuracy >= 0.8:
                summary.append(f"  ✅ 对话意图识别表现优秀（准确率: {dialogue_accuracy:.1%}，共{total_dialogues}个对话）")
            elif dialogue_accuracy >= 0.5:
                summary.append(f"  ⚠️  对话意图识别表现中等（准确率: {dialogue_accuracy:.1%}，共{total_dialogues}个对话）")
            elif dialogue_accuracy > 0:
                summary.append(f"  ❌ 对话意图识别表现较差（准确率: {dialogue_accuracy:.1%}，共{total_dialogues}个对话）")
            else:
                summary.append(f"  ❌ 对话意图识别完全失败（准确率: {dialogue_accuracy:.1%}，共{total_dialogues}个对话）")
        elif total_turns > 0:
            # 使用轮次级别准确率（如果没有对话数据）
            if accuracy >= 0.8:
                summary.append(f"  ✅ 意图识别表现优秀（准确率: {accuracy:.1%}）")
            elif accuracy >= 0.5:
                summary.append(f"  ⚠️  意图识别表现中等（准确率: {accuracy:.1%}）")
            elif accuracy > 0:
                summary.append(f"  ❌ 意图识别表现较差（准确率: {accuracy:.1%}）")
            else:
                summary.append(f"  ❌ 意图识别完全失败（准确率: {accuracy:.1%}）")
        
        # 2. 分类指标摘要（如果有）
        macro = metrics.get('macro_metrics', {})
        micro = metrics.get('micro_metrics', {})
        
        if macro and macro.get('f1', 0) > 0:
            summary.append("")
            summary.append("【分类指标】")
            summary.append(f"  宏平均F1: {macro.get('f1', 0):.1%}")
            summary.append(f"  微平均F1: {micro.get('f1', 0):.1%}")
        
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
        
        # 优先使用对话级别数据，如果不存在则使用轮次数据
        if has_dialogue_data and self.dialogue_intents:
            # 使用对话级别数据
            inferred_intents = [inf for _, _, inf in self.dialogue_intents]
            predicted_intents = [pred for _, pred, _ in self.dialogue_intents]
            total_count = len(self.dialogue_intents)
            
            inferred_dist = Counter(inferred_intents)
            predicted_dist = Counter(predicted_intents)
            
            if inferred_dist:
                top_inferred = sorted(inferred_dist.items(), key=lambda x: x[1], reverse=True)[:3]
                summary.append("  推断意图分布:")
                for intent, count in top_inferred:
                    percentage = count / total_count * 100
                    summary.append(f"    - {intent}: {count}次 ({percentage:.1f}%)")
            
            if predicted_dist and len(predicted_dist) > 1:
                top_predicted = sorted(predicted_dist.items(), key=lambda x: x[1], reverse=True)[:3]
                summary.append("  预测意图分布:")
                for intent, count in top_predicted:
                    percentage = count / total_count * 100
                    summary.append(f"    - {intent}: {count}次 ({percentage:.1f}%)")
        elif total_turns > 0:
            # 使用轮次级别数据（如果没有对话数据）
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
        
        # 4. 对话阶段分析（只在有轮次数据时显示）
        if total_turns > 0:
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
