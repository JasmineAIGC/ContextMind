# 场景清理总结

## 概述

按照项目要求，清理了多余的场景配置，现在只保留三个核心场景：
- **chat**（闲聊）
- **callcenter**（客服）
- **insurance**（保险挽回）

---

## 清理内容

### 删除的场景

从 `prompts.py` 中删除了以下场景的系统提示词：

1. **tech_support**（技术支持）
   - 删除了 `TECH_SUPPORT_PROMPT` 常量
   - 从 `PROMPT_MAP` 中移除
   - 从 `__all__` 导出列表中移除

2. **education**（教育辅导）
   - 删除了 `EDUCATION_PROMPT` 常量
   - 从 `PROMPT_MAP` 中移除
   - 从 `__all__` 导出列表中移除

### 保留的内容

#### 三个核心场景

1. **chat（闲聊场景）**
   - 提示词：`CHAT_SYSTEM_PROMPT`
   - 应用：`apps/chat_app.py`
   - 配置：`scenarios/chat_scenario.py`
   - 特点：友好智能的AI助手，自然交流

2. **callcenter（客服场景）**
   - 提示词：`CALLCENTER_SYSTEM_PROMPT`
   - 应用：`apps/callcenter_app.py`
   - 配置：`scenarios/callcenter_scenario.py`
   - 特点：专业客服，快速解决问题

3. **insurance（保险挽回场景）**
   - 提示词：`INSURANCE_SYSTEM_PROMPT`
   - 应用：`apps/insurance_app.py`
   - 配置：`scenarios/insurance_scenario.py`
   - 特点：共荣保险专业顾问，团体癌症保险

#### DST 提示词（内部使用）

- `DST_SYSTEM_PROMPT` 保留
- **用途**：供 DST 模式内部使用（对话状态追踪）
- **不作为独立场景**：不在 `PROMPT_MAP` 中，不对外暴露

---

## 代码变更

### prompts.py

**删除的代码**（约 60 行）：
```python
# 删除了 TECH_SUPPORT_PROMPT 定义
# 删除了 EDUCATION_PROMPT 定义
```

**更新的配置**：
```python
# 场景映射字典（三个核心场景）
PROMPT_MAP = {
    "chat": CHAT_SYSTEM_PROMPT,
    "callcenter": CALLCENTER_SYSTEM_PROMPT,
    "insurance": INSURANCE_SYSTEM_PROMPT,
}

# 导出配置（三个核心场景 + DST 内部使用）
__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "CALLCENTER_SYSTEM_PROMPT",
    "INSURANCE_SYSTEM_PROMPT",
    "DST_SYSTEM_PROMPT",  # 保留供 DST 模式内部使用
    "PROMPT_MAP",
    "DEFAULT_PROMPT",
    "get_prompt",
]
```

**更新的文档**：
```python
"""
支持场景：
- chat: 闲聊场景
- callcenter: 客服场景
- insurance: 保险挽回场景

DST 提示词保留供内部使用（对话状态追踪）
"""

def get_prompt(scenario: str = "chat") -> str:
    """
    获取指定场景的系统提示词
    
    Args:
        scenario: 场景名称，可选值：chat, callcenter, insurance
        
    Returns:
        对应场景的系统提示词
    """
```

### scenarios/config.py

**ScenarioType 枚举**（已经正确）：
```python
class ScenarioType(Enum):
    """场景类型枚举"""
    CHAT = "chat"  # 闲聊场景
    CALLCENTER = "callcenter"  # 客服场景
    INSURANCE = "insurance"  # 保险挽回场景
```

---

## 目录结构

### scenarios/ 目录

```
scenarios/
├── __init__.py
├── config.py               # 场景配置基类和枚举
├── chat_scenario.py        # ✅ 闲聊场景
├── callcenter_scenario.py  # ✅ 客服场景
└── insurance_scenario.py   # ✅ 保险挽回场景
```

### apps/ 目录

```
apps/
├── chat_app.py          # ✅ 闲聊应用
├── callcenter_app.py    # ✅ 客服应用
├── insurance_app.py     # ✅ 保险挽回应用
└── plugin_examples.py   # 插件示例
```

---

## 验证结果

### 1. prompts.py 测试

```python
✅ prompts module imported successfully
Available prompts: ['chat', 'callcenter', 'insurance']
✅ chat: 306 characters
✅ callcenter: 358 characters
✅ insurance: 756 characters
✅ DST_SYSTEM_PROMPT available: True (内部使用)
✅ tech_support correctly removed from PROMPT_MAP
✅ education correctly removed from PROMPT_MAP
```

### 2. scenarios 测试

```python
Testing scenario imports...
✅ Chat scenario: 闲聊
✅ Callcenter scenario: 客服
✅ Insurance scenario: 保险挽回

ScenarioType enum values:
  - chat
  - callcenter
  - insurance

✅ Correct: 3 scenarios
```

### 3. 应用模块测试

```python
✅ ChatApplication
✅ CallCenterApplication
✅ InsuranceApplication
```

---

## 使用示例

### 获取场景提示词

```python
from prompts import get_prompt

# 获取闲聊场景提示词
chat_prompt = get_prompt("chat")

# 获取客服场景提示词
callcenter_prompt = get_prompt("callcenter")

# 获取保险场景提示词
insurance_prompt = get_prompt("insurance")
```

### 创建场景配置

```python
from scenarios import get_chat_scenario, get_callcenter_scenario, get_insurance_scenario

# 创建闲聊场景
chat_scenario = get_chat_scenario()

# 创建客服场景
callcenter_scenario = get_callcenter_scenario()

# 创建保险场景
insurance_scenario = get_insurance_scenario()
```

### 创建应用

```python
from apps.chat_app import ChatApplication
from apps.callcenter_app import CallCenterApplication
from apps.insurance_app import InsuranceApplication

# 创建闲聊应用
chat_app = ChatApplication(context_engine=engine)

# 创建客服应用
callcenter_app = CallCenterApplication(context_engine=engine)

# 创建保险应用
insurance_app = InsuranceApplication(context_engine=engine)
```

---

## 总结

### 清理成果

- ✅ 删除了 2 个不需要的场景提示词
- ✅ 更新了配置和文档
- ✅ 保留了 3 个核心场景
- ✅ 保留了 DST 提示词供内部使用
- ✅ 所有测试通过

### 当前状态

**三个核心场景**：
1. **chat**（闲聊） - 友好智能的AI助手
2. **callcenter**（客服） - 专业客服支持
3. **insurance**（保险挽回） - 共荣保险顾问

**文件结构清晰**：
- scenarios/ 目录：3 个场景文件
- apps/ 目录：3 个应用文件
- prompts.py：3 个场景提示词 + DST 内部提示词

### 版本信息

- **版本**：v0.4.1
- **状态**：✅ 场景清理完成
- **核心场景数**：3 个（chat, callcenter, insurance）

---

**文档创建时间**：2026-02-03  
**最后更新**：v0.4.1
