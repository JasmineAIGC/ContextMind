# 贡献指南

感谢您对 ContextMind 项目的关注！我们欢迎所有形式的贡献。

## 贡献方式

您可以通过以下方式为项目做出贡献：

- 🐛 报告 Bug
- 💡 提出新功能建议
- 📝 改进文档
- 🔧 提交代码修复
- ✨ 实现新功能
- 🧪 添加测试用例
- 🌍 提供翻译

## 开始之前

### 行为准则

请遵守我们的行为准则：
- 尊重所有贡献者
- 使用友善和包容的语言
- 接受建设性的批评
- 关注什么对社区最有利

### 开发环境设置

1. Fork 仓库到您的账号

2. 克隆您的 fork
```bash
git clone https://github.com/YOUR_USERNAME/ContextMind.git
cd ContextMind
```

3. 添加上游仓库
```bash
git remote add upstream https://github.com/Jasmine66Bloom/ContextMind.git
```

4. 创建开发分支
```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

5. 安装开发依赖
```bash
pip install -r requirements.txt
pip install -e .
```

## 报告 Bug

### 在报告 Bug 之前

- 检查是否已有相同的 issue
- 确认问题在最新版本中仍然存在
- 收集相关信息（Python 版本、错误堆栈等）

### 如何报告

创建新的 Issue，包含以下信息：

**标题格式**: `[Bug] 简短描述`

**内容模板**:
```markdown
## 问题描述
简要描述遇到的问题

## 复现步骤
1. 第一步
2. 第二步
3. ...

## 预期行为
描述预期应该发生什么

## 实际行为
描述实际发生了什么

## 环境信息
- OS: [例如 Ubuntu 20.04]
- Python 版本: [例如 3.9.7]
- ContextMind 版本: [例如 0.3.0]
- LLM 提供商: [例如 Qwen]

## 错误日志
```
粘贴完整的错误堆栈
```

## 最小可复现代码
```python
# 提供最简单的复现代码
```

## 截图
如果适用，添加截图说明问题
```

## 提出功能建议

### 如何提出

创建新的 Issue，包含以下信息：

**标题格式**: `[Feature] 功能名称`

**内容模板**:
```markdown
## 功能描述
清晰描述您想要的功能

## 使用场景
说明为什么需要这个功能，它解决什么问题

## 建议实现方案
如果有想法，可以描述如何实现

## 替代方案
是否考虑过其他解决方案？

## 额外信息
其他任何相关信息
```

## 贡献代码

### 代码规范

#### Python 代码风格

我们遵循 PEP 8 规范：

```python
# 好的例子
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import AdkLLMClient

class MyTracker:
    """跟踪器类的文档字符串"""
    
    def __init__(self, client: AdkLLMClient):
        """初始化方法"""
        self.client = client
        self.state = {}
    
    def process_input(self, user_input: str) -> dict:
        """
        处理用户输入
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            包含处理结果的字典
        """
        # 实现逻辑
        return {"result": "success"}
```

**关键规范：**
- 使用 4 空格缩进
- 类名使用 PascalCase
- 函数名和变量名使用 snake_case
- 常量使用 UPPER_SNAKE_CASE
- 添加类型提示
- 编写文档字符串

#### 文档规范

- 使用中文编写文档和注释
- Markdown 文件使用 kebab-case 命名（例如：`quick-start.md`）
- 每个文档添加"最后更新"日期
- 代码示例要可运行

#### 命名规范

**文件命名：**
```
Python 文件: snake_case.py
配置文件: lowercase.yaml, kebab-case.json
文档文件: kebab-case.md
```

**代码命名：**
```python
# 类
class DialogueStateTracker:
    pass

# 函数
def process_dialogue_turn():
    pass

# 变量
user_input = "hello"
max_history_turns = 10

# 常量
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 60
```

### Git 提交规范

#### 提交信息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type（类型）：**
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建过程或辅助工具的变动

**示例：**
```bash
feat(dst): 添加历史摘要功能

- 实现模板摘要方法
- 实现 LLM 摘要方法
- 添加摘要配置选项

Closes #123
```

```bash
fix(fnctod): 修复函数调用解析错误

修复当参数为空时的解析失败问题

Fixes #456
```

### Pull Request 流程

#### 1. 准备工作

```bash
# 同步上游最新代码
git fetch upstream
git checkout main
git merge upstream/main

# 创建功能分支
git checkout -b feature/your-feature
```

#### 2. 开发和测试

```bash
# 开发您的功能...

# 运行测试（如果有）
python -m pytest tests/

# 检查代码风格
flake8 contextmind/

# 提交代码
git add .
git commit -m "feat: 添加新功能"
```

#### 3. 推送和创建 PR

```bash
# 推送到您的 fork
git push origin feature/your-feature
```

然后在 GitHub 上创建 Pull Request。

#### 4. PR 描述模板

```markdown
## 变更说明
简要描述此 PR 的目的和变更内容

## 变更类型
- [ ] Bug 修复
- [ ] 新功能
- [ ] 重构
- [ ] 文档更新
- [ ] 其他

## 相关 Issue
Closes #xxx

## 变更清单
- [ ] 添加了新功能 A
- [ ] 修复了Bug B
- [ ] 更新了文档 C

## 测试
描述如何测试这些变更

## 截图
如果有 UI 变更，添加截图

## 检查清单
- [ ] 代码遵循项目规范
- [ ] 已添加必要的测试
- [ ] 已更新相关文档
- [ ] 所有测试通过
- [ ] 没有引入新的警告
```

### 代码审查

所有 PR 都需要经过代码审查才能合并。审查过程中：

- 保持开放和友好的态度
- 及时响应审查意见
- 清楚说明您的设计决策
- 如有分歧，理性讨论

## 贡献文档

### 文档类型

- **用户文档**: 面向最终用户的使用指南
- **开发文档**: 面向开发者的技术文档
- **API 文档**: API 参考和示例

### 文档要求

1. **清晰易懂**: 使用简单明了的语言
2. **结构完整**: 包含标题、目录、示例
3. **代码可运行**: 确保代码示例可以直接运行
4. **保持更新**: 修改代码时同步更新文档

### 文档提交

```bash
# 创建文档分支
git checkout -b docs/update-api-reference

# 编辑文档
# ...

# 提交
git add docs/
git commit -m "docs: 更新 API 参考文档"

# 推送并创建 PR
git push origin docs/update-api-reference
```

## 开发指南

### 项目结构

```
ContextMind/
├── contextmind/          # 主包
│   ├── modes/           # 三种模式实现
│   ├── infra/           # 基础设施
│   ├── config/          # 配置管理
│   ├── scenarios/       # 场景定义
│   └── apps/            # 应用实现
├── examples/            # 示例程序
├── tests/               # 测试代码
├── docs/                # 文档
└── benchmark/           # 评测代码
```

### 添加新模式

参考 `contextmind/modes/` 目录下的现有实现。

### 添加新场景

参考 [扩展场景指南](../guides/configuration.md)。

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试
python -m pytest tests/test_dst_mode.py

# 运行并显示覆盖率
python -m pytest --cov=contextmind tests/
```

## 发布流程

（仅适用于维护者）

1. 更新版本号
2. 更新 CHANGELOG.md
3. 创建 release tag
4. 发布到 PyPI

## 获取帮助

如果您有任何问题：

1. 查看现有文档
2. 搜索现有 Issues
3. 在 Discussions 中提问
4. 联系维护者

## 致谢

感谢所有为 ContextMind 做出贡献的人！

---

**最后更新**: 2026-02-10
