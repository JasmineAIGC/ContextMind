"""
ContextMind v3.0 Interactive Demo

展示新架构的使用方式，提供命令行交互式演示。
"""

import asyncio
import os
from dotenv import load_dotenv

from contextmind import (
    ContextEngine,
    Client,
    ClientConfig,
    setup_logging,
    INFO,
)
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService

from examples.applications.callcenter import CallCenterApplication

# 加载环境变量
load_dotenv()


async def main():
    """主函数"""
    
    # 设置日志
    setup_logging(level=INFO, log_to_console=True, auto_create_file=False)
    
    print("=" * 60)
    print("ContextMind v3.0 Interactive Demo")
    print("完全重构的上下文优化框架")
    print("=" * 60)
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
        memory_service=InMemoryMemoryService(),
        max_recent_events=10,
    )
    print("✅ 上下文引擎初始化完成")
    print()
    
    # 植入业务知识种子
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
        auto_extract_knowledge=True,
    )
    print("✅ 客服应用初始化完成")
    print()
    
    # 交互式对话
    print("=" * 60)
    print("开始对话（输入 'quit' 或 'exit' 退出）")
    print("特殊命令：/clear (清空会话), /status (查看状态)")
    print("=" * 60)
    print()
    
    turn_count = 0
    
    while True:
        # 获取用户输入
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！")
            break
        
        if not user_input:
            continue
        
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
            print(f"📊 当前会话状态:")
            print(f"  - 轮次: {turn_count}")
            print(f"  - 历史消息数: {len(history)}")
            print()
            continue
        
        # 处理对话
        try:
            turn_count += 1
            print(f"\n[第 {turn_count} 轮]")
            
            # 调用应用处理对话
            response = await app.process_turn(user_input)
            
            print(f"助手: {response}\n")
            
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}\n")
            import traceback
            traceback.print_exc()
    
    print("\n感谢使用 ContextMind v3.0!")


if __name__ == "__main__":
    asyncio.run(main())
