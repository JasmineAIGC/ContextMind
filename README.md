# ContextMind

基于 ADK 的上下文工程框架，提供多轮对话的短期记忆（Session）和长期记忆（Memory）管理。


## 快速开始

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 运行交互式演示：
   ```bash
   python interactive_demo.py
   ```

3. 或运行网页演示：
   ```bash
   python gradio_demo.py
   ```

## 项目结构

```
ContextMind/
├── contextmind/        # 核心代码目录
│   ├── client.py       # 客户端实现
│   ├── engine.py       # 上下文引擎
│   └── logger.py       # 日志功能
├── data/               # 示例数据
├── interactive_demo.py # 命令行演示
├── gradio_demo.py      # 网页演示
└── requirements.txt    # 项目依赖
```