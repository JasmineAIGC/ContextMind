# API密钥配置指南

## 问题说明

如果您在运行Demo时看到以下错误：

```
❌ 错误: 缺少 API key。请在 .env 文件中设置以下变量之一: QWEN3_API_KEY, LLM_API_KEY, OPENAI_API_KEY 等
```

这表示您需要配置LLM API密钥。

## 快速配置

### 步骤1：创建.env文件

在项目根目录创建 `.env` 文件：

```bash
cd /path/to/ContextMind
touch .env
```

### 步骤2：添加API配置

编辑 `.env` 文件，添加以下内容（选择一个配置即可）：

**选项1：使用Qwen3配置**
```bash
QWEN3_API_KEY=sk-your-api-key-here
QWEN3_BASE_URL=http://your-api-endpoint/v1
QWEN3_MODEL=Qwen3-32B
```

**选项2：使用通用LLM配置**
```bash
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=http://your-api-endpoint/v1
LLM_MODEL=Qwen3-32B
```

**选项3：使用OpenAI配置**
```bash
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=http://your-api-endpoint/v1
OPENAI_MODEL=gpt-4
```

### 步骤3：重新运行

```bash
python interactive_demo.py
# 或
python gradio_demo.py
```

## 支持的环境变量

系统会按以下顺序查找环境变量：

| 变量名 | 用途 | 示例 |
|--------|------|------|
| QWEN3_API_KEY | API密钥 | sk-xxx |
| QWEN3_BASE_URL | API端点 | http://host:port/v1 |
| QWEN3_MODEL | 模型名称 | Qwen3-32B |
| LLM_API_KEY | API密钥（通用） | sk-xxx |
| LLM_BASE_URL | API端点（通用） | http://host:port/v1 |
| LLM_MODEL | 模型名称（通用） | Qwen3-32B |
| OPENAI_API_KEY | OpenAI密钥 | sk-xxx |
| OPENAI_BASE_URL | OpenAI端点 | https://api.openai.com/v1 |
| OPENAI_MODEL | OpenAI模型 | gpt-4 |

## 完整配置示例

### 示例1：本地Qwen3服务

```bash
# .env文件内容
QWEN3_API_KEY=sk-7e7c8b9ad0e1f2a3b4c5
QWEN3_BASE_URL=http://10.112.172.30:18019/v1
QWEN3_MODEL=Qwen3-32B
```

### 示例2：OpenAI服务

```bash
# .env文件内容
OPENAI_API_KEY=sk-your-openai-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4
```

### 示例3：其他兼容服务

```bash
# .env文件内容
LLM_API_KEY=your-api-key
LLM_BASE_URL=http://your-service:port/v1
LLM_MODEL=your-model-name
```

## 常见问题

### Q: .env文件放在哪里？

A: 放在项目根目录，与 `interactive_demo.py` 和 `gradio_demo.py` 同级。

### Q: 是否需要所有环境变量？

A: 不需要。只需要配置一组即可（如 QWEN3_* 或 LLM_* 或 OPENAI_*）。

### Q: 配置后仍然报错？

A: 请检查：
1. .env文件是否在正确位置
2. API密钥是否正确
3. API端点是否可访问
4. 是否安装了openai包：`pip install openai`

### Q: 如何验证配置？

A: 运行Demo，如果看到以下日志表示成功：

```
[2026-02-02 09:14:36] INFO - [LLM Client] 正在初始化，model: Qwen3-32B
[2026-02-02 09:14:36] INFO - [LLM Client] 初始化成功
```

## 安全提示

⚠️ **注意：**
- 不要将 `.env` 文件提交到Git仓库
- `.env` 已在 `.gitignore` 中，确保不会意外提交
- 不要在代码中硬编码API密钥

## 获取帮助

如果仍有问题，请：
1. 查看日志文件：`logs/contextmind_*.log`
2. 提供完整的错误信息
3. 检查网络连接和API端点状态
