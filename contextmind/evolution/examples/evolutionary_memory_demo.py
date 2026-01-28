"""
进化式记忆更新器演示

展示如何使用 EvolutionaryMemoryUpdater 借鉴 AlphaEvolve/ThetaEvolve 的进化思想
来优化对话任务中的记忆库管理。

核心思想：
- 记忆库作为"种群"
- 每条记忆是"个体"
- 适应度评估记忆价值
- 进化操作优化记忆质量
"""

import asyncio
from datetime import datetime, timedelta
from contextmind.evolution import EvolutionaryMemoryUpdater
from contextmind.memory import FitnessCalculator
from contextmind.core.data_models import ContextItem, Knowledge, ScoreInfo
from contextmind.core.types import ContextSource, KnowledgeType


def create_sample_memory(content: str, score: float, days_old: int = 0, usage_count: int = 0) -> ContextItem:
    """创建示例记忆"""
    timestamp = datetime.now() - timedelta(days=days_old)
    return ContextItem(
        content=content,
        source=ContextSource.MEMORY,
        score=score,
        timestamp=timestamp,
        metadata={
            'usage_count': usage_count,
            'last_used': timestamp.timestamp(),
            'accuracy': 1.0,
            'relevance': score,
            'creation_time': timestamp.timestamp()
        }
    )


def create_sample_knowledge(content: str, ktype: KnowledgeType, confidence: float) -> Knowledge:
    """创建示例知识"""
    from contextmind.core.data_models import ScoreInfo
    return Knowledge(
        knowledge_type=ktype,
        content=content,
        scores=ScoreInfo(confidence=confidence),
        metadata={"source": "demo"}
    )


async def demo_evolutionary_updater():
    """演示进化式记忆更新器"""
    
    print("=" * 70)
    print("进化式记忆更新器演示")
    print("借鉴 AlphaEvolve/ThetaEvolve 的进化思想优化记忆库")
    print("=" * 70)
    print()
    
    # 创建进化式更新器
    updater = EvolutionaryMemoryUpdater(
        max_memory_size=10,      # 最多保留10条记忆
        elite_ratio=0.7,         # 保留70%精英
        similarity_threshold=0.85,  # 相似度阈值
        min_fitness_threshold=0.2,  # 最低适应度
        enable_decay=True        # 启用使用次数衰减
    )
    
    print("配置:")
    print(f"  - 最大记忆容量: {updater.max_memory_size}")
    print(f"  - 精英保留比例: {updater.elite_ratio}")
    print(f"  - 相似度合并阈值: {updater.similarity_threshold}")
    print(f"  - 最低适应度阈值: {updater.min_fitness_threshold}")
    print()
    
    # 场景1: 初始记忆库
    print("场景1: 建立初始记忆库")
    print("-" * 70)
    
    initial_memories = [
        create_sample_memory("[PREFERENCE] 我喜欢喝咖啡", 0.9, days_old=5, usage_count=10),
        create_sample_memory("[FACT] 我在北京工作", 0.85, days_old=10, usage_count=5),
        create_sample_memory("[PREFERENCE] 我喜欢看电影", 0.8, days_old=15, usage_count=3),
        create_sample_memory("[FACT] 我是程序员", 0.95, days_old=20, usage_count=15),
        create_sample_memory("[EVENT] 昨天去了公园", 0.7, days_old=1, usage_count=1),
    ]
    
    # 添加一些新知识
    new_knowledge_1 = [
        create_sample_knowledge("我非常喜欢喝拿铁咖啡", KnowledgeType.PREFERENCE, 0.92),  # 与第1条相似
        create_sample_knowledge("我住在上海", KnowledgeType.FACT, 0.88),  # 新知识
        create_sample_knowledge("我喜欢打篮球", KnowledgeType.PREFERENCE, 0.85),  # 新知识
    ]
    
    # 执行第一次更新
    updated_memories = await updater.update(initial_memories, new_knowledge_1)
    
    print(f"初始记忆数: {len(initial_memories)}")
    print(f"新知识数: {len(new_knowledge_1)}")
    print(f"更新后记忆数: {len(updated_memories)}")
    print()
    
    # 显示适应度评分
    print("记忆适应度评分:")
    fitness_calc = FitnessCalculator()
    for i, memory in enumerate(updated_memories[:5], 1):
        fitness_score = memory.metadata.get('fitness_score', 'N/A')
        usage_count = memory.metadata.get('usage_count', 0)
        if isinstance(fitness_score, (int, float)):
            fitness_str = f"{fitness_score:.3f}"
        else:
            fitness_str = str(fitness_score)
        print(f"  {i}. {memory.content[:50]}... ")
        print(f"     适应度={fitness_str}, "
              f"使用次数={usage_count}, 置信度={memory.score:.2f}")
    print()
    
    # 场景2: 持续对话中的记忆演化
    print("场景2: 多轮对话中的记忆演化")
    print("-" * 70)
    
    # 模拟多轮对话
    for turn in range(1, 4):
        print(f"\n第{turn}轮对话:")
        
        # 每轮添加一些新知识
        new_knowledge = [
            create_sample_knowledge(f"今天学习了Python第{turn}课", KnowledgeType.EVENT, 0.75),
            create_sample_knowledge(f"我对人工智能很感兴趣", KnowledgeType.PREFERENCE, 0.80 + turn * 0.05),
        ]
        
        # 模拟记忆使用（提升某些记忆的使用次数）
        for i, memory in enumerate(updated_memories):
            if "喜欢" in memory.content and turn % 2 == 0:
                # 模拟使用
                updated_memories[i] = fitness_calc.observe_usage(memory)
        
        # 更新记忆库
        updated_memories = await updater.update(updated_memories, new_knowledge)
        
        print(f"  新增知识: {len(new_knowledge)} 条")
        print(f"  当前记忆数: {len(updated_memories)} 条")
        
        # 显示统计信息
        stats = updater.get_stats()
        print(f"  统计: 总更新={stats['updates']}, 合并={stats['merges']}, "
              f"淘汰={stats['evictions']}, 新增={stats['additions']}")
    
    print()
    
    # 场景3: 记忆质量对比
    print("场景3: 进化前后的记忆质量对比")
    print("-" * 70)
    
    # 计算平均适应度
    total_fitness = 0
    for memory in updated_memories:
        fitness_score = memory.metadata.get('fitness_score', 0)
        if isinstance(fitness_score, float):
            total_fitness += fitness_score
    
    avg_fitness = total_fitness / len(updated_memories) if updated_memories else 0
    
    print(f"最终记忆库状态:")
    print(f"  - 记忆总数: {len(updated_memories)}")
    print(f"  - 平均适应度: {avg_fitness:.3f}")
    print(f"  - 最高适应度: {max((m.metadata.get('fitness_score', 0) for m in updated_memories), default=0):.3f}")
    print()
    
    print("记忆库内容（按适应度排序）:")
    sorted_memories = sorted(
        updated_memories,
        key=lambda m: m.metadata.get('fitness_score', 0),
        reverse=True
    )
    
    for i, memory in enumerate(sorted_memories[:5], 1):
        fitness = memory.metadata.get('fitness_score', 0)
        usage = memory.metadata.get('usage_count', 0)
        merged = memory.metadata.get('merged', False)
        status = "🔄合并" if merged else "✨新增"
        
        print(f"  {i}. {status} [适应度={fitness:.3f}, 使用={usage}次]")
        print(f"     {memory.content}")
    
    print()
    
    # 场景4: 进化思想的应用效果
    print("场景4: 进化思想的应用效果总结")
    print("-" * 70)
    
    stats = updater.get_stats()
    print("进化操作统计:")
    print(f"  ✅ 适应度评估: 每次更新自动评估所有记忆")
    print(f"  ✅ 精英选择: 保留前{int(updater.elite_ratio * 100)}%的高质量记忆")
    print(f"  ✅ 记忆合并: 总共合并 {stats['merges']} 对相似记忆")
    print(f"  ✅ 新增记忆: 总共新增 {stats['additions']} 条记忆")
    print(f"  ✅ 记忆淘汰: 总共淘汰 {stats['evictions']} 条低价值记忆")
    print(f"  ✅ 容量控制: 保持在 {updater.max_memory_size} 条以内")
    print()
    
    print("进化思想 vs 传统方法:")
    print("  传统方法: 简单添加 → 容易爆炸 → 质量参差不齐")
    print("  进化方法: 适应度评估 → 精英选择 → 自动优化 → 高质量稳定")
    print()
    
    print("=" * 70)
    print("演示完成！")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(demo_evolutionary_updater())
