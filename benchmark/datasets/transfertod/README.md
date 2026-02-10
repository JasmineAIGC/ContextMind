# TransferTOD 数据集集成

## 概述

本模块提供了与 [TransferTOD](https://github.com/KongLongGeFDU/TransferTOD) 数据集的完整集成，用于：

1. **FnCTOD 模式的函数预定义**：从 TransferTOD 的 30 个域中提取槽位定义
2. **对话数据加载**：标准化的对话实例格式
3. **Schema 自动提取**：从实际对话数据中提取域-槽位信息

## TransferTOD 数据集

TransferTOD 是一个多领域任务型对话数据集，包含：

- **30 个不同的领域**：酒店、餐厅、景点、机票、火车票等
- **每个域的特定槽位**：从实际对话数据中定义
- **多轮对话**：包含槽位变化追踪

数据集来源：https://github.com/KongLongGeFDU/TransferTOD

## 30 个标准域

TransferTOD 包含以下 30 个域：

1. 酒店
2. 餐厅
3. 景点
4. 机票
5. 火车票
6. 电影
7. 音乐会
8. 租车
9. 租房
10. 外卖
11. 打印
12. 搬家
13. 快递
14. 送水
15. 洗衣
16. 保洁
17. 理发店
18. 美容院
19. 健身房
20. 摄影
21. 家电维修
22. 医院
23. 牙医
24. 律师
25. 培训班
26. 博物馆
27. 度假村
28. 邮轮
29. 电话卡
30. 购物

## 快速开始

### 1. 准备数据集

从 TransferTOD GitHub 仓库下载数据集：

```bash
# 下载数据集（请参考 TransferTOD 项目的说明）
# 确保数据集结构如下：
# ./data/TransferTOD/
# ├── data/
# │   └── raw_data/
# │       ├── clean/
# │       │   ├── 1-hotel/
# │       │   ├── 2-restaurant/
# │       │   └── ...
# │       └── noise/
# │           └── ...
```

### 2. 提取所有域的 Schema

使用提供的脚本提取所有 30 个域的预定义函数信息：

```bash
# 提取所有域的 Schema 并保存到文件
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --output transfertod_schemas.json

# 查看特定域的详细信息
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --domain 酒店
```

### 3. 在 FnCTOD 中使用

```python
from benchmark.datasets.transfertod.adapter import TransferTODAdapter
from contextmind.modes.fnctod import FunctionManager, DomainSpec, FunctionParameter, ParameterType

# 初始化适配器
adapter = TransferTODAdapter("./data/TransferTOD")

# 方式 1: 获取单个域的 Schema
hotel_schema = adapter.get_domain_schema("酒店")
print(f"酒店域槽位: {list(hotel_schema['slots'].keys())}")

# 方式 2: 获取所有域的 Schema
all_schemas = adapter.get_all_domain_schemas()
print(f"总共 {len(all_schemas)} 个域")

# 方式 3: 获取 30 个标准域列表
standard_domains = TransferTODAdapter.get_transfertod_30_domains()
print(f"标准域: {standard_domains}")

# 转换为 FnCTOD 的 DomainSpec
def create_domain_spec(domain: str, schema: dict) -> DomainSpec:
    """将 TransferTOD schema 转换为 FnCTOD DomainSpec"""
    domain_spec = DomainSpec(
        name=domain,
        description=schema.get("description", f"{domain}领域对话")
    )
    
    for slot_name, slot_info in schema["slots"].items():
        param = FunctionParameter(
            name=slot_name,
            description=slot_info.get("description", slot_name),
            param_type=ParameterType.STRING,
            required=False
        )
        domain_spec.add_parameter(param)
    
    return domain_spec

# 使用
hotel_schema = adapter.get_domain_schema("酒店")
hotel_spec = create_domain_spec("酒店", hotel_schema)
print(f"FnCTOD DomainSpec 创建完成: {hotel_spec.name}")
```

## API 文档

### TransferTODAdapter 类

#### 核心方法

##### `get_domain_schema(domain: str) -> Dict`

获取指定域的槽位 Schema。

**参数：**
- `domain`: 域名称（如 "酒店"、"餐厅"）

**返回：**
```python
{
    "domain": "酒店",
    "description": "酒店领域的对话任务处理",
    "slots": {
        "hotel_name": {
            "type": "string",
            "description": "hotel_name（如：华盛顿酒店、希尔顿酒店）",
            "occurrence_count": 150,
            "example_values": ["华盛顿酒店", "希尔顿酒店", "万豪酒店"]
        },
        # ... 更多槽位
    },
    "metadata": {
        "dialogue_count": 200,
        "slot_count": 15,
        "source": "TransferTOD数据集自动提取"
    }
}
```

##### `get_all_domains() -> List[str]`

获取数据集中所有可用的域列表。

**返回：** 域名称列表（已排序）

##### `get_all_domain_schemas() -> Dict[str, Dict]`

获取所有域的 Schema 定义。

**返回：** 字典，键为域名称，值为该域的 Schema

##### `get_transfertod_30_domains() -> List[str]` (静态方法)

获取 TransferTOD 项目的 30 个标准域列表。

**返回：** 30 个域的中文名称列表

#### 对话数据加载

##### `load_dialogue(dialogue_id: str) -> DialogueInstance`

加载单个对话实例。

##### `get_dialogues_by_domain(domain: str, data_type: str) -> List[str]`

获取指定域和数据类型的对话 ID 列表。

## Schema 结构

### 基本结构

每个域的 Schema 包含：

```python
{
    "domain": str,           # 域名称
    "description": str,      # 域描述
    "slots": {               # 槽位定义
        "slot_name": {
            "type": str,                    # 数据类型
            "description": str,             # 槽位描述（含示例）
            "occurrence_count": int,        # 出现次数
            "example_values": List[str]     # 示例值
        }
    },
    "metadata": {            # 元数据
        "dialogue_count": int,              # 对话数量
        "slot_count": int,                  # 槽位数量
        "source": str                       # 数据来源
    }
}
```

### Schema 提取过程

1. **数据来源**：扫描该域的所有对话文件
2. **槽位收集**：从每轮对话的 `expected_slots` 和 `final_state` 收集
3. **示例生成**：收集槽位的实际值作为示例
4. **统计信息**：计算出现次数和对话数量
5. **描述增强**：基于示例值生成更详细的描述

## 使用场景

### 1. FnCTOD 函数预定义

```python
from benchmark.datasets.transfertod.adapter import TransferTODAdapter
from contextmind.modes.fnctod import FunctionManager

adapter = TransferTODAdapter("./data/TransferTOD")
function_manager = FunctionManager()

# 为所有 30 个域添加预定义函数
for domain in TransferTODAdapter.get_transfertod_30_domains():
    schema = adapter.get_domain_schema(domain)
    domain_spec = create_domain_spec(domain, schema)
    function_manager.add_domain(domain_spec)

print(f"已加载 {len(function_manager.domains)} 个域的函数定义")
```

### 2. 批量评测

```python
# 对所有域进行评测
for domain in adapter.get_all_domains():
    dialogues = adapter.get_dialogues_by_domain(domain, "clean")
    print(f"{domain}: {len(dialogues)} 个对话")
    
    # 初始化该域的追踪器
    schema = adapter.get_domain_schema(domain)
    # ... 进行评测
```

### 3. Schema 导出

```bash
# 导出所有 Schema 为 JSON 文件
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --output benchmark/configs/transfertod_30_domains_schemas.json
```

## 示例输出

### 酒店域 Schema 示例

```json
{
  "domain": "酒店",
  "description": "酒店领域的对话任务处理",
  "slots": {
    "hotel_name": {
      "type": "string",
      "description": "hotel_name（如：华盛顿酒店、希尔顿酒店、万豪酒店）",
      "occurrence_count": 150,
      "example_values": ["华盛顿酒店", "希尔顿酒店", "万豪酒店"]
    },
    "check_in_date": {
      "type": "string",
      "description": "check_in_date（如：2024-01-15、明天、下周一）",
      "occurrence_count": 145,
      "example_values": ["2024-01-15", "明天", "下周一"]
    },
    "room_type": {
      "type": "string",
      "description": "room_type（如：标准间、大床房、套房）",
      "occurrence_count": 120,
      "example_values": ["标准间", "大床房", "套房"]
    }
  },
  "metadata": {
    "dialogue_count": 200,
    "slot_count": 15,
    "source": "TransferTOD数据集自动提取"
  }
}
```

## 注意事项

1. **数据集路径**：确保 TransferTOD 数据集正确下载并放置在指定路径
2. **性能考虑**：首次提取 Schema 时会遍历所有对话，建议使用缓存
3. **中文域名**：所有域名使用中文，与 TransferTOD 项目保持一致
4. **Schema 缓存**：Adapter 会自动缓存已提取的 Schema，避免重复计算

## 相关文件

- `benchmark/datasets/transfertod/adapter.py` - TransferTOD 适配器主文件
- `benchmark/extract_transfertod_schemas.py` - Schema 提取工具脚本
- `benchmark/run_fnctod_transfertod.py` - FnCTOD 评测脚本
- `benchmark/shared/configs/intent_labels_30_domains_Version2.json` - 30 域意图配置

## 参考资源

- TransferTOD 项目：https://github.com/KongLongGeFDU/TransferTOD
- FnCTOD 模式文档：`contextmind/modes/fnctod/README.md`
