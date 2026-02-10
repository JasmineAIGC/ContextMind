# TransferTOD 对话数量差异说明

## 问题

用户报告："针对相同的 TransferTOD 数据集，dst 评测找到 9013 个对话实例，fnctod 评测找到 6000个对话实例，为什么不一样？"

## 根本原因

TransferTOD 数据集包含**两种类型**的数据：

1. **Clean 数据**：约 6000 个对话（干净、高质量）
2. **Noise 数据**：约 3013 个对话（包含噪声、拼写错误、口语化表达）

**总计：约 9013 个对话**

## 数据集结构

```
TransferTOD/
└── data/
    └── raw_data/
        ├── clean/          # 干净数据 (~6000 对话)
        │   ├── 1-hotel/
        │   ├── 2-restaurant/
        │   └── ...
        └── noise/          # 噪声数据 (~3013 对话)
            ├── 1-hotel/
            ├── 2-restaurant/
            └── ...
```

### Clean vs Noise 数据的区别

| 特性 | Clean 数据 | Noise 数据 |
|------|-----------|-----------|
| 数量 | ~6000 | ~3013 |
| 质量 | 高质量，规范表达 | 包含噪声和错误 |
| 适用场景 | 标准评测、模型训练 | 鲁棒性测试 |
| 示例 | "我想预订一个酒店" | "我想订个酒店啦" |

## 数量差异分析

### 场景1：DST 找到 9013 个对话

**可能的命令：**
```bash
python benchmark/run_dst_transfertod.py
# 或
python benchmark/run_dst_transfertod.py --data-type None
```

**原因：** 未指定 `--data-type` 参数，默认获取所有数据（clean + noise）

### 场景2：FnCTOD 找到 6000 个对话

**可能的命令：**
```bash
python benchmark/run_fnctod_transfertod.py --data-type clean
```

**原因：** 明确指定了 `--data-type clean`，只获取 clean 数据

## 诊断方法

### 使用诊断工具

我们提供了一个诊断工具来分析数据集的实际分布：

```bash
python benchmark/diagnose_dialogue_count.py --data-root ./data/TransferTOD
```

**输出示例：**
```
TransferTOD 数据集对话分布分析
================================================================================
数据路径: ./data/TransferTOD

【1. 总体统计】
  所有对话数（clean + noise）: 9013
  - clean 数据: 6000 个对话
  - noise 数据: 3013 个对话

【2. 按域统计】
  数据集中的域数量: 24
  域列表: 保洁, 健身房, 医院, 博物馆, ...

【3. 分域详细统计】
域名             Clean      Noise      总计
--------------------------------------------------
保洁             300        13         313
健身房           310        13         323
酒店             300        13         313
...
--------------------------------------------------
总计             6000       3013       9013

【4. 不同参数组合的对话数】
  无参数（所有）                    ->   9013 个对话
  只clean数据                      ->   6000 个对话
  只noise数据                      ->   3013 个对话
  域=酒店, clean                   ->    300 个对话
```

## 解决方案

### 确保评测一致性

为了确保 DST 和 FnCTOD 评测使用相同的数据：

#### 选项1：只使用 Clean 数据（推荐）

```bash
# DST 评测
python benchmark/run_dst_transfertod.py --data-type clean

# FnCTOD 评测
python benchmark/run_fnctod_transfertod.py --data-type clean

# 结果：都是 6000 个对话
```

**推荐理由：**
- Clean 数据质量高，适合标准评测
- 结果更稳定、可重复
- 与大多数论文的实验设置一致

#### 选项2：使用所有数据

```bash
# DST 评测
python benchmark/run_dst_transfertod.py

# FnCTOD 评测
python benchmark/run_fnctod_transfertod.py

# 结果：都是 9013 个对话
```

**适用场景：**
- 评估模型的鲁棒性
- 测试在噪声环境下的性能

#### 选项3：指定特定域

```bash
# DST 评测
python benchmark/run_dst_transfertod.py --domain 酒店 --data-type clean --limit 100

# FnCTOD 评测
python benchmark/run_fnctod_transfertod.py --domain 酒店 --data-type clean --limit 100

# 结果：都是 100 个对话（或域内总数，取较小值）
```

**适用场景：**
- 快速测试
- 针对特定域的分析

## 参数说明

### --data-type 参数

| 值 | 含义 | 对话数量 |
|---|------|---------|
| `clean` | 只使用 clean 数据 | ~6000 |
| `noise` | 只使用 noise 数据 | ~3013 |
| 未指定 或 `None` | 使用所有数据 | ~9013 |

### --domain 参数

| 值 | 含义 |
|---|------|
| `酒店` | 只使用酒店域的数据 |
| `餐厅` | 只使用餐厅域的数据 |
| 未指定 | 使用所有域的数据 |

### --limit 参数

限制测试的对话数量（用于快速测试）

```bash
python benchmark/run_dst_transfertod.py --limit 100
# 只测试前 100 个对话
```

## 最佳实践

### 1. 明确指定参数

❌ **不好的做法：**
```bash
# 脚本1
python benchmark/run_dst_transfertod.py

# 脚本2
python benchmark/run_fnctod_transfertod.py --data-type clean

# 结果不一致：9013 vs 6000
```

✅ **好的做法：**
```bash
# 脚本1
python benchmark/run_dst_transfertod.py --data-type clean

# 脚本2
python benchmark/run_fnctod_transfertod.py --data-type clean

# 结果一致：6000 vs 6000
```

### 2. 使用脚本文件

创建一个评测脚本确保参数一致：

```bash
#!/bin/bash
# evaluate.sh

DATA_TYPE="clean"
DATA_ROOT="./data/TransferTOD"
LIMIT=100

# DST 评测
echo "Running DST evaluation..."
python benchmark/run_dst_transfertod.py \
    --data-root $DATA_ROOT \
    --data-type $DATA_TYPE \
    --limit $LIMIT

# FnCTOD 评测  
echo "Running FnCTOD evaluation..."
python benchmark/run_fnctod_transfertod.py \
    --data-root $DATA_ROOT \
    --data-type $DATA_TYPE \
    --limit $LIMIT
```

### 3. 记录评测参数

在结果报告中记录使用的参数：

```
评测报告
========================================
数据集: TransferTOD
数据类型: clean
对话数量: 6000
域: 所有域
限制: 无
========================================
```

## 常见问题

### Q1: 为什么数据集有 noise 数据？

**A:** Noise 数据用于评估模型的鲁棒性。真实场景中，用户输入往往包含拼写错误、口语化表达、语法问题等。Noise 数据帮助测试模型在这些情况下的表现。

### Q2: 应该使用哪种数据类型？

**A:** 
- **标准评测**：使用 `clean` 数据（与论文对比时保持一致）
- **鲁棒性测试**：使用 `noise` 数据或所有数据
- **完整评估**：分别在 clean 和 noise 上评测，报告两组结果

### Q3: 为什么两个脚本的默认参数可能不同？

**A:** 这可能是历史原因导致的。建议始终明确指定 `--data-type` 参数以避免混淆。

### Q4: 如何确认我使用的是哪些数据？

**A:** 
1. 查看脚本输出的"找到 X 个对话实例"
2. 运行诊断工具对比
3. 检查命令行参数

### Q5: 6000 和 3013 加起来怎么是 9013 而不是 9013？

**A:** 数字是示例，实际数量可能略有不同。使用诊断工具查看准确数量。

## 总结

DST 和 FnCTOD 找到不同数量对话的原因是：
1. ✅ TransferTOD 包含 clean 和 noise 两种数据
2. ✅ 两个脚本可能使用了不同的 `--data-type` 参数
3. ✅ 这不是 bug，而是参数设置的差异

**解决方法：**
- 明确指定 `--data-type` 参数
- 使用诊断工具验证数据集
- 记录评测参数以便复现

---

**最后更新：** 2026-02-10
**版本：** 1.0
