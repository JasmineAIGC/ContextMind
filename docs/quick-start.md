# Evolution v0.4.0 快速开始指南

## 1. 配置API密钥

创建 `.env` 文件：

```bash
# 选择以下配置方式之一

# 方式1：Qwen3配置（推荐）
QWEN3_API_KEY=sk-your-api-key-here
QWEN3_BASE_URL=http://10.112.172.30:18019/v1
QWEN3_MODEL=Qwen3-32B

# 方式2：通用LLM配置
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=http://10.112.172.30:18019/v1
LLM_MODEL=Qwen3-32B
```

## 2. 启动Interactive Demo

### 基础使用
```bash
python interactive_demo.py
```

### 完整配置
```bash
python interactive_demo.py \
  --scenario insurance \
  --mode dst \
  --log-level INFO \
  --max-history-turns 15
```

### 所有参数
- `--scenario`: chat | callcenter | insurance
- `--mode`: dst | evolution
- `--log-level`: DEBUG | INFO | WARNING | ERROR
- `--max-history-turns`: 数字（默认10）
- `--enable-summary` / `--no-summary`
- `--use-llm-summary`

## 3. 启动Gradio Demo

### 基础使用
```bash
python gradio_demo.py
```

### 完整配置
```bash
python gradio_demo.py \
  --log-level INFO \
  --max-history-turns 15 \
  --port 7860
```

### 创建公共链接
```bash
python gradio_demo.py --share
```

### 所有参数
- `--log-level`: DEBUG | INFO | WARNING | ERROR
- `--max-history-turns`: 数字（默认10）
- `--port`: 端口号（默认7860）
- `--share`: 创建公共分享链接

## 4. 常见问题

### 缺少API密钥
**错误：** `ValueError: 缺少 API key`

**解决：** 创建 `.env` 文件并配置API密钥（见上文）

### Gradio版本问题
**错误：** `unexpected keyword argument`

**解决：** 更新Gradio `pip install --upgrade gradio`

### 端口被占用
**错误：** `Address already in use`

**解决：** 使用其他端口 `python gradio_demo.py --port 8080`

## 5. 查看帮助

```bash
python interactive_demo.py --help
python gradio_demo.py --help
```
