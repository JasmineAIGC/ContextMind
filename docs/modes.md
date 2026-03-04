# DST vs Evolve vs FnCTOD 模式对比与高级设置说明

## 概述

ContextMind支持三种对话模式，每种模式有不同的计算流程和参数设置：
- **DST模式**：基于槽位提取的对话状态追踪
- **Evolve模式**：基于记忆进化的智能对话系统
- **FnCTOD模式**：基于函数调用的对话状态追踪（DST的升级版）

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

### Evolve模式（完整架构）

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

Evolve模式显示以下信息：

```json
{
  "🎯 模式": "Evolve (完整架构)",
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

### 使用Evolve模式的场景
- ✅ 开放域闲聊
- ✅ 需要长期记忆的对话
- ✅ 需要系统学习和进化
- ✅ 复杂的上下文理解
- ✅ 多轮复杂对话

### 使用FnCTOD模式的场景
- ✅ 任务导向型对话（DST的升级版）
- ✅ 需要遵循OpenAI function calling标准
- ✅ 多domain场景需要明确分离

### 使用PyTOD模式的场景
- ✅ 需要真实API调用并获取执行结果
- ✅ 高精度任务型对话（最大限度减少幻觉）
- ✅ 快速原型开发（开放域模式，无需预定义意图）

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

### Evolve模式架构

```python
class EvolveEngine:
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
- **Evolve模式**：完整架构、记忆与学习、复杂对话处理
- **高级设置**：根据具体需求调整，平衡性能和效果
- **状态显示**：两种模式都提供详细的状态信息，便于理解和调试

### FnCTOD模式（函数调用DST）

#### 计算流程
```
用户输入
  ↓
1. 接收 user_utterance（用户话语）
  ↓
2. Stage 1: Domain Selection（域选择）
   - 构建domain选择提示词
   - LLM识别相关的domain
   - 输出: <domain>domain_name</domain>
  ↓
3. Stage 2: Function Calling（函数调用）
   - 构建选中domain的完整函数规格
   - LLM生成function call
   - 输出: <function_call name="domain">{"param": "value"}</function_call>
  ↓
4. 解析function call提取参数
  ↓
5. 更新累积状态
  ↓
6. 生成自然语言回复
  ↓
7. 返回结果（包含状态、function_call、回复）
```

#### 核心特性
- **函数调用范式**：将domain视为函数，槽位视为参数
- **两阶段处理**：先选择domain，再填充参数
- **预定义Schema**：为三个场景预定义了函数规格
- **结构化输出**：XML格式的function call + 自然语言回复
- **零样本能力**：无需训练，基于LLM prompting
- **向后兼容**：支持动态创建schema作为fallback

#### 预定义Schema

FnCTOD为三个场景提供了预定义的函数Schema：

##### 1. 闲聊场景 (Chat)
- **Domain**: `chat`
- **参数数量**: 6个
- **必需参数**: `intent_level1`
- **参数列表**:
  - intent_level1: 一级意图（闲聊、求助、分享、情感、其他）
  - intent_level2: 二级意图
  - topic: 对话话题
  - emotion: 情绪状态（开心、平静、烦恼、兴奋、其他）
  - user_name: 用户名称
  - context_info: 其他上下文信息

##### 2. 客服场景 (Callcenter)
- **Domain**: `callcenter`
- **参数数量**: 9个
- **必需参数**: `intent_level1`
- **参数列表**:
  - intent_level1: 一级意图（咨询、投诉、售后、账户、其他）
  - intent_level2: 二级意图
  - issue_type: 问题类型
  - customer_name: 客户姓名
  - product: 相关产品
  - order_number: 订单号
  - resolution_status: 解决状态（未解决、处理中、已解决、需升级）
  - urgency: 紧急程度（低、中、高、紧急）
  - satisfaction: 满意度（满意、一般、不满意、未知）

##### 3. 保险场景 (Insurance)
- **Domain**: `insurance`
- **参数数量**: 14个
- **必需参数**: `intent_level1`
- **参数列表**:
  - intent_level1: 一级意图（拒绝、无意向、用户忙、考虑、质疑类、接受、咨询）
  - intent_level2, intent_level3: 二级、三级意图
  - customer_name: 客户姓名
  - age, gender, occupation: 基本信息
  - existing_insurance: 已有保险情况
  - insurance_interest: 保险兴趣（是、否、考虑中）
  - budget, family_info, health_concern: 需求信息
  - rejection_reason: 拒绝原因
  - follow_up_status: 跟进状态（待跟进、已跟进、已成交、已放弃）

#### 使用示例

```python
from fnctod import get_function_schema_for_scenario, FunctionManager, FnCTODTracker

# 1. 获取预定义schema
schema = get_function_schema_for_scenario("闲聊")

# 2. 创建FunctionManager
function_manager = FunctionManager()
function_manager.add_domain(schema)

# 3. 创建FnCTOD追踪器
tracker = FnCTODTracker(
    llm_client=llm_client,
    function_manager=function_manager,
    use_two_stage=True  # 启用两阶段处理
)

# 4. 处理对话
result = await tracker.process_turn(user_utterance="你好")
# 返回: {
#   "state": {"chat-intent_level1": "闲聊", ...},
#   "response": "你好！很高兴见到你...",
#   "function_call": {...}
# }
```

#### 高级设置参数

##### 1. 两阶段处理（use_two_stage）
- **作用**：控制是否使用两阶段处理
- **默认值**：True
- **说明**：
  - **True**: 先选择domain，再调用函数（适合多domain场景）
  - **False**: 直接调用函数（适合单domain场景）

##### 2. 历史轮数（max_history_turns）
- **作用**：控制保留的历史轮数
- **默认值**：10轮
- **范围**：5-50轮

#### 对话状态显示

FnCTOD模式显示以下信息：

```json
{
  "模式": "FnCTOD (函数调用DST)",
  "场景": "💬 闲聊对话",
  "对话轮数": 3,
  "本轮函数调用": "chat",
  "  intent_level1": "闲聊",
  "  topic": "天气",
  "  emotion": "平静",
  "---": "---",
  "累积状态": "已提取 3 个参数",
  "chat-intent_level1": "闲聊",
  "chat-topic": "天气",
  "chat-emotion": "平静"
}
```

## 四种模式对比

| 特性 | DST | Evolve | FnCTOD | PyTOD |
|------|-----|--------|--------|-------|
| **方法论** | 槽位-值提取 | 记忆进化 | 函数调用 | 程序执行 |
| **技术基础** | ACL 2023 DST | 五层架构 | FnCTOD论文 | Apple PyTOD |
| **核心能力** | 状态追踪 | 记忆+学习 | 结构化提取 | API执行 |
| **处理模式** | 单阶段 | 多层流水线 | 两阶段 | 三步流程 |
| **Schema管理** | 动态或预定义 | 无 | 预定义Schema | 可选Schema |
| **输出格式** | JSON状态 | 自然回复 | Function call + 回复 | 程序语句 + 回复 |
| **记忆系统** | ❌ 无 | ✅ 完整 | ❌ 无 | ❌ 无 |
| **学习能力** | ❌ 无 | ✅ 持续学习 | ❌ 无 | ❌ 无 |
| **真实API调用** | ❌ 无 | ❌ 无 | ❌ 无 | ✅ 支持 |
| **适用场景** | 结构化任务 | 开放对话 | 任务对话+API集成 | 高精度任务型 |
| **复杂度** | ⭐⭐ 中等 | ⭐⭐⭐⭐ 完整 | ⭐⭐⭐ 较高 | ⭐⭐⭐⭐ 高 |
| **扩展性** | 中等 | 高 | 非常高 | 高 |
| **标准兼容** | 自定义 | 自定义 | OpenAI兼容 | 自定义 |

## 模式选择建议（更新）

### 使用FnCTOD模式的场景
- ✅ 需要与外部API/工具集成
- ✅ 任务导向型对话（DST的升级版）
- ✅ 需要结构化的function calling输出
- ✅ 多domain场景需要明确分离
- ✅ 希望遵循OpenAI function calling标准
- ✅ 需要预定义Schema保证一致性

### 使用PyTOD模式的场景
- ✅ 需要真实API调用并获取执行结果
- ✅ 高精度任务型对话（最大限度减少幻觉）
- ✅ 快速原型开发（开放域模式，无需预定义意图）
- ✅ 有明确业务场景（Schema驱动模式）

### DST vs FnCTOD 选择建议
- **选择DST**: 简单的槽位提取，不需要function calling
- **选择FnCTOD**: 需要更结构化的输出，或需要与工具集成
- **选择PyTOD**: 需要真实API调用和执行反馈

