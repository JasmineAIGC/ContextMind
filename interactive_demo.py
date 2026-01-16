"""
ContextMind v3.2 Interactive Demo

展示新架构的使用方式，提供命令行交互式演示。
支持通过参数配置上下文控制。
"""

import asyncio
import os
import argparse
from dotenv import load_dotenv

from contextmind import (
    ContextEngine,
    Client,
    ClientConfig,
    setup_logging,
    INFO,
    DEBUG,
)
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService

from examples.applications.callcenter import CallCenterApplication

# 导入logger（用于记录对话）
from contextmind.logger import get_logger

# 加载环境变量
load_dotenv()

# 创建logger
logger = get_logger(__name__)


async def main():
    """主函数"""
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='ContextMind v3.2 Interactive Demo')
    parser.add_argument('--no-session', action='store_true', help='禁用会话历史')
    parser.add_argument('--use-memory', action='store_true', help='启用长期记忆')
    parser.add_argument('--max-events', type=int, default=9999, help='最大历史轮数 (默认: 9999，实际不限制)')
    parser.add_argument('--debug', action='store_true', help='启用调试模式（打印上下文和完整prompt）')
    args = parser.parse_args()
    
    # 设置日志（debug模式时使用DEBUG级别）
    from contextmind import DEBUG
    log_level = DEBUG if args.debug else INFO
    setup_logging(level=log_level, log_to_console=True, auto_create_file=True)
    
    print("=" * 60)
    print("ContextMind v3.2 Interactive Demo")
    print("通用、可扩展的上下文优化框架")
    print("=" * 60)
    print()
    
    # 显示配置
    print("⚙️  当前配置:")
    print(f"   - 会话历史: {'❌ 禁用' if args.no_session else '✅ 启用'}")
    print(f"   - 长期记忆: {'✅ 启用' if args.use_memory else '❌ 禁用'}")
    print(f"   - 最大轮数: {args.max_events}")
    print(f"   - 调试模式: {'✅ 启用' if args.debug else '❌ 禁用'}")
    print()
    
    # 初始化LLM客户端
    print("🔧 初始化LLM客户端...")
    llm_client = Client(config=ClientConfig.from_env())
    print(f"✅ LLM客户端初始化完成: {llm_client.config.model}")
    print()
    
    # 初始化上下文引擎
    print("🔧 初始化上下文引擎...")
    context_engine = ContextEngine(
        app_name="demo-app",
        user_id="demo-user",
        llm_client=llm_client,
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService() if args.use_memory else None,
        max_recent_events=args.max_events,
    )
    print("✅ 上下文引擎初始化完成")
    print()
    
    # 如果启用长期记忆，植入业务知识种子
    if args.use_memory:
        print("🧠 植入业务知识种子...")
        business_facts = [
            "产品名称：智能助手 Pro",
            "主要功能：智能对话、知识问答、任务管理",
            "服务时间：7x24小时在线",
            "联系方式：support@example.com",
        ]
        await context_engine.seed_memory(business_facts)
        print(f"✅ 已植入 {len(business_facts)} 条业务知识")
        print()
    
    # 初始化客服应用
    print("🔧 初始化客服应用...")
    business_info = """
产品介绍：
- 智能助手 Pro 是一款基于大语言模型的智能对话系统
- 支持多轮对话、上下文理解、知识检索
- 提供个性化服务，记住用户偏好

服务承诺：
- 7x24小时在线服务
- 响应时间小于3秒
- 专业、友好、高效
"""
    
    app = CallCenterApplication(
        context_engine=context_engine,
        llm_client=llm_client,
        business_info=business_info.strip(),
        auto_extract_knowledge=True,  # 始终启用知识提取，从对话中学习
    )
    print("✅ 客服应用初始化完成")
    print()
    
    # 交互式对话
    print("=" * 60)
    print("开始对话（输入 'quit' 或 'exit' 退出）")
    print("特殊命令：")
    print("  /clear  - 清空会话")
    print("  /status - 查看状态")
    print("  /config - 显示当前配置")
    print("=" * 60)
    print()
    
    # 系统发起第一句话
    opening_message = "您好！我是智能助手 Pro，很高兴为您服务。请问有什么可以帮助您的吗？"
    print(f"助手: {opening_message}\n")
    logger.info(f"助手: {opening_message}")
    
    # 将开场白添加到会话历史
    from contextmind import MessageRole
    await context_engine.session_manager.add_message(
        role=MessageRole.ASSISTANT,
        content=opening_message
    )
    
    turn_count = 0
    
    while True:
        # 获取用户输入
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！")
            break
        
        if not user_input:
            continue
        
        # 记录用户输入到日志
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
            logger.info(f"📊 当前会话状态:")
            logger.info(f"  - 轮次: {turn_count}")
            logger.info(f"  - 历史消息数: {len(history)}")
            print(f"📊 当前会话状态:")
            print(f"  - 轮次: {turn_count}")
            print(f"  - 历史消息数: {len(history)}")
            print()
            continue
        
        if user_input == "/config":
            logger.info(f"⚙️  当前配置:")
            logger.info(f"  - 会话历史: {'❌ 禁用' if args.no_session else '✅ 启用'}")
            logger.info(f"  - 长期记忆: {'✅ 启用' if args.use_memory else '❌ 禁用'}")
            logger.info(f"  - 最大轮数: {args.max_events}")
            logger.info(f"  - 调试模式: {'✅ 启用' if args.debug else '❌ 禁用'}")
            print(f"⚙️  当前配置:")
            print(f"  - 会话历史: {'❌ 禁用' if args.no_session else '✅ 启用'}")
            print(f"  - 长期记忆: {'✅ 启用' if args.use_memory else '❌ 禁用'}")
            print(f"  - 最大轮数: {args.max_events}")
            print(f"  - 调试模式: {'✅ 启用' if args.debug else '❌ 禁用'}")
            print()
            continue
        
        # 处理对话
        try:
            turn_count += 1
            print(f"\n[第 {turn_count} 轮]")
            
            # 调用应用处理对话
            response = await app.process_turn(user_input)
            
            print(f"助手: {response}\n")
            
            # 记录助手回复到日志
            logger.info(f"助手: {response}")
            
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}\n")
            import traceback
            traceback.print_exc()
    
    print("\n感谢使用 ContextMind v3.2!")


if __name__ == "__main__":
    asyncio.run(main())
