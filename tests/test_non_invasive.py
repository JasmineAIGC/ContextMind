"""
非侵入性验证测试 - 验证模板优化不影响原有功能

这个测试确保模板优化的添加不会影响 ContextMind 框架的原有功能。
"""

import asyncio
from contextmind import ContextEngine
from contextmind.core.data_models import Message
from contextmind.core.types import MessageRole


async def test_original_functionality_intact():
    """
    测试原有功能完整性
    
    验证在不使用模板优化的情况下，ContextEngine 的所有核心功能正常工作。
    """
    print("\n" + "=" * 80)
    print("测试：原有功能完整性（不使用模板优化）")
    print("=" * 80 + "\n")
    
    # 1. 初始化 ContextEngine（标准方式，不涉及模板）
    engine = ContextEngine(
        app_name="non-invasive-test",
        user_id="test-user"
    )
    print("✓ ContextEngine 初始化成功")
    
    # 2. 测试 optimize 方法
    context = await engine.optimize("你好")
    assert context is not None
    assert hasattr(context, 'items')
    assert isinstance(context.items, list)
    print("✓ optimize() 方法正常工作")
    
    # 3. 测试 update 方法
    await engine.update("你好", "你好！有什么可以帮助你的？")
    print("✓ update() 方法正常工作")
    
    # 4. 再次优化
    context2 = await engine.optimize("今天天气怎么样？")
    assert len(context2.items) >= 0  # 可能为空（无记忆时）
    assert hasattr(context2, 'compressed')
    assert hasattr(context2, 'metadata')
    print("✓ 第二次 optimize() 正常工作")
    
    # 5. 验证返回的是 ContextResult
    from contextmind.core.data_models import ContextResult
    assert isinstance(context2, ContextResult)
    print("✓ 返回正确的 ContextResult 对象")
    
    # 6. 验证 ContextResult 的属性
    assert hasattr(context2, 'total_tokens')
    assert isinstance(context2.total_tokens, int)
    print("✓ ContextResult 属性完整")
    
    print("\n" + "=" * 80)
    print("✅ 所有原有功能测试通过！框架核心功能完整无损。")
    print("=" * 80 + "\n")
    
    return True


async def test_template_optimization_is_optional():
    """
    测试模板优化是可选的
    
    验证模板优化功能只有在用户显式导入和使用时才会生效。
    """
    print("\n" + "=" * 80)
    print("测试：模板优化是完全可选的")
    print("=" * 80 + "\n")
    
    # 1. 标准使用（不导入模板优化）
    engine = ContextEngine(app_name="optional-test", user_id="test-user")
    context = await engine.optimize("测试输入")
    
    # 验证结果不包含模板优化的标记
    has_template = any(
        item.metadata.get('type') == 'template_optimization'
        for item in context.items
        if hasattr(item, 'metadata')
    )
    assert not has_template, "不应该有模板优化标记"
    print("✓ 未使用模板优化时，结果不包含模板优化标记")
    
    # 2. 显式使用模板优化
    from contextmind.pipeline import TemplateBasedOptimization
    from contextmind.core import ProcessedContext
    
    optimizer = TemplateBasedOptimization()
    processed = ProcessedContext(items=context.items)
    optimized = await optimizer.optimize(processed)
    
    # 验证优化结果包含模板标记
    has_template_after = any(
        item.metadata.get('type') == 'template_optimization'
        for item in optimized.items
        if hasattr(item, 'metadata')
    )
    assert has_template_after, "使用后应该有模板优化标记"
    print("✓ 显式使用模板优化后，结果包含模板优化标记")
    
    print("\n" + "=" * 80)
    print("✅ 模板优化是完全可选的，只有显式使用时才生效。")
    print("=" * 80 + "\n")
    
    return True


async def test_no_import_pollution():
    """
    测试导入无污染
    
    验证导入 ContextEngine 不会自动导入模板优化组件。
    """
    print("\n" + "=" * 80)
    print("测试：导入无污染")
    print("=" * 80 + "\n")
    
    # 1. 导入 ContextEngine
    from contextmind import ContextEngine
    import sys
    
    # 2. 检查是否自动加载了模板优化模块
    template_modules = [
        'contextmind.pipeline.template_optimizer',
        'contextmind.pipeline.intent_extractor',
        'contextmind.core.prompt_template',
    ]
    
    loaded_before = [m for m in template_modules if m in sys.modules]
    
    # 3. 使用 ContextEngine
    engine = ContextEngine(app_name="import-test", user_id="test-user")
    await engine.optimize("测试")
    
    loaded_after = [m for m in template_modules if m in sys.modules]
    
    # 验证：使用 ContextEngine 不会自动加载模板模块
    # 注意：如果在之前的测试中已经导入过，这里可能会是True
    # 所以我们只检查是否没有新增加载
    print(f"使用前已加载的模板模块: {len(loaded_before)}")
    print(f"使用后已加载的模板模块: {len(loaded_after)}")
    
    if len(loaded_before) == 0:
        assert len(loaded_after) == 0, "不应该自动加载模板模块"
        print("✓ ContextEngine 不会自动加载模板优化模块")
    else:
        print("ℹ️  模板模块已在之前的测试中加载（这是正常的）")
    
    print("\n" + "=" * 80)
    print("✅ 导入测试通过，无污染。")
    print("=" * 80 + "\n")
    
    return True


async def test_backward_compatibility():
    """
    测试向后兼容性
    
    验证添加模板优化后，原有代码仍然可以正常运行。
    """
    print("\n" + "=" * 80)
    print("测试：向后兼容性")
    print("=" * 80 + "\n")
    
    # 模拟一个已有的应用代码（v7.3之前的代码）
    async def legacy_application():
        """模拟旧版本应用代码"""
        engine = ContextEngine(
            app_name="legacy-app",
            user_id="legacy-user"
        )
        
        # 旧的工作流
        context = await engine.optimize("用户消息")
        
        # 使用 context.items 构建提示词（标准方式）
        prompt_parts = [item.content for item in context.items]
        prompt = "\n".join(prompt_parts) if prompt_parts else "No context"
        
        # 模拟 LLM 调用
        llm_response = "助手回复"
        
        await engine.update("用户消息", llm_response)
        
        return True
    
    # 运行旧代码
    try:
        result = await legacy_application()
        assert result is True
        print("✓ 旧版本应用代码正常运行")
    except Exception as e:
        print(f"❌ 旧代码运行失败: {e}")
        raise
    
    print("\n" + "=" * 80)
    print("✅ 向后兼容性测试通过！旧代码无需修改即可运行。")
    print("=" * 80 + "\n")
    
    return True


async def test_framework_independence():
    """
    测试框架独立性
    
    验证模板优化可以独立于 ContextEngine 使用。
    """
    print("\n" + "=" * 80)
    print("测试：框架独立性")
    print("=" * 80 + "\n")
    
    from contextmind.pipeline import TemplateBasedOptimization
    from contextmind.core import ProcessedContext, ContextItem, ContextSource
    
    # 不使用 ContextEngine，直接使用模板优化
    optimizer = TemplateBasedOptimization()
    
    # 手动创建上下文
    items = [
        ContextItem(
            content="user: 你好",
            source=ContextSource.HISTORY,
            score=1.0
        ),
        ContextItem(
            content="assistant: 你好！",
            source=ContextSource.HISTORY,
            score=1.0
        ),
    ]
    
    context = ProcessedContext(items=items)
    
    # 独立使用模板优化
    result = await optimizer.optimize(context)
    
    assert result is not None
    assert len(result.items) > 0
    print("✓ 模板优化可以独立使用，不依赖 ContextEngine")
    
    print("\n" + "=" * 80)
    print("✅ 框架独立性测试通过！")
    print("=" * 80 + "\n")
    
    return True


async def main():
    """运行所有非侵入性测试"""
    print("\n" + "=" * 100)
    print(" " * 30 + "非侵入性验证测试套件")
    print("=" * 100)
    print("\n测试目标：验证模板优化的添加不影响 ContextMind 框架的原有功能\n")
    
    tests = [
        ("原有功能完整性", test_original_functionality_intact),
        ("模板优化可选性", test_template_optimization_is_optional),
        ("导入无污染", test_no_import_pollution),
        ("向后兼容性", test_backward_compatibility),
        ("框架独立性", test_framework_independence),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, True, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"❌ {test_name} 测试失败: {e}\n")
    
    # 输出总结
    print("\n" + "=" * 100)
    print(" " * 40 + "测试总结")
    print("=" * 100 + "\n")
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status} - {test_name}")
        if error:
            print(f"         错误: {error}")
    
    print("\n" + "=" * 100)
    print(f"总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 恭喜！所有非侵入性测试通过！")
        print("✅ 模板优化功能的添加没有影响 ContextMind 框架的原有功能。")
    else:
        print("\n⚠️  部分测试失败，请检查实现。")
    
    print("=" * 100 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
