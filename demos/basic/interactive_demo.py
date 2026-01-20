"""
ContextMind v5.1 Interactive Demo

五层架构 (core/pipeline/strategies/adapters/utils) + 智能记忆系统
提供命令行交互式演示。
"""

import asyncio
import os
import argparse
import random
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

from demos.applications.callcenter_app import CallCenterApplication

load_dotenv()
logger = get_logger(__name__)

# 开场白选项
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
    parser = argparse.ArgumentParser(description='ContextMind v5.1 Interactive Demo')
    parser.add_argument('--no-session', action='store_true', help='禁用会话历史')
    parser.add_argument('--use-memory', action='store_true', help='启用长期记忆')
    parser.add_argument('--max-events', type=int, default=9999, help='最大历史轮数')
    parser.add_argument('--history-turns', type=int, default=10, help='Prompt中的历史轮数')
    parser.add_argument('--enable-memory-thinking', action='store_true', help='启用记忆思考')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    args = parser.parse_args()
    
    log_level = DEBUG if args.debug else INFO
    setup_logging(level=log_level, log_to_console=True, auto_create_file=True)
    
    print("=" * 60)
    print("ContextMind v5.1 Interactive Demo")
    print("五层架构 (core/pipeline/strategies/adapters/utils)")
    print("=" * 60)
    print()
    
    # 显示配置
    print("⚙️  当前配置:")
    print(f"   - 会话历史: {'❌ 禁用' if args.no_session else '✅ 启用'}")
    print(f"   - 长期记忆: {'✅ 启用' if args.use_memory else '❌ 禁用'}")
    print(f"   - 最大轮数: {args.max_events}")
    print(f"   - Prompt历史: {args.history_turns}")
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
        app_name="demo-app",
        user_id="demo-user",
        llm_client=llm_client,
        max_recent_events=args.max_events,
    )
    print("✅ 引擎初始化完成")
    print()
    
    # 不再植入预设记忆，让对话更自然流畅
    # 记忆系统会根据实际对话动态学习
    
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
        llm_client=llm_client,
        business_info=business_info.strip(),
        auto_extract_knowledge=True,
        history_turns=args.history_turns,
    )
    print("✅ 应用初始化完成")
    print()
    
    # 交互对话
    print("=" * 60)
    print("开始对话（输入 'quit' 或 'exit' 退出）")
    print("特殊命令：")
    print("  /clear  - 清空会话")
    print("  /status - 查看状态")
    print("  /config - 显示配置")
    print("=" * 60)
    print()
    
    # 系统开场白
    opening_message = random.choice(OPENING_SCRIPTS)
    print(f"助手: {opening_message}\n")
    logger.info(f"助手: {opening_message}")
    
    # 添加到会话
    from contextmind import MessageRole
    await context_engine.session_manager.add_message(
        role=MessageRole.ASSISTANT,
        content=opening_message
    )
    
    turn_count = 0
    
    while True:
        # 获取输入
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！")
            break
        
        if not user_input:
            continue
        
        logger.info(f"你: {user_input}")
        
        if user_input.lower() in ["quit", "exit", "退出", "再见"]:
            print("\n👋 再见！")
            break
        
        # 特殊命令
        if user_input == "/clear":
            await context_engine.clear_session()
            print("✅ 会话已清空\n")
            turn_count = 0
            continue
        
        if user_input == "/status":
            history = await context_engine.session_manager.get_recent_history()
            print(f"📊 状态:")
            print(f"  - 轮次: {turn_count}")
            print(f"  - 历史消息: {len(history)}")
            print()
            continue
        
        if user_input == "/config":
            print(f"⚙️  配置:")
            print(f"  - 会话: {'❌' if args.no_session else '✅'}")
            print(f"  - 记忆: {'✅' if args.use_memory else '❌'}")
            print(f"  - 调试: {'✅' if args.debug else '❌'}")
            print()
            continue
        
        # 处理对话
        try:
            turn_count += 1
            print(f"\n[第 {turn_count} 轮]")
            
            response = await app.process_turn(user_input)
            
            print(f"助手: {response}\n")
            
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}\n")
            import traceback
            traceback.print_exc()
    
    print("\n感谢使用 ContextMind v5.1!")


if __name__ == "__main__":
    asyncio.run(main())
