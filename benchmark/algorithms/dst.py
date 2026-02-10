"""
DST (Dialogue State Tracking) 算法评测模块
"""

from typing import Dict, List, Any
from dataclasses import dataclass, field


@dataclass
class DSTMetrics:
    """DST评测指标"""
    slot_accuracy: float = 0.0
    slot_precision: float = 0.0
    slot_recall: float = 0.0
    slot_f1: float = 0.0
    joint_accuracy: float = 0.0
    joint_accuracy_strict: float = 0.0
    total_slots: int = 0
    correct_slots: int = 0
    total_turns: int = 0
    correct_turns: int = 0
    domain_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_level": {
                "accuracy": round(self.slot_accuracy, 4),
                "precision": round(self.slot_precision, 4),
                "recall": round(self.slot_recall, 4),
                "f1": round(self.slot_f1, 4),
            },
            "dialogue_state_level": {
                "joint_accuracy": round(self.joint_accuracy, 4),
                "joint_accuracy_strict": round(self.joint_accuracy_strict, 4),
            },
            "statistics": {
                "total_slots": self.total_slots,
                "correct_slots": self.correct_slots,
                "total_turns": self.total_turns,
                "correct_turns": self.correct_turns,
            },
            "domain_breakdown": self.domain_metrics
        }


class DSTEvaluator:
    """DST评测器"""
    
    def __init__(self):
        self.predictions = []
        self.ground_truths = []
        self.domains = []
    
    def add_prediction(self, predicted: Dict[str, str], 
                      ground_truth: Dict[str, str],
                      domain: str = "unknown"):
        self.predictions.append(predicted)
        self.ground_truths.append(ground_truth)
        self.domains.append(domain)
    
    def calculate_metrics(self) -> DSTMetrics:
        if not self.predictions:
            return DSTMetrics()
        
        total_slots = 0
        correct_slots = 0
        total_turns = len(self.predictions)
        correct_turns = 0
        domain_stats = {}
        
        # For precision/recall/F1 calculation
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        
        for pred, gt, domain in zip(self.predictions, self.ground_truths, self.domains):
            if domain not in domain_stats:
                domain_stats[domain] = {"total": 0, "correct": 0, "exact_match": 0, "turns": 0}
            
            domain_stats[domain]["turns"] += 1
            all_slots = set(pred.keys()) | set(gt.keys())
            turn_correct = True
            
            for slot in all_slots:
                total_slots += 1
                domain_stats[domain]["total"] += 1
                
                # Normalize values to strings for comparison
                # Handle None, int, bool, and string types
                pred_val = str(pred.get(slot, "")) if pred.get(slot) is not None else ""
                gt_val = str(gt.get(slot, "")) if gt.get(slot) is not None else ""
                
                if pred_val == gt_val:
                    correct_slots += 1
                    domain_stats[domain]["correct"] += 1
                    # True positive: predicted and ground truth match
                    if pred_val != "":
                        true_positives += 1
                else:
                    turn_correct = False
                    # False positive: predicted but incorrect
                    if pred_val != "":
                        false_positives += 1
                    # False negative: should have predicted but didn't or predicted wrong
                    if gt_val != "":
                        false_negatives += 1
            
            if turn_correct:
                correct_turns += 1
                domain_stats[domain]["exact_match"] += 1
        
        slot_accuracy = correct_slots / total_slots if total_slots > 0 else 0.0
        joint_accuracy = correct_turns / total_turns if total_turns > 0 else 0.0
        
        # Calculate precision, recall, F1
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        domain_metrics = {}
        for domain, stats in domain_stats.items():
            domain_metrics[domain] = {
                "slot_accuracy": round(stats["correct"] / stats["total"], 4) if stats["total"] > 0 else 0.0,
                "joint_accuracy": round(stats["exact_match"] / stats["turns"], 4) if stats["turns"] > 0 else 0.0,
                "total_turns": stats["turns"]
            }
        
        return DSTMetrics(
            slot_accuracy=slot_accuracy,
            slot_precision=precision,
            slot_recall=recall,
            slot_f1=f1,
            joint_accuracy=joint_accuracy,
            joint_accuracy_strict=joint_accuracy,
            total_slots=total_slots,
            correct_slots=correct_slots,
            total_turns=total_turns,
            correct_turns=correct_turns,
            domain_metrics=domain_metrics
        )
    
    def reset(self):
        self.predictions = []
        self.ground_truths = []
        self.domains = []
