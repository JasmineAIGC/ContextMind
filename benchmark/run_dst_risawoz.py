#!/usr/bin/env python3
"""
DST模式 - RiSAWOZ数据集评测脚本

使用RiSAWOZ数据集测试DialogueStateTracker的槽位提取能力。
参考DST模式在TransferTOD的实现，但使用RiSAWOZ一致的评测指标。

使用方式:
    python benchmark/run_dst_risawoz.py
    python benchmark/run_dst_risawoz.py --domain 景点 --split val --limit 10
"""

import asyncio
import argparse
import datetime
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict, Counter

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter
from benchmark.shared.intent_evaluator import IntentEvaluator
from benchmark.shared.intent_label_loader import IntentLabelLoader
from contextmind.modes.dst import DialogueStateTracker, PromptManager
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel
from contextmind.infra.embedding import get_embedding_client, calculate_embedding_similarity

logger = get_logger(__name__)


class DSTRiSAWOZTest:
    """
    DST模式 - RiSAWOZ测试类
    """
    
    def __init__(self, data_root: str = "./data/RiSAWOZ", file_mapping: Dict[str, str] = None, 
                 use_semantic_match: bool = False, semantic_threshold: float = 0.85):
        """
        初始化测试
        
        Args:
            data_root: RiSAWOZ数据集根目录
            file_mapping: 自定义文件名映射 (可选)
            use_semantic_match: 是否使用语义embedding匹配
            semantic_threshold: 语义相似度阈值 (0-1)
        """
        self.adapter = RiSAWOZAdapter(data_root, file_mapping=file_mapping)
        self.llm_client = None
        self.tracker = None
        
        # 使用RiSAWOZ专用的意图标签配置
        risawoz_intent_config = Path(__file__).parent / "shared" / "configs" / "intent_labels_risawoz.json"
        self.intent_label_loader = IntentLabelLoader(str(risawoz_intent_config))
        self.intent_evaluator = IntentEvaluator(intent_label_loader=self.intent_label_loader)  # 意图评测器
        
        # 语义匹配配置
        self.use_semantic_match = use_semantic_match
        self.semantic_threshold = semantic_threshold
        self.embedding_client = None
        
        # 如果启用语义匹配，初始化embedding客户端
        if use_semantic_match:
            try:
                self.embedding_client = get_embedding_client()
                if self.embedding_client and self.embedding_client.embedding_supported:
                    logger.info(f"✅ 语义匹配已启用 - 相似度阈值: {semantic_threshold}")
                else:
                    logger.warning("⚠️  Embedding客户端不可用，将回退到字符串匹配")
                    self.use_semantic_match = False
            except Exception as e:
                logger.warning(f"⚠️  Embedding客户端初始化失败: {e}，将回退到字符串匹配")
                self.use_semantic_match = False
        
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
        
        # 获取领域schema
        schema = self.adapter.get_domain_schema(domain)
        
        # 创建PromptManager（启用动态槽位，使用RiSAWOZ意图配置）
        pm = PromptManager(
            domain=domain,
            enable_dynamic_slots=True,
            intent_label_loader=self.intent_label_loader
        )
        
        # 可选：添加槽位定义作为指导
        for slot_name, slot_info in schema.get("slots", {}).items():
            pm.add_slot(slot_name, slot_info.get("description", slot_name))
        
        # 创建DialogueStateTracker
        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=10,
            enable_history_summary=True,
            use_llm_summary=False
        )
        
        logger.info(f"✅ DST模式初始化完成 - 领域: {domain}")
        logger.info(f"   动态槽位模式: 启用")
    
    def _extract_dialogue_intent(self, dialogue: 'DialogueInstance') -> str:
        """
        从对话的user_acts中提取对话级别的意图
        
        策略：
        1. 优先选择最后一个有实际槽位的Inform意图
        2. 其次选择Request意图
        3. 再选择其他非General/Greeting的意图
        4. 最后使用Greeting或General
        
        Args:
            dialogue: 对话实例
            
        Returns:
            提取的对话意图，如果没有找到返回空字符串
        """
        # 收集所有意图，按优先级分类
        inform_intents = []
        request_intents = []
        other_intents = []
        general_intents = []
        
        for turn in dialogue.turns:
            for intent_info in turn.user_intents:
                if len(intent_info) >= 2:
                    intent = intent_info[0]  # [intent, domain, slot, value]
                    
                    if not intent:  # 跳过空意图
                        continue
                    
                    # 分类
                    if intent == "Inform":
                        inform_intents.append(intent)
                    elif intent == "Request":
                        request_intents.append(intent)
                    elif intent in ["General", "Greeting", "Bye"]:
                        general_intents.append(intent)
                    else:
                        other_intents.append(intent)
        
        # 按优先级选择
        if inform_intents:
            return inform_intents[-1]  # 最后一个Inform
        elif request_intents:
            return request_intents[-1]  # 最后一个Request
        elif other_intents:
            return other_intents[-1]  # 最后一个其他意图
        elif general_intents:
            return general_intents[-1]  # 最后一个通用意图
        else:
            return ""  # 没有找到任何意图
    
    async def test_dialogue(self, dialogue_id: str, split: str = "val", verbose: bool = True) -> Dict[str, Any]:
        """
        测试单个对话
        
        Args:
            dialogue_id: 对话ID
            split: 数据集划分
            verbose: 是否输出详细信息
            
        Returns:
            测试指标
        """
        # 加载对话
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
        
        if verbose:
            print("\n" + "=" * 60)
            print(f"测试对话: {dialogue_id}")
            print(f"领域: {dialogue.domain}")
            print(f"轮次数: {len(dialogue.turns)}")
            print("=" * 60)
        
        # 重置追踪器状态
        self.tracker.current_state = {}
        self.tracker.dialogue_history = []
        
        # RiSAWOZ评测指标（与官方指标一致）
        total_slots = 0
        correct_slots = 0
        total_turns = len(dialogue.turns)
        correct_turns_strict = 0  # Joint Accuracy - 严格匹配
        correct_turns_soft = 0    # Joint Accuracy - 软匹配
        
        # 收集所有轮次的预测和真实状态（用于计算turn-level指标）
        all_turn_predictions = []
        all_turn_ground_truths = []
        
        # Turn-level意图评测（RiSAWOZ每一轮都有意图）
        turn_intent_correct = 0
        turn_intent_total = 0
        
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
                # 获取本轮的更新（从tracker的dialogue_history中获取最后一轮）
                if self.tracker.dialogue_history:
                    last_turn = self.tracker.dialogue_history[-1]
                    turn_updates = last_turn.turn_updates if last_turn.turn_updates else {}
                else:
                    turn_updates = {}
            except Exception as e:
                logger.error(f"处理轮次 {turn.turn_id} 时出错: {e}")
                extracted_state = {}
                turn_updates = {}
            
            # 获取期望状态（RiSAWOZ使用累积的belief state）
            expected_state = turn.expected_slots
            
            # 计算本轮的槽位准确率（使用语义匹配）
            turn_correct_slots = 0
            turn_total_slots = len(expected_state)
            turn_exact_match_strict = True  # 本轮是否完全匹配（严格）
            turn_exact_match_soft = True    # 本轮是否软匹配（允许额外槽位）
            
            # 标准化expected_state和extracted_state的key（添加domain前缀）
            # 同时过滤掉 'intent' 字段，因为那不是真正的槽位
            norm_expected = {}
            norm_extracted = {}
            
            for key, value in expected_state.items():
                norm_key = self._normalize_slot_key(key, dialogue.domain)
                if value:
                    norm_expected[norm_key] = str(value)
            
            for key, value in extracted_state.items():
                # 跳过 intent 字段
                if key == 'intent':
                    continue
                norm_key = self._normalize_slot_key(key, dialogue.domain)
                if value:
                    norm_extracted[norm_key] = str(value)
            
            # 比较每个槽位（使用语义匹配）
            for exp_key, exp_value in norm_expected.items():
                ext_value = norm_extracted.get(exp_key, "")
                
                # 只有在两个值都非空时才进行语义匹配
                if exp_value and ext_value:
                    # 使用语义匹配
                    is_match, similarity, method = self._semantic_value_match(exp_value, ext_value)
                    
                    if is_match:
                        turn_correct_slots += 1
                        if verbose and method == 'semantic':
                            logger.debug(f"[Turn {turn.turn_id}] 语义匹配: {exp_key} = '{exp_value}' ≈ '{ext_value}' (相似度: {similarity:.3f})")
                    else:
                        turn_exact_match_strict = False
                        turn_exact_match_soft = False  # 期望槽位不正确，软匹配也失败
                else:
                    # 如果任一值为空，则不匹配
                    turn_exact_match_strict = False
                    turn_exact_match_soft = False
            
            # 检查是否有多余的槽位（只影响严格匹配）
            for slot_key in norm_extracted:
                if slot_key not in norm_expected:
                    turn_exact_match_strict = False  # 有额外槽位，严格匹配失败
                    # 软匹配不受影响
            
            total_slots += turn_total_slots
            correct_slots += turn_correct_slots
            
            if turn_exact_match_strict:
                correct_turns_strict += 1
            if turn_exact_match_soft:
                correct_turns_soft += 1
            
            # 记录本轮的预测和真实状态
            all_turn_predictions.append(extracted_state)
            all_turn_ground_truths.append(expected_state)
            
            # Turn-level意图评测（RiSAWOZ每轮都有意图）
            if turn.user_intents:
                # 从user_intents提取本轮的真实意图（取第一个非空意图）
                turn_true_intent = ""
                for intent_info in turn.user_intents:
                    if len(intent_info) >= 1 and intent_info[0]:
                        turn_true_intent = intent_info[0]
                        break
                
                # 从本轮的槽位更新（而非累积状态）推断意图
                # 过滤掉'intent'字段本身，只使用槽位信息
                turn_updates_for_intent = {k: v for k, v in turn_updates.items() if k != 'intent'}
                
                # 从提取的槽位中检测实际领域（而非使用对话元数据的领域）
                # 这很重要，因为LLM可能使用"通用"作为前缀而非实际领域
                detected_domain = dialogue.domain  # 默认使用对话领域
                known_domains = ['医院', '天气', '旅游景点', '汽车', '火车', '电影', 
                               '电脑', '电视剧', '辅导班', '酒店', '飞机', '餐厅']
                
                # 从turn_updates的槽位键中提取领域前缀
                for slot_key in turn_updates_for_intent.keys():
                    if '-' in slot_key:
                        slot_domain = slot_key.split('-')[0]
                        if slot_domain in known_domains:
                            detected_domain = slot_domain
                            break  # 找到第一个有效领域就使用
                
                # 如果检测到的领域和对话领域不一致，优先使用检测到的领域
                # 这避免了LLM使用"通用"前缀时导致的意图推断错误
                
                turn_inferred_intent, _ = self.intent_evaluator.infer_intent_from_slots(
                    domain=detected_domain,  # 使用检测到的领域，而非对话元数据领域
                    turn_updates=turn_updates_for_intent,
                    previous_state={},
                    user_utterance=turn.user_utterance,
                    turn_id=turn.turn_id
                )
                
                # 标准化并比较
                turn_true_normalized = self.intent_evaluator.normalize_intent(turn_true_intent, dialogue.domain)
                turn_inferred_normalized = self.intent_evaluator.normalize_intent(turn_inferred_intent, dialogue.domain)
                
                if turn_true_normalized.lower() == turn_inferred_normalized.lower():
                    turn_intent_correct += 1
                turn_intent_total += 1
                
                if verbose:
                    intent_match_str = "✓" if turn_true_normalized.lower() == turn_inferred_normalized.lower() else "✗"
                    print(f"轮次意图: {turn_true_intent} -> {turn_inferred_intent} {intent_match_str}")
            
            if verbose:
                print(f"期望状态: {expected_state}")
                print(f"提取状态: {extracted_state}")
                print(f"匹配数: {turn_correct_slots}/{turn_total_slots}")
        
        # 计算RiSAWOZ评测指标（对齐TransferTOD）
        # 1. Slot Accuracy (turn-level)
        slot_accuracy = correct_slots / total_slots if total_slots > 0 else 0.0
        
        # 2. 使用最终状态计算dialogue-level指标（对齐TransferTOD）
        final_extracted = self.tracker.current_state
        final_expected = dialogue.final_state
        
        # 3. Joint Accuracy (dialogue-level) - 对齐TransferTOD论文
        # 使用最终状态而非turn-level统计，与TransferTOD保持一致
        joint_accuracy_strict = self._calculate_joint_accuracy(final_expected, final_extracted, domain=dialogue.domain, mode='strict')
        joint_accuracy_soft = self._calculate_joint_accuracy(final_expected, final_extracted, domain=dialogue.domain, mode='soft')
        
        # 计算Precision/Recall/F1（基于slot-value pairs）
        precision, recall, f1 = self._calculate_prf_pairs(final_expected, final_extracted, domain=dialogue.domain)
        
        # 4. Turn-level意图准确率（RiSAWOZ特有）
        turn_intent_accuracy = turn_intent_correct / turn_intent_total if turn_intent_total > 0 else 0.0
        
        if verbose:
            print("\n" + "=" * 70)
            print("📊 对话评测结果")
            print("=" * 70)
            
            # 1. 槽位评测结果（与TransferTOD一致）
            print("\n【槽位评测结果】")
            print(f"槽位准确率 (Slot Accuracy): {slot_accuracy * 100:.2f}%")
            print(f"联合准确率-严格 (Joint Accuracy Strict): {joint_accuracy_strict * 100:.2f}%")
            print(f"联合准确率-软匹配 (Joint Accuracy Soft): {joint_accuracy_soft * 100:.2f}%")
            print(f"精确率 (Precision): {precision * 100:.2f}%")
            print(f"召回率 (Recall): {recall * 100:.2f}%")
            print(f"F1分数 (F1 Score): {f1 * 100:.2f}%")
            
            # 最终状态显示（与TransferTOD一致）
            print(f"\n最终期望状态: {final_expected}")
            print(f"最终提取状态: {final_extracted}")
            
            # 2. Turn-level意图评测结果（RiSAWOZ特有）
            print("\n【轮次级别意图评测结果】")
            print(f"意图准确率 (Turn Intent Accuracy): {turn_intent_accuracy * 100:.2f}%")
            print(f"正确轮次数: {turn_intent_correct}/{turn_intent_total}")
            print("=" * 70)
            print()  # 添加空行分隔不同对话
        
        return {
            "dialogue_id": dialogue_id,
            "domain": dialogue.domain,
            "slot_accuracy": slot_accuracy,
            "joint_accuracy": joint_accuracy_strict,  # 主指标（对齐TransferTOD）
            "joint_accuracy_soft": joint_accuracy_soft,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total_slots": total_slots,
            "correct_slots": correct_slots,
            "total_turns": total_turns,
            "matched_slots": correct_slots,  # 添加matched_slots以对齐TransferTOD
            "turn_intent_accuracy": turn_intent_accuracy,  # Turn-level意图准确率
            "turn_intent_correct": turn_intent_correct,
            "turn_intent_total": turn_intent_total,
        }
    
    def _normalize_slot_key(self, slot_key: str, domain: str) -> str:
        """
        标准化槽位键：确保包含领域前缀
        
        Args:
            slot_key: 原始槽位键
            domain: 领域名称
            
        Returns:
            标准化后的槽位键
        """
        # 如果已经有领域前缀，直接返回
        if '-' in slot_key:
            return slot_key
        # 否则添加领域前缀
        return f"{domain}-{slot_key}"
    
    def _normalize_value(self, value: str) -> str:
        """
        标准化槽位值：去除空格、统一格式
        
        Args:
            value: 原始值
            
        Returns:
            标准化后的值
        """
        if value is None:
            return ""
        # 转换为字符串并去除所有类型的空格
        normalized = str(value)
        # 移除所有空白字符（包括空格、全角空格、制表符等）
        import re
        normalized = re.sub(r'\s+', '', normalized)
        return normalized.lower()  # 转小写以忽略大小写差异
    
    def _normalize_state_dict(self, state: Dict, domain: str) -> Dict:
        """
        标准化状态字典：统一槽位键和值的格式
        
        Args:
            state: 原始状态字典
            domain: 领域名称
            
        Returns:
            标准化后的状态字典
        """
        normalized = {}
        for key, value in state.items():
            # 标准化键和值
            norm_key = self._normalize_slot_key(key, domain)
            norm_value = self._normalize_value(value)
            if norm_value:  # 只保留非空值
                normalized[norm_key] = norm_value
        return normalized
    
    def _semantic_value_match(self, value1: str, value2: str, threshold: float = None) -> Tuple[bool, float, str]:
        """
        使用语义embedding判断两个值是否匹配（支持三级匹配策略）
        
        Args:
            value1: 值1
            value2: 值2
            threshold: 相似度阈值（默认使用self.semantic_threshold）
            
        Returns:
            (is_match, similarity_score, match_method)
            - is_match: 是否匹配
            - similarity_score: 相似度分数（0-1，字符串匹配为1.0或0.0）
            - match_method: 匹配方法 ('exact', 'normalized', 'semantic', 'none')
        """
        if threshold is None:
            threshold = self.semantic_threshold
        
        # 检查空值
        if not value1 or not value2:
            return False, 0.0, 'none'
        
        # 策略1: 精确匹配（最快）
        if value1 == value2:
            return True, 1.0, 'exact'
        
        # 策略2: 标准化匹配（去除空格、大小写）
        norm1 = self._normalize_value(value1)
        norm2 = self._normalize_value(value2)
        if norm1 == norm2:
            return True, 1.0, 'normalized'
        
        # 策略3: 语义embedding匹配
        if self.use_semantic_match and self.embedding_client:
            try:
                # 生成embedding
                emb1 = self.embedding_client.generate_embedding(value1)
                emb2 = self.embedding_client.generate_embedding(value2)
                
                if emb1 and emb2:
                    # 计算相似度
                    similarity, success = calculate_embedding_similarity(emb1, emb2)
                    
                    if success:
                        # 判断是否超过阈值
                        is_match = similarity >= threshold
                        return is_match, similarity, 'semantic'
                    else:
                        logger.debug(f"[语义匹配] 相似度计算失败")
                else:
                    logger.debug(f"[语义匹配] Embedding生成失败: {value1} vs {value2}")
            except Exception as e:
                logger.debug(f"[语义匹配] 异常: {e}")
        
        # 所有策略都失败
        return False, 0.0, 'none'
    
    def _calculate_prf_pairs(self, expected: Dict, extracted: Dict, domain: str = "") -> Tuple[float, float, float]:
        """
        计算Precision/Recall/F1（基于slot-value pairs，支持语义匹配）
        
        Args:
            expected: 期望状态
            extracted: 提取状态
            domain: 领域名称（用于标准化）
            
        Returns:
            (precision, recall, f1)
        """
        # 首先标准化slot keys（确保都有domain前缀）
        # 同时过滤掉 'intent' 字段
        norm_expected = {}
        norm_extracted = {}
        
        for key, value in expected.items():
            norm_key = self._normalize_slot_key(key, domain) if domain else key
            if value:
                norm_expected[norm_key] = str(value)
        
        for key, value in extracted.items():
            # 跳过 intent 字段，因为那不是真正的槽位
            if key == 'intent':
                continue
            norm_key = self._normalize_slot_key(key, domain) if domain else key
            if value:
                norm_extracted[norm_key] = str(value)
        
        # 计算TP: 期望和提取中都存在，且值匹配的槽位
        tp = 0
        matched_extracted_keys = set()
        
        for exp_key, exp_value in norm_expected.items():
            if exp_key in norm_extracted:
                ext_value = norm_extracted[exp_key]
                # 使用语义匹配判断值是否相同
                is_match, similarity, method = self._semantic_value_match(exp_value, ext_value)
                if is_match:
                    tp += 1
                    matched_extracted_keys.add(exp_key)
                    if method == 'semantic':
                        logger.debug(f"[P/R/F1] 语义匹配成功: {exp_key} = '{exp_value}' ≈ '{ext_value}' (相似度: {similarity:.3f})")
        
        # FP: 提取中存在但不在期望中的槽位，或值不匹配的槽位
        fp = len(norm_extracted) - tp
        
        # FN: 期望中存在但提取中缺失或值不匹配的槽位
        fn = len(norm_expected) - tp
        
        # 计算P/R/F1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return precision, recall, f1
    
    def _calculate_joint_accuracy(self, expected: Dict, extracted: Dict, domain: str = "", mode: str = 'strict') -> float:
        """
        计算Joint Accuracy（对话级别，支持语义匹配）- 对齐TransferTOD论文
        
        Args:
            expected: 期望的最终状态
            extracted: 提取的最终状态
            domain: 领域名称（用于标准化slot keys）
            mode: 'strict' (完全匹配) 或 'soft' (期望槽位都存在即可)
            
        Returns:
            1.0 if matched, 0.0 otherwise
        """
        # 首先标准化slot keys（确保都有domain前缀）
        # 同时过滤掉 'intent' 字段
        norm_expected = {}
        norm_extracted = {}
        
        for key, value in expected.items():
            norm_key = self._normalize_slot_key(key, domain) if domain else key
            if value:
                norm_expected[norm_key] = str(value)
        
        for key, value in extracted.items():
            # 跳过 intent 字段，因为那不是真正的槽位
            if key == 'intent':
                continue
            norm_key = self._normalize_slot_key(key, domain) if domain else key
            if value:
                norm_extracted[norm_key] = str(value)
        
        # 检查所有期望的槽位是否都在提取结果中且值匹配（使用语义匹配）
        for exp_key, exp_value in norm_expected.items():
            if exp_key not in norm_extracted:
                logger.debug(f"[Joint Acc] 缺失槽位: {exp_key}")
                return 0.0  # 缺失槽位
            
            ext_value = norm_extracted[exp_key]
            is_match, similarity, method = self._semantic_value_match(exp_value, ext_value)
            
            if not is_match:
                logger.debug(f"[Joint Acc] 槽位值不匹配: {exp_key} = '{exp_value}' vs '{ext_value}'")
                return 0.0  # 值不匹配
            elif method == 'semantic':
                logger.debug(f"[Joint Acc] 语义匹配成功: {exp_key} = '{exp_value}' ≈ '{ext_value}' (相似度: {similarity:.3f})")
        
        # strict模式：检查是否有额外的槽位
        if mode == 'strict':
            if len(norm_extracted) > len(norm_expected):
                logger.debug(f"[Joint Acc] Strict模式下有额外槽位: {set(norm_extracted.keys()) - set(norm_expected.keys())}")
                return 0.0  # 有额外槽位
        
        # 所有检查都通过
        return 1.0
    
    async def run_evaluation(self, domain: str = None, split: str = "val", limit: int = None, verbose: bool = True):
        """
        运行完整评测
        
        Args:
            domain: 领域名称（如果为None则评测所有领域）
            split: 数据集划分
            limit: 限制测试数量
            verbose: 是否输出详细信息
        """
        # 获取对话列表
        dialogue_ids = self.adapter.get_dialogues_by_domain(domain, split=split)
        
        if limit:
            dialogue_ids = dialogue_ids[:limit]
        
        logger.info(f"找到 {len(dialogue_ids)} 个对话实例")
        if limit:
            logger.info(f"限制测试数量: {limit}")
        
        # 如果指定了领域，初始化该领域的追踪器
        if domain:
            self.initialize(domain)
        
        # 运行测试
        all_metrics = []
        current_domain = domain  # 跟踪当前初始化的领域
        
        for idx, dialogue_id in enumerate(dialogue_ids):
            logger.info(f"\n处理对话 {idx+1}/{len(dialogue_ids)}: {dialogue_id}")
            
            try:
                # 如果没有指定领域，需要为每个对话的领域动态初始化
                if not domain:
                    # 先加载对话获取其领域
                    dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
                    dialogue_domain = dialogue.domain
                    
                    # 如果领域变化，重新初始化追踪器
                    if dialogue_domain != current_domain:
                        logger.info(f"切换到领域: {dialogue_domain}")
                        self.initialize(dialogue_domain)
                        current_domain = dialogue_domain
                
                metrics = await self.test_dialogue(dialogue_id, split=split, verbose=verbose)
                all_metrics.append(metrics)
            except Exception as e:
                logger.error(f"❌ 对话 {dialogue_id} 评测失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue
            
            logger.info(f"✅ 对话 {dialogue_id} 评测完成")
        
        # 计算总体指标并返回
        summary_text, metrics = self._print_summary(all_metrics, split, domain)
        return summary_text, metrics
    
    def _print_summary(self, all_metrics: List[Dict], split: str, domain: str = None):
        """
        打印评测汇总
        
        Args:
            all_metrics: 所有对话的评测指标
            split: 数据集划分
            domain: 领域名称
        """
        if not all_metrics:
            print("\n⚠️  没有成功评测的对话")
            return "", []
        
        summary_lines = []
        summary_lines.append("")
        summary_lines.append("=" * 70)
        summary_lines.append("📊 测试指标汇总（对齐TransferTOD论文）")
        summary_lines.append("=" * 70)
        summary_lines.append(f"\n数据集划分: {split}")
        summary_lines.append(f"领域: {domain if domain else '所有领域'}")
        summary_lines.append(f"对话数: {len(all_metrics)}")
        
        # 计算平均指标
        avg_slot_accuracy = sum(m["slot_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy = sum(m["joint_accuracy"] for m in all_metrics) / len(all_metrics)
        avg_joint_accuracy_soft = sum(m["joint_accuracy_soft"] for m in all_metrics) / len(all_metrics)
        avg_precision = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        total_slots = sum(m["total_slots"] for m in all_metrics)
        correct_slots = sum(m["matched_slots"] for m in all_metrics)
        total_turns = sum(m["total_turns"] for m in all_metrics)
        
        
        # 按领域统计
        domain_metrics = defaultdict(list)
        for m in all_metrics:
            domain_metrics[m["domain"]].append(m)
        
        if len(domain_metrics) > 1:
            summary_lines.append("\n【分领域统计】")
            summary_lines.append("-" * 70)
            for d, metrics in sorted(domain_metrics.items()):
                d_slot_acc = sum(m["slot_accuracy"] for m in metrics) / len(metrics)
                d_joint_acc = sum(m["joint_accuracy"] for m in metrics) / len(metrics)
                d_joint_acc_soft = sum(m["joint_accuracy_soft"] for m in metrics) / len(metrics)
                d_precision = sum(m["precision"] for m in metrics) / len(metrics)
                d_recall = sum(m["recall"] for m in metrics) / len(metrics)
                d_f1 = sum(m["f1"] for m in metrics) / len(metrics)
                summary_lines.append(f"\n{d}领域 (对话数: {len(metrics)}):")
                summary_lines.append(f"  槽位准确率: {d_slot_acc * 100:.2f}%")
                summary_lines.append(f"  联合准确率-严格: {d_joint_acc * 100:.2f}%")
                summary_lines.append(f"  联合准确率-软匹配: {d_joint_acc_soft * 100:.2f}%")
                summary_lines.append(f"  精确率: {d_precision * 100:.2f}%")
                summary_lines.append(f"  召回率: {d_recall * 100:.2f}%")
                summary_lines.append(f"  F1分数: {d_f1 * 100:.2f}%")
            summary_lines.append("")
        
        # 整体汇总统计
        summary_lines.append("\n【整体汇总统计】")
        summary_lines.append("-" * 70)
        summary_lines.append(f"总测试对话数: {len(all_metrics)}")
        summary_lines.append(f"平均槽位准确率 (Slot Accuracy): {avg_slot_accuracy * 100:.2f}%")
        summary_lines.append(f"平均联合准确率-严格 (Joint Accuracy Strict): {avg_joint_accuracy * 100:.2f}%")
        summary_lines.append(f"平均联合准确率-软匹配 (Joint Accuracy Soft): {avg_joint_accuracy_soft * 100:.2f}%")
        summary_lines.append(f"平均精确率 (Precision): {avg_precision * 100:.2f}%")
        summary_lines.append(f"平均召回率 (Recall): {avg_recall * 100:.2f}%")
        summary_lines.append(f"平均F1分数 (F1 Score): {avg_f1 * 100:.2f}%")
        
        # Turn-level意图准确率（RiSAWOZ特有）
        if all_metrics and "turn_intent_accuracy" in all_metrics[0]:
            total_turn_intent_correct = sum(m.get("turn_intent_correct", 0) for m in all_metrics)
            total_turn_intent_total = sum(m.get("turn_intent_total", 0) for m in all_metrics)
            avg_turn_intent_accuracy = total_turn_intent_correct / total_turn_intent_total if total_turn_intent_total > 0 else 0.0
            summary_lines.append(f"平均轮次意图准确率 (Turn Intent Accuracy): {avg_turn_intent_accuracy * 100:.2f}%")
            summary_lines.append(f"总轮次数: {total_turn_intent_total}, 正确轮次数: {total_turn_intent_correct}")
        summary_lines.append("")
        
        # 输出汇总（使用 print）
        for line in summary_lines:
            print(line)
        
        # 返回汇总数据，用于保存到文件
        summary_text = "\n".join(summary_lines)
        return summary_text, all_metrics


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="DST模式 - RiSAWOZ数据集评测")
    parser.add_argument("--data-root", type=str, default="./data/RiSAWOZ",
                       help="RiSAWOZ数据集根目录")
    parser.add_argument("--domain", type=str, default=None,
                       help="指定评测的领域（如：景点、酒店、餐厅等）")
    parser.add_argument("--split", type=str, default="val", choices=["train", "val", "test"],
                       help="数据集划分")
    parser.add_argument("--limit", type=int, default=None,
                       help="限制测试对话数量")
    parser.add_argument("--verbose", action="store_true",
                       help="输出详细信息")
    parser.add_argument("--log-level", type=str, default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="日志级别")
    
    # 语义匹配参数
    parser.add_argument("--use-semantic-match", action="store_true",
                       help="启用语义embedding匹配（需要配置EMBEDDING_MODEL）")
    parser.add_argument("--semantic-threshold", type=float, default=0.85,
                       help="语义相似度阈值（0-1，默认：0.85）")
    
    # 自定义文件名参数
    parser.add_argument("--train-file", type=str, default="train.json",
                       help="训练集文件名（默认：train.json）")
    parser.add_argument("--val-file", type=str, default="val.json",
                       help="验证集文件名（默认：val.json）")
    parser.add_argument("--test-file", type=str, default="test.json",
                       help="测试集文件名（默认：test.json）")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(LogLevel[args.log_level])
    
    # 处理文件路径参数
    # 如果用户提供的是完整路径（包含目录），需要分离目录和文件名
    data_root = args.data_root
    train_file = args.train_file
    val_file = args.val_file
    test_file = args.test_file
    
    # 检查test-file是否包含路径
    test_path = Path(args.test_file)
    train_path = Path(args.train_file)
    val_path = Path(args.val_file)
    
    # 检测哪个文件使用了完整路径
    detected_split = None
    
    if len(test_path.parts) > 1:  # 包含目录
        # 提取目录和文件名
        data_root = str(test_path.parent)
        test_file = test_path.name
        detected_split = "test"
        logger.info(f"检测到完整路径，使用: data_root={data_root}, test_file={test_file}")
    
    # 同样处理 train-file 和 val-file
    if len(train_path.parts) > 1:
        if data_root != args.data_root:
            logger.warning(f"train-file 路径 {args.train_file} 与 test-file 路径不一致，使用 test-file 的目录")
        else:
            data_root = str(train_path.parent)
        train_file = train_path.name
        if not detected_split:
            detected_split = "train"
    
    if len(val_path.parts) > 1:
        if data_root != args.data_root:
            logger.warning(f"val-file 路径 {args.val_file} 与 test-file 路径不一致，使用 test-file 的目录")
        else:
            data_root = str(val_path.parent)
        val_file = val_path.name
        if not detected_split:
            detected_split = "val"
    
    # 如果检测到文件路径且用户没有明确指定 split，自动设置 split
    if detected_split and args.split == "val":  # "val" 是默认值
        args.split = detected_split
        logger.info(f"根据文件路径自动设置 split={detected_split}")
    
    # 创建文件映射
    file_mapping = {
        "train": train_file,
        "val": val_file,
        "test": test_file
    }
    
    # 显示解析后的配置信息
    logger.info(f"数据根目录: {data_root}")
    logger.info(f"数据划分: {args.split}")
    logger.info(f"文件映射: {file_mapping}")
    logger.info(f"语义匹配: {'启用' if args.use_semantic_match else '禁用'}")
    if args.use_semantic_match:
        logger.info(f"相似度阈值: {args.semantic_threshold}")
    
    # 验证将要使用的数据文件是否存在
    expected_file = Path(data_root) / file_mapping.get(args.split, f"{args.split}.json")
    logger.info(f"将要加载的数据文件: {expected_file}")
    
    if not expected_file.exists():
        error_msg = (
            f"\n{'='*70}\n"
            f"❌ 错误：数据文件不存在\n"
            f"{'='*70}\n\n"
            f"文件路径: {expected_file.absolute()}\n"
            f"数据根目录: {Path(data_root).absolute()}\n"
            f"文件名: {file_mapping.get(args.split)}\n"
            f"数据划分: {args.split}\n\n"
            f"请检查：\n"
            f"1. 文件路径是否正确\n"
            f"2. 文件是否存在于指定位置\n"
            f"3. 当前工作目录: {Path.cwd()}\n\n"
            f"提示：\n"
            f"- 如果使用相对路径，请确保从正确的目录运行脚本\n"
            f"- 建议使用绝对路径以避免路径问题\n"
            f"- 使用 --val-file 时，请提供完整的文件路径\n"
            f"{'='*70}\n"
        )
        logger.error(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)
    
    # 创建测试实例（使用自定义文件映射和语义匹配参数）
    test = DSTRiSAWOZTest(
        data_root=data_root, 
        file_mapping=file_mapping,
        use_semantic_match=args.use_semantic_match,
        semantic_threshold=args.semantic_threshold
    )
    
    # 运行评测
    summary_text, all_metrics = await test.run_evaluation(
        domain=args.domain,
        split=args.split,
        limit=args.limit,
        verbose=args.verbose
    )
    
    # 保存评测结果到文件（对齐TransferTOD）
    if all_metrics:
        output_dir = Path("benchmark_results")
        output_dir.mkdir(exist_ok=True)
        
        # 生成带时间戳的文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics_file = output_dir / f"dst_risawoz_metrics_{timestamp}.txt"
        
        # 保存详细的评测结果
        with open(metrics_file, 'w', encoding='utf-8') as f:
            # 写入命令和参数
            f.write("=" * 70 + "\n")
            f.write("DST RiSAWOZ 评测结果（对齐TransferTOD）\n")
            f.write("=" * 70 + "\n")
            f.write(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"领域: {args.domain if args.domain else '所有领域'}\n")
            f.write(f"数据划分: {args.split}\n")
            f.write(f"测试数量: {len(all_metrics)}\n")
            f.write(f"数据路径: {data_root}\n")
            f.write("\n")
            
            # 写入汇总结果
            f.write(summary_text)
            
            # 写入详细的每个对话的指标
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("详细对话指标\n")
            f.write("=" * 70 + "\n\n")
            for m in all_metrics:
                try:
                    # 安全地获取和格式化指标值
                    dialogue_id = m.get('dialogue_id', 'Unknown')
                    slot_acc = m.get('slot_accuracy', 0) or 0
                    joint_acc = m.get('joint_accuracy', 0) or 0
                    joint_acc_soft = m.get('joint_accuracy_soft', 0) or 0
                    precision = m.get('precision', 0) or 0
                    recall = m.get('recall', 0) or 0
                    f1 = m.get('f1', 0) or 0
                    
                    f.write(f"对话ID: {dialogue_id}\n")
                    f.write(f"  槽位准确率: {slot_acc * 100:.2f}%\n")
                    f.write(f"  联合准确率(严格): {joint_acc * 100:.2f}%\n")
                    f.write(f"  联合准确率(软匹配): {joint_acc_soft * 100:.2f}%\n")
                    f.write(f"  精确率: {precision * 100:.2f}%\n")
                    f.write(f"  召回率: {recall * 100:.2f}%\n")
                    f.write(f"  F1分数: {f1 * 100:.2f}%\n")
                except Exception as e:
                    logger.error(f"写入指标时出错: {e}, 指标数据: {m}")
                    continue
                f.write("\n")
        
        print(f"\n✅ 评测结果已保存到: {metrics_file}")
        logger.info(f"评测结果已保存到: {metrics_file}")


if __name__ == "__main__":
    asyncio.run(main())
