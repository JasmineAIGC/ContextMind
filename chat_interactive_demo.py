"""
ContextMind v7.1 闲聊 Interactive Demo

五层架构 (core/pipeline/strategies/adapters/utils) + 智能记忆系统
命令行交互式闲聊演示。
"""

import asyncio
import os
import argparse
import time
from dotenv import load_dotenv

from contextmind import (
    ContextEngine,
    setup_logging,
    get_logger,
    LogLevel,
)

from demos.chat_app import ChatApplication, CHAT_SYSTEM_PROMPT

load_dotenv()
logger = get_logger(__name__)


async def main():
    """主函数"""
    
    # 解析参数
    parser = argparse.ArgumentParser(description='ContextMind v7.1 闲聊 Interactive Demo')
    parser.add_argument('--no-session', action='store_true', help='禁用会话历史')
    parser.add_argument('--no-memory', action='store_true', help='禁用长期记忆')
    parser.add_argument('--max-events', type=int, default=20, help='最大历史轮数')
    parser.add_argument('--history-turns', type=int, default=10, help='Prompt中的历史轮数')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    args = parser.parse_args()
    
    log_level = LogLevel.DEBUG if args.debug else LogLevel.BASIC
    setup_logging(level=log_level)
    
    print("=" * 60)
    print("🎭 ContextMind v7.1 闲聊 Interactive Demo")
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
    
    # 初始化引擎 (v7.1: LLM invocation is external, no client needed)
    print("🔧 初始化引擎...")
    context_engine = ContextEngine(
        app_name="chat-demo",
        user_id="chat-user",
        max_recent_events=args.max_events,
    )
    print("✅ 引擎初始化完成 (v7.1 - Pure Context Engineering)")
    print()
    
    # 初始化应用
    print("🔧 初始化应用...")
    app = ChatApplication(
        context_engine=context_engine,
        # Note: In v7.1, LLM client is handled externally
        system_prompt=CHAT_SYSTEM_PROMPT,
        history_turns=args.history_turns,
        auto_extract_knowledge=not args.no_memory,  # 根据参数决定是否提取知识
    )
    print("✅ 应用初始化完成")
    print()
    
    # 开始对话
    print("💡 使用提示:")
    print("   - 直接输入消息开始聊天")
    print("   - 输入 'quit' 或 'exit' 退出")
    print("   - 输入 'reset' 重置对话")
    print("   - 输入 'help' 查看帮助")
    if not args.no_memory:
        print("   - 输入 '/status' 查看记忆状态")
    print()
    print("=" * 60)
    print("🎭 开始闲聊吧！")
    print("=" * 60)
    print()
    
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
            print("\n💬 话题建议:")
            print("   - 自我介绍")
            print("   - 聊聊兴趣爱好")
            print("   - 讲个笑话")
            print("   - 推荐电影/书籍")
            print("   - 生活小窍门\n")
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
            response = await app.process_turn(user_input=user_input)
            
            processing_time = time.time() - start_time
            
            # 显示回复
            print(f"\n助手: {response}")
            
            # 显示统计信息
            if args.debug:
                memory_cache = context_engine.memory_bank.get_memory_cache()
                print(f"\n[统计] 耗时: {processing_time:.2f}s | 记忆: {len(memory_cache)}条")
            
            print("\n" + "-" * 60 + "\n")
            
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}\n")
            logger.error(f"处理失败: {e}", exc_info=True)
            continue


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 程序已中断")
    except Exception as e:
        print(f"\n❌ 程序错误: {str(e)}")
        logger.error("程序异常", exc_info=True)
