"""
Adapter Integration Example

演示如何使用适配器将 ContextMind 集成到不同的对话系统。
"""

import asyncio
from contextmind import (
    ContextEngine,
    Client,
    ClientConfig,
    OpenAIAdapter,
    LangChainAdapter,
    CustomAdapter,
    DialogContext,
    DialogMessage,
    PerformanceMonitor,
    ContextVisualizer,
    EventBus,
)
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService


async def openai_adapter_example():
    """OpenAI 适配器示例"""
    print("=" * 60)
    print("OpenAI Adapter Example")
    print("=" * 60)
    
    # 创建引擎
    engine = ContextEngine(
        app_name="openai-app",
        user_id="user-123",
        llm_client=Client(config=ClientConfig.from_env()),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    
    # 创建适配器
    adapter = OpenAIAdapter(engine=engine)
    
    # 处理对话
    response = await adapter.process(
        user_input="你好，介绍一下你自己",
        context=DialogContext(system_prompt="你是一个智能助手")
    )
    
    print(f"Response: {response.content}\n")


async def langchain_adapter_example():
    """LangChain 适配器示例"""
    print("=" * 60)
    print("LangChain Adapter Example")
    print("=" * 60)
    
    # 创建引擎
    engine = ContextEngine(
        app_name="langchain-app",
        user_id="user-456",
        session_service=InMemorySessionService(),
    )
    
    # 创建适配器
    adapter = LangChainAdapter(engine=engine)
    
    # 处理对话
    response = await adapter.process(
        user_input="解释一下什么是上下文优化",
    )
    
    print(f"Response: {response.content}\n")


async def custom_adapter_example():
    """自定义适配器示例"""
    print("=" * 60)
    print("Custom Adapter Example")
    print("=" * 60)
    
    # 创建引擎
    engine = ContextEngine(
        app_name="custom-app",
        user_id="user-789",
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    
    # 定义自定义处理函数
    async def custom_processor(user_input, context, **kwargs):
        # 自定义处理逻辑
        enhanced_context = await adapter.inject_context(user_input, context)
        
        # 构建自定义响应
        response = f"收到你的消息: {user_input}"
        
        return DialogMessage(
            role='assistant',
            content=response,
            metadata={'custom': True}
        )
    
    # 创建自定义适配器
    adapter = CustomAdapter(
        engine=engine,
        processor=custom_processor
    )
    
    # 处理对话
    response = await adapter.process(
        user_input="测试自定义适配器",
    )
    
    print(f"Response: {response.content}")
    print(f"Metadata: {response.metadata}\n")


async def adapter_with_hooks_example():
    """带钩子的适配器示例"""
    print("=" * 60)
    print("Adapter with Hooks Example")
    print("=" * 60)
    
    # 创建引擎
    engine = ContextEngine(
        app_name="hooks-app",
        user_id="user-hooks",
        session_service=InMemorySessionService(),
    )
    
    # 创建适配器
    adapter = OpenAIAdapter(engine=engine)
    
    # 注册钩子
    def before_optimize_hook(user_input, context):
        print(f"[HOOK] Before optimize: {user_input}")
    
    def after_optimize_hook(context_result):
        print(f"[HOOK] After optimize: {len(context_result.recent_history)} messages")
    
    adapter.register_hook('before_optimize', before_optimize_hook)
    adapter.register_hook('after_optimize', after_optimize_hook)
    
    # 处理对话
    response = await adapter.process(
        user_input="测试钩子功能",
    )
    
    print(f"Response: {response.content}\n")


async def adapter_with_monitoring_example():
    """带性能监控的适配器示例"""
    print("=" * 60)
    print("Adapter with Performance Monitoring Example")
    print("=" * 60)
    
    # 创建引擎
    engine = ContextEngine(
        app_name="monitor-app",
        user_id="user-monitor",
        session_service=InMemorySessionService(),
    )
    
    # 创建性能监控器
    monitor = PerformanceMonitor()
    
    # 创建适配器
    adapter = OpenAIAdapter(engine=engine)
    
    # 处理多轮对话并监控
    for i in range(3):
        monitor.start_turn()
        
        response = await adapter.process(
            user_input=f"第 {i+1} 轮对话",
        )
        
        # 记录上下文信息
        monitor.record_context_info(
            context_length=len(response.content),
            history_count=i + 1
        )
        
        metrics = monitor.end_turn()
        print(f"Turn {i+1}: {response.content}")
        print(f"  Time: {metrics.total_time:.3f}s")
    
    # 显示性能摘要
    print("\n" + monitor.get_summary())


async def adapter_with_events_example():
    """带事件系统的适配器示例"""
    print("=" * 60)
    print("Adapter with Event System Example")
    print("=" * 60)
    
    # 创建事件总线
    event_bus = EventBus()
    
    # 订阅事件
    def on_message(event):
        print(f"[EVENT] New message: {event.data['content'][:30]}...")
    
    def on_response(event):
        print(f"[EVENT] Generated response: {event.data['content'][:30]}...")
    
    event_bus.subscribe('user_message', on_message)
    event_bus.subscribe('assistant_response', on_response)
    
    # 创建引擎
    engine = ContextEngine(
        app_name="events-app",
        user_id="user-events",
        session_service=InMemorySessionService(),
    )
    
    # 创建适配器
    adapter = OpenAIAdapter(engine=engine)
    
    # 发布用户消息事件
    user_input = "测试事件系统"
    event_bus.publish('user_message', {'content': user_input}, source='user')
    
    # 处理对话
    response = await adapter.process(user_input=user_input)
    
    # 发布响应事件
    event_bus.publish('assistant_response', {'content': response.content}, source='adapter')
    
    print(f"\nTotal events: {len(event_bus.get_history())}\n")


async def main():
    """主函数"""
    print("\n🚀 ContextMind Adapter Integration Examples\n")
    
    # 运行各种示例
    await openai_adapter_example()
    await langchain_adapter_example()
    await custom_adapter_example()
    await adapter_with_hooks_example()
    await adapter_with_monitoring_example()
    await adapter_with_events_example()
    
    print("✅ All examples completed!\n")


if __name__ == "__main__":
    asyncio.run(main())
