# Benchmark - 对话系统评测框架

简化的评测框架，用于在标准数据集上评测不同的对话系统算法。

## 目录结构

```
benchmark/
├── datasets/              # 数据集
│   ├── transfertod/      # TransferTOD数据集
│   │   ├── adapter.py    # 数据适配器
│   │   ├── utils.py      # 工具函数
│   │   └── configs/      # 配置文件
│   └── risawoz/          # RiSAWOZ数据集（待实现）
│
├── algorithms/           # 算法评测
│   ├── dst.py           # DST算法
│   └── fnctod.py        # FnCTOD算法
│
├── shared/              # 共享组件
│   ├── intent_evaluator.py
│   └── intent_label_loader.py
│
├── run_dst_transfertod.py      # DST on TransferTOD
├── run_dst_risawoz.py          # DST on RiSAWOZ（待实现）
├── run_fnctod_transfertod.py   # FnCTOD on TransferTOD
└── run_fnctod_risawoz.py       # FnCTOD on RiSAWOZ（待实现）
```

## 使用方法

### DST评测

```bash
# 评测所有领域
python run_dst_transfertod.py

# 评测特定领域，限制数量
python run_dst_transfertod.py --domain 酒店 --limit 10

# 使用噪声数据
python run_dst_transfertod.py --data-type noise
```

### FnCTOD评测

```bash
python run_fnctod_transfertod.py --domain 酒店 --limit 10
```

## 支持的算法和数据集

| 算法 / 数据集 | TransferTOD | RiSAWOZ |
|-------------|-------------|---------|
| DST         | ✅          | ⏳ 待实现 |
| FnCTOD      | ✅          | ⏳ 待实现 |

## 添加新数据集

1. 在 `datasets/` 下创建新目录
2. 实现 `adapter.py` 适配器
3. 创建运行脚本 `run_<algorithm>_<dataset>.py`

## 添加新算法

1. 在 `algorithms/` 下创建 `<algorithm>.py`
2. 实现评测器类
3. 创建运行脚本
