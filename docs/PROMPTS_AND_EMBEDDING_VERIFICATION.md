# prompts.py 和 Embedding 配置验证报告

## 概述

本文档记录了对 `prompts.py` 文件状态和 Embedding 配置的检查和验证结果。

---

## 1. prompts.py 状态

### 结论：**需要保留** ✅

### 使用情况

`prompts.py` 是一个**必要文件**，被多个模块依赖：

**应用层引用**：
- `apps/chat_app.py` - 引用 `CHAT_SYSTEM_PROMPT`
- `apps/callcenter_app.py` - 引用 `CALLCENTER_SYSTEM_PROMPT`
- `apps/insurance_app.py` - 引用 `INSURANCE_SYSTEM_PROMPT`

**场景配置引用**：
- `scenarios/chat_scenario.py` - 引用 `CHAT_SYSTEM_PROMPT`
- `scenarios/callcenter_scenario.py` - 引用 `CALLCENTER_SYSTEM_PROMPT`

### 功能

提供集中化的系统提示词管理，支持以下场景：

| 场景 | 常量名 | 用途 |
|------|--------|------|
| chat | `CHAT_SYSTEM_PROMPT` | 闲聊场景 |
| callcenter | `CALLCENTER_SYSTEM_PROMPT` | 客服场景 |
| dst | `DST_SYSTEM_PROMPT` | 对话状态追踪 |
| tech_support | `TECH_SUPPORT_PROMPT` | 技术支持 |
| education | `EDUCATION_PROMPT` | 教育辅导 |
| insurance | `INSURANCE_SYSTEM_PROMPT` | 保险挽回 |

### 已完成的更新

- ✅ 版本号更新：v0.4.0 → v0.4.1
- ✅ 完善文档字符串，列出所有支持场景
- ✅ 保持向后兼容

---

## 2. Embedding 配置验证

### 结论：**配置正确** ✅

### 核心原则

**Embedding 提取默认使用 `.env` 中配置的 `EMBEDDING_MODEL`，而不是 LLM。**

### 配置优先级（已验证）

代码 (`utils/embedding.py`) 按以下顺序检查配置：

1. **本地模型路径**（最高优先级）
   ```ini
   EMBEDDING_MODEL_PATH=/path/to/model
   EMBEDDING_MODEL=bge-large-zh-v1.5
   ```
   - 使用 `sentence-transformers` 直接加载本地模型
   - 速度快，不需要网络请求
   - **当前 .env 使用此方式** ✅

2. **API 调用**
   ```ini
   EMBEDDING_MODEL=bge-large-zh-v1.5
   EMBEDDING_BASE_URL=http://localhost:8001/v1
   EMBEDDING_API_KEY=your-key  # 可选
   ```
   - 通过 API 调用 embedding 服务（如 vLLM）
   - 支持远程部署

3. **LLM 回退**（向后兼容）
   - 当没有配置专门的 embedding 模型时
   - 尝试使用 LLM 模型（QWEN3_MODEL 等）
   - 记录警告日志

### 当前 .env 配置

```ini
# LLM 配置
QWEN3_API_KEY=sk-7e7c8b9ad0e1f2a3b4c5
QWEN3_BASE_URL=http://10.112.172.30:18023/v1
QWEN3_MODEL=Qwen2.5-7B-Instruct

# Embedding 配置（独立于 LLM）
EMBEDDING_MODEL_PATH=/share/airesearch/data/aowen.xiao/models/BAAI/bge-large-zh-v1.5
EMBEDDING_MODEL=bge-large-zh-v1.5
```

**关键点**：
- ✅ LLM 使用 `Qwen2.5-7B-Instruct`
- ✅ Embedding 使用 `bge-large-zh-v1.5`（独立模型）
- ✅ 两者完全分离，互不干扰

### 验证测试结果

```python
=== Final Verification ===
✅ Embedding uses dedicated model: bge-large-zh-v1.5
✅ Using local model path: True
✅ Model path: /share/airesearch/data/aowen.xiao/models/BAAI/bge-large-zh-v1.5
✅ NOT using LLM model for embedding

Configuration matches .env file:
  EMBEDDING_MODEL: bge-large-zh-v1.5
  EMBEDDING_MODEL_PATH: /share/airesearch/data/aowen.xiao/models/BAAI/bge-large-zh-v1.5

🎉 Embedding configuration is CORRECT!
   Embedding uses EMBEDDING_MODEL, not LLM!
```

### 代码逻辑验证

`utils/embedding.py` 中的 `EmbeddingConfig.from_env()` 方法：

```python
# 1. 检查本地模型路径（最高优先级）
if embedding_model_path:
    return cls(
        model=model_name,
        model_path=embedding_model_path,
        use_local=True,
    )

# 2. 检查 API 配置
if embedding_model and embedding_base_url:
    return cls(
        model=embedding_model,
        base_url=embedding_base_url,
        ...
    )

# 3. 回退到 LLM（向后兼容）
logger.info("未配置专门的 embedding 模型，将尝试使用 LLM 模型")
...
```

---

## 3. 更新的文档

### .env.example 更新

增强了 Embedding 配置的说明：

```ini
# ========================================
# Embedding 配置 (可选，用于语义检索和去重)
# ========================================
# 注意：Embedding 使用专门的 EMBEDDING_MODEL，而非 LLM
# 
# 选项 1: 使用本地 embedding 模型（推荐，速度快）
# EMBEDDING_MODEL_PATH=/path/to/your/model
# EMBEDDING_MODEL=bge-large-zh-v1.5
# 
# 选项 2: 使用 API 部署的 embedding 模型（如 vLLM）
# EMBEDDING_MODEL=bge-large-zh-v1.5
# EMBEDDING_BASE_URL=http://localhost:8001/v1
# EMBEDDING_API_KEY=your-key  # 可选
```

---

## 4. 总结

### prompts.py
- ✅ **状态**：保留（必要文件）
- ✅ **版本**：已更新为 v0.4.1
- ✅ **文档**：已完善
- ✅ **测试**：导入和功能正常

### Embedding 配置
- ✅ **配置正确**：优先使用专门的 EMBEDDING_MODEL
- ✅ **不使用 LLM**：Embedding 和 LLM 完全分离
- ✅ **优先级正确**：本地模型 > API > LLM 回退
- ✅ **文档完善**：.env.example 说明清晰
- ✅ **.env 未修改**：按要求保持不变

### 关键原则

1. **prompts.py** 是重要的场景配置文件，不能删除
2. **Embedding** 使用专门的模型（EMBEDDING_MODEL），而非 LLM
3. **配置优先级** 确保最佳性能和灵活性
4. **向后兼容** 保持系统稳定性

---

**文档版本**: v0.4.1  
**最后更新**: 2026-02-03  
**验证状态**: ✅ 全部通过
