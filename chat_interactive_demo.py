"""
ContextMind v5.1 闲聊 Interactive Demo

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
    Client,
    ClientConfig,
    setup_logging,
    get_logger,
    INFO,
    DEBUG,
)

load_dotenv()
logger = get_logger(__name__)


async def main():
    """主函数"""
    
    # 解析参数
    parser = argparse.ArgumentParser(description='ContextMind v5.1 闲聊 Interactive Demo')
    parser.add_argument('--no-session', action='store_true', help='禁用会话历史')
    parser.add_argument('--no-memory', action='store_true', help='禁用长期记忆')
    parser.add_argument('--max-events', type=int, default=20, help='最大历史轮数')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    args = parser.parse_args()
    
    log_level = DEBUG if args.debug else INFO
    setup_logging(level=log_level, log_to_console=True, auto_create_file=True)
    
    print("=" * 60)
    print("🎭 ContextMind v5.1 闲聊 Interactive Demo")
    print("五层架构 (core/pipeline/strategies/adapters/utils)")
    print("=" * 60)
    print()
    
    # 显示配置
    print("⚙️  当前配置:")
    print(f"   - 会话历史: {'❌ 禁用' if args.no_session else '✅ 启用'}")
    print(f"   - 长期记忆: {'❌ 禁用' if args.no_memory else '✅ 启用'}")
    print(f"   - 最大轮数: {args.max_events}")
    print(f"   - 调试模式: {'✅ 启用' if args.debug else '❌ 禁用'}")
    print()
    
    # 初始化客户端
    print("🔧 初始化客户端...")
    client_config = ClientConfig.from_env()
    llm_client = Client(config=client_config)
    print(f"✅ 客户端初始化完成: {llm_client.config.model}")
    print()
    
    # 初始化引擎
    print("🔧 初始化引擎...")
    context_engine = ContextEngine(
        app_name="chat-demo",
        user_id="chat-user",
        llm_client=llm_client,
        max_recent_events=args.max_events,
    )
    print("✅ 引擎初始化完成")
    print()
    
    # 系统提示词 - 简洁的闲聊角色设定
    system_prompt = """你是一个友好、有趣的聊天助手。

特点：
- 亲切自然，像朋友一样交流
- 适当使用表情和轻松的语气
- 记住用户提到的信息，让对话更连贯
- 话题广泛，可以聊天、讲笑话、分享知识

注意：
- 回复简洁有趣，不要过于正式
- 适当提问，保持对话互动
- 如果用户分享了个人信息（如名字、爱好、城市等），记住并在后续对话中自然提及"""
    
    # 开始对话
    print("💡 使用提示:")
    print("   - 直接输入消息开始聊天")
    print("   - 输入 'quit' 或 'exit' 退出")
    print("   - 输入 'reset' 重置对话")
    print("   - 输入 'help' 查看帮助")
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
            continue
        
        if user_input.lower() == 'help':
            print("\n💡 可用命令:")
            print("   - quit/exit/q: 退出程序")
            print("   - reset: 重置对话")
            print("   - help: 显示此帮助")
            print("\n💬 话题建议:")
            print("   - 自我介绍")
            print("   - 聊聊兴趣爱好")
            print("   - 讲个笑话")
            print("   - 推荐电影/书籍")
            print("   - 生活小窍门\n")
            continue
        
        if not user_input:
            continue
        
        turn_counter += 1
        
        # 处理消息
        try:
            print()
            print(f"[轮次 {turn_counter}] 处理中...")
            start_time = time.time()
            
            # 使用引擎处理
            result = await context_engine.process(
                query=user_input,
                system_prompt=system_prompt,
                use_session_history=not args.no_session,
                use_long_term_memory=not args.no_memory,
            )
            
            assistant_response = result.get_final_response()
            processing_time = time.time() - start_time
            
            # 显示回复
            print(f"\n助手: {assistant_response}")
            
            # 显示统计信息
            if args.debug:
                context_count = len(result.context_items) if hasattr(result, 'context_items') else 0
                print(f"\n[统计] 耗时: {processing_time:.2f}s | 上下文: {context_count}项")
            
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
