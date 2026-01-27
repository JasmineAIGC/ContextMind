# ContextMind 示例

本目录包含 ContextMind v7.2 的示例代码。

## 文件

所有演示文件位于 `demos/` 目录中，采用**扁平结构**（无子目录）：

- **plugin_examples.py** - 演示自定义插件注册和使用
- **callcenter_app.py** - 呼叫中心客户服务应用模板
- **chat_app.py** - 通用聊天应用模板

## 根目录演示文件

四个主要演示文件位于**仓库根目录**以便于访问：

- **interactive_demo.py** - 用于测试上下文工程的交互式命令行演示
- **gradio_demo.py** - 使用 Gradio 的 Web UI 演示
- **chat_interactive_demo.py** - 交互式聊天模式演示
- **chat_gradio_demo.py** - 带 Gradio Web UI 的聊天模式

## 用法

每个演示都是独立的，可以直接运行：

```bash
# 根目录演示（在仓库根目录中）
python interactive_demo.py
python gradio_demo.py
python chat_interactive_demo.py
python chat_gradio_demo.py

# 示例代码（在 demos/ 目录中）
python demos/plugin_examples.py
python demos/callcenter_app.py
python demos/chat_app.py
```

## v7.2 架构

所有演示都使用清晰的 v7.2 ContextMind 架构：
- 纯上下文工程框架（步骤 1-4 + 6）
- 大语言模型调用（步骤 5）由用户代码在外部处理
- 所有组件的模块化插件系统（提取器、检索器、更新器）
- 扁平目录结构 - 无不必要的嵌套
