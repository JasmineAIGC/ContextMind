"""
ContextMind v7.1 闲聊 Interactive Demo

五层架构 (core/pipeline/strategies/adapters/utils) + 智能记忆系统
命令行交互式闲聊演示。
"""

import asyncio
import os
import argparse
import time

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
)

from demos.chat_app import ChatApplication, CHAT_SYSTEM_PROMPT

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
        # 注意: 在 v7.1 中，LLM 客户端由外部处理
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
                
                # 2. 召回结果
                if debug_info.get('context_result'):
                    ctx = debug_info['context_result']
                    print(f"\n2️⃣  召回结果（共{ctx['total_items']}项，压缩: {ctx['compressed']}）:")
                    for i, item in enumerate(ctx['items'], 1):
                        print(f"   [{i}] [{item['source']}] {item['content'][:80]}... (分数: {item['score']:.2f})")
                else:
                    print("\n2️⃣  召回结果: 无")
                
                # 3. 上下文优化后的结果 (已包含在召回结果中)
                print(f"\n3️⃣  上下文优化: 已完成 (压缩: {debug_info.get('context_result', {}).get('compressed', False)})")
                
                # 4. 完整的Prompt
                if debug_info.get('prompt'):
                    prompt_preview = debug_info['prompt']
                    print(f"\n4️⃣  完整Prompt ({len(prompt_preview)}字符):")
                    print("   " + "-" * 76)
                    # 显示前500字符
                    print("   " + prompt_preview[:500].replace("\n", "\n   "))
                    if len(prompt_preview) > 500:
                        print(f"   ... (还有{len(prompt_preview) - 500}字符)")
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
