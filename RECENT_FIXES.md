# 最近修复的问题 (v0.4.0)

## 修复日期: 2026-02-02

### 1. ✅ process_turn参数错误

**问题：**
```
TypeError: DialogueStateTracker.process_turn() got an unexpected keyword argument 'agent_message'
```

**原因：** 参数名错误

**修复：** 使用正确的参数名 `system_utterance` 和 `user_utterance`

### 2. ✅ Gradio 6.0消息格式错误

**问题：**
```
gradio.exceptions.Error: "Data incompatible with messages format..."
```

**原因：** 返回元组格式而非字典格式

**修复：** 所有返回改为字典格式：
```python
[
    {"role": "user", "content": "消息"},
    {"role": "assistant", "content": "回复"}
]
```

### 3. ✅ UI布局说明

**UI已经是左右布局：**
- 左侧70%：对话框
- 右侧30%：配置面板

**如果看到上下布局：**
1. 清除浏览器缓存（Ctrl+Shift+R）
2. 检查屏幕宽度（太窄会自动切换为垂直布局）

## 运行程序

```bash
python gradio_demo.py
# 访问 http://localhost:7860
```

## 相关提交

- 1283b06: Fix process_turn arguments and Gradio 6.0 message format
- 1f25276: Fix missing logging import in interactive_demo.py  
- 85a1821: Fix .env file loading - add load_dotenv()
