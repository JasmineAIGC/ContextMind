"""
Plugin 架构示例

此文件演示如何使用 ContextMind 的 plugin 架构
来自定义 memory 提取、检索和更新策略。
"""

import asyncio
from contextmind import ContextEngine
from contextmind.core.models import Message, MessageRole


# ============================================================================
# 示例 1: 基本用法（默认 Plugins）
# ============================================================================

async def example_basic_usage():
    """
    使用默认 plugins 的基本用法。
    无需配置 - 开箱即用。
    """
    print("=" * 80)
    print("示例 1: 基本用法（默认 Plugins）")
    print("=" * 80)
    
    # 使用默认设置创建 engine
    engine = ContextEngine(
        app_name="plugin-demo",
        user_id="demo-user"
    )
    
    # 正常使用 - plugins 透明工作
    await engine.update(
        user_input="我喜欢吃辣",
        assistant_response="好的，我记住了您喜欢吃辣的食物。"
    )
    
    # 提取知识（默认使用 RuleBasedExtractor）
    knowledge = await engine.extract_knowledge()
    print(f"\n✓ 已提取 {len(knowledge)} 个知识项")
    
    # 优化 context（默认使用 SemanticSearchRetriever）
    context = await engine.optimize("推荐一些食物", include_memory=True)
    print(f"✓ 已检索 {len(context.long_term_memory)} 条记忆")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# 示例 2: 使用可选组件
# ============================================================================

async def example_optional_components():
    """
    启用可选的 PostProcessor 和 Summarizer 组件。
    """
    print("=" * 80)
    print("示例 2: 使用可选组件")
    print("=" * 80)
    
    # 创建启用了可选组件的 engine
    engine = ContextEngine(
        app_name="plugin-demo",
        user_id="demo-user",
        use_postprocessor=True,  # 启用输出后处理
        use_summarizer=True      # 启用对话摘要
    )
    
    # 添加一些对话
    await engine.update("你好", "你好！有什么可以帮你的？")
    await engine.update("我想了解Python", "当然，Python是一门很强大的编程语言。")
    
    # 生成摘要（如果 summarizer 可用）
    if engine.summarizer:
        messages = await engine.session_manager.get_recent_history()
        summary = await engine.summarizer.generate_summary(messages)
        print(f"\n✓ 已生成摘要:\n{summary}")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# 示例 3: 自定义检索器插件
# ============================================================================

async def example_custom_retriever():
    """
    演示使用自定义检索器插件。
    """
    print("=" * 80)
    print("示例 3: 自定义检索器插件")
    print("=" * 80)
    
    from contextmind.memory import HybridRetriever
    from contextmind.memory import MemoryBank
    
    # 使用 HybridRetriever 创建自定义记忆库
    memory_bank = MemoryBank(
        app_name="plugin-demo",
        user_id="demo-user",
        retriever=HybridRetriever(
            semantic_weight=0.7,    # 语义相似度权重 70%
            keyword_weight=0.3       # 关键词匹配权重 30%
        )
    )
    
    # 存储一些记忆
    from contextmind.core.models import Knowledge, KnowledgeType
    
    test_knowledge = [
        Knowledge(
            content="用户喜欢Python编程",
            type=KnowledgeType.PREFERENCE,
            confidence=0.9
        ),
        Knowledge(
            content="用户是软件工程师",
            type=KnowledgeType.FACT,
            confidence=0.85
        )
    ]
    
    await memory_bank.store(test_knowledge)
    
    # 使用混合 retriever 检索
    results = await memory_bank.retrieve("Python", limit=5)
    print(f"\n✓ HybridRetriever 找到 {len(results)} 条相关记忆")
    for i, item in enumerate(results, 1):
        print(f"  {i}. {item.content} (score: {item.score:.2f})")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# 示例 4: 自定义提取器插件
# ============================================================================

async def example_custom_extractor():
    """
    演示创建简单的自定义 extractor。
    """
    print("=" * 80)
    print("示例 4: 自定义 Extractor Plugin")
    print("=" * 80)
    
    from contextmind.memory import BaseExtractor
    from contextmind.core.models import Knowledge, KnowledgeType, Message
    from typing import List
    
    class SimpleKeywordExtractor(BaseExtractor):
        """
        自定义提取器，查找特定关键词。
        """
        def __init__(self, keywords=None):
            self.keywords = keywords or ['喜欢', '讨厌', '想要']
        
        async def extract(self, messages: List[Message]) -> List[Knowledge]:
            knowledge = []
            
            for msg in messages:
                if msg.role.value != 'user':
                    continue
                
                # 检查关键词
                for keyword in self.keywords:
                    if keyword in msg.content:
                        knowledge.append(Knowledge(
                            content=msg.content,
                            type=KnowledgeType.PREFERENCE,
                            confidence=0.8,
                            metadata={'keyword': keyword}
                        ))
                        break
            
            return knowledge
    
    # 使用自定义 extractor
    extractor = SimpleKeywordExtractor(keywords=['喜欢', '想要'])
    
    test_messages = [
        Message(role=MessageRole.USER, content="我喜欢编程"),
        Message(role=MessageRole.ASSISTANT, content="很好"),
        Message(role=MessageRole.USER, content="我想要学习AI"),
    ]
    
    knowledge = await extractor.extract(test_messages)
    print(f"\n✓ CustomExtractor 已提取 {len(knowledge)} 项:")
    for i, k in enumerate(knowledge, 1):
        print(f"  {i}. {k.content} (置信度: {k.confidence:.2f})")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# 示例 5: 自定义 Updater Plugin
# ============================================================================

async def example_custom_updater():
    """
    演示创建带容量限制的简单自定义 updater。
    """
    print("=" * 80)
    print("示例 5: 自定义 Updater Plugin")
    print("=" * 80)
    
    from contextmind.memory import BaseUpdater
    from contextmind.core.models import ContextItem, ContextSource, Knowledge, KnowledgeType
    from typing import List
    
    class CapacityLimitedUpdater(BaseUpdater):
        """
        自定义更新器，限制 cache 大小并淘汰最旧项。
        """
        def __init__(self, max_size=10):
            self.max_size = max_size
        
        async def update(
            self,
            memory_cache: List[ContextItem],
            new_knowledge: List[Knowledge]
        ) -> List[ContextItem]:
            # 添加新项
            for k in new_knowledge:
                if k.confidence >= 0.7:  # 质量过滤
                    memory_cache.append(ContextItem(
                        content=f"[{k.type.value}] {k.content}",
                        source=ContextSource.MEMORY,
                        score=k.confidence
                    ))
            
            # 如果超出容量，淘汰最旧的项
            if len(memory_cache) > self.max_size:
                # 保留最新的项
                memory_cache = memory_cache[-self.max_size:]
                print(f"  ⚠️  已淘汰最旧的项（保留 {self.max_size} 个最新的）")
            
            return memory_cache
    
    # 使用自定义 updater
    from contextmind.memory import MemoryBank
    
    memory_bank = MemoryBank(
        app_name="plugin-demo",
        user_id="demo-user",
        updater=CapacityLimitedUpdater(max_size=5)
    )
    
    # 添加知识项
    test_knowledge = [
        Knowledge(content=f"记忆 {i}", type=KnowledgeType.FACT, confidence=0.8)
        for i in range(10)
    ]
    
    await memory_bank.store(test_knowledge)
    cache = memory_bank.get_memory_cache()
    
    print(f"\n✓ CustomUpdater 维护的 cache 大小: {len(cache)} 项 (最大: 5)")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# Main: 运行所有示例
# ============================================================================

async def main():
    """运行所有示例。"""
    print("\n" + "=" * 80)
    print("ContextMind Plugin 架构示例")
    print("=" * 80 + "\n")
    
    await example_basic_usage()
    await example_optional_components()
    await example_custom_retriever()
    await example_custom_extractor()
    await example_custom_updater()
    
    print("=" * 80)
    print("所有示例已完成！")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
