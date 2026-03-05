# FnCTOD 对话任务追踪报告

> **生成时间**：2026-03-05T01:37:48.793533  
> **会话 ID**：`2025102811215858702023182`  
> **算法**：FnCTOD（域选择 → 函数调用，两阶段 DST）  
> **场景**：安逸花外呼促活（callcenter domain）

---

## 一、概述

本报告记录了 **FnCTOD（Function Calling for Task-Oriented Dialogue）** 算法
在一条安逸花外呼真实对话上的完整运行过程。

**FnCTOD 的核心价值**：传统 DST（对话状态追踪）直接提取「槽位-值」对，
FnCTOD 将槽位提取建模为**函数调用**，输出更结构化、更易扩展，
同时在同一次 LLM 调用中完成状态提取和自然语言回复生成。

```
用户输入
  │
  ▼
┌─────────────────────────────────┐
│  Stage 1  域选择                │  识别当前对话涉及的业务域
│           Domain Selection      │  （多域场景下启用）
└──────────────┬──────────────────┘
               │ 候选 domain 列表
               ▼
┌─────────────────────────────────┐
│  Stage 2  函数调用              │  LLM 以 <function_call> 格式
│           Function Calling      │  提取对话状态 + 生成自然语言回复
└──────────────┬──────────────────┘
               │
               ▼
结构化状态（DST 结果）+ 自然语言回复
```

---

## 二、对话背景（测试数据）

**数据来源**：`resources/data/chat_test_100.json`，随机抽取一条会话

### 2.1 用户信息

```
现在是上午十一点二十一分#高先生#手机尾号是六七八#注册时间是二零一八年九月二十日#最近登录时间是二零二五年十月二十五日#距离上次登录三天#近30天登录九次#已授信四百五十七天#初始额度为九千六百元#授信额度为一万八千元#可提现额度为七千零四十一元#取现比例是百分之一百#提额时间是二零二五年十月十日#距离上次提额一十七天#末次提额八千五百元#临时额度为二万六千五百元#临时提额为八千五百元#临时提额从二零二五年十月十日到二零二五年十月二十六日#临时提额已过期#借款利率是二十四#账单日是每月二十七号#还款日是二零二五年十一月一日#绑定农业银行#现有三笔借款#累计提现八笔#距离上次借款一百七十八天#最近一次借款是二零二五年五月二日#借款未还清
```

### 2.2 完整对话历史

> 以下为本条会话的原始对话记录，最后一条用户发言将作为 FnCTOD 的当前输入。

**第 1 句** · 🤖 **坐席**：诶您好，打扰一下，请问您这边是高先生吗？来电是有事情找一下高先生本人。

**第 2 句** · 👤 **用户**：喂你说。

**第 3 句** · 🤖 **坐席**：诶高先生您好，我是马上消费安逸花的工作人员，安逸花这个账户是您自己本人在使用的，对吧？

**第 4 句** · 👤 **用户**：对我就要我就就想和你们说了这个。

**第 5 句** · 🤖 **坐席**：诶您说高先生。

**第 6 句** · 👤 **用户**：贷款是怎么回事。

**第 7 句** · 🤖 **坐席**：您在安逸花账户有一笔两万一千九百块钱的额度嘛，对吧？

**第 8 句** · 👤 **用户**：不是这个我说七月二十三号七月二十三号的这一笔贷款我没贷怎么怎么会有一笔一万三千多块钱的还有一个八月。

**第 9 句** · 🤖 **坐席**：哦您是说您之前有借过款吗？

**第 10 句** · 👤 **用户**：我有借款我有借款但是都还掉了呀。

**第 11 句** · 🤖 **坐席**：哦是这样的先生，因为您这边就是您上一次借款的话，是在二五年五月份嘛，然后您当时借款了六百块钱，然后您这边就是还款的时候嘛，就是逾期了几天的样子，对吧？

**第 12 句** · 👤 **用户**：这有有过。

**第 13 句** · 🤖 **坐席**：诶是这样的哈，因为公司嘛也是考虑到现在是用钱的高峰期嘛，那目前给到您的这个两万一千九百的额度呢还没有开始使用，所以今天专门来电话呢也是重新帮您确认一下账户的这个额度和利息的问题的，明白吧，先生？

**第 14 句** · 👤 **用户**：我我说的不是这个你帮我你帮我看一下那个七月二十三号七月二十三号我没有借款为什么有一笔借款。

**第 15 句** · 🤖 **坐席**：啊您说您没有借款，怎么会有这笔借款呢？

**第 16 句** · 👤 **用户**：对还有一个。

**第 17 句** · 🤖 **坐席**：嗯您稍等哈，我这边儿马上帮您查询一下，您稍等。

**第 18 句** · 👤 **用户**：嗯啊。

**第 19 句** · 🤖 **坐席**：我这边儿马上帮您查询一下，您稍等。

**第 20 句** · 👤 **用户**：三号和八七号。

**第 21 句** · 🤖 **坐席**：抱歉哈，没听清楚，您能再讲一遍吗？

**第 22 句** · 👤 **用户**：七月二十三号。

**第 23 句** · 🤖 **坐席**：对呀，就是您在二五年五月份的时候有去借款，对吧？

**第 24 句** · 👤 **用户**：五月份有呀我是说七月份。

**第 25 句** · 🤖 **坐席**：哦是这样的先生，因为您这边就是您上一次借款的话，是在二五年五月份嘛，然后您当时借款了六百块钱，然后您这边就是还款的时候嘛，就是逾期了几天的样子，对吧？

**第 26 句** · 👤 **用户**：这这个有什么问题吗。

**第 27 句** · 🤖 **坐席**：诶是这样的哈，因为公司嘛也是考虑到现在是用钱的高峰期嘛，那目前给到您的这个两万一千九百的额度呢还没有开始使用，所以今天专门来电话呢也是重新帮您确认一下账户的这个额度和利息的问题的，明白吧，先生？

**第 28 句** · 👤 **用户**：嗯这现在因为现在我不敢用了因为这个上面不对了你这个安逸花上面。

**第 29 句** · 🤖 **坐席**：哦您是说现在用不了了吗，先生？

**第 30 句** · 👤 **用户**：不是用不了是我没有借款你这个上面。

**第 31 句** · 🤖 **坐席**：哦您说您没有借款，怎么会有这笔借款呢？

**第 32 句** · 👤 **用户**：对一万四千四还有一个八月一号。

### 2.3 当前待处理的用户发言（FnCTOD 输入）

> 👤 **用户**：**对一万四千四还有一个八月一号。**

_（对话历史中共注入 16 轮历史到 Tracker）_

### 2.4 实际坐席回复（来自数据集，供对比）

> 🤖 **实际坐席回复**：那我这边就先不打扰您了，祝您生活愉快，也邀请您多登录安逸花APP看看，APP会不定期上线各种优惠活动，给您更多借款优惠，再见！

**人工校验标签**：`不当告别`

---

## 三、FnCTOD 预置配置（运行前定义）

> 以下内容在 FnCTOD 启动前已完全定义，不依赖用户输入，是算法的「知识底座」。

### 3.1 场景上下文（注入系统提示的业务背景）

```
这是一个外呼小额借款推介场景（安逸花外呼促活）。坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。标准流程：① 核实用户身份（姓名/手机尾号）→ ② 告知可用额度和利率 → ③ 解答疑问（还款方式、账单争议等）→ ④ 引导用户在 APP 完成借款操作 → ⑤ 确认无未解决诉求后礼貌告别。
```

### 3.2 函数 Schema（域名、描述与参数定义）

> FnCTOD 将每个业务域建模为一个「函数」，槽位对应函数参数。
> LLM 通过调用函数并填写参数来完成对话状态追踪（DST）。

#### 域：`callcenter`

**描述**：客户服务对话场景，全面提取客户意图、问题详情、解决方案、服务质量等多维度信息  
**参数数量**：29

**必填参数：**

- `intent_level1` — 一级意图（主意图） ← 枚举值：`咨询`, `投诉`, `售后`, `账户`, `技术支持`, `建议反馈`, `预约服务`, `其他`

**可选参数（部分展示）：**

- `intent_level2` — 二级意图（子意图）：如产品咨询、退换货、登录问题、支付问题等
- `issue_category` — 问题大类
- `issue_subcategory` — 问题子类（具体问题类型）
- `issue_description` — 问题详细描述
- `customer_name` — 客户姓名
- `customer_id` — 客户ID或会员号
- `customer_level` — 客户等级
- `contact_phone` — 联系电话
- _…（另有 20 个可选参数）_

**函数提示词格式（注入 LLM 系统消息中的函数规格）：**

```
Function: callcenter
Description: 客户服务对话场景，全面提取客户意图、问题详情、解决方案、服务质量等多维度信息
Parameters:
  - intent_level1 (string) (required): 一级意图（主意图） [options: 咨询, 投诉, 售后, 账户, 技术支持, 建议反馈, 预约服务, 其他]
  - intent_level2 (string): 二级意图（子意图）：如产品咨询、退换货、登录问题、支付问题等
  - issue_category (string): 问题大类 [options: 产品问题, 订单问题, 支付问题, 物流问题, 账户问题, 技术问题, 服务问题, 其他]
  - issue_subcategory (string): 问题子类（具体问题类型）
  - issue_description (string): 问题详细描述
  - customer_name (string): 客户姓名
  - customer_id (string): 客户ID或会员号
  - customer_level (string): 客户等级 [options: 普通, VIP, 黄金, 钻石, 未知]
  - contact_phone (string): 联系电话
  - contact_email (string): 联系邮箱
  - preferred_contact_method (string): 首选联系方式 [options: 电话, 短信, 邮件, 微信, APP推送, 其他]
  - preferred_contact_time (string): 首选联系时间
  - order_number (string): 订单号
  - product_name (string): 产品名称
  - product_model (string): 产品型号
  - purchase_date (string): 购买日期
  - resolution_status (string): 解决状态 [options: 未解决, 处理中, 待回复, 已解决, 需升级, 已转接]
  - solution_provided (string): 提供的解决方案
  - follow_up_action (string): 后续跟进行动
  - estimated_resolution_time (string): 预计解决时间
  - urgency (string): 紧急程度 [options: 低, 中, 高, 紧急]
  - priority (string): 处理优先级 [options: P1-最高, P2-高, P3-中, P4-低]
  - escalation_needed (string): 是否需要升级 [options: 是, 否, 待定]
  - satisfaction (string): 客户满意度 [options: 非常满意, 满意, 一般, 不满意, 非常不满意, 未知]
  - service_quality (string): 服务质量评价
  - agent_name (string): 客服代表姓名
  - complaint_reason (string): 投诉原因（如果是投诉）
  - reference_number (string): 工单号或参考号
  - notes (string): 备注或其他重要信息
```

### 3.3 系统提示词

#### Stage 1 系统提示（域选择，仅包含域描述）

```
You are a task-oriented dialogue assistant.
Your task is to identify the relevant domain(s) from the user's utterance.

Available domains:
- callcenter: 客户服务对话场景，全面提取客户意图、问题详情、解决方案、服务质量等多维度信息

Based on the conversation history and current user utterance, identify the relevant domain(s).
Output format:
<domain>domain_name</domain>

You can output multiple domains if needed.
```

#### Stage 2 系统提示（函数调用，包含完整参数规格）

```
You are a task-oriented dialogue assistant with function calling capability.
Use the provided functions to track dialogue state and generate appropriate responses.

Available functions:

Function: callcenter
Description: 客户服务对话场景，全面提取客户意图、问题详情、解决方案、服务质量等多维度信息
Parameters:
  - intent_level1 (string) (required): 一级意图（主意图） [options: 咨询, 投诉, 售后, 账户, 技术支持, 建议反馈, 预约服务, 其他]
  - intent_level2 (string): 二级意图（子意图）：如产品咨询、退换货、登录问题、支付问题等
  - issue_category (string): 问题大类 [options: 产品问题, 订单问题, 支付问题, 物流问题, 账户问题, 技术问题, 服务问题, 其他]
  - issue_subcategory (string): 问题子类（具体问题类型）
  - issue_description (string): 问题详细描述
  - customer_name (string): 客户姓名
  - customer_id (string): 客户ID或会员号
  - customer_level (string): 客户等级 [options: 普通, VIP, 黄金, 钻石, 未知]
  - contact_phone (string): 联系电话
  - contact_email (string): 联系邮箱
  - preferred_contact_method (string): 首选联系方式 [options: 电话, 短信, 邮件, 微信, APP推送, 其他]
  - preferred_contact_time (string): 首选联系时间
  - order_number (string): 订单号
  - product_name (string): 产品名称
  - product_model (string): 产品型号
  - purchase_date (string): 购买日期
  - resolution_status (string): 解决状态 [options: 未解决, 处理中, 待回复, 已解决, 需升级, 已转接]
  - solution_provided (string): 提供的解决方案
  - follow_up_action (string): 后续跟进行动
  - estimated_resolution_time (string): 预计解决时间
  - urgency (string): 紧急程度 [options: 低, 中, 高, 紧急]
  - priority (string): 处理优先级 [options: P1-最高, P2-高, P3-中, P4-低]
  - escalation_needed (string): 是否需要升级 [options: 是, 否, 待定]
  - satisfaction (string): 客户满意度 [options: 非常满意, 满意, 一般, 不满意, 非常不满意, 未知]
  - service_quality (string): 服务质量评价
  - agent_name (string): 客服代表姓名
  - complaint_reason (string): 投诉原因（如果是投诉）
  - reference_number (string): 工单号或参考号
  - notes (string): 备注或其他重要信息

Instructions:
1. Based on the conversation, call the appropriate function with relevant parameters
2. Output the function call in this format:
   <function_call name="function_name">
   {"param1": "value1", "param2": "value2"}
   </function_call>
3. After the function call, provide a natural language response to the user

Remember: Only fill parameters that are mentioned or can be inferred from the conversation.
```

---

## 四、FnCTOD 两阶段流水线追踪

> 本次共处理 **1 轮**用户输入（demo 仅处理最后一轮，展示完整两阶段流程）。

### 第 1 轮

**用户输入**：对一万四千四还有一个八月一号。

#### Stage 2：函数调用（Function Calling）

**作用**：以 function_call 格式提取对话状态（DST），同时生成自然语言回复

**目标域**：`callcenter`

**📥 输入（发送给 LLM 的 messages）**

**`[SYSTEM]`**

```
你是一个具有函数调用能力的任务型对话助手。
使用提供的函数来追踪对话状态并生成适当的响应。


Available functions:

Function: callcenter
Description: 客户服务对话场景，全面提取客户意图、问题详情、解决方案、服务质量等多维度信息
Parameters:
  - intent_level1 (string) (required): 一级意图（主意图） [options: 咨询, 投诉, 售后, 账户, 技术支持, 建议反馈, 预约服务, 其他]
  - intent_level2 (string): 二级意图（子意图）：如产品咨询、退换货、登录问题、支付问题等
  - issue_category (string): 问题大类 [options: 产品问题, 订单问题, 支付问题, 物流问题, 账户问题, 技术问题, 服务问题, 其他]
  - issue_subcategory (string): 问题子类（具体问题类型）
  - issue_description (string): 问题详细描述
  - customer_name (string): 客户姓名
  - customer_id (string): 客户ID或会员号
  - customer_level (string): 客户等级 [options: 普通, VIP, 黄金, 钻石, 未知]
  - contact_phone (string): 联系电话
  - contact_email (string): 联系邮箱
  - preferred_contact_method (string): 首选联系方式 [options: 电话, 短信, 邮件, 微信, APP推送, 其他]
  - preferred_contact_time (string): 首选联系时间
  - order_number (string): 订单号
  - product_name (string): 产品名称
  - product_model (string): 产品型号
  - purchase_date (string): 购买日期
  - resolution_status (string): 解决状态 [options: 未解决, 处理中, 待回复, 已解决, 需升级, 已转接]
  - solution_provided (string): 提供的解决方案
  - follow_up_action (string): 后续跟进行动
  - estimated_resolution_time (string): 预计解决时间
  - urgency (string): 紧急程度 [options: 低, 中, 高, 紧急]
  - priority (string): 处理优先级 [options: P1-最高, P2-高, P3-中, P4-低]
  - escalation_needed (string): 是否需要升级 [options: 是, 否, 待定]
  - satisfaction (string): 客户满意度 [options: 非常满意, 满意, 一般, 不满意, 非常不满意, 未知]
  - service_quality (string): 服务质量评价
  - agent_name (string): 客服代表姓名
  - complaint_reason (string): 投诉原因（如果是投诉）
  - reference_number (string): 工单号或参考号
  - notes (string): 备注或其他重要信息

重要要求：你必须始终为每个用户输入输出一个函数调用。
不要只用自然语言回复 - 你必须包含 <function_call> 标签。


必需的输出格式 - 你必须严格遵循以下格式：

步骤1：以这个精确格式输出函数调用（函数名需要带引号）：
   <function_call name="function_name">
   {"param1": "value1", "param2": "value2"}
   </function_call>

步骤2：然后，向用户提供自然语言响应

正确输出示例：
   <function_call name="insurance">
   {"intent_level1": "咨询"}
   </function_call>
   好的，我理解您想咨询保险。请问您对哪方面的保险感兴趣？


示例（你必须遵循此格式）：
   <function_call name="callcenter">
   {"intent_level1": "咨询", "issue_type": "产品咨询"}
   </function_call>
   好的，我理解您想咨询产品相关问题。请问具体是哪个产品呢？


多轮示例（始终包含 <function_call> 标签）：
   第1轮 用户：我的订单有问题
   第1轮 助手：
   <function_call name="callcenter">
   {"intent_level1": "投诉", "issue_type": "订单问题"}
   </function_call>
   非常抱歉给您带来不便。请问您的订单号是多少？
   
   第2轮 用户：订单号是12345
   第2轮 助手：
   <function_call name="callcenter">
   {"intent_level1": "投诉", "issue_type": "订单问题", "order_number": "12345"}
   </function_call>
   好的，我已经查到您的订单12345。让我为您查看一下具体问题。


每轮对话的关键指令：
- 你必须在每个响应中包含 <function_call> 标签
- 包含之前所有轮次的参数，加上任何新的或更新的参数
- 即使没有提取到新参数，仍然要输出包含现有参数的函数调用
- 格式：<function_call name="domain_name">{"param": "value"}</function_call>
- 然后在函数调用标签后添加你的自然语言响应
```

**`[USER]`**

```
我我说的不是这个你帮我你帮我看一下那个七月二十三号七月二十三号我没有借款为什么有一笔借款。
```

**`[ASSISTANT]`**

```
诶是这样的哈，因为公司嘛也是考虑到现在是用钱的高峰期嘛，那目前给到您的这个两万一千九百的额度呢还没有开始使用，所以今天专门来电话呢也是重新帮您确认一下账户的这个额度和利息的问题的，明白吧，先生？
```

**`[USER]`**

```
对还有一个。
```

**`[ASSISTANT]`**

```
啊您说您没有借款，怎么会有这笔借款呢？
```

**`[USER]`**

```
嗯啊。
```

**`[ASSISTANT]`**

```
嗯您稍等哈，我这边儿马上帮您查询一下，您稍等。
```

**`[USER]`**

```
三号和八七号。
```

**`[ASSISTANT]`**

```
我这边儿马上帮您查询一下，您稍等。
```

**`[USER]`**

```
七月二十三号。
```

**`[ASSISTANT]`**

```
抱歉哈，没听清楚，您能再讲一遍吗？
```

**`[USER]`**

```
五月份有呀我是说七月份。
```

**`[ASSISTANT]`**

```
对呀，就是您在二五年五月份的时候有去借款，对吧？
```

**`[USER]`**

```
这这个有什么问题吗。
```

**`[ASSISTANT]`**

```
哦是这样的先生，因为您这边就是您上一次借款的话，是在二五年五月份嘛，然后您当时借款了六百块钱，然后您这边就是还款的时候嘛，就是逾期了几天的样子，对吧？
```

**`[USER]`**

```
嗯这现在因为现在我不敢用了因为这个上面不对了你这个安逸花上面。
```

**`[ASSISTANT]`**

```
诶是这样的哈，因为公司嘛也是考虑到现在是用钱的高峰期嘛，那目前给到您的这个两万一千九百的额度呢还没有开始使用，所以今天专门来电话呢也是重新帮您确认一下账户的这个额度和利息的问题的，明白吧，先生？
```

**`[USER]`**

```
不是用不了是我没有借款你这个上面。
```

**`[ASSISTANT]`**

```
哦您是说现在用不了了吗，先生？
```

**`[USER]`**

```

```

**`[ASSISTANT]`**

```
哦您说您没有借款，怎么会有这笔借款呢？
```

**`[USER]`**

```
对一万四千四还有一个八月一号。
```

**📤 输出**

> ⚠️ **LLM 未配置或调用失败**：LLM_NOT_CONFIGURED：请配置 .env 文件后重新运行
> （回复占位）：（LLM 未配置，无法生成回复）

**✅ 本轮 function_call（DST 结果）**：

> _（无 function_call）_

**✅ 本轮自然语言回复**：（LLM 未配置，无法生成回复）

**📊 本轮累积对话状态（Cumulative State）**：

```json
{}
```

---

## 五、结果对比与分析

| | 内容 |
|---|---|
| 👤 **用户输入** | 对一万四千四还有一个八月一号。 |
| 🤖 **FnCTOD 生成回复** | （LLM 未配置，无法生成回复） |
| 📝 **实际坐席回复** | 那我这边就先不打扰您了，祝您生活愉快，也邀请您多登录安逸花APP看看，APP会不定期上线各种优惠活动，给您更多借款优惠，再见！ |
| 🏷️ **人工校验标签** | `不当告别` |

### 提取的对话状态（DST 结果）

```json
{}
```

### 算法价值说明

- **Stage 1（域选择）** 的价值：在多业务域场景下，自动聚焦到与当前对话相关的域，
  减少无关参数噪声，提升 Stage 2 的提取精度。

- **Stage 2（函数调用）** 的价值：将对话状态追踪（DST）建模为函数调用，
  输出**结构化** `<function_call>` 格式，同时在同一次 LLM 调用中生成自然语言回复，
  相比传统 DST 更易于扩展到新域（只需增加函数定义，无需重新训练）。

- **累积状态（Cumulative State）** 的价值：FnCTOD 在多轮对话中
  持续累积已提取的槽位值，形成完整的会话状态，
  供下游系统（CRM 写入、工单生成等）直接使用。

---

_本报告由 `examples/fnctod_trace_demo.py` 自动生成。_
