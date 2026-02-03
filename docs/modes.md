# DST vs Evolution 模式对比与高级设置说明

## 概述

Evolution支持两种对话模式，每种模式有不同的计算流程和参数设置。

## 模式对比

### DST模式（对话状态追踪）

#### 计算流程
```
用户输入
  ↓
1. 接收 system_utterance（系统话语）和 user_utterance（用户话语）
  ↓
2. 调用 process_turn(system_utterance, user_utterance)
  ↓
3. 准备历史对话（根据设置应用摘要）
  ↓
4. 构建提示词，调用LLM提取槽位和意图
  ↓
5. 解析LLM响应，提取JSON格式的slot-value对
  ↓
6. 更新累积状态（current_state）
  ↓
7. 追踪意图变化（current_intents）
  ↓
8. 管理历史（超过max_history_turns时触发摘要）
  ↓
9. 返回更新后的状态
  ↓
10. 基于状态生成回复
```

#### 核心特性
- **零样本学习**：无需训练，完全基于提示词
- **动态槽位提取**：不限制槽位类型，LLM自由提取信息
- **多意图追踪**：同时追踪多个用户意图
- **智能历史管理**：自动摘要长对话历史

#### 高级设置参数

##### 1. 历史轮数（max_history_turns）
- **作用**：控制完整保留的最近对话轮数
- **默认值**：10轮
- **范围**：5-50轮
- **影响**：
  - 更大的值：更多上下文，但消耗更多token
  - 更小的值：节省token，但可能丢失上下文

##### 2. 启用历史摘要（enable_history_summary）
- **作用**：主开关，控制是否启用历史摘要功能
- **默认值**：启用（True）
- **说明**：
  - **启用时**：超过max_history_turns的旧对话会被摘要
  - **禁用时**：不生成摘要，但仍然只保留最近N轮完整对话
- **目的**：减少token消耗，同时保留重要历史信息

##### 3. 使用LLM生成摘要（use_llm_summary）
- **作用**：选择摘要生成方式（仅当enable_history_summary=True时有效）
- **默认值**：禁用（False，使用模板摘要）
- **两种摘要方式**：
  - **模板摘要（False）**：
    - 快速、节省成本
    - 使用预定义模板格式化历史
    - 适合大多数场景
  - **LLM摘要（True）**：
    - 更智能、更自然
    - 调用LLM生成摘要
    - 消耗额外token，速度较慢
    - 适合复杂对话或需要高质量摘要的场景

##### 设置关系图
```
enable_history_summary
├── False: 不使用摘要（use_llm_summary无效）
└── True: 启用摘要
    ├── use_llm_summary = False: 使用模板摘要（快速）
    └── use_llm_summary = True: 使用LLM摘要（智能）
```

#### 对话状态显示

DST模式显示以下信息：

```json
{
  "🎯 模式": "DST (对话状态追踪)",
  "📋 场景": "💬 闲聊对话",
  "💬 对话轮数": 5,
  "📌 name": "张三",           // 提取的槽位-槽值对
  "📌 phone": "13800138000",   // 提取的槽位-槽值对
  "📌 intent": "查询订单",      // 提取的槽位-槽值对
  "✅ 已提取槽位数": 3,
  "🎭 当前意图": "查询订单, 确认信息",
  "📊 历史摘要": "已启用",
  "⚙️ 最大历史轮数": 10,
  "🤖 LLM摘要": "禁用(使用模板)"
}
```

### Evolution模式（完整架构）

#### 计算流程
```
用户输入
  ↓
1. 感知层（Perception Layer）
   - 接收和预处理用户输入
  ↓
2. 记忆层（Memory Layer）
   - 检索相关历史记忆
   - 存储新的对话信息
  ↓
3. 上下文层（Context Layer）
   - 整合当前对话和历史记忆
   - 构建完整上下文
  ↓
4. 生成层（Generation Layer）
   - 基于上下文生成回复
  ↓
5. 进化层（Evolution Layer）
   - 从对话中学习
   - 更新知识和策略
  ↓
生成回复
```

#### 核心特性
- **五层架构**：感知→记忆→上下文→生成→进化
- **长期记忆**：持久化存储重要信息
- **进化学习**：从交互中持续学习和优化

#### 高级设置参数

##### 1. 启用记忆功能（enable_memory）
- **作用**：控制是否启用长期记忆存储
- **默认值**：启用（True）
- **说明**：
  - **启用时**：系统会记住重要信息，支持长期对话
  - **禁用时**：仅使用当前会话信息，不保存历史

##### 2. 启用进化学习（enable_evolution）
- **作用**：控制是否从对话中学习和优化
- **默认值**：启用（True）
- **说明**：
  - **启用时**：系统会从交互中学习，改进响应策略
  - **禁用时**：使用固定策略，不进行学习

#### 对话状态显示

Evolution模式显示以下信息：

```json
{
  "🎯 模式": "Evolution (完整架构)",
  "📋 场景": "💬 闲聊对话",
  "💾 记忆功能": "已启用",
  "🔄 进化学习": "已启用",
  "📝 应用ID": "gradio_demo_chat",
  "👤 用户ID": "gradio_user",
  "🧠 记忆数量": 15,
  "📚 最近记忆": [
    "用户喜欢篮球运动",
    "讨论了天气情况",
    "计划周末旅游"
  ],
  "📊 会话ID": "session_12345"
}
```

## 模式选择建议

### 使用DST模式的场景
- ✅ 需要明确的槽位填充（如订票、订餐）
- ✅ 任务导向型对话
- ✅ 需要追踪对话状态变化
- ✅ 关注信息提取和结构化
- ✅ 需要优化token使用（通过摘要）

### 使用Evolution模式的场景
- ✅ 开放域闲聊
- ✅ 需要长期记忆的对话
- ✅ 需要系统学习和进化
- ✅ 复杂的上下文理解
- ✅ 多轮复杂对话

## 常见问题

### Q1: "启用历史摘要"和"使用LLM生成摘要"是一样的功能吗？

**A:** 不是。它们是两个不同层次的设置：

- **启用历史摘要**：主开关，决定是否使用摘要功能
- **使用LLM生成摘要**：在摘要启用后，选择具体的摘要方式

类比：
- "启用历史摘要" = 决定是否要"压缩文件"
- "使用LLM生成摘要" = 决定用"智能压缩"还是"快速压缩"

### Q2: 什么时候应该使用LLM摘要？

**A:** 建议场景：
- 对话历史非常复杂，包含多个交织的主题
- 需要高质量的摘要以保持语义连贯性
- token成本不是主要考虑因素
- 对话质量优先于响应速度

默认使用模板摘要即可满足大多数需求。

### Q3: DST模式下为什么没有提取到槽位？

**A:** 可能的原因：
1. LLM返回的不是有效JSON格式
2. 提示词不够明确
3. 对话内容中确实没有可提取的信息
4. LLM理解有偏差

解决方法：
- 查看日志中的原始LLM响应
- 检查response_parser的解析结果
- 尝试更明确的用户输入
- 调整temperature参数（降低随机性）

### Q4: 两种模式可以切换吗？

**A:** 可以在UI中切换，但切换会：
- 重置当前对话
- 清空对话历史
- 重新初始化相应的引擎

建议在同一个会话中保持使用同一种模式。

## 技术细节

### DST模式槽位提取流程

1. **提示词构建**：
   ```python
   # 系统指令 + 历史摘要（如启用）+ 当前对话
   prompt = system_instruction + history_summary + current_turn
   ```

2. **LLM调用**：
   ```python
   response = await llm_client.chat_async(
       messages=messages,
       temperature=0.0  # 降低随机性，提高一致性
   )
   ```

3. **响应解析**：
   ```python
   # 提取JSON
   updates = response_parser.extract_json(response)
   # 更新状态
   current_state.update(updates)
   ```

4. **历史管理**：
   ```python
   if len(dialogue_history) > max_history_turns:
       if enable_history_summary:
           if use_llm_summary:
               summary = generate_llm_summary(old_history)
           else:
               summary = generate_template_summary(old_history)
   ```

### Evolution模式架构

```python
class EvolutionEngine:
    def __init__(self):
        self.perception_layer = PerceptionLayer()
        self.memory_bank = MemoryBank()  # 记忆层
        self.context_manager = ContextManager()
        self.generator = Generator()
        self.evolution_layer = EvolutionLayer()  # 进化层
    
    async def process_turn(self, user_input):
        # 1. 感知
        perceived = await self.perception_layer.process(user_input)
        
        # 2. 记忆检索
        if self.enable_memory:
            relevant_memories = self.memory_bank.retrieve(perceived)
        
        # 3. 上下文整合
        context = self.context_manager.build(perceived, relevant_memories)
        
        # 4. 生成回复
        response = await self.generator.generate(context)
        
        # 5. 学习进化
        if self.enable_evolution:
            self.evolution_layer.learn(context, response)
        
        return response
```

## 总结

- **DST模式**：轻量级、任务导向、结构化信息提取
- **Evolution模式**：完整架构、记忆与学习、复杂对话处理
- **高级设置**：根据具体需求调整，平衡性能和效果
- **状态显示**：两种模式都提供详细的状态信息，便于理解和调试
