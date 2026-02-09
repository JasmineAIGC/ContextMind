# 迁移指南：tests → benchmark

## 📋 变更概述

为了更好地组织评测代码，我们将 `tests` 目录重构为 `benchmark` 目录，采用更清晰的模块化结构。

## 🔄 主要变更

### 1. 目录重命名

```
tests/  →  benchmark/
```

### 2. 文件重新组织

| 旧路径 | 新路径 | 说明 |
|--------|--------|------|
| `tests/test_dst_transfertod.py` | `benchmark/runners/run_dst_transfertod.py` | DST评测运行器 |
| `tests/test_fnctod_transfertod.py` | `benchmark/runners/run_fnctod_transfertod.py` | FnCTOD评测运行器 |
| `tests/adapters/transfertod_adapter.py` | `benchmark/datasets/transfertod/adapters/transfertod_adapter.py` | TransferTOD适配器 |
| `tests/intent_evaluator.py` | `benchmark/shared/intent_evaluator.py` | 意图评测器 |
| `tests/intent_label_loader.py` | `benchmark/shared/intent_label_loader.py` | 意图标签加载器 |
| `tests/configs/intent_labels_30_domains_Version2.json` | `benchmark/datasets/transfertod/configs/intent_labels_30_domains_Version2.json` | 意图标签配置 |

### 3. 新增结构

```
benchmark/
├── algorithms/        # 算法专属代码（新增）
├── datasets/         # 数据集组织（新增）
├── adapters/         # 算法-数据集适配（新增）
├── shared/           # 共享组件
└── runners/          # 评测运行脚本
```

## 🚀 命令行变更

### DST 评测

```bash
# 旧命令
python tests/test_dst_transfertod.py --domain 酒店 --limit 10

# 新命令
python benchmark/runners/run_dst_transfertod.py --domain 酒店 --limit 10
```

### FnCTOD 评测

```bash
# 旧命令
python tests/test_fnctod_transfertod.py --domain 酒店 --limit 10

# 新命令
python benchmark/runners/run_fnctod_transfertod.py --domain 酒店 --limit 10
```

## 📝 代码导入变更

### 适配器导入

```python
# 旧导入
from tests.adapters import TransferTODAdapter

# 新导入
from benchmark.adapters.dst_transfertod import DSTTransferTODAdapter
# 或
from benchmark.datasets.transfertod.adapters import TransferTODAdapter
```

### 评测器导入

```python
# 旧导入
from tests.intent_evaluator import IntentEvaluator

# 新导入
from benchmark.shared.intent_evaluator import IntentEvaluator
```

### 意图标签加载器

```python
# 旧导入
from tests.intent_label_loader import get_intent_label_loader

# 新导入
from benchmark.shared.intent_label_loader import get_intent_label_loader
```

## 🆕 新增功能

### 1. 算法-数据集适配器

```python
# 专门的适配器用于不同的算法-数据集组合
from benchmark.adapters.dst_transfertod import DSTTransferTODAdapter
from benchmark.adapters.fnctod_transfertod import FnCTODTransferTODAdapter

# RiSAWOZ支持（待实现）
# from benchmark.adapters.dst_risawoz import DSTRiSAWOZAdapter
# from benchmark.adapters.fnctod_risawoz import FnCTODRiSAWOZAdapter
```

### 2. RiSAWOZ 框架

已创建 RiSAWOZ 数据集的目录结构和占位符，待后续实现：
- `benchmark/datasets/risawoz/`
- `benchmark/adapters/dst_risawoz.py`
- `benchmark/adapters/fnctod_risawoz.py`
- `benchmark/runners/run_dst_risawoz.py`
- `benchmark/runners/run_fnctod_risawoz.py`

## 📚 文档更新

### 主要文档

- `benchmark/README.md` - 评测框架总览
- `benchmark/datasets/risawoz/README.md` - RiSAWOZ数据集说明（待实现）

## ⚠️ 注意事项

### 1. 旧代码兼容性

目前 `tests` 目录仍然保留，但建议：
- 新代码使用 `benchmark` 目录
- 逐步迁移现有代码到新结构
- 验证无误后删除 `tests` 目录

### 2. 配置文件路径

配置文件路径已更新：
```python
# 旧路径
"tests/configs/intent_labels_30_domains_Version2.json"

# 新路径
"benchmark/datasets/transfertod/configs/intent_labels_30_domains_Version2.json"
```

### 3. 导入路径

所有导入路径都已更新为绝对导入，避免相对导入带来的问题。

## 🔍 验证步骤

### 1. 验证导入

```bash
python3 -c "from benchmark.adapters.dst_transfertod import DSTTransferTODAdapter; print('✅ Import OK')"
```

### 2. 验证运行

```bash
# 测试 DST 评测
python benchmark/runners/run_dst_transfertod.py --domain 酒店 --limit 2

# 测试 FnCTOD 评测
python benchmark/runners/run_fnctod_transfertod.py --domain 酒店 --limit 2
```

## 🎯 下一步

1. **验证功能**: 确认所有评测功能正常工作
2. **完善文档**: 补充各模块的详细文档
3. **实现 RiSAWOZ**: 完成 RiSAWOZ 数据集支持
4. **删除旧代码**: 验证无误后删除 `tests` 目录

## 📧 问题反馈

如遇到问题，请：
1. 检查导入路径是否正确更新
2. 查看 `benchmark/README.md` 了解新结构
3. 提交 Issue 说明具体问题

## 📅 时间线

- **创建时间**: 2026-02-09
- **状态**: 已完成基础重构
- **下一步**: 实现 RiSAWOZ 支持
