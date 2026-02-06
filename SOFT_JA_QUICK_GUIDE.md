# Soft JA Quick Guide - 快速参考

## TL;DR

**问题**: JA = 0% 因为模型总是预测额外槽位  
**解决**: 添加Soft JA指标（允许额外槽位）  
**结果**: 两个指标一起使用，更好地诊断模型行为

---

## 快速理解

### 两种指标

| 指标 | 定义 | 何时 = 1.0 |
|------|------|-----------|
| **Strict JA** | 完全匹配 | `expected == extracted` |
| **Soft JA** | 子集匹配 | `expected ⊆ extracted` |

### 示例

```python
Expected: {("姓名", "张三"), ("电话", "123")}
Extracted: {("姓名", "张三"), ("电话", "123"), ("地址", "北京")}

Strict JA = 0.0  # 不相等（有额外）
Soft JA = 1.0    # 是子集（所有期望都在）
```

---

## 快速诊断表

| Strict JA | Soft JA | 问题 | 解决方案 |
|-----------|---------|------|---------|
| 0% | 0% | ❌ 漏检 | ⬆️ 提高Recall |
| 0% | 45% | ❌ 过度预测 | ⬆️ 提高Precision |
| 45% | 45% | ✅ 良好 | 继续优化 |
| 70% | 70% | ✅ 优秀 | 保持 |

---

## 输出解读

```
平均联合准确率-严格 (Joint Accuracy Strict): 0.00%
平均联合准确率-软匹配 (Joint Accuracy Soft): 45.00%
```

**含义**:
- 0%对话完全匹配（Strict）
- 45%对话找到所有期望槽位（Soft）
- 差值45%表示这些对话有额外预测

**诊断**: 模型过度预测

---

## 优化方向

### 当前情况：过度预测

**快速修复**:

1. **Prompt调整**
   ```
   "只提取明确提到的槽位"
   "不确定的槽位请返回null"
   ```

2. **Temperature**
   ```python
   temperature = 0.0
   ```

3. **后处理**
   ```python
   # 过滤低置信度槽位
   ```

---

## FAQ

**Q: 为什么不直接去掉额外槽位？**  
A: 额外槽位可能包含有用信息，需要先分析是否真的多余。

**Q: Soft JA违背论文标准吗？**  
A: 不，我们保留Strict JA对齐论文，Soft JA是补充。

**Q: 何时两个指标相等？**  
A: 当模型没有过度预测时（extracted == expected）。

---

## 代码位置

- `tests/test_dst_transfertod.py` - DST测试
- `tests/test_fnctod_transfertod.py` - FnCTOD测试
- `SOFT_JA_EXPLANATION.md` - 详细文档

---

## 一句话总结

> **Soft JA帮助区分"缺失槽位"和"额外槽位"，为模型优化提供明确方向。**

---

**版本**: 1.0  
**状态**: ✅ 已实现
