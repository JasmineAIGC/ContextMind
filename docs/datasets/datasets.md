# 数据集说明

ContextMind 评测框架支持三个主要数据集。

---

## SGD（Schema-Guided Dialogue）

**用途**：PyTOD 算法官方数据集（英文，多领域任务型对话）

| 统计项 | 数量 |
|--------|------|
| 总对话数 | 22,825 |
| 覆盖领域 | 16 个 |
| 覆盖服务 | 26 个 |
| 槽位总数 | 214 个 |

**获取方式**：

```bash
git clone https://github.com/google-research-datasets/dstc8-schema-guided-dialogue.git
```

**关键链接**：
- GitHub: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
- 论文: [Towards Scalable Multi-Domain Conversational Agents](https://arxiv.org/abs/1909.05855)（AAAI 2020）
- pyTOD 官方源码: https://github.com/apple/ml-pytod

---

## TransferTOD

**用途**：DST / FnCTOD 评测（中文，30 领域，重点研究跨领域迁移）

| 划分 | 领域数 | 对话数 |
|------|--------|--------|
| 训练集 | 27 | 4,320 |
| 域内测试（ID Test） | 27 | 540 |
| 域外测试（OOD Test） | 3 | 600 |

**获取方式**：

```bash
git clone https://github.com/KongLongGeFDU/TransferTOD.git
```

**关键链接**：
- GitHub: https://github.com/KongLongGeFDU/TransferTOD
- 论文: [TransferTOD: A Generalizable Chinese Multi-Domain TOD System](https://aclanthology.org/2024.emnlp-main.710.pdf)（EMNLP 2024）

**目录布局**（需与 `.env` 配置路径一致）：

```
TransferTOD/
└── data/
    └── raw_data/
        ├── clean/              # 干净对话（~6,000 条，标准评测）
        │   ├── 1-hotel/
        │   └── ...             # 30 个领域子目录
        └── dirty/              # 带噪声对话（~3,000 条）
```

---

## RiSAWOZ

**用途**：DST 评测（中文，12 领域，含丰富语义标注）

| 统计项 | 数量 |
|--------|------|
| 对话总数 | 11,200 |
| 覆盖领域 | 12 个 |
| 多领域对话占比 | ~35% |

**获取方式**：

```bash
git clone https://github.com/terryqj0107/RiSAWOZ.git
# 或从百度网盘下载：https://pan.baidu.com/s/1BQImRCvnnP_nQzXVM1CTZQ（提取码：73jl）
```

**关键链接**：
- GitHub: https://github.com/terryqj0107/RiSAWOZ
- 论文: [RiSAWOZ](https://aclanthology.org/2020.emnlp-main.67)（EMNLP 2020）
- 许可证: CC BY-NC 4.0

**12 个领域**：景点、汽车、辅导班、航班、医院、酒店、电影、电脑、餐厅、火车、电视剧、天气

---

## 算法 × 数据集支持矩阵

| 算法 | TransferTOD | RiSAWOZ | SGD |
|------|-------------|---------|-----|
| DST | ✅ | ✅ | ⏳ |
| FnCTOD | ✅ | ⏳ | ⏳ |
| PyTOD | ⏳ | ⏳ | ✅（评测集成待完成）|
| Evolve | ⏳ | ⏳ | ⏳ |

---

**最后更新**: 2026-03-30 | **版本**: 0.3.0
