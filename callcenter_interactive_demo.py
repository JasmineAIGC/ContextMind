"""
ContextMind v7.3 客服对话 Interactive Demo

五层架构 (core/pipeline/strategies/adapters/utils) + 智能记忆系统
命令行交互式客服对话演示。
"""

import asyncio
import os
import argparse
import time
import random

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("警告: 未安装 python-dotenv。请通过以下命令安装: pip install python-dotenv")
    print("未配置 .env 文件可能导致 LLM 功能无法正常工作")

from contextmind import (
    ContextEngine,
    setup_logging,
    get_logger,
    LogLevel,
    MessageRole,
)

from examples.callcenter_app import CallCenterApplication, CALLCENTER_SYSTEM_PROMPT

logger = get_logger(__name__)

# 开场白列表 - 客服机器人会从中随机选择一条作为开场
OPENING_SCRIPTS = [
    "您好，请问是胡女士本人吗？耽误您一分钟，有项业务想跟您同步。",
    "您好，我是马上消费的客服，有个好消息要通知您。",
    "您好，打扰您一下，有个重要业务需要跟您确认一下。",
    "您好，我是优逸花客服，有个专属福利要通知您。",
    "您好，耽误您两分钟时间，有个限时优惠要介绍给您。",
    "您好，我是马上消费工作人员，有个额度提升的好消息。",
    "您好，打扰您了，有个重要提醒需要通知您。",
    "您好，我是优逸花客服，有个预留额度业务要介绍。",
    "您好，有个限时福利要通知您，耽误您一分钟好吗？",
    "您好，我是马上消费客服，有个资金周转的好方案要介绍。",
]


async def main():
    """主函数"""
    
    # 解析参数
    parser = argparse.ArgumentParser(description='ContextMind v7.3 客服对话 Interactive Demo')
    parser.add_argument('--no-session', action='store_true', help='禁用会话历史')
    parser.add_argument('--no-memory', action='store_true', help='禁用长期记忆')
    parser.add_argument('--max-events', type=int, default=10, help='最大历史轮数')
    parser.add_argument('--history-turns', type=int, default=10, help='Prompt中的历史轮数')
    parser.add_argument('--debug', action='store_true', help='调试模式 (详细日志)')
    args = parser.parse_args()
    
    # 设置日志级别: DEBUG (详细信息) 或 INFO (重要信息)
    log_level = LogLevel.DEBUG if args.debug else LogLevel.INFO
    setup_logging(level=log_level)
    
    print("=" * 60)
    print("📞 ContextMind v7.3 客服对话 Interactive Demo")
    print("五层架构 (core/pipeline/strategies/adapters/utils)")
    print("=" * 60)
    print()
    
    # 显示配置
    print("⚙️  当前配置:")
    print(f"   - 会话历史: {'❌ 禁用' if args.no_session else '✅ 启用'}")
    print(f"   - 长期记忆: {'❌ 禁用' if args.no_memory else '✅ 启用'}")
    print(f"   - 最大轮数: {args.max_events}")
    print(f"   - Prompt历史: {args.history_turns}")
    print(f"   - 调试模式: {'✅ 启用' if args.debug else '❌ 禁用'}")
    print()
    
    # 初始化引擎 (v7.3: LLM 调用在外部，不需要客户端)
    print("🔧 初始化引擎...")
    
    # 配置知识提取和检索 - 优化客服场景的记忆管理
    from contextmind.core.configs import RetrievalConfig, ExtractionConfig
    
    # 配置知识提取 - 确保全面捕获(需求3)
    extraction_config = ExtractionConfig(
        extraction_method="llm",  # 使用LLM提取，更全面
        min_confidence=0.5,  # 适当降低置信度阈值，捕获更多潜在有价值的知识
        extract_preferences=True,
        extract_facts=True,
        extract_events=True,
        extract_entities=True,
        extract_relationships=True,
    )
    
    context_engine = ContextEngine(
        app_name="customer-service-demo",
        user_id="customer-user",
        max_recent_events=args.max_events,
        extraction_config=extraction_config,
    )
    
    # 配置记忆库检索 - 设置上限(需求4)和综合性(需求3)
    # 需要在引擎初始化后配置MemoryBank
    
    retrieval_config = RetrievalConfig(
        top_k=3,  # 限制检索出的记忆数量上限为3条(需求4)
        min_score=0.3,  # 降低阈值，确保不遗漏重要信息(需求3)
        use_semantic=True,
        enable_recency_boost=True,  # 启用新近性加权
    )
    # 更新内存银行的配置
    context_engine.memory_bank.config = retrieval_config
    
    print("✅ 引擎初始化完成 (v7.3 - 纯上下文工程)")
    print(f"   - 记忆检索限制: top_k={retrieval_config.top_k}")
    print(f"   - 知识提取阈值: min_confidence={extraction_config.min_confidence}")
    print()
    
    # 初始化应用
    print("🔧 初始化应用...")
    business_info = """
产品介绍：
- 安逸花/马上消费智能金融服务
- 支持额度提升、资金周转、优惠福利

服务承诺：
- 7x24小时在线
- 响应快速、专业友好
"""
    app = CallCenterApplication(
        context_engine=context_engine,
        # 注意: 在 v7.3 中，LLM 客户端由外部处理
        business_info=business_info.strip(),
        system_prompt=CALLCENTER_SYSTEM_PROMPT,
        history_turns=args.history_turns,
    )
    print("✅ 应用初始化完成")
    print()
    
    # 开始对话
    print("💡 使用提示:")
    print("   - 直接输入消息咨询客服")
    print("   - 输入 'quit' 或 'exit' 退出")
    print("   - 输入 'reset' 重置对话")
    print("   - 输入 'help' 查看帮助")
    if not args.no_memory:
        print("   - 输入 '/status' 查看记忆状态")
    print()
    print("=" * 60)
    print("📞 客服为您服务！")
    print("=" * 60)
    print()
    
    # 机器人主动发起对话 - 随机选择一条开场白
    opening_message = random.choice(OPENING_SCRIPTS)
    print(f"客服: {opening_message}\n")
    logger.info(f"客服开场: {opening_message}")
    
    # 将开场白添加到会话历史
    await context_engine.session_manager.add_message(
        role=MessageRole.ASSISTANT,
        content=opening_message
    )
    
    turn_counter = 0
    
    while True:
        # 获取用户输入
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！")
            break
        
        # 处理特殊命令
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("\n👋 再见！")
            break
        
        if user_input.lower() == 'reset':
            print("\n🔄 对话已重置\n")
            turn_counter = 0
            await context_engine.clear_session()
            continue
        
        if user_input.lower() == 'help':
            print("\n💡 可用命令:")
            print("   - quit/exit/q: 退出程序")
            print("   - reset: 重置对话")
            print("   - help: 显示此帮助")
            if not args.no_memory:
                print("   - /status: 查看记忆状态")
            print("\n💬 常见咨询:")
            print("   - 业务办理")
            print("   - 额度查询")
            print("   - 优惠活动")
            print("   - 账户问题")
            print("   - 服务咨询\n")
            continue
        
        if user_input.lower() == '/status' and not args.no_memory:
            # 显示记忆状态
            memory_cache = context_engine.memory_bank.get_memory_cache()
            history = await context_engine.session_manager.get_recent_history()
            print(f"\n📊 状态:")
            print(f"  - 对话轮次: {turn_counter}")
            print(f"  - 历史消息: {len(history)}")
            print(f"  - 长期记忆: {len(memory_cache)} 条")
            if memory_cache:
                print("  记忆内容:")
                for i, mem in enumerate(memory_cache[:5], 1):  # 显示前5条
                    print(f"    {i}. {mem.content}")
            print()
            continue
        
        if not user_input:
            continue
        
        turn_counter += 1
        
        # 处理消息
        try:
            print()
            print(f"[轮次 {turn_counter}] 处理中...")
            start_time = time.time()
            
            # 使用应用的process_turn方法处理对话
            # 这会自动处理: optimize → generate → update → extract_knowledge
            if args.debug:
                response, debug_info = await app.process_turn(user_input=user_input, debug=True)
            else:
                response = await app.process_turn(user_input=user_input)
            
            processing_time = time.time() - start_time
            
            # 显示回复
            print(f"\n助手: {response}")
            
            # Debug 模式下显示详细信息
            if args.debug:
                print("\n" + "=" * 80)
                print("📊 DEBUG 信息")
                print("=" * 80)
                
                # 1. 记忆库内容
                if debug_info.get('memory_before'):
                    print(f"\n1️⃣  记忆库内容（{len(debug_info['memory_before'])}条）:")
                    for i, mem in enumerate(debug_info['memory_before'], 1):
                        print(f"   [{i}] [{mem['type']}] {mem['content']} (置信度: {mem['confidence']:.2f})")
                else:
                    print("\n1️⃣  记忆库内容: 空")
                
                # 2. 召回结果 - 明确区分记忆库和历史对话
                if debug_info.get('context_result'):
                    ctx = debug_info['context_result']
                    print(f"\n2️⃣  召回结果（共{ctx['total_items']}项，压缩: {ctx['compressed']}）:")
                    
                    # 分类显示：记忆库 vs 历史对话
                    memory_items = [item for item in ctx['items'] if item['source'] == 'ContextSource.MEMORY']
                    history_items = [item for item in ctx['items'] if item['source'] != 'ContextSource.MEMORY']
                    
                    if memory_items:
                        print(f"\n   📚 从记忆库召回 ({len(memory_items)}项):")
                        for i, item in enumerate(memory_items, 1):
                            print(f"      [{i}] {item['content']} (分数: {item['score']:.2f})")
                    else:
                        print(f"\n   📚 从记忆库召回: 无")
                    
                    if history_items:
                        print(f"\n   💬 从历史对话召回 ({len(history_items)}项):")
                        for i, item in enumerate(history_items, 1):
                            content = item['content'][:80] + "..." if len(item['content']) > 80 else item['content']
                            print(f"      [{i}] {content} (分数: {item['score']:.2f})")
                    else:
                        print(f"\n   💬 从历史对话召回: 无")
                else:
                    print("\n2️⃣  召回结果: 无")
                
                # 3. 上下文优化后的结果 (已包含在召回结果中)
                print(f"\n3️⃣  上下文优化: 已完成 (压缩: {debug_info.get('context_result', {}).get('compressed', False)})")
                
                # 4. 完整的Prompt - 显示完整内容，不省略
                if debug_info.get('prompt'):
                    prompt_text = debug_info['prompt']
                    print(f"\n4️⃣  完整Prompt ({len(prompt_text)}字符):")
                    print("   " + "-" * 76)
                    
                    # 解析并完整显示各个部分
                    # 查找摘要部分
                    if "## 早期对话摘要" in prompt_text:
                        parts = prompt_text.split("## 早期对话摘要")
                        print("   " + parts[0].replace("\n", "\n   ").strip())
                        print("\n   ## 早期对话摘要")
                        
                        # 提取摘要内容（到下一个##或最近对话）
                        summary_part = parts[1].split("## 对话历史")[0] if "## 对话历史" in parts[1] else parts[1]
                        summary_part = summary_part.split("## 最近对话")[0] if "## 最近对话" in summary_part else summary_part
                        print("   " + summary_part.replace("\n", "\n   ").strip())
                    
                    # 查找最近对话部分，完整显示不省略
                    if "## 最近对话" in prompt_text or "## 对话历史" in prompt_text:
                        history_marker = "## 最近对话" if "## 最近对话" in prompt_text else "## 对话历史"
                        parts = prompt_text.split(history_marker)
                        if len(parts) > 1:
                            print(f"\n   {history_marker}")
                            # 提取对话部分，直到当前问题
                            history_part = parts[1].split("## 当前问题")[0] if "## 当前问题" in parts[1] else parts[1]
                            history_part = history_part.split("## 已知信息")[0] if "## 已知信息" in history_part else history_part
                            print("   " + history_part.replace("\n", "\n   ").strip())
                    
                    # 显示当前问题
                    if "## 当前问题" in prompt_text:
                        parts = prompt_text.split("## 当前问题")
                        if len(parts) > 1:
                            print("\n   ## 当前问题")
                            print("   " + parts[1].replace("\n", "\n   ").strip())
                    
                    print("   " + "-" * 76)
                
                # 5. 提取的知识
                if debug_info.get('extracted_knowledge'):
                    print(f"\n5️⃣  提取的知识（{len(debug_info['extracted_knowledge'])}条）:")
                    for i, k in enumerate(debug_info['extracted_knowledge'], 1):
                        print(f"   [{i}] [{k['type']}] {k['content']} (置信度: {k['confidence']:.2f})")
                else:
                    print("\n5️⃣  提取的知识: 无")
                
                print("\n" + "=" * 80)
            
            # 显示统计信息
            if args.debug:
                memory_cache = context_engine.memory_bank.get_memory_cache()
                print(f"\n[统计] 耗时: {processing_time:.2f}s | 记忆: {len(memory_cache)}条")
            
            print("\n" + "-" * 60 + "\n")
            
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}\n")
            import traceback
            logger.error(f"处理失败: {e}")
            logger.debug(traceback.format_exc())
            continue


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 程序已中断")
    except Exception as e:
        print(f"\n❌ 程序错误: {str(e)}")
        import traceback
        logger.error("程序异常")
        logger.debug(traceback.format_exc())
