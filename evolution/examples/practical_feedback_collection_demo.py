"""
实践示例：在真实对话系统中集成观测和反馈收集

展示如何在实际的对话系统中：
1. 观测记忆的检索和使用
2. 收集各种类型的反馈
3. 分析隐式反馈
4. 应用到记忆优化
"""

import sys
import asyncio
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from contextmind.core.data_models import ContextItem, ContextSource
from contextmind.memory.memory_fitness import FitnessCalculator
from evolution.feedback import (
    ObservationCollector,
    FeedbackCollector,
    ImplicitFeedbackAnalyzer,
    ConversationTurn,
    ConversationSession,
    FeedbackSource
)


def create_test_memory(content: str, memory_id: str) -> ContextItem:
    """创建测试记忆"""
    return ContextItem(
        content=content,
        source=ContextSource.MEMORY,
        score=0.8,
        timestamp=datetime.now(),
        metadata={'id': memory_id}
    )


def print_memory_status(memory: ContextItem, calculator: FitnessCalculator, title: str):
    """打印记忆状态"""
    fitness = calculator.get_fitness(memory)
    score = calculator.calculate_fitness_score(memory)
    
    print(f"\n{title}")
    print(f"  适应度: {score:.3f}")
    print(f"  检索: {fitness.retrieval_count}次, 使用: {fitness.actual_usage_count}次, "
          f"使用率: {fitness.usage_rate:.0%}")
    print(f"  反馈: 👍{fitness.positive_feedback_count} "
          f"👎{fitness.negative_feedback_count} "
          f"✏️{fitness.correction_count}")
    print(f"  准确性: {fitness.accuracy:.2f}, 贡献度: {fitness.contribution_score:.2f}")


async def main():
    print("\n" + "=" * 70)
    print("实践示例：对话系统中的观测和反馈收集")
    print("=" * 70)
    
    # 初始化组件
    fitness_calculator = FitnessCalculator()
    obs_collector = ObservationCollector(fitness_calculator)
    feedback_collector = FeedbackCollector(fitness_calculator)
    implicit_analyzer = ImplicitFeedbackAnalyzer(feedback_collector)
    
    # 创建测试记忆
    memories = {
        'hobby': create_test_memory("用户喜欢编程", "mem_hobby"),
        'location': create_test_memory("用户住在北京", "mem_location"),
        'job': create_test_memory("用户是软件工程师", "mem_job"),
    }
    
    # ========================================================================
    # 场景1：完整的对话流程（检索 → 使用 → 反馈）
    # ========================================================================
    print("\n\n【场景1】完整对话流程")
    print("-" * 70)
    
    print("\n步骤1: 用户提问")
    print("用户: 我最近在学什么？")
    
    print("\n步骤2: 检索相关记忆")
    retrieved = [memories['hobby'], memories['job']]
    for i, mem in enumerate(retrieved):
        obs_collector.observe_retrieval(mem, query="我最近在学什么", position=i)
    print(f"  检索到 {len(retrieved)} 条记忆")
    
    print("\n步骤3: 生成回复（仅使用hobby记忆）")
    used = [memories['hobby']]
    ignored = [memories['job']]
    
    for mem in used:
        obs_collector.observe_usage(mem, used_in_prompt=True, contributed=True)
    for mem in ignored:
        obs_collector.observe_ignored(mem, reason="不够相关")
    
    response = "根据记录，您喜欢编程"
    print(f"  助手: {response}")
    print(f"  使用了 {len(used)} 条记忆")
    
    print("\n步骤4: 用户给予正面反馈")
    feedback_collector.collect_positive_feedback(
        used,
        source=FeedbackSource.EXPLICIT_USER,
        details={'user_action': '点赞'}
    )
    print("  用户点击了 👍")
    
    # 查看记忆状态
    print_memory_status(memories['hobby'], fitness_calculator, "\n记忆状态（hobby）")
    print_memory_status(memories['job'], fitness_calculator, "记忆状态（job - 被忽略）")
    
    # ========================================================================
    # 场景2：负面反馈和纠正
    # ========================================================================
    print("\n\n【场景2】负面反馈和纠正")
    print("-" * 70)
    
    print("\n用户: 我在哪里工作？")
    print("助手: 根据记录，您住在北京  [使用了location记忆]")
    
    # 模拟观测
    obs_collector.observe_retrieval(memories['location'], "我在哪里工作", position=0)
    obs_collector.observe_usage(memories['location'])
    
    print("\n用户: 不对，我问的是工作地点，不是住址")
    print("  [系统识别为负面反馈]")
    
    feedback_collector.collect_negative_feedback(
        [memories['location']],
        source=FeedbackSource.EXPLICIT_USER,
        details={'reason': '回答不相关'}
    )
    
    print_memory_status(memories['location'], fitness_calculator, "\n记忆状态（location - 收到负面反馈）")
    
    # ========================================================================
    # 场景3：评分反馈
    # ========================================================================
    print("\n\n【场景3】评分反馈")
    print("-" * 70)
    
    print("\n对话结束后，用户对整体对话评分: 4.5/5")
    
    # 将高评分转换为正面反馈
    session_memories = [memories['hobby'], memories['location'], memories['job']]
    feedback_collector.collect_rating(
        session_memories,
        rating=0.9,  # 4.5/5 = 0.9
        details={'session_id': 'session_123'}
    )
    
    print("\n所有记忆收到正面反馈：")
    for name, mem in memories.items():
        fitness = fitness_calculator.get_fitness(mem)
        print(f"  {name}: 准确性 {fitness.accuracy:.2f}")
    
    # ========================================================================
    # 场景4：隐式反馈分析
    # ========================================================================
    print("\n\n【场景4】隐式反馈分析")
    print("-" * 70)
    
    # 创建对话会话
    session = ConversationSession(session_id="session_456")
    
    # 第一轮对话
    turn1 = ConversationTurn(
        turn_id="turn_1",
        user_query="你好",
        system_response="您好！有什么可以帮您的吗？",
        used_memory_ids=[]
    )
    session.add_turn(turn1)
    
    # 第二轮对话（3秒后）
    import time
    time.sleep(0.1)  # 模拟时间流逝
    turn2 = ConversationTurn(
        turn_id="turn_2",
        user_query="我的爱好是什么？",
        system_response="您喜欢编程",
        used_memory_ids=['mem_hobby']
    )
    session.add_turn(turn2)
    
    # 第三轮对话（2秒后，快速回复）
    time.sleep(0.1)
    turn3 = ConversationTurn(
        turn_id="turn_3",
        user_query="对，我最近在学Python",
        system_response="太好了！Python是一门很强大的语言",
        used_memory_ids=[]
    )
    session.add_turn(turn3)
    
    print("\n分析对话行为：")
    print("  turn2 → turn3: 用户快速回复，说明满意")
    print("  turn3内容: 用户肯定了turn2的回答（'对'）")
    
    # 运行隐式分析
    implicit_analyzer.analyze_turn(turn3, session)
    
    print("\n隐式反馈推断：")
    print("  ✅ 对话延续 → 弱正面信号")
    print("  ✅ 快速回复 → 弱正面信号")
    print("  ✅ 用户肯定 → 正面信号")
    
    # ========================================================================
    # 场景5：贡献度评估
    # ========================================================================
    print("\n\n【场景5】贡献度评估")
    print("-" * 70)
    
    print("\n自动评估记忆对回复的贡献")
    
    # 模拟LLM评估
    print("\n评估1: hobby记忆对'您喜欢编程'的贡献")
    feedback_collector.update_contribution_score(memories['hobby'], 0.95)
    print("  贡献度: 0.95 (高)")
    
    print("\n评估2: location记忆对工作地点问题的贡献")
    feedback_collector.update_contribution_score(memories['location'], 0.1)
    print("  贡献度: 0.1 (低，回答不相关)")
    
    # 显示最终状态
    print("\n所有记忆的最终状态：")
    for name, mem in memories.items():
        print_memory_status(mem, fitness_calculator, f"\n{name.upper()}")
    
    # ========================================================================
    # 场景6：统计和总结
    # ========================================================================
    print("\n\n【场景6】统计和总结")
    print("-" * 70)
    
    # 观测统计
    print("\n观测统计：")
    observations = obs_collector.get_observations()
    print(f"  总观测事件: {len(observations)}")
    print(f"  检索事件: {len([o for o in observations if o.event_type == 'retrieved'])}")
    print(f"  使用事件: {len([o for o in observations if o.event_type == 'used'])}")
    print(f"  忽略事件: {len([o for o in observations if o.event_type == 'ignored'])}")
    
    # 反馈统计
    print("\n反馈统计：")
    stats = feedback_collector.get_feedback_stats()
    print(f"  总反馈: {stats['total']}")
    print(f"  正面: {stats['positive']}")
    print(f"  负面: {stats['negative']}")
    print(f"  纠正: {stats['correction']}")
    
    # 记忆排名
    print("\n记忆适应度排名：")
    memory_scores = [
        (name, fitness_calculator.calculate_fitness_score(mem))
        for name, mem in memories.items()
    ]
    memory_scores.sort(key=lambda x: x[1], reverse=True)
    
    for i, (name, score) in enumerate(memory_scores, 1):
        print(f"  {i}. {name}: {score:.3f}")
    
    # ========================================================================
    # 总结
    # ========================================================================
    print("\n\n" + "=" * 70)
    print("总结：实践中的观测和反馈")
    print("=" * 70)
    
    print("\n✅ 实现的功能：")
    print("  1. 观测收集：检索、使用、忽略事件")
    print("  2. 显式反馈：点赞/点踩、纠正、评分")
    print("  3. 隐式反馈：对话延续、响应时间、用户行为")
    print("  4. 自动评估：贡献度计算")
    print("  5. 适应度更新：基于所有观测和反馈")
    
    print("\n💡 关键发现：")
    print("  • hobby记忆: 高使用率、正面反馈 → 高适应度")
    print("  • location记忆: 被误用、负面反馈 → 适应度下降")
    print("  • job记忆: 被检索但未使用 → 使用率影响适应度")
    
    print("\n🎯 下一步：")
    print("  • 在进化更新时，根据适应度选择保留/淘汰记忆")
    print("  • 高适应度记忆优先保留")
    print("  • 低适应度记忆可能被淘汰")
    print("  • 持续学习和优化")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
