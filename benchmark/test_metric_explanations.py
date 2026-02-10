#!/usr/bin/env python3
"""
测试指标说明是否正确显示
"""

from shared.intent_evaluator import IntentEvaluator

def test_intent_metrics_explanations():
    """测试意图评测报告中是否包含指标说明"""
    
    # 创建评测器
    evaluator = IntentEvaluator()
    
    # 添加一些测试数据
    evaluator.add_dialogue_evaluation(
        dialogue_id="test_1",
        predicted_intent="预订酒店",
        ground_truth_intent="预订酒店"
    )
    
    evaluator.add_dialogue_evaluation(
        dialogue_id="test_2",
        predicted_intent="查询信息",
        ground_truth_intent="预订酒店"
    )
    
    # 生成报告
    report = evaluator.get_detailed_report(save_confusion_plot=False)
    
    # 检查是否包含指标说明
    print("检查意图评测报告...")
    print("=" * 70)
    
    # 检查关键部分
    checks = {
        "📊 指标说明": "指标说明标题",
        "【对话意图准确率 (Dialogue Intent Accuracy)】": "对话准确率说明",
        "【精确率 (Precision)】": "精确率说明",
        "【召回率 (Recall)】": "召回率说明",
        "【F1分数 (F1 Score)】": "F1分数说明",
        "【宏平均 (Macro Average)】": "宏平均说明",
        "【微平均 (Micro Average)】": "微平均说明",
        "【支持数 (Support)】": "支持数说明",
        "TP / (TP + FP)": "精确率计算公式",
        "TP / (TP + FN)": "召回率计算公式",
    }
    
    all_passed = True
    for key, desc in checks.items():
        if key in report:
            print(f"✅ {desc}: 存在")
        else:
            print(f"❌ {desc}: 缺失")
            all_passed = False
    
    print("=" * 70)
    
    if all_passed:
        print("\n✅ 所有指标说明检查通过！")
        print("\n报告示例:")
        print("-" * 70)
        # 只打印指标说明部分
        lines = report.split('\n')
        in_explanation = False
        for line in lines:
            if "📊 指标说明" in line:
                in_explanation = True
            if in_explanation:
                print(line)
                if line.strip() == "=" * 70 and "📊 指标说明" not in line:
                    break
    else:
        print("\n❌ 部分指标说明缺失")
        print("\n完整报告:")
        print(report)
    
    return all_passed

if __name__ == "__main__":
    success = test_intent_metrics_explanations()
    exit(0 if success else 1)
