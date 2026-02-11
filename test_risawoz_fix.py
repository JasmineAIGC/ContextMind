#!/usr/bin/env python3
"""
单元测试：验证RiSAWOZ评测修复的正确性

测试内容：
1. Joint Accuracy计算方式（dialogue-level vs turn-level）
2. 与TransferTOD一致性
3. 指标计算准确性
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_joint_accuracy_calculation():
    """测试Joint Accuracy计算方法"""
    print("=" * 70)
    print("测试1: Joint Accuracy 计算方法")
    print("=" * 70)
    
    # 模拟一个简单的测试实例
    from benchmark.run_dst_risawoz import DSTRiSAWOZTest
    
    test = DSTRiSAWOZTest()
    
    # 测试case 1: 完全匹配
    expected = {"酒店-名称": "希尔顿", "酒店-区域": "苏州"}
    extracted = {"酒店-名称": "希尔顿", "酒店-区域": "苏州"}
    
    ja_strict = test._calculate_joint_accuracy(expected, extracted, mode='strict')
    ja_soft = test._calculate_joint_accuracy(expected, extracted, mode='soft')
    
    assert ja_strict == 1.0, f"严格模式应该返回1.0，实际: {ja_strict}"
    assert ja_soft == 1.0, f"软匹配模式应该返回1.0，实际: {ja_soft}"
    print("✅ Case 1: 完全匹配 - PASSED")
    
    # 测试case 2: 缺少槽位
    expected = {"酒店-名称": "希尔顿", "酒店-区域": "苏州"}
    extracted = {"酒店-名称": "希尔顿"}
    
    ja_strict = test._calculate_joint_accuracy(expected, extracted, mode='strict')
    ja_soft = test._calculate_joint_accuracy(expected, extracted, mode='soft')
    
    assert ja_strict == 0.0, f"严格模式应该返回0.0，实际: {ja_strict}"
    assert ja_soft == 0.0, f"软匹配模式应该返回0.0，实际: {ja_soft}"
    print("✅ Case 2: 缺少槽位 - PASSED")
    
    # 测试case 3: 额外槽位
    expected = {"酒店-名称": "希尔顿"}
    extracted = {"酒店-名称": "希尔顿", "酒店-区域": "苏州"}
    
    ja_strict = test._calculate_joint_accuracy(expected, extracted, mode='strict')
    ja_soft = test._calculate_joint_accuracy(expected, extracted, mode='soft')
    
    assert ja_strict == 0.0, f"严格模式应该返回0.0（有额外槽位），实际: {ja_strict}"
    assert ja_soft == 1.0, f"软匹配模式应该返回1.0（允许额外槽位），实际: {ja_soft}"
    print("✅ Case 3: 额外槽位 - PASSED")
    
    # 测试case 4: 值不匹配
    expected = {"酒店-名称": "希尔顿"}
    extracted = {"酒店-名称": "香格里拉"}
    
    ja_strict = test._calculate_joint_accuracy(expected, extracted, mode='strict')
    ja_soft = test._calculate_joint_accuracy(expected, extracted, mode='soft')
    
    assert ja_strict == 0.0, f"严格模式应该返回0.0，实际: {ja_strict}"
    assert ja_soft == 0.0, f"软匹配模式应该返回0.0，实际: {ja_soft}"
    print("✅ Case 4: 值不匹配 - PASSED")
    
    print("\n✅ 所有Joint Accuracy测试通过！\n")


def test_prf_calculation():
    """测试Precision/Recall/F1计算方法"""
    print("=" * 70)
    print("测试2: Precision/Recall/F1 计算方法")
    print("=" * 70)
    
    from benchmark.run_dst_risawoz import DSTRiSAWOZTest
    
    test = DSTRiSAWOZTest()
    
    # 测试case 1: 完全匹配
    expected = {"酒店-名称": "希尔顿", "酒店-区域": "苏州"}
    extracted = {"酒店-名称": "希尔顿", "酒店-区域": "苏州"}
    
    p, r, f1 = test._calculate_prf_pairs(expected, extracted)
    
    assert p == 1.0, f"Precision应该是1.0，实际: {p}"
    assert r == 1.0, f"Recall应该是1.0，实际: {r}"
    assert f1 == 1.0, f"F1应该是1.0，实际: {f1}"
    print("✅ Case 1: 完全匹配 (P=1.0, R=1.0, F1=1.0) - PASSED")
    
    # 测试case 2: 部分正确
    expected = {"酒店-名称": "希尔顿", "酒店-区域": "苏州"}
    extracted = {"酒店-名称": "希尔顿", "酒店-区域": "上海"}
    
    p, r, f1 = test._calculate_prf_pairs(expected, extracted)
    
    assert p == 0.5, f"Precision应该是0.5，实际: {p}"
    assert r == 0.5, f"Recall应该是0.5，实际: {r}"
    assert abs(f1 - 0.5) < 0.001, f"F1应该是0.5，实际: {f1}"
    print(f"✅ Case 2: 部分正确 (P={p:.2f}, R={r:.2f}, F1={f1:.2f}) - PASSED")
    
    # 测试case 3: 完全错误
    expected = {"酒店-名称": "希尔顿"}
    extracted = {"餐厅-名称": "麦当劳"}
    
    p, r, f1 = test._calculate_prf_pairs(expected, extracted)
    
    assert p == 0.0, f"Precision应该是0.0，实际: {p}"
    assert r == 0.0, f"Recall应该是0.0，实际: {r}"
    assert f1 == 0.0, f"F1应该是0.0，实际: {f1}"
    print("✅ Case 3: 完全错误 (P=0.0, R=0.0, F1=0.0) - PASSED")
    
    print("\n✅ 所有P/R/F1测试通过！\n")


def test_consistency_with_transfertod():
    """测试与TransferTOD的一致性"""
    print("=" * 70)
    print("测试3: 与TransferTOD的方法一致性")
    print("=" * 70)
    
    from benchmark.run_dst_risawoz import DSTRiSAWOZTest
    from benchmark.run_dst_transfertod import DSTTransferTODTest
    
    risawoz_test = DSTRiSAWOZTest()
    transfertod_test = DSTTransferTODTest()
    
    # 测试相同的输入
    expected = {"name": "Hilton", "area": "Suzhou"}
    extracted = {"name": "Hilton", "area": "Suzhou", "price": "500"}
    
    # RiSAWOZ
    ja_strict_r = risawoz_test._calculate_joint_accuracy(expected, extracted, mode='strict')
    ja_soft_r = risawoz_test._calculate_joint_accuracy(expected, extracted, mode='soft')
    p_r, r_r, f1_r = risawoz_test._calculate_prf_pairs(expected, extracted)
    
    # TransferTOD
    ja_strict_t = transfertod_test._calculate_joint_accuracy(expected, extracted, mode='strict')
    ja_soft_t = transfertod_test._calculate_joint_accuracy(expected, extracted, mode='soft')
    p_t, r_t, f1_t = transfertod_test._calculate_prf_pairs(expected, extracted)
    
    # 验证一致性
    assert ja_strict_r == ja_strict_t, f"Joint Accuracy (strict) 不一致: RiSAWOZ={ja_strict_r}, TransferTOD={ja_strict_t}"
    assert ja_soft_r == ja_soft_t, f"Joint Accuracy (soft) 不一致: RiSAWOZ={ja_soft_r}, TransferTOD={ja_soft_t}"
    assert p_r == p_t, f"Precision 不一致: RiSAWOZ={p_r}, TransferTOD={p_t}"
    assert r_r == r_t, f"Recall 不一致: RiSAWOZ={r_r}, TransferTOD={r_t}"
    assert f1_r == f1_t, f"F1 不一致: RiSAWOZ={f1_r}, TransferTOD={f1_t}"
    
    print(f"✅ Joint Accuracy (strict): {ja_strict_r} (一致)")
    print(f"✅ Joint Accuracy (soft): {ja_soft_r} (一致)")
    print(f"✅ Precision: {p_r:.3f} (一致)")
    print(f"✅ Recall: {r_r:.3f} (一致)")
    print(f"✅ F1 Score: {f1_r:.3f} (一致)")
    
    print("\n✅ RiSAWOZ与TransferTOD的评测方法完全一致！\n")


def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("RiSAWOZ 评测修复 - 单元测试")
    print("=" * 70 + "\n")
    
    try:
        test_joint_accuracy_calculation()
        test_prf_calculation()
        test_consistency_with_transfertod()
        
        print("=" * 70)
        print("🎉 所有测试通过！评测修复验证成功！")
        print("=" * 70)
        return 0
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
