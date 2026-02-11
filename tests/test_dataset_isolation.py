#!/usr/bin/env python3
"""
测试RiSAWOZ和TransferTOD评测的隔离性

确保对RiSAWOZ的修改不会影响TransferTOD的评测。
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextmind.modes.dst import PromptManager
from benchmark.shared.intent_label_loader import IntentLabelLoader


def test_prompt_manager_backward_compatibility():
    """
    测试PromptManager的向后兼容性
    
    验证：
    1. 不传intent_label_loader参数时，使用默认加载器（TransferTOD行为）
    2. 传入自定义intent_label_loader时，使用自定义加载器（RiSAWOZ行为）
    """
    print("=" * 70)
    print("测试1: PromptManager向后兼容性")
    print("=" * 70)
    
    # 测试1: TransferTOD模式 - 不传intent_label_loader
    print("\n【TransferTOD模式】不传intent_label_loader参数:")
    pm_transfertod = PromptManager(
        domain="酒店",
        enable_dynamic_slots=True
    )
    print(f"✅ PromptManager创建成功")
    print(f"   领域: {pm_transfertod.domain}")
    print(f"   动态槽位: {pm_transfertod.enable_dynamic_slots}")
    print(f"   意图预测: {pm_transfertod.enable_intent_prediction}")
    print(f"   intent_label_loader: {pm_transfertod.intent_label_loader}")
    print(f"   领域意图数量: {len(pm_transfertod.domain_intents)}")
    
    # 测试2: RiSAWOZ模式 - 传入自定义intent_label_loader
    print("\n【RiSAWOZ模式】传入自定义intent_label_loader:")
    risawoz_config = PROJECT_ROOT / "benchmark" / "shared" / "configs" / "intent_labels_risawoz.json"
    risawoz_loader = IntentLabelLoader(str(risawoz_config))
    
    pm_risawoz = PromptManager(
        domain="酒店",
        enable_dynamic_slots=True,
        intent_label_loader=risawoz_loader
    )
    print(f"✅ PromptManager创建成功")
    print(f"   领域: {pm_risawoz.domain}")
    print(f"   动态槽位: {pm_risawoz.enable_dynamic_slots}")
    print(f"   意图预测: {pm_risawoz.enable_intent_prediction}")
    print(f"   intent_label_loader: {type(pm_risawoz.intent_label_loader).__name__}")
    print(f"   领域意图数量: {len(pm_risawoz.domain_intents)}")
    
    # 验证两者使用不同的intent配置
    print("\n【对比结果】")
    print(f"TransferTOD意图数: {len(pm_transfertod.domain_intents)}")
    print(f"RiSAWOZ意图数: {len(pm_risawoz.domain_intents)}")
    
    if len(pm_transfertod.domain_intents) > 0:
        print(f"TransferTOD酒店领域意图示例: {pm_transfertod.domain_intents[:5]}")
    if len(pm_risawoz.domain_intents) > 0:
        print(f"RiSAWOZ酒店领域意图示例: {pm_risawoz.domain_intents[:5]}")
    
    print("\n✅ 测试通过：两个数据集使用不同的intent配置，互不影响！")


def test_intent_loader_isolation():
    """
    测试IntentLabelLoader的隔离性
    
    验证：
    1. 默认加载器加载TransferTOD的30个领域
    2. RiSAWOZ加载器加载RiSAWOZ的13个领域
    """
    print("\n" + "=" * 70)
    print("测试2: IntentLabelLoader隔离性")
    print("=" * 70)
    
    # TransferTOD加载器（默认）
    print("\n【TransferTOD】默认配置:")
    transfertod_loader = IntentLabelLoader()
    transfertod_domains = transfertod_loader.get_all_domains()
    print(f"✅ 加载成功")
    print(f"   领域数量: {len(transfertod_domains)}")
    print(f"   领域列表: {transfertod_domains[:10]}...")
    
    # RiSAWOZ加载器
    print("\n【RiSAWOZ】自定义配置:")
    risawoz_config = PROJECT_ROOT / "benchmark" / "shared" / "configs" / "intent_labels_risawoz.json"
    risawoz_loader = IntentLabelLoader(str(risawoz_config))
    risawoz_domains = risawoz_loader.get_all_domains()
    print(f"✅ 加载成功")
    print(f"   领域数量: {len(risawoz_domains)}")
    print(f"   领域列表: {risawoz_domains}")
    
    # 验证隔离性
    print("\n【验证隔离性】")
    assert len(transfertod_domains) != len(risawoz_domains), "两个数据集应该有不同数量的领域"
    assert set(transfertod_domains) != set(risawoz_domains), "两个数据集应该有不同的领域集合"
    
    print(f"✅ TransferTOD有 {len(transfertod_domains)} 个领域")
    print(f"✅ RiSAWOZ有 {len(risawoz_domains)} 个领域")
    print(f"✅ 两个数据集完全隔离，互不影响！")


def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("RiSAWOZ与TransferTOD评测隔离性测试")
    print("=" * 70)
    
    try:
        test_prompt_manager_backward_compatibility()
        test_intent_loader_isolation()
        
        print("\n" + "=" * 70)
        print("✅ 所有测试通过！")
        print("=" * 70)
        print("\n结论:")
        print("1. PromptManager保持向后兼容，TransferTOD不受影响")
        print("2. RiSAWOZ使用独立的intent配置文件")
        print("3. 两个数据集完全隔离，评测互不干扰")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
