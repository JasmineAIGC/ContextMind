# FnCTOD + RiSAWOZ 脚本 Bug 修复文档

## 概述

本文档记录了 `benchmark/run_fnctod_risawoz.py` 脚本中发现并修复的关键bug。

## 修复的问题

### 问题1: FunctionParameter 参数名称错误

**位置**: Line 145

**错误代码**:
```python
param = FunctionParameter(
    name=slot_name,
    type=param_type,  # ❌ 错误: 应该是 param_type
    description=f"{domain}领域的{slot_name}槽位",
    required=False,
    enum_values=slot_info.get('values', []) if isinstance(slot_info, dict) else []
)
```

**错误原因**:
- `FunctionParameter` 数据类定义中参数名是 `param_type`，不是 `type`
- 使用错误的参数名会导致 `TypeError: __init__() got an unexpected keyword argument 'type'`

**修复代码**:
```python
param = FunctionParameter(
    name=slot_name,
    param_type=param_type,  # ✅ 正确: 使用 param_type
    description=f"{domain}领域的{slot_name}槽位",
    required=False,
    enum_values=enum_values
)
```

**参考**: `contextmind/modes/fnctod/data_models.py` Line 22-29
```python
@dataclass
class FunctionParameter:
    """函数参数定义"""
    name: str
    description: str
    param_type: ParameterType = ParameterType.STRING  # 注意是 param_type
    required: bool = False
    enum_values: Optional[List[str]] = None
```

---

### 问题2: 不存在的 ParameterType.ENUM

**位置**: Lines 135, 140

**错误代码**:
```python
# 如果有values列表，则为枚举类型
if isinstance(slot_info, dict):
    values = slot_info.get('values', [])
    if values and len(values) > 0:
        param_type = ParameterType.ENUM  # ❌ 错误: ENUM 不存在
```

**错误原因**:
- `ParameterType` 枚举只定义了: STRING, NUMBER, BOOLEAN, ARRAY, OBJECT
- 没有 ENUM 类型
- 使用不存在的枚举值会导致 `AttributeError: type object 'ParameterType' has no attribute 'ENUM'`

**修复代码**:
```python
# 确定参数类型
param_type = ParameterType.STRING  # ✅ 始终使用 STRING
enum_values = []

# 如果有values列表，将它们存储在enum_values中
if isinstance(slot_info, dict):
    values = slot_info.get('values', [])
    if values and len(values) > 0:
        enum_values = values  # ✅ 通过 enum_values 参数传递
```

**参考**: `contextmind/modes/fnctod/data_models.py` Line 12-18
```python
class ParameterType(Enum):
    """参数类型枚举"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    # 注意: 没有 ENUM
```

**设计说明**:
- 枚举值通过 `enum_values` 参数传递，而不是通过类型
- 类型保持为 `STRING`，但同时提供 `enum_values` 列表
- 这样可以在生成 JSON schema 时添加 `"enum": [...]` 约束

---

### 问题3: 不存在的 LogLevel.ERROR

**位置**: Lines 462-463, 469-473

**错误代码**:
```python
# Line 462-463
parser.add_argument("--log-level", type=str, default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],  # ❌ ERROR 不存在
                   help="日志级别 (默认: INFO)")

# Line 469-473
log_level_map = {
    "DEBUG": LogLevel.DEBUG,
    "INFO": LogLevel.INFO,
    "WARNING": LogLevel.WARNING,
    "ERROR": LogLevel.ERROR  # ❌ 错误: ERROR 不存在
}
```

**错误原因**:
- `LogLevel` 枚举只定义了: INFO, DEBUG, WARNING
- 没有 ERROR 级别
- 使用不存在的枚举值会导致 `AttributeError: type object 'LogLevel' has no attribute 'ERROR'`

**修复代码**:
```python
# Line 462-463
parser.add_argument("--log-level", type=str, default="INFO",
                   choices=["DEBUG", "INFO", "WARNING"],  # ✅ 只包含存在的级别
                   help="日志级别 (默认: INFO)")

# Line 469-472
log_level_map = {
    "DEBUG": LogLevel.DEBUG,
    "INFO": LogLevel.INFO,
    "WARNING": LogLevel.WARNING
    # ✅ 移除了 ERROR
}
```

**参考**: `contextmind/infra/logger.py` Line 13-17
```python
class LogLevel(PyEnum):
    """Evolve 日志级别"""
    INFO = "INFO"      # 信息模式
    DEBUG = "DEBUG"    # 调试模式
    WARNING = "WARNING"  # 警告模式
    # 注意: 没有 ERROR
```

---

## 修复前后对比

### 修复前
运行脚本会立即失败，出现以下错误:

```bash
$ python benchmark/run_fnctod_risawoz.py

Traceback (most recent call last):
  File "benchmark/run_fnctod_risawoz.py", line 145, in _create_domain_spec_from_schema
    param = FunctionParameter(
TypeError: __init__() got an unexpected keyword argument 'type'
```

或者:

```bash
AttributeError: type object 'ParameterType' has no attribute 'ENUM'
```

或者:

```bash
AttributeError: type object 'LogLevel' has no attribute 'ERROR'
```

### 修复后
脚本可以正常运行:

```bash
$ python benchmark/run_fnctod_risawoz.py --limit 5

======================================================================
FnCTOD模式 - RiSAWOZ数据集评测
======================================================================
数据集划分: val
领域过滤: 全部
测试对话数: 5
======================================================================

✅ LLM客户端初始化成功
✅ FnCTOD追踪器初始化完成 - 领域: 景点
✅ 对话 1/5 完成
...
```

---

## 验证方法

### 1. 语法验证
```bash
python -m py_compile benchmark/run_fnctod_risawoz.py
echo $?  # 应该输出 0
```

### 2. 导入测试
```python
import sys
sys.path.insert(0, '/path/to/ContextMind')
from benchmark.run_fnctod_risawoz import FnCTODRiSAWOZTest

# 如果没有错误，说明修复成功
print("✅ 导入成功")
```

### 3. 参数创建测试
```python
from contextmind.modes.fnctod.data_models import FunctionParameter, ParameterType

# 测试修复后的参数创建
param = FunctionParameter(
    name="test_param",
    param_type=ParameterType.STRING,  # ✅ 使用 param_type
    description="测试参数",
    required=False,
    enum_values=["选项1", "选项2"]
)

print(f"✅ 参数创建成功: {param.name}")
```

### 4. 日志级别测试
```python
from contextmind.infra.logger import LogLevel, setup_logging

# 测试所有有效的日志级别
for level in [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING]:
    setup_logging(level=level)
    print(f"✅ 日志级别 {level.value} 设置成功")
```

---

## 相关文件

### 修改的文件
- `benchmark/run_fnctod_risawoz.py` (8行修改)

### 参考的定义文件
- `contextmind/modes/fnctod/data_models.py` - FunctionParameter 和 ParameterType 定义
- `contextmind/infra/logger.py` - LogLevel 定义

### 参考的类似脚本
- `benchmark/run_fnctod_transfertod.py` - FnCTOD + TransferTOD (正确实现)
- `benchmark/run_dst_risawoz.py` - DST + RiSAWOZ (日志级别参考)

---

## 总结

### 修复的本质
1. **参数名称**: 使用正确的参数名 `param_type` 而不是 `type`
2. **枚举类型**: 使用 `STRING` 类型 + `enum_values` 参数，而不是不存在的 `ENUM` 类型
3. **日志级别**: 只使用存在的级别 (DEBUG, INFO, WARNING)，移除 ERROR

### 为什么会出现这些bug
- 可能是复制其他语言或框架的代码模式，但没有适配到当前代码库
- 可能是假设存在某些枚举值，但实际没有定义
- 缺少对数据类定义和枚举定义的检查

### 如何避免类似bug
1. **查看数据类定义**: 使用 dataclass 前先查看其定义
2. **检查枚举值**: 使用枚举前确认该值存在
3. **参考现有代码**: 类似功能参考已有的正确实现
4. **语法验证**: 提交前运行 `py_compile` 检查
5. **单元测试**: 为关键组件添加测试

---

**修复日期**: 2026-02-25
**修复人员**: GitHub Copilot
**文档版本**: 1.0
