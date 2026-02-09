# Benchmark 增强功能说明

## 概述

根据用户需求，对 benchmark 评测系统进行了全面增强，添加了以下三个关键功能：

1. **清晰的数值指标结果** - 规范、清晰的评测指标显示
2. **结果保存** - 支持保存为 JSON、文本和图片文件
3. **日志详细度控制** - 通过参数控制输出的详细程度

---

## 功能特性

### 1. 综合评测指标

#### Slot-Level（槽位级别）指标
- **Slot Accuracy**: 槽位准确率
- **Precision**: 精确率
- **Recall**: 召回率
- **F1 Score**: F1分数

#### Dialogue-State-Level（对话状态级别）指标
- **Joint Accuracy**: 联合准确率
- **Joint Accuracy (Strict)**: 严格联合准确率

#### 统计信息
- **Total Turns**: 总轮次数
- **Total Slots**: 总槽位数
- **Correct Slots**: 正确槽位数
- **Correct Turns**: 完全正确的轮次数

#### 领域细分
- 每个领域的独立指标统计

---

### 2. 结果输出功能

#### 自动生成的文件

**metrics.json** - JSON格式的完整指标
```json
{
  "slot_level": {
    "accuracy": 0.8542,
    "precision": 0.8542,
    "recall": 0.8542,
    "f1": 0.8542
  },
  "dialogue_state_level": {
    "joint_accuracy": 0.65,
    "joint_accuracy_strict": 0.65
  },
  "statistics": {
    "total_slots": 124,
    "correct_slots": 106,
    "total_turns": 10,
    "correct_turns": 7
  },
  "domain_breakdown": {
    "酒店": {
      "slot_accuracy": 0.8542,
      "joint_accuracy": 0.7,
      "total_turns": 10
    }
  }
}
```

**summary.txt** - 人类可读的摘要
```
============================================================
            DST on TransferTOD 评测结果摘要
============================================================

评测时间: 2026-02-09 10:45:32

主要指标:
  Slot Accuracy:  0.8542
  Joint Accuracy: 0.6500
  F1 Score:       0.8542

统计信息:
  Total Turns:    10
  Total Slots:    124
  Correct Slots:  106
  Correct Turns:  7
```

**metrics_chart.png** - 可视化图表（需要 matplotlib）
- 柱状图展示所有主要指标
- 高分辨率（150 DPI）
- 包含数值标签

---

### 3. 详细度控制

通过 `--verbose` 参数控制输出级别：

#### Level 0 - 安静模式（Quiet）
```bash
python benchmark/run_dst_transfertod.py --verbose 0 --limit 10
```
**输出：**
```
Slot Accuracy: 0.8542
Joint Accuracy: 0.6500
```

#### Level 1 - 正常模式（Normal，默认）
```bash
python benchmark/run_dst_transfertod.py --verbose 1 --limit 10
# 或简写
python benchmark/run_dst_transfertod.py --limit 10
```
**输出：**
- 评测配置信息
- 进度指示（每10个对话）
- 格式化的指标表格
- 领域细分统计

#### Level 2 - 详细模式（Debug）
```bash
python benchmark/run_dst_transfertod.py --verbose 2 --limit 10
```
**输出：**
- 所有 Level 1 的信息
- 每个对话的详细评测信息
- 完整的对话ID和领域

---

## 使用示例

### 基础评测
```bash
# 评测10个对话，显示完整指标
python benchmark/run_dst_transfertod.py --data-type clean --limit 10
```

### 保存结果
```bash
# 保存指标和摘要到文件
python benchmark/run_dst_transfertod.py \
    --limit 20 \
    --output-dir ./results/run_001
```

### 生成可视化图表
```bash
# 保存结果并生成图表
python benchmark/run_dst_transfertod.py \
    --limit 50 \
    --output-dir ./results/run_002 \
    --save-plots
```

### 特定领域评测
```bash
# 只评测酒店领域
python benchmark/run_dst_transfertod.py \
    --domain 酒店 \
    --limit 20 \
    --output-dir ./results/hotel
```

### 安静模式（脚本集成）
```bash
# 只输出关键指标，适合脚本解析
python benchmark/run_dst_transfertod.py \
    --verbose 0 \
    --limit 100 \
    --output-dir ./results/batch_run
```

### 详细调试
```bash
# 显示每个对话的详细信息
python benchmark/run_dst_transfertod.py \
    --verbose 2 \
    --limit 5
```

---

## 输出示例

### 正常模式输出

```
==========================================================
           DST on TransferTOD 评测
==========================================================

领域: 所有
数据类型: clean
限制数量: 10

找到 10 个对话

进度: 10/10 完成

==========================================================
                     评测结果
==========================================================

╔════════════════════════════════════════════════════════╗
║                   DST 评测指标                          ║
╠════════════════════════════════════════════════════════╣
║ Slot-Level Metrics                                     ║
║   Slot Accuracy:        0.8542                         ║
║   Precision:            0.8542                         ║
║   Recall:               0.8542                         ║
║   F1 Score:             0.8542                         ║
║                                                        ║
║ Dialogue-State-Level Metrics                           ║
║   Joint Accuracy:       0.6500                         ║
║   Joint Accuracy (Strict): 0.6500                      ║
║                                                        ║
║ Statistics                                             ║
║   Total Turns:          10                             ║
║   Total Slots:          124                            ║
║   Correct Slots:        106                            ║
║   Correct Turns:        7                              ║
╚════════════════════════════════════════════════════════╝

领域细分指标:
------------------------------------------------------------
  酒店:
    Slot Accuracy:  0.8542
    Joint Accuracy: 0.7000
    Total Turns:    10
------------------------------------------------------------

评测完成！
```

---

## 命令行参数完整列表

```
参数                   说明                              默认值
--data-root DIR      TransferTOD数据集根目录            ./data/TransferTOD
--data-type TYPE     数据类型：clean或noise             clean
--domain DOMAIN      指定评测领域（可选）               所有领域
--limit N            限制评测对话数量                   无限制
--verbose LEVEL      详细度：0=安静,1=正常,2=详细       1
--output-dir DIR     结果输出目录（可选）               不保存
--save-plots         生成可视化图表                     False
```

---

## 技术实现

### 核心模块

**benchmark/algorithms/dst.py**
- `DSTMetrics` - 指标数据类
- `DSTEvaluator` - 评测器类
- 指标计算逻辑

**benchmark/run_dst_transfertod.py**
- 命令行参数解析
- 评测流程控制
- 结果格式化输出
- 文件保存功能

### 依赖项

**必需：**
- Python 3.7+
- 标准库（argparse, json, pathlib, datetime）

**可选：**
- matplotlib（用于生成图表，使用 --save-plots 时需要）

---

## 常见问题

### Q: 如何只看关键指标？
A: 使用 `--verbose 0` 参数

### Q: 结果保存在哪里？
A: 使用 `--output-dir` 指定目录，会生成 metrics.json 和 summary.txt

### Q: 如何生成图表？
A: 使用 `--save-plots` 参数（需要安装 matplotlib）

### Q: 如何调试评测过程？
A: 使用 `--verbose 2` 查看详细信息

### Q: 如何在脚本中使用？
A: 使用 `--verbose 0` 安静模式，解析简单的输出

---

## 未来改进

可能的增强功能：
- [ ] 更多可视化图表类型（混淆矩阵、ROC曲线等）
- [ ] HTML格式的详细报告
- [ ] 实时进度条（tqdm）
- [ ] 多线程评测加速
- [ ] 对比不同运行结果
- [ ] 导出Excel格式

---

**版本**: 1.0  
**最后更新**: 2026-02-09
