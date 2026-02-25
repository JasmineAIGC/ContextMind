# FnCTOD + RiSAWOZ 评测指南

## 概述

本文档介绍如何使用 `run_fnctod_risawoz.py` 脚本在 RiSAWOZ 数据集上评测 FnCTOD 模式。

### 什么是 FnCTOD？

**FnCTOD** (Function Calling for Task-Oriented Dialogue) 是一种基于函数调用的对话状态追踪方法：

- 将每个**领域**视为一个**函数**
- 将**槽位**视为函数的**参数**
- DST 任务转化为"调用正确的函数并填充参数"
- 更结构化、更易于扩展

### 与 DST 模式的区别

| 特性 | DST 模式 | FnCTOD 模式 |
|------|---------|------------|
| 核心思想 | 槽位-值提取 | 函数调用 |
| 表示方式 | `{slot: value}` | `function_name(param1=value1, ...)` |
| 领域处理 | 动态槽位 | 函数选择 |
| 结构化程度 | 中等 | 高 |
| 扩展性 | 好 | 更好 |

## 快速开始

### 1. 环境准备

确保已安装所有依赖：

```bash
pip install -r requirements.txt
```

需要的关键包：
- `openai` - LLM API 调用
- 其他标准包（已在 requirements.txt 中）

### 2. 数据准备

确保 RiSAWOZ 数据集已正确放置：

```
./data/RiSAWOZ/
├── train.json
├── val.json
└── test.json
```

如果数据在其他位置，使用 `--data-root` 参数指定。

### 3. 配置 API 密钥

设置 LLM API 密钥环境变量：

```bash
# 通义千问
export QWEN3_API_KEY="your_api_key"

# 或者 OpenAI
export OPENAI_API_KEY="your_api_key"
```

### 4. 运行评测

#### 基础用法

```bash
# 测试验证集（默认）
python benchmark/run_fnctod_risawoz.py

# 测试特定领域
python benchmark/run_fnctod_risawoz.py --domain 景点

# 限制测试数量（快速测试）
python benchmark/run_fnctod_risawoz.py --limit 10

# 详细输出
python benchmark/run_fnctod_risawoz.py --domain 酒店 --limit 5 --verbose
```

#### 高级用法

```bash
# 使用测试集
python benchmark/run_fnctod_risawoz.py --split test --limit 20

# 自定义数据目录
python benchmark/run_fnctod_risawoz.py --data-root /path/to/risawoz

# 调试模式
python benchmark/run_fnctod_risawoz.py --log-level DEBUG --verbose --limit 3

# 完整评测（所有数据）
python benchmark/run_fnctod_risawoz.py --split val
```

## 评测指标

### 1. 参数准确率 (Parameter Accuracy)

**定义**: 正确提取的参数（槽位）占总参数的百分比

```
Parameter Accuracy = 正确参数数 / 总参数数
```

**示例**:
- 期望: `{景点-名称: "拙政园", 景点-区域: "苏州"}`
- 提取: `{景点-名称: "拙政园", 景点-区域: "苏州"}`
- 结果: 2/2 = 100%

### 2. 函数调用准确率 (Function Call Accuracy)

**定义**: 正确调用领域函数的轮次占总轮次的百分比

```
Function Call Accuracy = 正确调用次数 / 总轮次数
```

**说明**:
- 检查是否调用了正确的领域函数
- 每轮对话应该调用对应领域的函数

### 3. 意图准确率 (Intent Accuracy)

**定义**: 正确推断意图的轮次占总轮次的百分比

```
Intent Accuracy = 正确意图数 / 总轮次数
```

**意图类型** (RiSAWOZ):
- `Inform` - 提供信息
- `Request` - 请求信息
- `General` - 一般对话
- `Greeting` - 问候
- `Bye` - 告别

## 输出示例

### 简洁模式（默认）

```
======================================================================
FnCTOD模式 - RiSAWOZ数据集评测
======================================================================
数据集划分: val
领域过滤: 景点
测试对话数: 10
======================================================================

✅ 对话 1/10 完成: attraction_001
✅ 对话 2/10 完成: attraction_002
✅ 对话 3/10 完成: attraction_003
...

======================================================================
📊 评测结果汇总
======================================================================

【整体汇总统计】
----------------------------------------------------------------------
总测试对话数: 10
平均参数准确率 (Parameter Accuracy): 65.30%
  总参数数: 85, 正确参数数: 55
平均函数调用准确率 (Function Call Accuracy): 92.00%
  总调用数: 60, 正确调用数: 55
平均意图准确率 (Intent Accuracy): 70.50%
  总意图数: 60, 正确意图数: 42
----------------------------------------------------------------------
```

### 详细模式（--verbose）

```
======================================================================
测试对话: attraction_001
领域: 景点
======================================================================

--- 轮次 1 ---
系统: 您好，有什么可以帮您？
用户: 我想找苏州的景点
函数调用: 1个
  - 景点({景点-区域: "苏州"})
期望参数: {景点-区域: "苏州"}
提取参数: {景点-区域: "苏州"}
  ✓ 景点-区域: 苏州
轮次意图: Inform -> Inform ✓

--- 轮次 2 ---
系统: 苏州有很多著名景点，请问您想了解哪个？
用户: 拙政园怎么样？
函数调用: 1个
  - 景点({景点-名称: "拙政园", 景点-区域: "苏州"})
期望参数: {景点-名称: "拙政园"}
提取参数: {景点-名称: "拙政园"}
  ✓ 景点-名称: 拙政园
轮次意图: Request -> Request ✓

======================================================================
📊 对话评测结果
======================================================================
参数准确率 (Parameter Accuracy): 100.00%
函数调用准确率 (Function Call Accuracy): 100.00%
意图准确率 (Intent Accuracy): 100.00%
======================================================================
```

### 多领域评测

```
【分领域统计】
----------------------------------------------------------------------

景点领域 (对话数: 15):
  参数准确率: 68.20%
  函数调用准确率: 91.30%
  意图准确率: 72.50%

酒店领域 (对话数: 12):
  参数准确率: 71.50%
  函数调用准确率: 94.20%
  意图准确率: 75.80%

餐厅领域 (对话数: 10):
  参数准确率: 62.30%
  函数调用准确率: 88.50%
  意图准确率: 68.40%

【整体汇总统计】
----------------------------------------------------------------------
总测试对话数: 37
平均参数准确率: 67.60%
平均函数调用准确率: 91.20%
平均意图准确率: 72.30%
----------------------------------------------------------------------
```

## 技术细节

### FnCTOD 工作原理

1. **Schema 转换**
   ```python
   # RiSAWOZ Schema
   {
       "slots": {
           "名称": {"values": [...]},
           "区域": {"values": [...]}
       }
   }
   
   # ↓ 转换为 ↓
   
   # FnCTOD DomainSpec
   DomainSpec(
       name="景点",
       parameters=[
           FunctionParameter(name="名称", type=STRING, ...),
           FunctionParameter(name="区域", type=ENUM, ...)
       ]
   )
   ```

2. **函数调用处理**
   ```python
   # 用户输入
   "我想找苏州的拙政园"
   
   # FnCTOD 输出
   FunctionCall(
       function_name="景点",
       parameters={
           "名称": "拙政园",
           "区域": "苏州"
       }
   )
   ```

3. **两阶段处理**
   - **阶段1**: 确定应该调用哪个函数（领域选择）
   - **阶段2**: 提取函数参数（槽位填充）

### 数据格式适配

脚本自动处理 RiSAWOZ 的特殊字段：

- `transcript` → `user_utterance`
- `system_transcript` → `system_utterance`
- `belief_state` → `expected_slots`
- `user_acts` → `user_intents`

### 评测流程

1. 加载 RiSAWOZ 对话数据
2. 转换 schema 为 FnCTOD 格式
3. 初始化 FnCTODTracker
4. 逐轮处理对话：
   - 调用 tracker 处理用户输入
   - 获取函数调用和参数
   - 与 ground truth 比较
5. 计算各项指标
6. 输出汇总结果

## 常见问题

### Q1: 为什么所有指标都是 0%？

**可能原因**:
1. LLM API 密钥未设置或无效
2. 网络连接问题
3. API 配额不足

**解决方法**:
```bash
# 检查环境变量
echo $QWEN3_API_KEY
echo $OPENAI_API_KEY

# 重新设置
export QWEN3_API_KEY="your_valid_key"

# 测试连接
python -c "from contextmind.infra.llm_client import SimpleLLMClient; client = SimpleLLMClient(); print('✅ LLM连接成功')"
```

### Q2: FileNotFoundError: 数据文件不存在

**解决方法**:
```bash
# 检查数据目录
ls ./data/RiSAWOZ/

# 如果数据在其他位置
python benchmark/run_fnctod_risawoz.py --data-root /path/to/your/risawoz
```

### Q3: 参数准确率很低（<30%）

**可能原因**:
1. Schema 不匹配
2. LLM 提示词需要优化
3. 数据格式问题

**调试方法**:
```bash
# 使用详细模式查看具体问题
python benchmark/run_fnctod_risawoz.py --limit 1 --verbose --log-level DEBUG
```

### Q4: 如何测试单个对话？

```bash
# 使用 limit 1 并启用 verbose
python benchmark/run_fnctod_risawoz.py --limit 1 --verbose
```

### Q5: 支持哪些 RiSAWOZ 领域？

RiSAWOZ 包含 12 个领域：
- 景点 (Attraction)
- 酒店 (Hotel)
- 餐厅 (Restaurant)
- 地铁 (Metro)
- 出租 (Taxi)
- 火车 (Train)
- 电视剧 (TV Series)
- 天气 (Weather)
- 航班 (Flight)
- 医院 (Hospital)
- 电影 (Movie)
- 音乐 (Music)

## 最佳实践

### 1. 快速测试

开发时先用小数据量测试：

```bash
python benchmark/run_fnctod_risawoz.py --limit 5 --verbose
```

### 2. 领域测试

逐个领域测试，便于发现问题：

```bash
for domain in 景点 酒店 餐厅; do
    echo "测试领域: $domain"
    python benchmark/run_fnctod_risawoz.py --domain $domain --limit 10
done
```

### 3. 批量评测

正式评测使用完整数据：

```bash
# 验证集
python benchmark/run_fnctod_risawoz.py --split val

# 测试集
python benchmark/run_fnctod_risawoz.py --split test
```

### 4. 保存结果

将结果保存到文件：

```bash
python benchmark/run_fnctod_risawoz.py --split val 2>&1 | tee results_fnctod_risawoz.log
```

### 5. 性能优化

如果 API 调用较慢，可以：
- 使用更快的 LLM 服务
- 减少历史轮次数（默认10轮）
- 批量处理多个对话

## 进阶使用

### 自定义 Schema

如果需要自定义 schema：

```python
# 在脚本中修改 _create_domain_spec_from_schema 方法
def _create_domain_spec_from_schema(self, domain: str, schema: Dict) -> DomainSpec:
    # 自定义参数类型判断
    # 自定义必填参数
    # 自定义描述文本
    pass
```

### 修改评测指标

在 `test_dialogue` 方法中添加自定义指标：

```python
# 例如：计算完整度（所有必填参数都有值）
completeness = all(required_param in extracted_state for required_param in required_params)
```

### 对比 DST 和 FnCTOD

```bash
# 运行 DST 模式
python benchmark/run_dst_risawoz.py --limit 20 > dst_results.txt

# 运行 FnCTOD 模式
python benchmark/run_fnctod_risawoz.py --limit 20 > fnctod_results.txt

# 对比结果
diff dst_results.txt fnctod_results.txt
```

## 相关文档

- [RiSAWOZ 数据集说明](./RISAWOZ_TEST_README.md)
- [FnCTOD 模式文档](../../contextmind/modes/fnctod/README.md)
- [DST + RiSAWOZ 评测](./DST_QUALITY_IMPROVEMENT.md)
- [意图评测指南](./INTENT_INFERENCE_FIX.md)

## 总结

`run_fnctod_risawoz.py` 提供了在 RiSAWOZ 数据集上评测 FnCTOD 模式的完整解决方案：

✅ **易用性**: 简单的命令行界面
✅ **灵活性**: 支持多种评测配置
✅ **全面性**: 多维度评测指标
✅ **可读性**: 清晰的输出格式
✅ **可扩展性**: 易于修改和定制

开始使用：

```bash
python benchmark/run_fnctod_risawoz.py --domain 景点 --limit 10 --verbose
```
