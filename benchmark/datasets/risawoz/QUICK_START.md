# RiSAWOZ DST 评测快速参考

## 快速开始

### 1. 准备数据集

```bash
# 克隆 RiSAWOZ 仓库
git clone https://github.com/terryqj0107/RiSAWOZ.git

# 复制数据文件到项目目录
mkdir -p ./data/RiSAWOZ
cp RiSAWOZ/data/*.json ./data/RiSAWOZ/
```

### 2. 运行评测

```bash
# 基本使用
python benchmark/run_dst_risawoz.py

# 评测特定领域
python benchmark/run_dst_risawoz.py --domain 景点

# 快速测试
python benchmark/run_dst_risawoz.py --limit 10
```

## 评测指标

| 指标 | 级别 | 公式 | 说明 |
|------|------|------|------|
| Slot Accuracy | Turn | `correct/total` | 所有轮次的槽位准确率 |
| **Joint Accuracy** | **Turn** | `exact/total` | **每轮完全匹配** ⭐ |
| Precision | Dialogue | `TP/(TP+FP)` | 基于最终状态 |
| Recall | Dialogue | `TP/(TP+FN)` | 基于最终状态 |
| F1 Score | Dialogue | `2PR/(P+R)` | 综合指标 |

## RiSAWOZ vs TransferTOD

### 关键差异

| 项目 | RiSAWOZ | TransferTOD |
|------|---------|-------------|
| Joint Accuracy | **Turn-level** | Dialogue-level |
| 领域数 | 12 | 24 |
| 格式 | MultiWOZ | 自定义 |

### 为什么 Joint Accuracy 不同？

- **RiSAWOZ**: 每轮状态都必须完全正确（更严格）
- **TransferTOD**: 只要求最终状态正确（更宽松）

**结果**: RiSAWOZ 的 Joint Accuracy 通常会低于 TransferTOD

## 命令行参数

```bash
python benchmark/run_dst_risawoz.py \
    --data-root ./data/RiSAWOZ \  # 数据集路径
    --domain 景点 \                # 领域（可选）
    --split val \                  # train/val/test
    --limit 10 \                   # 限制数量
    --verbose \                    # 详细输出
    --log-level INFO              # 日志级别
```

## 12个领域

1. 景点 (Attraction)
2. 酒店 (Hotel)
3. 餐厅 (Restaurant)
4. 地铁 (Metro)
5. 出租 (Taxi)
6. 火车 (Train)
7. 电视剧 (TV Series)
8. 天气 (Weather)
9. 航班 (Flight)
10. 医院 (Hospital)
11. 电影 (Movie)
12. 音乐 (Music)

## 代码示例

### Python API

```python
from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

# 初始化适配器
adapter = RiSAWOZAdapter(data_root="./data/RiSAWOZ")

# 加载对话
dialogue = adapter.load_dialogue("0", split="val")

# 获取领域对话
景点_ids = adapter.get_dialogues_by_domain("景点", split="val")
print(f"景点领域对话数: {len(景点_ids)}")

# 遍历对话
for dialogue_id in 景点_ids[:5]:
    dialogue = adapter.load_dialogue(dialogue_id, split="val")
    print(f"对话 {dialogue_id}: {len(dialogue.turns)} 轮")
```

### 评测脚本使用

```python
from benchmark.run_dst_risawoz import DSTRiSAWOZTest
import asyncio

async def main():
    # 创建测试实例
    test = DSTRiSAWOZTest(data_root="./data/RiSAWOZ")
    
    # 初始化（指定领域）
    test.initialize(domain="景点")
    
    # 测试单个对话
    metrics = await test.test_dialogue("0", split="val", verbose=True)
    
    # 打印结果
    print(f"Slot Accuracy: {metrics['slot_accuracy']:.2%}")
    print(f"Joint Accuracy: {metrics['joint_accuracy']:.2%}")
    print(f"F1 Score: {metrics['f1']:.2%}")

asyncio.run(main())
```

## 常见问题

### Q: 数据集在哪里下载？

```bash
git clone https://github.com/terryqj0107/RiSAWOZ.git
```

### Q: 为什么找不到数据文件？

确保目录结构：
```
./data/RiSAWOZ/
├── train.json
├── val.json
└── test.json
```

### Q: Joint Accuracy 太低怎么办？

这是正常的！RiSAWOZ 使用 turn-level 评测，每轮都必须完全正确。通常：
- Slot Accuracy: 80-95%
- Joint Accuracy: 60-85% (turn-level)
- F1 Score: 75-90%

### Q: 如何评测多个领域？

```bash
# 方法1: 不指定领域（评测所有）
python benchmark/run_dst_risawoz.py

# 方法2: 逐个评测
for domain in 景点 酒店 餐厅; do
    python benchmark/run_dst_risawoz.py --domain $domain
done
```

### Q: 如何调试？

```bash
# 启用详细输出
python benchmark/run_dst_risawoz.py \
    --domain 景点 \
    --limit 5 \
    --verbose \
    --log-level DEBUG
```

## 参考资料

- [RiSAWOZ GitHub](https://github.com/terryqj0107/RiSAWOZ)
- [RiSAWOZ 论文](https://arxiv.org/abs/2010.08738)
- [完整文档](./README.md)

## 版本

- **实现版本**: 0.1.0
- **实现日期**: 2026-02-11
- **基于**: TransferTOD DST 实现
