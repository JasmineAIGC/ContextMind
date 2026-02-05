# 贡献指南

感谢您对 ContextMind 项目的关注！我们欢迎任何形式的贡献。

## 如何贡献

### 报告问题

如果您发现了bug或有功能建议：

1. 在 [Issues](https://github.com/Jasmine66Bloom/ContextMind/issues) 中搜索，确认问题尚未被报告
2. 创建新的 Issue，清楚描述问题或建议
3. 提供复现步骤（对于bug）或使用场景（对于功能请求）

### 提交代码

1. **Fork 项目** 到您的账户
2. **创建分支** 用于您的修改
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **进行修改** 并遵循代码规范
4. **编写测试** 确保新功能有测试覆盖
5. **提交代码** 使用清晰的提交信息
   ```bash
   git commit -m "Add: 新功能描述"
   ```
6. **推送分支** 到您的 Fork
   ```bash
   git push origin feature/your-feature-name
   ```
7. **创建 Pull Request** 到主仓库

## 代码规范

### Python 代码风格

- 遵循 [PEP 8](https://pep8.org/) 规范
- 使用 4 空格缩进
- 最大行长度 100 字符
- 使用有意义的变量和函数名

### 命名规范

详见 [命名标准文档](docs/naming-standards.md)

- **文件名**: snake_case（如 `dialogue_state_tracker.py`）
- **类名**: PascalCase（如 `DialogueStateTracker`）
- **函数名**: snake_case（如 `process_turn`）
- **常量**: UPPER_SNAKE_CASE（如 `MAX_HISTORY_TURNS`）

### 文档规范

- 所有公开的类和函数必须有文档字符串
- 使用 Google 风格的文档字符串
- 示例：

```python
def process_turn(user_input: str) -> Dict[str, Any]:
    """
    处理单轮对话输入
    
    Args:
        user_input: 用户输入文本
        
    Returns:
        包含状态和响应的字典
        
    Raises:
        ValueError: 当输入为空时
    """
    pass
```

### 提交信息规范

使用以下前缀：

- `Add:` 添加新功能
- `Fix:` 修复bug
- `Update:` 更新现有功能
- `Refactor:` 代码重构
- `Docs:` 文档更新
- `Test:` 测试相关

示例：
```
Add: 支持自定义提示词模板
Fix: 修复DST模式下的状态重置问题
Docs: 更新快速开始指南
```

## 开发环境设置

### 安装开发依赖

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/ContextMind.git
cd ContextMind

# 安装依赖
pip install -r requirements.txt

# 安装为可编辑模式
pip install -e .
```

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试
python -m pytest tests/test_dst_mode.py

# 查看测试覆盖率
python -m pytest --cov=contextmind tests/
```

### 代码检查

```bash
# 使用 flake8 检查代码风格
flake8 contextmind/ --max-line-length=100

# 使用 mypy 进行类型检查（如果配置）
mypy contextmind/
```

## 添加新场景

如果您想添加新的对话场景：

1. 在 `contextmind/scenarios/` 创建场景配置文件
2. 在 `contextmind/apps/` 创建应用实现（如使用Evolve模式）
3. 在 `contextmind/config/scenarios.yaml` 注册场景
4. 添加测试和文档

详细步骤请参考 [扩展场景指南](docs/extending-scenarios.md)。

## 添加新模式

如果您想添加新的对话处理模式：

1. 在 `contextmind/modes/` 创建新目录
2. 实现核心追踪器类
3. 添加必要的辅助组件
4. 在 `contextmind/__init__.py` 导出主要接口
5. 编写完整的文档和示例
6. 添加单元测试和集成测试

## 文档贡献

文档同样重要！您可以：

- 修正文档中的错误
- 改进现有文档的清晰度
- 添加示例代码
- 翻译文档（如果支持多语言）

## 社区准则

- 尊重所有贡献者
- 保持友好和包容
- 欢迎新手提问
- 建设性地提供反馈

## 许可证

通过贡献代码，您同意您的贡献将在 [MIT License](LICENSE) 下发布。

## 联系方式

如有疑问，请通过以下方式联系：

- 创建 [Issue](https://github.com/Jasmine66Bloom/ContextMind/issues)
- 在 Pull Request 中评论

感谢您的贡献！🎉
