"""
ContextMind v7.1 交互式演示

五层架构 (core/pipeline/strategies/adapters/utils) + 智能记忆系统
提供命令行交互式演示
"""

import asyncio
import os
import argparse
import random

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("警告: 未安装 python-dotenv。请使用 pip install python-dotenv 安装")
    print("LLM 功能可能无法正常工作, 需要 .env 配置文件")

from contextmind import (
    ContextEngine,
    setup_logging,
    get_logger,
    LogLevel,
)

from examples.callcenter_app import CallCenterApplication

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
    parser = argparse.ArgumentParser(description='ContextMind v7.1 Interactive Demo')
    parser.add_argument('--no-session', action='store_true', help='禁用会话历史')
    parser.add_argument('--use-memory', action='store_true', help='启用长期记忆')
    parser.add_argument('--max-events', type=int, default=9999, help='最大历史轮数')
    parser.add_argument('--history-turns', type=int, default=10, help='Prompt 中的历史轮数')
    parser.add_argument('--enable-memory-thinking', action='store_true', help='启用记忆思考')
    parser.add_argument('--no-llm', action='store_true', help='禁用真实 LLM, 使用模拟回复')
    parser.add_argument('--debug', action='store_true', help='调试模式 (详细日志)')
    args = parser.parse_args()
    
    # 设置日志级别: DEBUG (详细信息) 或 INFO (重要信息)
    log_level = LogLevel.DEBUG if args.debug else LogLevel.INFO
    setup_logging(level=log_level)
    
    print("=" * 60)
    print("ContextMind v7.1 Interactive Demo")
    print("五层架构 (core/pipeline/strategies/adapters/utils)")
    print("=" * 60)
    print()
    
    # 显示配置
    print("⚙️  当前配置:")
    print(f"   - 会话历史: {'❌ 禁用' if args.no_session else '✅ 启用'}")
    print(f"   - 长期记忆: {'✅ 启用' if args.use_memory else '❌ 禁用'}")
    print(f"   - 最大轮数: {args.max_events}")
    print(f"   - Prompt 历史: {args.history_turns}")
    print(f"   - 调试模式: {'✅ 启用' if args.debug else '❌ 禁用'}")
    print()
    
    # 初始化引擎 (v7.1: LLM 调用在外部，不需要客户端)
    print("🔧 初始化引擎...")
    context_engine = ContextEngine(
        app_name="demo-app",
        user_id="demo-user",
        max_recent_events=args.max_events,
    )
    print("✅ 引擎初始化完成 (v7.1 - 纯上下文工程)")
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
        business_info=business_info.strip(),
        history_turns=args.history_turns,
        use_real_llm=not args.no_llm,  # 默认启用真实 LLM
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
            
            if args.debug:
                response, debug_info = await app.process_turn(user_input, debug=True)
            else:
                response = await app.process_turn(user_input)
            
            print(f"助手: {response}\n")
            
            # Debug 模式下显示详细信息
            if args.debug:
                print("=" * 80)
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
                
                # 3. 上下文优化后的结果
                print(f"\n3️⃣  上下文优化: 已完成 (压缩: {debug_info.get('context_result', {}).get('compressed', False)})")
                
                # 4. 完整的Prompt
                if debug_info.get('prompt'):
                    prompt_preview = debug_info['prompt']
                    print(f"\n4️⃣  完整Prompt ({len(prompt_preview)}字符):")
                    print("   " + "-" * 76)
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
                
                print("=" * 80)
                print()
            
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}\n")
            import traceback
            traceback.print_exc()
    
    print("\n感谢使用 ContextMind v7.1!")


if __name__ == "__main__":
    asyncio.run(main())
