# 测试样本分析文档

## 概述

本文档分析 `data/duihua.md` 中的 7 通电话对话，并说明如何将其转换为可用于 DST（对话状态追踪）和 Evolve（基于记忆进化）两种模式测试的测试样本。

## 对话数据概览

### 对话场景背景

所有 7 通对话均为**札幌生活合作社团体癌症保险**的电话销售场景：
- **销售方**：札幌合作社保险担当
- **客户方**：合作社会员
- **产品**：团体癌症保险（月保费享30%折扣）

### 对话摘要

| 对话 | 客户年龄段 | 月保费 | 最终结果 | 主要拒绝原因 |
|------|-----------|--------|----------|--------------|
| 对话1 | 中年 | 5140日元 | 拒绝 | 已有保险，满足现状 |
| 对话2 | 中年 | 6850日元 | 拒绝 | 保费负担困难 |
| 对话3 | 年轻 | 1090日元 | 拒绝 | 保险买太多，月付5万+ |
| 对话4 | 中年 | 5140日元 | 接受考虑 | 已有保险，但可接受增加 |
| 对话5 | 中年 | 5140日元 | 拒绝 | 收入不稳定，现有保障够用 |
| 对话6 | 中年 | 5140日元 | 拒绝 | 不喜欢消费型，想要返还型 |
| 对话7 | 年轻 | 1570日元 | 拒绝 | 只保癌症，不符合需求 |

---

## 测试样本提取规范

### 一、DST 模式测试样本

DST（Dialogue State Tracking）模式关注**对话状态追踪**，需要提取每轮对话的槽位更新和意图变化。

#### 1.1 需提取的核心信息

##### 意图层级（三层结构）

```json
{
  "intent_level1": "一级意图（必填）",
  "intent_level2": "二级意图（必填）",
  "intent_level3": "三级意图（可选，补充详细信息）"
}
```

**一级意图**（7个固定值）：
- 拒绝、无意向、用户忙、考虑、质疑类、接受、咨询

**二级意图**（根据一级意图选择）：
- 拒绝 → 明确/强硬拒绝、委婉拒绝
- 无意向 → 已有保险、保费贵、生活负担大、等11个子意图
- 质疑类 → 身份质疑、质疑是否能理赔、等5个子意图
- 接受 → 有意向、同意了解、愿意购买
- 咨询 → 询问保障内容、询问保费、等4个子意图

**三级意图**（39个预定义值，8个类别）：
- 态度程度：强硬态度、委婉态度、谨慎态度、开放态度
- 经济状况：负担过重、预算有限、收入担忧、价格敏感、经济稳定
- 已有状态：已有保障、刚做调整、非常满意、在他处投保、无任何保险
- 认知水平：不了解产品、不感兴趣、不相信需要、不觉得会发生、充分了解
- 决策阶段：需要商量、需要比较、需要时间、需要更多信息、准备接受、拒绝考虑
- 信任程度：怀疑身份、怀疑动机、过往受伤、不信销售、信任开放
- 时间因素：当前很忙、不太方便、改天联系、时机不当
- 产品理解：不懂条款、不懂理赔、不懂保障、不懂区别、理解清楚

##### 事实性槽位

```json
{
  "customer_age_range": "客户年龄段（30岁以下/30-40岁/40-50岁/50岁以上）",
  "has_insurance": "是否已有保险（是/否/未知）",
  "has_cancer_insurance": "是否已有癌症保险（是/否/未知）",
  "budget_range": "预算范围（自由文本）",
  "decision_maker": "决策者（本人/配偶/家人/需商量）",
  "conversation_stage": "对话阶段",
  "monthly_premium": "月保费金额",
  "insurance_plan": "方案类型（基础/半额）"
}
```

#### 1.2 测试样本格式

每个测试样本应包含：

```json
{
  "dialogue_id": "对话1",
  "turns": [
    {
      "turn_id": 1,
      "system_utterance": "销售员的话语",
      "user_utterance": "客户的回复",
      "expected_state": {
        "intent_level1": "...",
        "intent_level2": "...",
        "intent_level3": "...",
        "has_insurance": "...",
        "budget_range": "..."
      }
    }
  ],
  "final_state": {
    "全部累积状态"
  },
  "dialogue_metadata": {
    "customer_age_range": "...",
    "monthly_premium": "...",
    "final_result": "拒绝/接受/待定",
    "main_objection": "主要异议原因"
  }
}
```

#### 1.3 对话1测试样本示例

```json
{
  "dialogue_id": "对话1",
  "turns": [
    {
      "turn_id": 1,
      "system_utterance": "您好，打扰了。我是札幌生活合作社团体癌症保险的负责人。平时一直承蒙您对合作社的关照。请问札幌生活合作社的会员XX様在家吗？",
      "user_utterance": "是的，是我。",
      "expected_state": {
        "intent_level1": "接受",
        "intent_level2": "同意了解"
      }
    },
    {
      "turn_id": 2,
      "system_utterance": "今天打电话来，是想为札幌生活合作社会员专属的团体癌症保险做个简单介绍，可以占用您一点时间通过电话说明吗？",
      "user_utterance": "哦，请问有什么事？",
      "expected_state": {
        "intent_level1": "咨询",
        "intent_level2": "询问保障内容",
        "intent_level3": "开放态度"
      }
    },
    {
      "turn_id": 3,
      "system_utterance": "（介绍完基础方案和半额方案后）请问您已经买过癌症保险了吗？",
      "user_utterance": "啊，有买过。",
      "expected_state": {
        "intent_level1": "无意向",
        "intent_level2": "已有癌症保险",
        "has_cancer_insurance": "是"
      }
    },
    {
      "turn_id": 4,
      "system_utterance": "您要不要考虑一下半额方案？",
      "user_utterance": "嗯，其他地方也有类似的。",
      "expected_state": {
        "intent_level1": "无意向",
        "intent_level2": "已有保险",
        "intent_level3": "已有保障"
      }
    },
    {
      "turn_id": 5,
      "system_utterance": "果然还是有点难决定吗？",
      "user_utterance": "就先谢绝了。",
      "expected_state": {
        "intent_level1": "拒绝",
        "intent_level2": "委婉拒绝",
        "intent_level3": "委婉态度"
      }
    }
  ],
  "final_state": {
    "intent_level1": "拒绝",
    "intent_level2": "委婉拒绝",
    "intent_level3": "已有保障",
    "has_cancer_insurance": "是",
    "has_insurance": "是",
    "conversation_stage": "客户拒绝"
  },
  "dialogue_metadata": {
    "monthly_premium": "5140日元",
    "final_result": "拒绝",
    "main_objection": "已有保险，现有保障足够"
  }
}
```

---

### 二、Evolve 模式测试样本

Evolve 模式关注**知识提取和长期记忆进化**，需要从对话中提取可存储到记忆库的结构化知识。

#### 2.1 需提取的知识类型

##### 用户偏好（user_preferences）
从对话中提取客户的偏好和需求特点：

```json
{
  "type": "user_preferences",
  "content": "客户对保险产品的偏好",
  "examples": [
    "偏好返还型保险而非消费型",
    "希望综合保障而非单一癌症保障",
    "对价格敏感，关注性价比",
    "重视保障范围而非价格"
  ]
}
```

##### 事实性知识（facts）
对话中提及的客观事实：

```json
{
  "type": "facts",
  "content": "客户提供的事实信息",
  "examples": [
    "客户已购买其他保险，月付5万日元以上",
    "客户目前收入不稳定",
    "客户年龄在50岁以上"
  ]
}
```

##### 对话模式（patterns）
识别有效的销售策略和对话模式：

```json
{
  "type": "patterns",
  "content": "有效的销售对话模式",
  "examples": [
    "强调30%折扣优惠能引起客户兴趣",
    "提供半额方案是有效的降级策略",
    "安全确认问题能建立信任"
  ]
}
```

##### 策略知识（strategies）
总结有效的应对策略：

```json
{
  "type": "strategies",
  "content": "异议处理策略",
  "examples": [
    "已有保险 → 强调可叠加购买，单独领取",
    "保费贵 → 推荐半额方案",
    "消费型不喜欢 → 说明团体保险的特殊优势"
  ]
}
```

##### 经验总结（experiences）
从对话结果中总结的经验教训：

```json
{
  "type": "experiences",
  "content": "销售经验总结",
  "examples": [
    "客户明确表示保险买够了时，不应强行推销",
    "收入不稳定的客户对月付型保险敏感",
    "返还型偏好客户对消费型产品接受度低"
  ]
}
```

#### 2.2 测试样本格式

```json
{
  "dialogue_id": "对话1",
  "dialogue_summary": "简短对话摘要",
  "extracted_knowledge": {
    "user_preferences": [
      {"content": "...", "confidence": 0.9}
    ],
    "facts": [
      {"content": "...", "confidence": 1.0}
    ],
    "patterns": [
      {"content": "...", "confidence": 0.8}
    ],
    "strategies": [
      {"content": "...", "confidence": 0.85}
    ],
    "experiences": [
      {"content": "...", "confidence": 0.9}
    ]
  },
  "memory_items": [
    {
      "content": "可存储到记忆库的知识条目",
      "importance": 0.8,
      "category": "knowledge_type"
    }
  ]
}
```

#### 2.3 对话1知识提取示例

```json
{
  "dialogue_id": "对话1",
  "dialogue_summary": "销售员向已有保险的客户推销团体癌症保险，客户表示现有保障足够，最终委婉拒绝",
  "extracted_knowledge": {
    "user_preferences": [
      {
        "content": "客户满意现有保险配置，不希望增加额外保障",
        "confidence": 0.9
      }
    ],
    "facts": [
      {
        "content": "客户已购买癌症保险和其他医疗保险",
        "confidence": 1.0
      },
      {
        "content": "客户认为合作社现有保障已足够",
        "confidence": 0.95
      }
    ],
    "patterns": [
      {
        "content": "反复确认'果然还是有点难决定'容易让客户产生压力",
        "confidence": 0.75
      },
      {
        "content": "提供半额方案作为降级选择是标准销售流程",
        "confidence": 0.9
      }
    ],
    "strategies": [
      {
        "content": "对已有保险客户，强调叠加保障和单独领取优势",
        "confidence": 0.8
      },
      {
        "content": "客户犹豫时询问原因有助于了解真实想法",
        "confidence": 0.85
      }
    ],
    "experiences": [
      {
        "content": "客户表示'现有保障够了'时，继续推销可能适得其反",
        "confidence": 0.9
      },
      {
        "content": "即使推荐半额方案，满足现状的客户仍然难以转化",
        "confidence": 0.85
      }
    ]
  },
  "memory_items": [
    {
      "content": "对已有充足保障的客户，应尊重其决定，保持良好关系以便未来机会",
      "importance": 0.9,
      "category": "experiences"
    },
    {
      "content": "反复推销容易让客户产生抵触情绪",
      "importance": 0.8,
      "category": "experiences"
    }
  ]
}
```

---

## 三、7通对话关键信息汇总

### 对话1
- **客户特点**: 已有保险，满意现状
- **一级意图**: 无意向 → 拒绝
- **关键异议**: 已有保险，合作社现有保障足够
- **销售策略**: 推荐半额方案，强调叠加购买
- **结果**: 委婉拒绝
- **学习点**: 满意现状的客户难以转化

### 对话2
- **客户特点**: 中年，保费负担困难
- **一级意图**: 无意向 → 拒绝
- **关键异议**: 保费负担困难
- **销售策略**: 提供半额方案降低门槛
- **结果**: 明确拒绝
- **学习点**: 经济因素是重要考量

### 对话3
- **客户特点**: 年轻，保险支出已达5万日元/月
- **一级意图**: 咨询 → 无意向
- **关键异议**: 保险已买太多，无法再增加
- **销售策略**: 说明推荐期限，强调机会
- **结果**: 明确拒绝
- **学习点**: 保险过度客户需要不同策略

### 对话4
- **客户特点**: 中年，已有保险但态度开放
- **一级意图**: 无意向 → 接受考虑
- **关键异议**: 已有保险，但可接受适度增加
- **销售策略**: 推荐半额方案作为补充
- **结果**: 表示可以考虑
- **学习点**: 开放态度客户有转化可能

### 对话5
- **客户特点**: 曾接受介绍，收入不稳定
- **一级意图**: 考虑 → 拒绝
- **关键异议**: 收入不稳定，不想增加月付负担
- **销售策略**: 回访确认意向
- **结果**: 委婉拒绝
- **学习点**: 经济压力是核心障碍

### 对话6
- **客户特点**: 中年，偏好返还型保险
- **一级意图**: 咨询 → 拒绝
- **关键异议**: 消费型不符合期望，想要返还型
- **销售策略**: 解释产品特点，提供半额方案
- **结果**: 委婉拒绝
- **学习点**: 产品类型偏好难以改变

### 对话7
- **客户特点**: 年轻，需要综合保障
- **一级意图**: 咨询 → 拒绝
- **关键异议**: 只保癌症太局限，不符合需求
- **销售策略**: 解释专属癌症保障
- **结果**: 明确拒绝
- **学习点**: 需求不匹配难以成交

---

## 四、测试样本使用建议

### DST 模式测试

1. **槽位提取准确性测试**: 验证每轮对话后系统提取的槽位值是否与预期匹配
2. **意图识别测试**: 验证三层意图识别的准确性
3. **状态累积测试**: 验证多轮对话后累积状态的正确性
4. **历史管理测试**: 验证长对话的摘要和历史管理功能

### Evolve 模式测试

1. **知识提取测试**: 验证从对话中提取的知识是否完整和准确
2. **记忆存储测试**: 验证提取的知识是否正确存储到记忆库
3. **记忆检索测试**: 验证相关记忆在后续对话中是否被正确召回
4. **进化学习测试**: 验证系统是否从对话经验中学习和改进

### 综合测试

1. **端到端测试**: 使用完整对话测试整个处理流程
2. **异常处理测试**: 使用模糊或不完整的用户输入测试鲁棒性
3. **边界条件测试**: 测试极长对话、快速意图切换等边界情况

---

## 五、实现建议

### 测试数据文件结构

```
data/
├── duihua.md                    # 原始对话数据
├── test_samples/                # 测试样本目录
│   ├── dst_samples.json         # DST模式测试样本
│   ├── evolve_samples.json      # Evolve模式测试样本
│   └── metadata.json            # 元数据和配置
tests/
├── test_dst_extraction.py       # DST槽位提取测试
├── test_evolve_knowledge.py     # Evolve知识提取测试
└── test_integration.py          # 集成测试
```

### 测试脚本示例

```python
import json
import pytest
from dst import DialogueStateTracker, PromptManager
from scenarios import get_insurance_scenario

class TestDSTExtraction:
    @pytest.fixture
    def tracker(self, llm_client):
        config = get_insurance_scenario()
        pm = PromptManager(
            domain=config.name,
            enable_dynamic_slots=config.enable_dynamic_slots
        )
        for slot_name, slot_desc in config.dst_slots.items():
            pm.add_slot(slot_name, slot_desc)
        return DialogueStateTracker(llm_client=llm_client, prompt_manager=pm)
    
    async def test_dialogue_1(self, tracker):
        # 加载测试样本
        with open('data/test_samples/dst_samples.json') as f:
            samples = json.load(f)
        
        dialogue = samples['dialogue_1']
        for turn in dialogue['turns']:
            state = await tracker.process_turn(
                system_utterance=turn['system_utterance'],
                user_utterance=turn['user_utterance']
            )
            # 验证关键槽位
            for key, expected in turn['expected_state'].items():
                assert state.get(key) == expected, f"Turn {turn['turn_id']}: {key}"
```

---

## 总结

本文档定义了将 7 通电话对话转换为测试样本的完整规范：

1. **DST 模式**: 关注意图识别和槽位提取，使用三层意图体系和预定义槽位
2. **Evolve 模式**: 关注知识提取和记忆进化，提取5类结构化知识
3. **测试样本**: 提供了完整的JSON格式规范和示例
4. **使用建议**: 包括测试策略和代码示例

通过这些测试样本，可以全面验证 ContextMind 框架在保险销售对话场景下的表现。
