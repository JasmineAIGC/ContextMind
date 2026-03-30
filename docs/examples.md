# 示例代码集合

本文档提供 ContextMind 各种使用场景的完整示例代码。

## 推荐入口：ContextPipeline 端到端示例

### 0. 从原始对话到上下文提取（端到端）

```python
import asyncio
from contextmind import ContextPipeline, AdkLLMClient

async def full_pipeline():
    """ContextPipeline 端到端演示：从原始对话到上下文提取"""
    pipeline = ContextPipeline(llm_client=AdkLLMClient())

    # Phase 1: 从原始对话构建知识库
    my_dialogues = [
        "坐席：你好，请问是张先生吗？\n用户：是的。\n坐席：您有 5 万元可用额度。",
        "坐席：您好，我是安逸花客服。\n用户：我想了解一下借款利率。",
    ]
    pipeline.build_kb(
        dialogues=my_dialogues,
        scene_name="银行贷款外呼",
        scene_description="银行客服主动致电客户推介贷款产品",
    )

    # 注册业务 API（PyTOD 模式，可选）
    @pipeline.register_api("query_loan_info")
    def query_loan_info(customer_name: str) -> dict:
        return {"credit_limit": 50000, "interest_rate": 0.12}

    # Phase 2: 对话上下文提取
    result = await pipeline.process_turn("我想查询一下我的贷款额度")
    print("回复:", result["response"])
    print("本轮上下文:", result["context"])
    print("累积上下文:", result["cumulative_context"])

asyncio.run(full_pipeline())
```

### 0b. 从已有 schema.json 加载

```python
import asyncio
from contextmind import ContextPipeline, AdkLLMClient

async def load_and_chat():
    """从已有 schema.json 加载知识库并对话"""
    pipeline = ContextPipeline(llm_client=AdkLLMClient(), mode="pytod")
    pipeline.load_kb("output/schema.json")

    result = await pipeline.process_turn("我是李明，想了解借款利率")
    print("回复:", result["response"])

asyncio.run(load_and_chat())
```

---

## 基础示例

### 1. 最简单的对话

```python
import asyncio
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_chat_scenario

async def simple_chat():
    """最简单的对话示例"""
    # 初始化
    llm_client = AdkLLMClient()
    config = get_chat_scenario()
    tracker = DialogueStateTracker.from_scenario(llm_client, config)
    
    # 对话
    await tracker.process_turn("你好")
    state = tracker.get_current_state()
    print(f"对话状态: {state}")

# 运行
asyncio.run(simple_chat())
```

### 2. 多轮对话

```python
import asyncio
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_callcenter_scenario

async def multi_turn_dialogue():
    """多轮对话示例"""
    llm_client = AdkLLMClient()
    config = get_callcenter_scenario()
    tracker = DialogueStateTracker.from_scenario(llm_client, config)
    
    # 模拟多轮对话
    turns = [
        "我要投诉",
        "订单号是12345",
        "商品有质量问题"
    ]
    
    for user_input in turns:
        await tracker.process_turn(user_input)
        state = tracker.get_current_state()
        print(f"用户: {user_input}")
        print(f"状态: {state}\n")

asyncio.run(multi_turn_dialogue())
```

---

## DST 模式示例

### 客服场景 - 问题追踪

```python
import asyncio
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_callcenter_scenario

async def callcenter_tracking():
    """客服问题追踪"""
    llm_client = AdkLLMClient()
    config = get_callcenter_scenario()
    tracker = DialogueStateTracker.from_scenario(llm_client, config)
    
    # 客服对话流程
    await tracker.process_turn("我的订单还没到")
    state = tracker.get_current_state()
    
    if 'intent' in state:
        intent = state['intent']
        if intent == '查询':
            print("检测到查询意图，请求订单号...")
            await tracker.process_turn("订单号是ABC123")
            state = tracker.get_current_state()
            order_id = state.get('order_id')
            print(f"订单号: {order_id}")
    
    # 获取最终状态
    final_state = tracker.get_current_state()
    print(f"最终状态: {final_state}")

asyncio.run(callcenter_tracking())
```

### 自定义槽位

```python
from contextmind.modes.dst import DialogueStateTracker, PromptManager
from contextmind.infra.llm_client import AdkLLMClient

async def custom_slots():
    """自定义槽位示例"""
    llm_client = AdkLLMClient()
    
    # 创建提示管理器
    pm = PromptManager(domain="restaurant")
    
    # 添加自定义槽位
    pm.add_slot("restaurant_name", "餐厅名称")
    pm.add_slot("num_people", "就餐人数")
    pm.add_slot("date", "预订日期")
    pm.add_slot("time", "预订时间")
    pm.add_slot("special_request", "特殊要求")
    
    # 创建追踪器
    tracker = DialogueStateTracker(
        llm_client=llm_client,
        prompt_manager=pm
    )
    
    # 对话
    await tracker.process_turn("我想订明天晚上7点的桌子，4个人")
    state = tracker.get_current_state()
    print(state)

asyncio.run(custom_slots())
```

---

## FnCTOD 模式示例

### 保险场景 - 函数调用

```python
import asyncio
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_insurance_scenario

async def insurance_function_calling():
    """保险场景函数调用"""
    llm_client = AdkLLMClient()
    config = get_insurance_scenario()
    tracker = FnCTODTracker.from_scenario(
        llm_client=llm_client,
        scenario_config=config,
        use_two_stage=True
    )
    
    # 对话
    result = await tracker.process_turn("我想了解保险产品")
    
    # 检查函数调用
    if result.get('function_call'):
        fc = result['function_call']
        print(f"函数名: {fc.function_name}")
        print(f"参数: {fc.arguments}")
    
    # 自然语言回复
    print(f"回复: {result.get('response')}")

asyncio.run(insurance_function_calling())
```

### 处理函数调用结果

```python
import asyncio
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_insurance_scenario

async def handle_function_result():
    """处理函数调用结果"""
    llm_client = AdkLLMClient()
    config = get_insurance_scenario()
    tracker = FnCTODTracker.from_scenario(llm_client, config)
    
    # 第一轮：用户请求
    result = await tracker.process_turn("帮我查一下保单")
    
    if result.get('function_call'):
        fc = result['function_call']
        
        # 模拟调用实际函数
        if fc.function_name == "query_policy":
            # 这里调用实际的API
            api_result = {
                "policy_id": "P123456",
                "status": "active",
                "amount": 100000
            }
            
            # 将结果传回LLM
            next_result = await tracker.process_turn(
                f"查询结果：{api_result}"
            )
            print(next_result['response'])

asyncio.run(handle_function_result())
```

---

## Evolve 模式示例

### 记忆功能

```python
import asyncio
from contextmind.modes.evolve import EvolveEngine
from contextmind.infra.llm_client import AdkLLMClient

async def memory_demo():
    """记忆功能演示"""
    llm_client = AdkLLMClient()
    
    engine = EvolveEngine(
        app_name="memory_test",
        user_id="user001",
        llm_client=llm_client,
        enable_memory=True,
        memory_limit=50
    )
    
    # 第一轮：告诉系统一些信息
    response1 = await engine.process_turn("我叫张三，今年25岁")
    print(f"助手: {response1}")
    
    # 第二轮：测试是否记住
    response2 = await engine.process_turn("我叫什么名字？")
    print(f"助手: {response2}")
    # 应该能回答"张三"
    
    # 查看记忆库
    memories = engine.session_manager.get_all_memories()
    print(f"\n记忆数量: {len(memories)}")

asyncio.run(memory_demo())
```

### 进化学习

```python
import asyncio
from contextmind.modes.evolve import EvolveEngine
from contextmind.infra.llm_client import AdkLLMClient

async def evolution_demo():
    """进化学习演示"""
    llm_client = AdkLLMClient()
    
    engine = EvolveEngine(
        app_name="evolution_test",
        user_id="user001",
        llm_client=llm_client,
        enable_memory=True,
        enable_evolution=True,
        evolution_interval=5  # 每5轮进化一次
    )
    
    # 多轮对话
    for i in range(10):
        user_msg = f"这是第{i+1}轮对话"
        response = await engine.process_turn(user_msg)
        print(f"[{i+1}] 用户: {user_msg}")
        print(f"[{i+1}] 助手: {response}\n")
        
        # 第5轮会触发进化
        if i == 4:
            print("--- 进化触发 ---\n")

asyncio.run(evolution_demo())
```

### 使用场景应用

```python
import asyncio
from contextmind.modes.evolve import create_app_for_scenario
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_chat_scenario

async def scenario_app_demo():
    """使用场景应用"""
    llm_client = AdkLLMClient()
    config = get_chat_scenario()
    
    # 创建应用
    app = create_app_for_scenario(
        scenario_name="chat",
        llm_client=llm_client,
        scenario_config=config
    )
    
    # 对话
    response = await app.process_turn("讲个笑话")
    print(response)

asyncio.run(scenario_app_demo())
```

---

## 高级示例

### 同时使用多个模式

```python
import asyncio
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.evolve import create_app_for_scenario
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_insurance_scenario

async def multi_mode_demo():
    """同时使用多个模式"""
    llm_client = AdkLLMClient()
    config = get_insurance_scenario()
    
    # DST: 提取状态
    dst_tracker = DialogueStateTracker.from_scenario(llm_client, config)
    await dst_tracker.process_turn("我想买保险")
    dst_state = dst_tracker.get_current_state()
    print(f"DST状态: {dst_state}")
    
    # FnCTOD: 生成函数调用
    fnctod_tracker = FnCTODTracker.from_scenario(llm_client, config)
    fnctod_result = await fnctod_tracker.process_turn("我想买保险")
    print(f"FnCTOD调用: {fnctod_result.get('function_call')}")
    
    # Evolve: 生成自然回复
    evolve_app = create_app_for_scenario("insurance", llm_client, config)
    evolve_response = await evolve_app.process_turn("我想买保险")
    print(f"Evolve回复: {evolve_response}")

asyncio.run(multi_mode_demo())
```

### 自定义LLM客户端

```python
from contextmind.infra.llm_client import AdkLLMClient
from typing import List, Dict, Any

class CustomLLMClient(AdkLLMClient):
    """自定义LLM客户端"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.call_count = 0
    
    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """重写异步调用方法"""
        self.call_count += 1
        print(f"第{self.call_count}次调用")
        
        # 调用父类方法
        response = await super().chat_async(messages, **kwargs)
        
        # 添加自定义逻辑
        print(f"响应长度: {len(response)}")
        
        return response

# 使用自定义客户端
async def use_custom_client():
    client = CustomLLMClient()
    from contextmind.modes.dst import DialogueStateTracker
    from contextmind.scenarios import get_chat_scenario
    
    tracker = DialogueStateTracker.from_scenario(
        llm_client=client,
        scenario_config=get_chat_scenario()
    )
    
    await tracker.process_turn("你好")
```

### 错误处理

```python
import asyncio
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_chat_scenario

async def error_handling_demo():
    """错误处理示例"""
    llm_client = AdkLLMClient()
    config = get_chat_scenario()
    tracker = DialogueStateTracker.from_scenario(llm_client, config)
    
    try:
        # 可能出错的操作
        await tracker.process_turn("")  # 空输入
    except ValueError as e:
        print(f"值错误: {e}")
    except Exception as e:
        print(f"未知错误: {e}")
    finally:
        # 清理
        tracker.reset()

asyncio.run(error_handling_demo())
```

---

## 实际应用示例

### 简单聊天机器人

```python
import asyncio
from contextmind.modes.evolve import create_app_for_scenario
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_chat_scenario

async def chatbot():
    """简单聊天机器人"""
    llm_client = AdkLLMClient()
    config = get_chat_scenario()
    app = create_app_for_scenario("chat", llm_client, config)
    
    print("聊天机器人已启动（输入'退出'结束）")
    
    while True:
        user_input = input("你: ")
        if user_input.lower() in ['退出', 'quit', 'exit']:
            break
        
        response = await app.process_turn(user_input)
        print(f"机器人: {response}\n")

# asyncio.run(chatbot())
```

### 客服系统

完整的客服系统示例请参考 `examples/cli_demo.py`。

---

## 相关文档

- [API 参考](api-reference.md)
- [配置指南](configuration.md)
- [快速开始](quick-start.md)
