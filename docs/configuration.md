# Evolution 配置指南

本指南介绍如何配置 Evolution 系统，包括 API 密钥设置和场景配置。

---

## API 密钥配置

### 问题说明

如果您在运行 Demo 时看到以下错误：

```
❌ 错误: 缺少 API key。请在 .env 文件中设置以下变量之一: QWEN3_API_KEY, LLM_API_KEY, OPENAI_API_KEY 等
```

这表示您需要配置 LLM API 密钥。

### 快速配置步骤

#### 步骤1：创建 .env 文件

在项目根目录创建 `.env` 文件：

```bash
cd /path/to/Evolution
touch .env
```

#### 步骤2：添加 API 配置

编辑 `.env` 文件，添加以下内容（选择一个配置即可）：

**选项1：使用 Qwen3 配置**
```bash
QWEN3_API_KEY=sk-your-api-key-here
QWEN3_BASE_URL=http://your-api-endpoint/v1
QWEN3_MODEL=Qwen3-32B
```

**选项2：使用通用 LLM 配置**
```bash
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=http://your-api-endpoint/v1
LLM_MODEL=Qwen3-32B
```

**选项3：使用 OpenAI 配置**
```bash
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=http://your-api-endpoint/v1
OPENAI_MODEL=gpt-4
```

#### 步骤3：重新运行

```bash
python interactive_demo.py
# 或
python gradio_demo.py
```

### 支持的环境变量

系统会按以下顺序查找环境变量：

| 变量名 | 用途 | 示例 |
|--------|------|------|
| QWEN3_API_KEY | API 密钥 | sk-xxx |
| QWEN3_BASE_URL | API 端点 | http://host:port/v1 |
| QWEN3_MODEL | 模型名称 | Qwen3-32B |
| LLM_API_KEY | API 密钥（通用） | sk-xxx |
| LLM_BASE_URL | API 端点（通用） | http://host:port/v1 |
| LLM_MODEL | 模型名称（通用） | Qwen3-32B |
| OPENAI_API_KEY | OpenAI 密钥 | sk-xxx |
| OPENAI_BASE_URL | OpenAI 端点 | https://api.openai.com/v1 |
| OPENAI_MODEL | OpenAI 模型 | gpt-4 |

### 配置示例

#### 示例1：本地 Qwen3 服务

```bash
# .env 文件内容
QWEN3_API_KEY=sk-7e7c8b9ad0e1f2a3b4c5
QWEN3_BASE_URL=http://10.112.172.30:18019/v1
QWEN3_MODEL=Qwen3-32B
```

#### 示例2：OpenAI 服务

```bash
# .env 文件内容
OPENAI_API_KEY=sk-your-openai-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4
```

#### 示例3：其他兼容服务

```bash
# .env 文件内容
LLM_API_KEY=your-api-key
LLM_BASE_URL=http://your-service:port/v1
LLM_MODEL=your-model-name
```

### 常见问题

**Q: .env 文件放在哪里？**  
A: 放在项目根目录，与 `interactive_demo.py` 和 `gradio_demo.py` 同级。

**Q: 是否需要所有环境变量？**  
A: 不需要。只需要配置一组即可（如 QWEN3_* 或 LLM_* 或 OPENAI_*）。

**Q: 配置后仍然报错？**  
A: 请检查：
1. .env 文件是否在正确位置
2. API 密钥是否正确
3. API 端点是否可访问
4. 是否安装了 openai 包：`pip install openai`

**Q: 如何验证配置？**  
A: 运行 Demo，如果看到以下日志表示成功：

```
[2026-02-02 09:14:36] INFO - [LLM Client] 正在初始化，model: Qwen3-32B
[2026-02-02 09:14:36] INFO - [LLM Client] 初始化成功
```

### 安全提示

⚠️ **注意：**
- 不要将 `.env` 文件提交到 Git 仓库
- `.env` 已在 `.gitignore` 中，确保不会意外提交
- 不要在代码中硬编码 API 密钥

---

## 场景配置

### 概述

Evolution 支持多种对话场景的灵活配置，每个场景都有独特的意图体系和槽位定义。

### 支持的场景

#### 1. 闲聊场景 (Chat)

**特点：**
- 动态槽位提取
- 开放式意图识别
- 轻松自然的对话风格

**使用：**
```python
from scenarios import get_chat_scenario
config = get_chat_scenario()
```

#### 2. 客服场景 (CallCenter)

**特点：**
- 问题追踪
- 工单管理
- 专业服务导向

**使用：**
```python
from scenarios import get_callcenter_scenario
config = get_callcenter_scenario()
```

#### 3. 保险挽回场景 (Insurance)

**特点：**
- 双层意图体系（7个一级 + 34个二级）
- 18个预定义槽位
- 销售导向的对话策略

**使用：**
```python
from scenarios import get_insurance_scenario
config = get_insurance_scenario()
```

### 场景配置结构

每个场景配置包含：

```python
class ScenarioConfig:
    scenario_name: str          # 场景名称
    scenario_type: ScenarioType # 场景类型枚举
    description: str            # 场景描述
    
    # DST 配置
    dst_intents: Dict           # 预定义意图
    dst_slots: Dict             # 预定义槽位
    dst_categorical_slots: Dict # 分类槽位
    enable_dynamic_slots: bool  # 是否启用动态槽位提取
    
    # 提示词
    system_prompt: str          # 系统提示词
    
    # Evolution 配置
    enable_memory: bool         # 启用记忆
    enable_evolution: bool      # 启用进化
    
    # UI 配置
    ui_title: str              # 界面标题
    ui_description: str        # 界面描述
```

### 场景对比

| 特性 | 闲聊 | 客服 | 保险 |
|------|------|------|------|
| 意图提取 | LLM 动态 | 预定义+LLM | 预定义 |
| 槽位数量 | 动态 | 12个 | 18个 |
| 分类槽位 | 无 | 4个 | 8个 |
| 意图层级 | 单层 | 单层 | 双层 |
| 记忆功能 | 是 | 是 | 是 |
| 进化功能 | 是 | 是 | 是 |

### 最佳实践

1. **预定义 vs 动态**
   - 对于规范化场景（如保险、客服），使用预定义意图和槽位
   - 对于开放场景（如闲聊），使用动态 LLM 提取

2. **分类槽位**
   - 为有限枚举值的槽位定义分类约束
   - 提高识别准确性和一致性

3. **双层意图**
   - 复杂场景使用一级+二级意图体系
   - 一级意图分大类，二级意图细化

4. **配置优先**
   - 将场景特定逻辑放在配置中
   - 保持框架代码的通用性

---

## 获取帮助

如果仍有问题，请：
1. 查看日志文件：`logs/evolution_*.log`
2. 提供完整的错误信息
3. 检查网络连接和 API 端点状态
