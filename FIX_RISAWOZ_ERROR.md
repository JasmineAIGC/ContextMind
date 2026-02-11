# RiSAWOZ 评测脚本错误修复

## 问题描述

用户在运行以下命令时遇到错误：

```bash
python benchmark/run_dst_risawoz.py --val-file .data/RiSAWOZ/task1-data/val.json
```

错误输出：
```
[2026-02-11 14:56:08] INFO - [main] 根据文件路径自动设置 split=val
[2026-02-11 14:56:08] INFO - [benchmark.shared.intent_label_loader] 已加载 30 个领域的意图标签
Traceback (most recent call last):
File "/share/airesearch/data/yejiang.zhou/workspace/ContextMind/benchmark/run_dst_risawoz.py", line 620, in 
```

## 根本原因

脚本正确解析了文件路径参数，但在尝试加载数据文件时发现文件不存在。原始错误消息不够清晰，用户难以定位问题所在。

## 解决方案

### 1. 添加文件存在性预检查

在尝试创建测试实例和加载数据之前，先验证数据文件是否存在：

```python
# 验证将要使用的数据文件是否存在
expected_file = Path(data_root) / file_mapping.get(args.split, f"{args.split}.json")
logger.info(f"将要加载的数据文件: {expected_file}")

if not expected_file.exists():
    # 显示详细的错误信息
    error_msg = (...)
    logger.error(error_msg)
    print(error_msg, file=sys.stderr)
    sys.exit(1)
```

### 2. 改进错误消息

提供清晰、结构化的错误信息，包括：

- 绝对文件路径
- 数据根目录
- 当前工作目录
- 具体的检查建议
- 使用提示

### 3. 修复返回值问题

修复了 `_print_summary()` 函数在没有成功评测结果时的返回值：

```python
# 修改前
if not all_metrics:
    print("\n⚠️  没有成功评测的对话")
    return  # 返回 None

# 修改后
if not all_metrics:
    print("\n⚠️  没有成功评测的对话")
    return "", []  # 返回空的 tuple
```

## 新的错误消息示例

当文件不存在时，用户会看到：

```
======================================================================
❌ 错误：数据文件不存在
======================================================================

文件路径: /home/user/ContextMind/.data/RiSAWOZ/task1-data/val.json
数据根目录: /home/user/ContextMind/.data/RiSAWOZ/task1-data
文件名: val.json
数据划分: val

请检查：
1. 文件路径是否正确
2. 文件是否存在于指定位置
3. 当前工作目录: /home/user/ContextMind

提示：
- 如果使用相对路径，请确保从正确的目录运行脚本
- 建议使用绝对路径以避免路径问题
- 使用 --val-file 时，请提供完整的文件路径
======================================================================
```

## 使用建议

### 1. 使用绝对路径

最可靠的方式是使用绝对路径：

```bash
python benchmark/run_dst_risawoz.py --val-file /path/to/RiSAWOZ/task1-data/val.json
```

### 2. 确认文件存在

运行前先确认文件存在：

```bash
ls -la .data/RiSAWOZ/task1-data/val.json
```

### 3. 检查工作目录

确保从正确的目录运行脚本：

```bash
cd /path/to/ContextMind
python benchmark/run_dst_risawoz.py --val-file data/RiSAWOZ/task1-data/val.json
```

### 4. 查看日志输出

脚本现在会显示：
- 数据根目录
- 数据划分
- 文件映射
- 将要加载的数据文件路径

这些信息有助于诊断路径问题。

## 测试验证

### 测试 1：不存在的文件

```bash
python benchmark/run_dst_risawoz.py --val-file .data/RiSAWOZ/task1-data/val.json --limit 1
```

结果：✅ 显示清晰的错误消息，不再抛出未处理的异常

### 测试 2：存在的文件

```bash
python benchmark/run_dst_risawoz.py --val-file /tmp/test_data/val.json --limit 1
```

结果：✅ 文件验证通过，脚本正常执行

## 相关文件

- `benchmark/run_dst_risawoz.py` - 主评测脚本（已修改）
- 提交: 01d588d

## 总结

此修复提升了脚本的用户体验，使错误信息更加清晰明确，帮助用户快速定位和解决路径相关问题。
