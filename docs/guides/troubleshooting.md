# 故障排查指南

本文档帮助您解决使用 ContextMind 时可能遇到的常见问题。

## 安装问题

### 依赖安装失败

**问题**: `pip install -r requirements.txt` 失败

**解决方案**:

1. 确保 Python 版本 >= 3.8
   ```bash
   python --version
   ```

2. 升级 pip
   ```bash
   pip install --upgrade pip
   ```

3. 尝试单独安装失败的包
   ```bash
   pip install package_name
   ```

4. 使用国内镜像源
   ```bash
   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

### 包安装后无法导入

**问题**: `ModuleNotFoundError: No module named 'contextmind'`

**解决方案**:

1. 确认在项目根目录执行
   ```bash
   cd /path/to/ContextMind
   ```

2. 以可编辑模式安装
   ```bash
   pip install -e .
   ```

3. 检查 Python 路径
   ```python
   import sys
   print(sys.path)
   ```

---

## 配置问题

### API Key 未生效

**问题**: 出现认证错误

**解决方案**:

1. 检查 `.env` 文件是否在项目根目录
   ```bash
   ls -la .env
   ```

2. 确认环境变量格式正确
   ```bash
   QWEN3_API_KEY=sk-xxxxxxxxxxxxx
   QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
   QWEN3_MODEL=qwen-plus
   ```

3. 重新加载环境变量
   ```python
   from dotenv import load_dotenv
   load_dotenv(override=True)
   ```

4. 检查是否正确加载
   ```python
   import os
   print(os.getenv('QWEN3_API_KEY'))
   ```

### 场景配置加载失败

**问题**: `ValueError: 场景未注册`

**解决方案**:

1. 检查 `scenarios.yaml` 文件
   ```bash
   cat contextmind/config/scenarios.yaml
   ```

2. 验证场景名称拼写
   ```python
   from contextmind.scenarios.registry import scenario_registry
   print(scenario_registry.list_scenarios())
   ```

3. 确认场景已注册
   ```python
   # 应返回 ['chat', 'callcenter', 'insurance']
   ```

---

## 运行问题

### 示例程序无法启动

**问题**: 运行 demo 时报错

**解决方案**:

1. 确认使用正确的路径
   ```bash
   # 正确
   python examples/step3_cli_demo.py --scenario chat --mode dst
   
   # 错误（旧路径）
   python interactive_demo.py
   ```

2. 检查参数是否正确
   ```bash
   python examples/step3_cli_demo.py --help
   ```

3. 验证场景和模式组合
   ```bash
   # 支持的组合
   --scenario chat --mode evolve
   --scenario callcenter --mode dst
   --scenario insurance --mode fnctod
   ```

### Web 界面无法访问

**问题**: `http://localhost:7860` 无法打开

**解决方案**:

1. 检查端口是否被占用
   ```bash
   lsof -i :7860
   ```

2. 更改端口
   ```bash
   # 在 step3_web_demo.py 中修改
   demo.launch(server_port=8080)
   ```

3. 检查防火墙设置
   ```bash
   # Linux
   sudo ufw allow 7860
   ```

4. 查看控制台错误信息

---

## 模式特定问题

### DST 模式问题

**问题**: 槽位提取不准确

**解决方案**:

1. 检查槽位定义
   ```python
   config = get_callcenter_scenario()
   print(config.dst_slots)
   ```

2. 优化提示词
   ```python
   # 在场景配置中调整 system_prompt
   ```

3. 增加对话历史
   ```python
   tracker = DialogueStateTracker.from_scenario(
       llm_client=llm_client,
       scenario_config=config
   )
   # 多轮对话会累积上下文
   ```

### FnCTOD 模式问题

**问题**: 未检测到 function call

**解决方案**:

1. 检查提示词模板
   ```bash
   cat contextmind/modes/fnctod/fnctod_prompts.yaml
   ```

2. 验证 Schema 定义
   ```python
   from contextmind.scenarios.registry import scenario_registry
   schema = scenario_registry.get_schema("insurance")
   print(schema)
   ```

3. 启用详细日志
   ```python
   from contextmind.infra.logger import get_logger
   logger = get_logger(__name__)
   logger.setLevel("DEBUG")
   ```

### Evolve 模式问题

**问题**: 记忆功能未生效

**解决方案**:

1. 确认已启用记忆
   ```python
   engine = EvolveEngine(
       enable_memory=True,  # 必须设置
       memory_limit=50
   )
   ```

2. 检查记忆库
   ```python
   # 查看当前记忆
   memories = engine.session_manager.get_all_memories()
   print(f"记忆数量: {len(memories)}")
   ```

3. 验证嵌入功能
   ```python
   from contextmind.infra.embedding import calculate_embedding_similarity
   # 测试嵌入计算
   ```

---

## 性能问题

### 响应速度慢

**问题**: LLM 响应时间过长

**解决方案**:

1. 检查网络连接
   ```bash
   ping api.openai.com
   ```

2. 减少上下文长度
   ```python
   # DST: 限制历史轮数
   tracker.max_history_turns = 5
   
   # Evolve: 压缩上下文
   engine.enable_compression = True
   ```

3. 使用更快的模型
   ```bash
   QWEN3_MODEL=qwen-turbo  # 而不是 qwen-plus
   ```

4. 启用缓存（如果支持）

### 内存占用过高

**问题**: 程序占用内存过多

**解决方案**:

1. 限制记忆库大小
   ```python
   engine = EvolveEngine(
       memory_limit=20,  # 减少限制
       enable_evolution=False  # 暂时禁用进化
   )
   ```

2. 定期清理会话
   ```python
   engine.reset_session()
   ```

3. 监控内存使用
   ```python
   import psutil
   process = psutil.Process()
   print(f"内存使用: {process.memory_info().rss / 1024 / 1024} MB")
   ```

---

## 日志和调试

### 启用详细日志

```python
from contextmind.infra.logger import get_logger
import logging

# 设置日志级别
logger = get_logger(__name__)
logger.setLevel(logging.DEBUG)

# 查看所有日志
import contextmind.infra.logger as logger_module
logger_module.setup_logger(level=logging.DEBUG)
```

### 查看日志文件

```bash
# 日志文件位置
tail -f logs/contextmind.log
```

### 调试特定模块

```python
# 只调试 DST 模式
from contextmind.modes.dst import dialogue_state_tracker
import logging
logging.getLogger('contextmind.modes.dst').setLevel(logging.DEBUG)
```

---

## 常见错误信息

### `ImportError: cannot import name 'XXX'`

**原因**: 导入路径错误或模块不存在

**解决**: 检查导入路径是否正确，参考 [API 参考](../reference/api-reference.md)

### `KeyError: 'scenario_name'`

**原因**: 场景配置缺少必要字段

**解决**: 检查场景配置文件的完整性

### `RuntimeError: Event loop is closed`

**原因**: 异步调用问题

**解决**: 使用 `asyncio.run()` 或确保在正确的事件循环中

```python
import asyncio

async def main():
    result = await tracker.process_turn("你好")
    return result

# 正确方式
result = asyncio.run(main())
```

---

## 获取帮助

如果以上方法都无法解决您的问题：

1. 查看 [FAQ](https://github.com/JasmineAIGC/ContextMind/wiki/FAQ)
2. 搜索 [Issues](https://github.com/JasmineAIGC/ContextMind/issues)
3. 创建新的 Issue，提供：
   - Python 版本
   - ContextMind 版本
   - 完整错误堆栈
   - 最小可复现代码
   - 预期行为 vs 实际行为

## 版本兼容性

| ContextMind | Python | 主要依赖 |
|-------------|--------|---------|
| 0.2.x       | 3.8+   | PyYAML >= 6.0 |
| 0.1.x       | 3.8+   | - |

---

## 相关文档

- [快速开始](quick-start.md)
- [配置指南](configuration.md)
- [API 参考](../reference/api-reference.md)
