# 如何使用 schemas.json 文件进行 FnCTOD 评测

## 概述

本文档说明如何使用 `extract_transfertod_schemas.py` 生成的 `schemas.json` 文件来加速 FnCTOD 评测，以及如何运行 `test_fnctod_transferTOD`。

## 快速开始

### 步骤 1: 生成 schemas.json 文件

首先，使用 `extract_transfertod_schemas.py` 脚本从 TransferTOD 数据集提取所有域的 schema：

```bash
# 提取所有域的 schemas 并保存到文件
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --output transfertod_schemas.json
```

这将生成一个包含所有 30 个域的槽位定义的 JSON 文件。

**输出示例：**
```
================================================================================
从 TransferTOD 数据集提取域-槽位预定义信息
================================================================================
数据路径: ./data/TransferTOD

TransferTOD 标准域数量: 30

数据集中可用域数量: 30

开始提取域 Schema...
--------------------------------------------------------------------------------
 1. ✅ 保洁      - 12 个槽位,  150 个对话
 2. ✅ 健身房    - 10 个槽位,  120 个对话
...
30. ✅ 餐厅      - 15 个槽位,  200 个对话
--------------------------------------------------------------------------------

成功提取 30 个域的 Schema

================================================================================
汇总统计
================================================================================
总域数:     30
总槽位数:   450
总对话数:   4500

✅ Schema 已保存到: transfertod_schemas.json
   文件大小: 125.3 KB
```

### 步骤 2: 使用 schemas.json 运行测试

有两种方式运行 FnCTOD 评测：

#### 方式 1: 使用预加载的 schemas.json（推荐）

**优点：**
- ⚡ 启动速度快（无需扫描数据集）
- ✅ Schema 一致性保证
- 📦 可以在没有完整数据集的情况下测试

```bash
# 使用 schemas.json 文件运行测试
python benchmark/run_fnctod_transfertod.py \
    --domain 酒店 \
    --limit 10 \
    --schemas-file transfertod_schemas.json
```

#### 方式 2: 动态提取 schemas（传统方式）

如果不指定 `--schemas-file`，脚本会从数据集动态提取：

```bash
# 不使用 schemas 文件，每次从数据集提取
python benchmark/run_fnctod_transfertod.py \
    --domain 酒店 \
    --limit 10
```

## 详细使用说明

### 命令行参数

`run_fnctod_transfertod.py` 脚本支持以下参数：

```bash
python benchmark/run_fnctod_transfertod.py [OPTIONS]

选项:
  --domain DOMAIN              指定测试领域（如：酒店、餐厅）
  --limit LIMIT                限制测试对话数量
  --data-type {clean,noise}    数据类型（默认: clean）
  --data-root DATA_ROOT        数据集根目录（默认: ./data/TransferTOD/）
  --schemas-file FILE          预加载的 schemas JSON 文件路径（可选）
  --verbose                    输出详细日志
  --no-verbose                不输出详细日志（默认）
```

### 使用场景

#### 场景 1: 快速测试单个域

```bash
# 使用预加载 schemas，测试酒店域的 10 个对话
python benchmark/run_fnctod_transfertod.py \
    --domain 酒店 \
    --limit 10 \
    --schemas-file transfertod_schemas.json
```

**输出示例：**
```
======================================================================
=== FnCTOD on TransferTOD 评测 ===
======================================================================
脚本版本: 2024-02-10 (完整评测版本)
======================================================================

📁 使用预加载的schemas文件: transfertod_schemas.json

✅ 从文件加载了 30 个域的schemas: transfertod_schemas.json
找到 200 个对话实例
限制测试数量: 10

初始化领域: 酒店
✅ FnCTOD模式初始化完成 - 领域: 酒店
   函数调用模式: 两阶段（domain选择 + parameter填充）
   预定义槽位数: 15

开始评测...
...
```

#### 场景 2: 测试多个域

```bash
# 不指定 --domain，测试所有可用域
python benchmark/run_fnctod_transfertod.py \
    --limit 5 \
    --schemas-file transfertod_schemas.json
```

#### 场景 3: 详细调试模式

```bash
# 启用详细日志
python benchmark/run_fnctod_transfertod.py \
    --domain 餐厅 \
    --limit 5 \
    --schemas-file transfertod_schemas.json \
    --verbose
```

#### 场景 4: 测试噪声数据

```bash
# 使用 noise 数据类型
python benchmark/run_fnctod_transfertod.py \
    --domain 酒店 \
    --data-type noise \
    --limit 10 \
    --schemas-file transfertod_schemas.json
```

## schemas.json 文件格式

生成的 `schemas.json` 文件格式如下：

```json
{
  "dataset": "TransferTOD",
  "source": "https://github.com/KongLongGeFDU/TransferTOD",
  "total_domains": 30,
  "domains": {
    "酒店": {
      "domain": "酒店",
      "description": "酒店领域的对话任务处理",
      "slots": {
        "hotel_name": {
          "type": "string",
          "description": "hotel_name（如：华盛顿酒店, 希尔顿酒店, 万豪酒店）",
          "occurrence_count": 150,
          "example_values": ["华盛顿酒店", "希尔顿酒店", "万豪酒店"]
        },
        "check_in_date": {
          "type": "string",
          "description": "check_in_date（如：2024-01-15, 明天, 下周一）",
          "occurrence_count": 145,
          "example_values": ["2024-01-15", "明天", "下周一"]
        }
      },
      "metadata": {
        "dialogue_count": 200,
        "slot_count": 15,
        "source": "TransferTOD数据集自动提取"
      }
    },
    "餐厅": {
      ...
    }
  }
}
```

## 优势对比

### 使用 schemas.json 文件

✅ **优点：**
- 快速启动（无需扫描数据集）
- Schema 一致性（所有测试使用相同的 schema）
- 可移植性（可以在不同环境使用）
- 离线使用（不需要完整数据集）

❌ **缺点：**
- 需要先生成文件
- 如果数据集更新，需要重新生成

### 动态提取 schemas

✅ **优点：**
- 总是使用最新的数据集
- 无需额外步骤

❌ **缺点：**
- 每次启动都需要扫描数据集（慢）
- 不同时间的测试可能使用不同的 schema

## 常见问题

### Q1: schemas.json 文件放在哪里？

A: 可以放在任何位置，通过 `--schemas-file` 指定路径即可。推荐放在项目根目录：

```bash
# 在项目根目录
./transfertod_schemas.json

# 使用时
python benchmark/run_fnctod_transfertod.py \
    --schemas-file ./transfertod_schemas.json
```

### Q2: 如何更新 schemas.json？

A: 重新运行 `extract_transfertod_schemas.py` 脚本：

```bash
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --output transfertod_schemas.json
```

### Q3: 可以只提取特定域的 schema 吗？

A: 目前 `extract_transfertod_schemas.py` 提取所有域，但你可以手动编辑 JSON 文件只保留需要的域。或者查看特定域：

```bash
# 查看特定域的详细信息
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --domain 酒店
```

### Q4: 如果 schemas.json 文件格式错误会怎样？

A: 脚本会报错并提示：

```
❌ 错误: Schemas文件格式错误: 缺少 'domains' 字段
```

确保文件是由 `extract_transfertod_schemas.py` 生成的，或者格式与之一致。

### Q5: 可以在没有数据集的情况下测试吗？

A: 如果只需要测试 schema 定义和函数调用逻辑，可以使用 schemas.json 文件。但实际运行对话测试仍需要数据集中的对话数据。

## 性能对比

### 启动时间对比（测试环境：30 个域，约 4500 个对话）

| 方式 | 首次启动时间 | 后续启动时间 |
|------|-------------|-------------|
| 动态提取 | ~30 秒 | ~30 秒 |
| 使用 schemas.json | ~2 秒 | ~2 秒 |

**提速约 15 倍！**

## 完整示例

### 示例 1: 完整工作流程

```bash
# 步骤 1: 提取 schemas
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --output transfertod_schemas.json

# 步骤 2: 测试酒店域
python benchmark/run_fnctod_transfertod.py \
    --domain 酒店 \
    --limit 20 \
    --schemas-file transfertod_schemas.json

# 步骤 3: 测试餐厅域
python benchmark/run_fnctod_transfertod.py \
    --domain 餐厅 \
    --limit 20 \
    --schemas-file transfertod_schemas.json
```

### 示例 2: 批量测试脚本

创建一个脚本 `test_all_domains.sh`：

```bash
#!/bin/bash

# 生成 schemas
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --output transfertod_schemas.json

# 测试所有域
for domain in 酒店 餐厅 景点 机票 火车票; do
    echo "Testing domain: $domain"
    python benchmark/run_fnctod_transfertod.py \
        --domain "$domain" \
        --limit 10 \
        --schemas-file transfertod_schemas.json
done
```

## 总结

使用 `schemas.json` 文件可以：

1. ⚡ **加速测试**：避免每次扫描数据集
2. ✅ **确保一致性**：所有测试使用相同的 schema
3. 📦 **提高可移植性**：schema 可以独立于数据集使用
4. 🔧 **简化调试**：固定的 schema 便于问题排查

**推荐工作流程：**
1. 首次设置时生成 `transfertod_schemas.json`
2. 日常测试时使用 `--schemas-file` 参数
3. 数据集更新后重新生成 schemas 文件
