# RiSAWOZ 数据集（待实现）

## 📋 概述

RiSAWOZ 是一个中文任务型对话数据集，用于对话状态追踪和任务完成评测。

## ⚠️ 当前状态

**待实现** - 此数据集的支持尚未完成。

## 📝 待实现功能

### 1. 数据加载器
- [ ] RiSAWOZ数据格式解析
- [ ] 对话数据结构定义
- [ ] 槽位和领域映射

### 2. 数据集适配器
- [ ] 实现 `RiSAWOZAdapter` 类
- [ ] 数据预处理逻辑
- [ ] 兼容性转换

### 3. 算法适配器
- [ ] DST-RiSAWOZ 适配器
- [ ] FnCTOD-RiSAWOZ 适配器
- [ ] 格式转换和特殊处理

### 4. 配置文件
- [ ] 意图标签定义
- [ ] 领域配置
- [ ] 槽位定义

### 5. 评测脚本
- [ ] DST评测运行器
- [ ] FnCTOD评测运行器
- [ ] 指标计算和报告生成

## 🎯 数据集特点

（待补充）

## 📊 领域信息

（待补充）

## 🔧 使用示例

```python
# 示例代码（待实现后可用）
from benchmark.datasets.risawoz.adapters import RiSAWOZAdapter

# 初始化适配器
adapter = RiSAWOZAdapter(data_root=".data/RiSAWOZ/")

# 加载对话
dialogue = adapter.load_dialogue("dialogue_001")

# 获取所有对话ID
all_ids = adapter.get_all_dialogue_ids()
```

## 📅 实现计划

1. **Phase 1**: 数据格式分析和定义
2. **Phase 2**: 基础适配器实现
3. **Phase 3**: 算法适配器实现
4. **Phase 4**: 评测脚本和指标
5. **Phase 5**: 测试和文档完善

## 📚 参考资料

（待添加RiSAWOZ数据集相关论文和文档链接）

## 💡 贡献

欢迎贡献 RiSAWOZ 数据集的支持！请参考以下步骤：

1. Fork 本项目
2. 创建功能分支
3. 实现相关功能
4. 提交 Pull Request

## 📧 联系方式

如有问题或建议，请提交 Issue。
