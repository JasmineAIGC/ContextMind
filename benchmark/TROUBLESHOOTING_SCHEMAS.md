# TransferTOD Schema 提取故障排查指南

## 重要提示：默认行为已更新 ✅

**从最新版本开始，默认行为已更改：**
- ✅ **默认：只提取数据集中实际存在的域**（不会显示"不可用"）
- 这是推荐的使用方式，避免看到"数据集中不可用"的提示
- 如果您的数据集有 24 个域，就会提取 24 个域

**如果您想尝试提取标准 30 域列表：**
```bash
python benchmark/extract_transfertod_schemas.py \
    --data-root .data/TransferTOD/ \
    --use-standard-list
```
这将尝试提取所有 30 个标准域，对于不存在的域会显示"⚠️ 数据集中不可用"。

---

## 问题：某些域未被提取（使用 --use-standard-list 时）

如果使用 `--use-standard-list` 参数时发现某些域显示为"数据集中不可用"，请按照以下步骤排查。

### 步骤 1：运行诊断模式

```bash
python benchmark/extract_transfertod_schemas.py \
    --data-root .data/TransferTOD/ \
    --diagnostics
```

诊断模式会显示：
- 数据集中实际发现的所有域
- 标准列表中但数据集中未找到的域
- 数据集中有但标准列表中没有的域

### 步骤 2：分析诊断结果

#### 情况 A：发现"额外的域"

**现象：**
```
数据集中有但标准列表中没有的域（共 6 个）：
  + 打印服务
  + 摄影工作室
  + 飞机票
  + 理发
  + 演唱会
  + 餐馆
```

**原因：** 域名不匹配，数据集使用了不同的名称。

**解决方案：** 创建域名映射表

在 `adapter.py` 中添加：
```python
# 域名映射表：标准名称 -> 数据集中的实际名称
DOMAIN_NAME_MAPPING = {
    "打印": "打印服务",
    "摄影": "摄影工作室",
    "机票": "飞机票",
    "理发店": "理发",
    "音乐会": "演唱会",
    "餐厅": "餐馆"
}

@staticmethod
def normalize_domain_name(domain: str) -> str:
    """将标准域名转换为数据集中的实际名称"""
    return DOMAIN_NAME_MAPPING.get(domain, domain)
```

然后更新提取逻辑：
```python
# 在 extract_all_schemas 中
for domain in standard_domains:
    actual_domain_name = TransferTODAdapter.normalize_domain_name(domain)
    if actual_domain_name in available_domains:
        # 使用 actual_domain_name 提取
        schema = adapter.get_domain_schema(actual_domain_name)
        # 但在结果中使用标准名称
        all_schemas[domain] = schema
```

#### 情况 B：没有额外的域

**现象：**
```
标准列表中但数据集中未找到的域（共 6 个）：
  - 打印
  - 摄影
  - 机票
  - 理发店
  - 音乐会
  - 餐厅

数据集中有但标准列表中没有的域（共 0 个）：
（无）
```

**原因：** 这些域的数据真的不在数据集中。

**解决方案：** 

✅ **推荐：使用默认模式（不使用 --use-standard-list）**
```bash
# 不需要任何特殊参数，直接运行
python benchmark/extract_transfertod_schemas.py \
    --data-root .data/TransferTOD/ \
    --output schemas.json
```
这将只提取数据集中实际存在的 24 个域，不会显示"不可用"的提示。

**其他选项：**

**选项 1：** 从标准列表中移除这些域
```python
# 更新 get_transfertod_30_domains() 方法
# 只列出数据集中实际存在的 24 个域
```

**选项 2：** 继续使用 --use-standard-list 但接受某些域不可用
```bash
# 输出会包含"⚠️ 数据集中不可用"的提示
# 这对于文档目的可能有用（显示哪些域缺失）
```

**选项 3：** 补充缺失的数据
- 从其他来源获取这些域的对话数据
- 按照 TransferTOD 格式添加到数据集

#### 情况 C：扫描时出现大量错误

**现象：**
```
扫描 6000 个对话以查找所有域...
  警告: 无法加载对话 clean/xxx.json:1: ...
  警告: 无法加载对话 clean/yyy.json:2: ...
  ...
  跳过了 500 个无法加载的对话
```

**原因：** 数据文件格式问题或路径问题。

**解决方案：**
1. 检查数据集结构是否正确：
   ```
   TransferTOD/
   └── data/
       └── raw_data/
           ├── clean/
           └── noise/
   ```

2. 检查 JSON 文件格式是否正确

3. 查看具体的错误消息，修复数据或适配器代码

### 步骤 3：查看特定域的详细信息

如果诊断显示某个域存在，但想查看其详细信息：

```bash
python benchmark/extract_transfertod_schemas.py \
    --data-root .data/TransferTOD/ \
    --domain 酒店
```

这会显示：
- 域的槽位数量
- 每个槽位的描述和示例值
- 对话数量

### 步骤 4：应用修复并重新提取

修复后，重新运行提取：

```bash
python benchmark/extract_transfertod_schemas.py \
    --data-root .data/TransferTOD/ \
    --output schemas.json
```

验证结果：
```
成功提取 30 个域的 Schema  # 应该是 30 而不是 24
```

## 常见问题

### Q1：为什么标准列表是 30 个域？

A：TransferTOD 项目定义了 30 个标准任务域，这是项目的官方规范。参考：
- `benchmark/shared/configs/intent_labels_30_domains_Version2.json`
- https://github.com/KongLongGeFDU/TransferTOD

### Q2：可以使用 24 个域而不是 30 个吗？

A：可以。如果数据集中确实只有 24 个域，可以：
1. 更新 `get_transfertod_30_domains()` 只返回可用的域
2. 在文档中说明实际可用域数
3. 使用 `get_all_domains()` 动态获取域列表

### Q3：域名必须是中文吗？

A：不必须，但 TransferTOD 数据集使用中文域名。如果需要英文，可以：
1. 创建中英文映射表
2. 在 API 层面做转换
3. 修改数据集使用英文名称

### Q4：如何添加自定义域？

A：在数据集目录中添加新的对话文件，格式与现有文件一致。适配器会自动发现新域。

## 进一步帮助

如果问题仍未解决：
1. 检查 GitHub Issues
2. 提交新 Issue 并附上诊断输出
3. 查看 TransferTOD 项目文档
