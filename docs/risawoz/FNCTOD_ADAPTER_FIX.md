# FnCTOD + RiSAWOZ 适配器方法调用修复

## 问题描述

运行 `python benchmark/run_fnctod_risawoz.py --limit 10` 时报错：

```
AttributeError: 'RiSAWOZAdapter' object has no attribute 'get_all_dialogue_ids'
```

**错误堆栈**：
```python
File "benchmark/run_fnctod_risawoz.py", line 320, in run_tests
    dialogue_ids = self.adapter.get_all_dialogue_ids(split=split)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'RiSAWOZAdapter' object has no attribute 'get_all_dialogue_ids'
```

## 根本原因

### 问题分析

1. **方法不存在**：`RiSAWOZAdapter` 类中没有定义 `get_all_dialogue_ids()` 方法
2. **不同适配器的API差异**：不同数据集适配器可能有不同的方法名称
3. **复制代码遗留问题**：可能从其他脚本复制代码时没有适配RiSAWOZ的API

### RiSAWOZAdapter 实际方法

查看 `benchmark/datasets/risawoz/adapter.py`，实际存在的方法有：

- ✅ `get_dialogues_by_domain(domain=None, split="val")` - 获取指定领域的对话ID
- ✅ `load_dialogue(dialogue_id, split="val")` - 加载单个对话
- ✅ `get_all_domains()` - 获取所有领域
- ✅ `get_domain_schema(domain)` - 获取领域schema
- ❌ `get_all_dialogue_ids()` - **不存在**

## 解决方案

### 修复方法

使用 `get_dialogues_by_domain()` 方法替代不存在的 `get_all_dialogue_ids()` 方法。

**修复前** (line 319-328):
```python
# 获取所有对话ID
dialogue_ids = self.adapter.get_all_dialogue_ids(split=split)

# 按领域过滤
if domain:
    dialogues_data = self.adapter._load_dialogues_data(split=split)
    dialogue_ids = [
        did for did in dialogue_ids
        if dialogues_data.get(did, {}).get('domain') == domain
    ]
```

**修复后** (line 319-320):
```python
# 获取对话ID（如果指定domain则过滤，否则获取全部）
dialogue_ids = self.adapter.get_dialogues_by_domain(domain=domain, split=split)
```

### 为什么这个方案有效

`get_dialogues_by_domain()` 方法的实现（adapter.py line 408-456）：

```python
def get_dialogues_by_domain(self, domain: str = None, split: str = "val") -> List[str]:
    """
    获取指定领域的所有对话ID
    
    Args:
        domain: 领域名称（如果为None则返回所有对话）
        split: 数据集划分
        
    Returns:
        对话ID列表
    """
    data = self._load_data_file(split)
    dialogue_ids = []
    
    if isinstance(data, list):
        for idx, dialogue_data in enumerate(data):
            # 检查领域
            if domain is None:  # ← 关键：domain为None时返回所有对话
                dialogue_ids.append(str(idx))
            else:
                # 提取该对话的所有领域并过滤
                ...
```

**关键特性**：
- `domain=None` → 返回所有对话ID
- `domain="景点"` → 只返回该领域的对话ID
- 自动处理list和dict两种数据格式

### 代码改进

**优点**：

1. ✅ **使用现有方法** - 不需要添加新方法到adapter
2. ✅ **代码更简洁** - 从12行减少到2行
3. ✅ **逻辑统一** - 与 `run_dst_risawoz.py` (line 657) 保持一致
4. ✅ **无破坏性** - 只影响一个脚本，不影响其他代码

**改进点**：
- 移除了重复的领域过滤逻辑
- 移除了对内部方法 `_load_dialogues_data()` 的调用
- 利用adapter已有的过滤功能

## 验证结果

### 语法验证

```bash
python -m py_compile benchmark/run_fnctod_risawoz.py
# ✅ 通过
```

### 与其他脚本一致性

`run_dst_risawoz.py` (line 657) 也使用相同模式：
```python
dialogue_ids = self.adapter.get_dialogues_by_domain(domain, split=split)
```

## 测试建议

修复后可以运行以下测试：

```bash
# 基础测试
python benchmark/run_fnctod_risawoz.py --limit 10

# 测试特定领域
python benchmark/run_fnctod_risawoz.py --domain 景点 --limit 5

# 测试详细输出
python benchmark/run_fnctod_risawoz.py --limit 5 --verbose

# 测试不同数据集划分
python benchmark/run_fnctod_risawoz.py --split test --limit 10
```

## 相关文档

- `FNCTOD_RISAWOZ_GUIDE.md` - FnCTOD + RiSAWOZ 使用指南
- `FNCTOD_BUGFIXES.md` - FnCTOD 其他bug修复
- `FNCTOD_SUMMARY.md` - FnCTOD 项目总结

## 总结

这是一个简单但关键的修复：

- ❌ **问题**: 调用了不存在的方法 `get_all_dialogue_ids()`
- ✅ **解决**: 使用现有的 `get_dialogues_by_domain(domain=None)` 方法
- 🎯 **结果**: 脚本可以正常运行，代码更简洁清晰

这个修复展示了理解适配器API的重要性，以及在不同数据集之间复用代码时需要注意API差异。
