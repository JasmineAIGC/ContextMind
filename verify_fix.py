#!/usr/bin/env python3
"""
验证 DST 通用领域支持修复

运行此脚本验证所有修改都已正确应用并工作正常。
"""

import sys

def print_header(text):
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80 + "\n")

def print_section(text):
    print("\n" + "-"*80)
    print(f"  {text}")
    print("-"*80 + "\n")

def test_response_parser():
    """测试 ResponseParser 的动态模式支持"""
    print_section("1️⃣  测试 ResponseParser 动态模式")
    
    from contextmind.modes.dst.response_parser import ResponseParser
    
    # 测试动态模式
    parser_dynamic = ResponseParser(
        ontology_slots={"姓名", "入住日期"},
        enable_filtering=False
    )
    
    test_slots = {
        "姓名": "张三",
        "入住日期": "2024-01-01",
        "用户名": "zhangsan",  # 未预定义
        "身份证号码": "123456",  # 未预定义
    }
    
    result = parser_dynamic.normalize_extracted(
        test_slots, 
        {"姓名": "姓名", "入住日期": "入住日期"},
        {}
    )
    
    success = len(result) == 4
    print(f"输入槽位数: {len(test_slots)}")
    print(f"输出槽位数: {len(result)}")
    print(f"动态模式测试: {'✅ PASS' if success else '❌ FAIL'}")
    
    # 测试严格模式
    parser_strict = ResponseParser(
        ontology_slots={"姓名", "入住日期"},
        enable_filtering=True
    )
    
    result_strict = parser_strict.normalize_extracted(
        test_slots,
        {"姓名": "姓名", "入住日期": "入住日期"},
        {}
    )
    
    success_strict = len(result_strict) == 2 and "用户名" not in result_strict
    print(f"严格模式输出: {len(result_strict)} 槽位")
    print(f"严格模式测试: {'✅ PASS' if success_strict else '❌ FAIL'}")
    
    return success and success_strict

def test_prompt_manager():
    """测试 PromptManager 配置"""
    print_section("2️⃣  测试 PromptManager 配置")
    
    from contextmind.modes.dst import PromptManager
    
    # 测试动态模式配置
    pm_dynamic = PromptManager(domain="通用", enable_dynamic_slots=True)
    print(f"动态模式 PM 创建: ✅")
    print(f"  - domain: {pm_dynamic.domain}")
    print(f"  - enable_dynamic_slots: {pm_dynamic.enable_dynamic_slots}")
    
    # 测试严格模式配置
    pm_strict = PromptManager(domain="酒店", enable_dynamic_slots=False)
    print(f"严格模式 PM 创建: ✅")
    print(f"  - domain: {pm_strict.domain}")
    print(f"  - enable_dynamic_slots: {pm_strict.enable_dynamic_slots}")
    
    return True

def test_dialogue_state_tracker():
    """测试 DialogueStateTracker 初始化"""
    print_section("3️⃣  测试 DialogueStateTracker 初始化")
    
    from contextmind.modes.dst import DialogueStateTracker, PromptManager
    
    # 测试动态模式
    pm = PromptManager(domain="通用", enable_dynamic_slots=True)
    tracker = DialogueStateTracker(
        llm_client=None,  # 不需要真实的 LLM 客户端
        prompt_manager=pm
    )
    
    print(f"Tracker 创建: ✅")
    print(f"  - ResponseParser.enable_filtering: {tracker.response_parser.enable_filtering}")
    
    success = tracker.response_parser.enable_filtering == False
    print(f"enable_filtering 正确设置: {'✅ PASS' if success else '❌ FAIL'}")
    
    return success

def test_transfertod_adapter():
    """测试 TransferTOD 适配器"""
    print_section("4️⃣  测试 TransferTOD 适配器")
    
    try:
        from tests.adapters import TransferTODAdapter
        
        adapter = TransferTODAdapter(data_root="./data/TransferTOD")
        print(f"TransferTOD 适配器创建: ✅")
        
        # 测试方法存在
        assert hasattr(adapter, 'get_domain_schema'), "缺少 get_domain_schema 方法"
        assert hasattr(adapter, 'load_dialogue'), "缺少 load_dialogue 方法"
        assert hasattr(adapter, 'get_all_dialogue_ids'), "缺少 get_all_dialogue_ids 方法"
        
        print(f"适配器方法验证: ✅")
        return True
    except Exception as e:
        print(f"❌ 适配器测试失败: {e}")
        return False

def test_test_scripts():
    """测试测试脚本导入"""
    print_section("5️⃣  测试脚本导入验证")
    
    try:
        import tests.test_dst_transfertod
        print(f"test_dst_transfertod.py 导入: ✅")
        
        import tests.test_fnctod_transfertod
        print(f"test_fnctod_transfertod.py 导入: ✅")
        
        return True
    except Exception as e:
        print(f"❌ 测试脚本导入失败: {e}")
        return False

def test_legacy_compatibility():
    """测试向后兼容性"""
    print_section("6️⃣  测试向后兼容性")
    
    try:
        import tests_legacy.test_dst_mode
        print(f"Legacy DST 测试导入: ✅")
        
        import tests_legacy.test_evolve_mode
        print(f"Legacy Evolve 测试导入: ✅")
        
        return True
    except Exception as e:
        print(f"❌ Legacy 测试导入失败: {e}")
        return False

def main():
    print_header("DST 通用领域支持修复 - 验证脚本")
    
    results = []
    
    try:
        results.append(("ResponseParser 测试", test_response_parser()))
        results.append(("PromptManager 测试", test_prompt_manager()))
        results.append(("DialogueStateTracker 测试", test_dialogue_state_tracker()))
        results.append(("TransferTOD 适配器测试", test_transfertod_adapter()))
        results.append(("测试脚本导入", test_test_scripts()))
        results.append(("向后兼容性", test_legacy_compatibility()))
    except Exception as e:
        print(f"\n❌ 测试过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 打印总结
    print_header("验证结果总结")
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*80)
    if all_passed:
        print("  🎉 所有验证通过！DST 通用领域支持修复成功！")
    else:
        print("  ⚠️  部分测试失败，请检查上述详情")
    print("="*80 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
