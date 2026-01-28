"""
观测和反馈机制演示

展示如何使用观测和反馈来改进记忆库的适应度评估。
这是真正的"进化式学习"：通过观测使用情况和收集反馈来持续优化记忆质量。
"""

import sys
import asyncio
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextmind.core.data_models import ContextItem, ContextSource
from contextmind.memory.memory_fitness import (
    MemoryFitness,
    FitnessCalculator,
    ObservationType,
    FeedbackType,
    MemoryObservation
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


def print_fitness(memory: ContextItem, calculator: FitnessCalculator, title: str):
    """打印适应度信息"""
    fitness = calculator.get_fitness(memory)
    score = fitness.calculate_score()
    
    print(f"\n{title}")
    print("=" * 60)
    print(f"  适应度分数: {score:.3f}")
    print(f"  检索次数: {fitness.retrieval_count}")
    print(f"  实际使用次数: {fitness.actual_usage_count}")
    print(f"  使用率: {fitness.usage_rate:.2f}")
    print(f"  准确性: {fitness.accuracy:.2f}")
    print(f"  反馈得分: {fitness.feedback_score:.2f}")
    print(f"  正面反馈: {fitness.positive_feedback_count}")
    print(f"  负面反馈: {fitness.negative_feedback_count}")
    print(f"  纠正次数: {fitness.correction_count}")
    print(f"  贡献度: {fitness.contribution_score:.2f}")


async def main():
    print("\n" + "=" * 70)
    print("观测和反馈机制演示 - 进化式记忆学习")
    print("=" * 70)
    
    # 创建适应度计算器
    calculator = FitnessCalculator()
    
    # ========================================================================
    # 场景1: 观测记忆使用情况
    # ========================================================================
    print("\n\n【场景1】观测记忆使用情况")
    print("-" * 70)
    
    memory1 = create_test_memory("用户喜欢喝咖啡", "mem_001")
    print_fitness(memory1, calculator, "初始状态")
    
    # 观测：记忆被检索了5次
    print("\n观测：记忆被检索 5 次")
    for i in range(5):
        memory1 = calculator.observe_retrieval(memory1)
    print_fitness(memory1, calculator, "检索 5 次后")
    
    # 观测：其中3次被实际使用
    print("\n观测：其中 3 次被实际使用")
    for i in range(3):
        memory1 = calculator.observe_usage(memory1)
    print_fitness(memory1, calculator, "使用 3 次后")
    
    # 观测：其余2次被忽略（检索但未使用）
    print("\n观测：其余 2 次被忽略")
    for i in range(2):
        memory1 = calculator.observe_ignored(memory1)
    print_fitness(memory1, calculator, "忽略 2 次后")
    
    print(f"\n💡 使用率 = 3 / 5 = 0.60，说明这条记忆有一定价值但不是总被需要")
    
    # ========================================================================
    # 场景2: 正面反馈 - 记忆被验证正确
    # ========================================================================
    print("\n\n【场景2】正面反馈 - 记忆被验证正确")
    print("-" * 70)
    
    memory2 = create_test_memory("用户住在北京", "mem_002")
    print_fitness(memory2, calculator, "初始状态")
    
    # 模拟使用和正面反馈
    print("\n模拟：记忆被使用，用户确认信息正确")
    memory2 = calculator.observe_retrieval(memory2)
    memory2 = calculator.observe_usage(memory2)
    memory2 = calculator.record_positive_feedback(memory2)
    print_fitness(memory2, calculator, "正面反馈后")
    
    # 再次正面反馈
    print("\n再次正面反馈")
    memory2 = calculator.record_positive_feedback(memory2)
    print_fitness(memory2, calculator, "累积正面反馈后")
    
    print(f"\n💡 准确性提升，适应度分数增加，未来更可能被保留")
    
    # ========================================================================
    # 场景3: 负面反馈 - 记忆导致错误
    # ========================================================================
    print("\n\n【场景3】负面反馈 - 记忆导致错误")
    print("-" * 70)
    
    memory3 = create_test_memory("用户的手机号是13800138000", "mem_003")
    print_fitness(memory3, calculator, "初始状态")
    
    # 模拟使用但收到负面反馈
    print("\n模拟：记忆被使用，但信息不正确")
    memory3 = calculator.observe_retrieval(memory3)
    memory3 = calculator.observe_usage(memory3)
    memory3 = calculator.record_negative_feedback(memory3)
    print_fitness(memory3, calculator, "负面反馈后")
    
    # 用户纠正
    print("\n用户纠正：手机号实际是13900139000")
    memory3 = calculator.record_correction(memory3)
    print_fitness(memory3, calculator, "纠正后")
    
    print(f"\n💡 准确性大幅降低，适应度分数下降，未来可能被淘汰")
    
    # ========================================================================
    # 场景4: 贡献度评估
    # ========================================================================
    print("\n\n【场景4】贡献度评估")
    print("-" * 70)
    
    memory4 = create_test_memory("用户正在学习机器学习", "mem_004")
    print_fitness(memory4, calculator, "初始状态 (贡献度=0.5)")
    
    # 模拟高贡献：记忆帮助生成了高质量回复
    print("\n观测：记忆对回复质量有重要贡献")
    memory4 = calculator.update_contribution(memory4, 0.9)
    print_fitness(memory4, calculator, "高贡献后")
    
    # 模拟低贡献：记忆几乎没用上
    print("\n后续使用中贡献较小")
    memory4 = calculator.update_contribution(memory4, 0.2)
    print_fitness(memory4, calculator, "低贡献后")
    
    print(f"\n💡 贡献度使用指数移动平均，逐渐反映真实价值")
    
    # ========================================================================
    # 场景5: 综合对比 - 好记忆 vs 坏记忆
    # ========================================================================
    print("\n\n【场景5】综合对比 - 好记忆 vs 坏记忆")
    print("-" * 70)
    
    # 好记忆：高使用率、正面反馈、高贡献
    good_memory = create_test_memory("用户对Python很感兴趣", "mem_good")
    for i in range(10):
        good_memory = calculator.observe_retrieval(good_memory)
    for i in range(8):  # 80%使用率
        good_memory = calculator.observe_usage(good_memory)
    for i in range(3):
        good_memory = calculator.record_positive_feedback(good_memory)
    good_memory = calculator.update_contribution(good_memory, 0.85)
    
    # 坏记忆：低使用率、负面反馈、低贡献
    bad_memory = create_test_memory("用户讨厌编程", "mem_bad")
    for i in range(10):
        bad_memory = calculator.observe_retrieval(bad_memory)
    for i in range(2):  # 20%使用率
        bad_memory = calculator.observe_usage(bad_memory)
    for i in range(5):
        bad_memory = calculator.observe_ignored(bad_memory)
    for i in range(2):
        bad_memory = calculator.record_negative_feedback(bad_memory)
    bad_memory = calculator.record_correction(bad_memory)
    bad_memory = calculator.update_contribution(bad_memory, 0.15)
    
    print_fitness(good_memory, calculator, "好记忆（应该被保留）")
    print_fitness(bad_memory, calculator, "坏记忆（应该被淘汰）")
    
    good_score = calculator.calculate_fitness_score(good_memory)
    bad_score = calculator.calculate_fitness_score(bad_memory)
    
    print(f"\n\n📊 适应度对比")
    print(f"  好记忆: {good_score:.3f}")
    print(f"  坏记忆: {bad_score:.3f}")
    print(f"  差距: {(good_score - bad_score):.3f}")
    
    print(f"\n💡 通过观测和反馈，系统能够自动识别和区分优质记忆与低质量记忆")
    
    # ========================================================================
    # 场景6: 进化流程演示
    # ========================================================================
    print("\n\n【场景6】进化流程演示 - 观测→反馈→学习循环")
    print("-" * 70)
    
    memory5 = create_test_memory("用户喜欢阅读科幻小说", "mem_005")
    
    print("第1轮对话:")
    print("  观测：记忆被检索并使用")
    memory5 = calculator.observe_retrieval(memory5)
    memory5 = calculator.observe_usage(memory5)
    print(f"  适应度: {calculator.calculate_fitness_score(memory5):.3f}")
    
    print("\n第2轮对话:")
    print("  反馈：用户表示满意 (正面反馈)")
    memory5 = calculator.record_positive_feedback(memory5)
    print(f"  适应度: {calculator.calculate_fitness_score(memory5):.3f}")
    
    print("\n第3轮对话:")
    print("  观测：记忆被检索但未使用 (忽略)")
    memory5 = calculator.observe_retrieval(memory5)
    memory5 = calculator.observe_ignored(memory5)
    print(f"  适应度: {calculator.calculate_fitness_score(memory5):.3f}")
    
    print("\n第4轮对话:")
    print("  观测：记忆再次被使用，高贡献")
    memory5 = calculator.observe_retrieval(memory5)
    memory5 = calculator.observe_usage(memory5)
    memory5 = calculator.update_contribution(memory5, 0.9)
    print(f"  适应度: {calculator.calculate_fitness_score(memory5):.3f}")
    
    print(f"\n💡 每轮对话都会观测和学习，适应度持续优化")
    
    # ========================================================================
    # 总结
    # ========================================================================
    print("\n\n" + "=" * 70)
    print("总结：观测-反馈-学习 进化循环")
    print("=" * 70)
    
    print("\n传统方法（基于规则）:")
    print("  ❌ 只统计使用次数")
    print("  ❌ 不考虑使用效果")
    print("  ❌ 无法从反馈中学习")
    print("  ❌ 适应度静态不变")
    
    print("\n进化方法（观测-反馈-学习）:")
    print("  ✅ 观测检索和使用情况")
    print("  ✅ 收集用户反馈（正面/负面/纠正）")
    print("  ✅ 评估实际贡献度")
    print("  ✅ 适应度动态学习和调整")
    print("  ✅ 自动识别优质记忆")
    print("  ✅ 淘汰低价值记忆")
    
    print("\n核心优势:")
    print("  1️⃣  真实评估：基于实际使用效果而非简单计数")
    print("  2️⃣  持续学习：从每次交互中学习和改进")
    print("  3️⃣  自动优化：无需人工干预，自适应调整")
    print("  4️⃣  质量保证：有反馈机制保证记忆准确性")
    
    print("\n" + "=" * 70)
    print("演示完成！")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
