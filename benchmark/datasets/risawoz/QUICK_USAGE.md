# RiSAWOZ DST 评测快速使用指南

## 最简单的用法

```bash
# 直接使用完整文件路径（推荐）✅
python benchmark/run_dst_risawoz.py \
    --test-file .data/RiSAWOZ/task1-data/test.json \
    --limit 10
```

**自动处理**:
- ✅ 自动提取目录：`data_root = .data/RiSAWOZ/task1-data`
- ✅ 自动提取文件名：`test_file = test.json`
- ✅ 自动设置 split：`split = test`

## 常见用法

### 1. 使用完整路径（最简单）

```bash
# 评测测试集
python benchmark/run_dst_risawoz.py \
    --test-file /path/to/test.json

# 评测验证集
python benchmark/run_dst_risawoz.py \
    --val-file /path/to/val.json

# 评测训练集
python benchmark/run_dst_risawoz.py \
    --train-file /path/to/train.json
```

### 2. 使用 task1-data-NLU.zip 的文件

```bash
# 不需要重命名！
python benchmark/run_dst_risawoz.py \
    --test-file .data/RiSAWOZ/task1-data/test.json \
    --limit 10
```

**注意**: 如果你的文件是 NLU 格式（包含 tokens, labels, intents），
评测会自动检测并给出错误提示。DST 评测需要包含 `dialogue` 和 `belief_state` 的数据。

### 3. 传统方式（仍支持）

```bash
python benchmark/run_dst_risawoz.py \
    --data-root ./data/RiSAWOZ \
    --split test \
    --domain 景点 \
    --limit 10
```

## 参数说明

### 必选参数（以下三选一）

- `--test-file`: 测试集文件路径
- `--val-file`: 验证集文件路径  
- `--train-file`: 训练集文件路径

### 可选参数

- `--data-root`: 数据集根目录（默认：`./data/RiSAWOZ`）
- `--split`: 数据集划分（train/val/test，默认：`val`）
  - **注意**: 使用完整文件路径时会自动设置
- `--domain`: 指定领域（如：景点、酒店、餐厅）
- `--limit`: 限制测试对话数量
- `--verbose`: 输出详细信息
- `--log-level`: 日志级别（DEBUG/INFO/WARNING/ERROR）

## 日志示例

### 使用完整路径

```bash
$ python benchmark/run_dst_risawoz.py --test-file .data/RiSAWOZ/task1-data/test.json

[INFO] 检测到完整路径，使用: data_root=.data/RiSAWOZ/task1-data, test_file=test.json
[INFO] 根据文件路径自动设置 split=test
[INFO] 已加载 30 个领域的意图标签
[INFO] 找到 10 个对话实例
...
```

### 检测到 NLU 格式数据

```bash
$ python benchmark/run_dst_risawoz.py --test-file .data/NLU/test.json

======================================================================
❌ 错误：检测到 NLU 标注数据格式
======================================================================

此格式用于 NLU 任务（意图识别、实体提取），
不适用于 DST（对话状态追踪）评测。

请使用包含 'dialogue' 和 'belief_state' 字段的 DST 格式数据。
======================================================================
```

## 评测指标

评测会输出以下指标：

### 核心指标
- **槽位准确率**: 所有槽位中正确的比例
- **联合准确率-严格**: 完全匹配（不允许额外槽位）
- **联合准确率-软匹配**: 软匹配（允许额外槽位）
- **精确率**: 预测正确的槽位占所有预测的比例
- **召回率**: 预测正确的槽位占所有真实槽位的比例
- **F1分数**: 精确率和召回率的调和平均

### 意图评测
- **意图识别准确率**
- **混淆矩阵**
- **宏平均和微平均指标**

## 故障排查

### FileNotFoundError

**问题**: `FileNotFoundError: 数据文件不存在`

**解决**:
1. 检查文件路径是否正确
2. 检查文件是否存在
3. 使用绝对路径或相对于当前目录的正确路径

### 领域 '未知' 警告

**问题**: `领域 '未知' 在意图标签中未找到`

**原因**: 数据格式可能不正确或缺少领域信息

**解决**:
1. 检查数据是否为 DST 格式（而不是 NLU 格式）
2. 确保数据包含正确的领域字段

### 所有指标为 0.00%

**问题**: 评测结果所有指标都是 0

**可能原因**:
1. 使用了 NLU 格式数据（应该会被自动检测）
2. 数据格式不正确
3. 数据为空

**解决**: 检查数据格式，参考文档说明

## 更多信息

- 完整文档: `benchmark/datasets/risawoz/README.md`
- 数据集设置: `benchmark/datasets/risawoz/DATASET_SETUP.md`
- 改进总结: `docs/RISAWOZ_DST_IMPROVEMENTS.md`
- 意图评测: `docs/INTENT_EVALUATION_GUIDE.md`
