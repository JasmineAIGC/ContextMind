### 文章技术框架：ChatGPT 用于零样本对话状态跟踪（Zero-shot DST）

文章（Section 3）提出一种**纯提示驱动的极简零样本DST框架**，完全不进行模型参数更新、微调、数据增强、跨任务迁移或提供标注示例（in-context examples）。方法将DST转化为多轮聊天交互，依赖ChatGPT（2023年1月9日研究预览版本）的原生对话接口、指令调优（instruction tuning）和人类反馈对齐（RLHF）能力，让模型自行维护隐式对话状态并每轮输出**增量更新ΔDS_t**，最终通过后处理累积完整状态DS_t。

#### 1. 任务形式化与严格零样本约束
- **DST任务**：
  - 输入：对话 {(M_t, U_t)}^T_{t=1}（M_t：系统utterance，U_t：用户utterance）。
  - 每轮t：
    1. 判断槽集合S = {S_n}^N_{n=1}中哪些槽被提及/更新。
    2. 预测每个槽的值。
    3. 输出增量更新ΔDS_t（仅本轮新出现或变化的槽-值对）。
  - 累积状态：DS_t = update(DS_{t-1}, ΔDS_t)，DS_t为累积状态。
- **零样本约束**（最严格）：
  - 训练槽集合S' = ∅（ChatGPT未针对DST训练）。
  - 推理槽S ∩ S' = ∅。
  - **不允许**：标注示例、正式schema定义、每轮附加先前状态DS_{t-1}、数据增强。
  - **仅允许**：一个初始自然语言提示P（非正式、无schema）。

#### 2. 提示P设计（唯一任务指导，仅第一轮发送）
提示P是框架核心，目标模仿TripPy（Heck et al., 2020）的triple copy策略（直接从utterance复制值）。P由三部分组成：
1. **Informable slots列表**：
   - 列出所有可告知槽名称 + 自然语言语义描述（例如： "hotel-name": "the name of the hotel the user wants to book"）。
   - 作用：帮助ChatGPT基于世界知识理解未见槽，实现零样本泛化。
2. **Categorical slots稀疏列表**：
   - 仅少数高变异/布尔槽 + 候选值列表（例如： "hotel-pricerange": ["cheap", "moderate", "expensive"]）。
   - 作用：辅助严格归一化、处理dontcare和布尔槽。
3. **非正式任务描述**：
   - 明确要求：
     - 每轮只提取**用户在本轮最新utterance中更新的槽-值对**（ΔDS_t）。
     - 输出纯JSON格式（便于提取）。
     - 特殊规则：用户请求的槽填"?"，不在意填"dontcare"，无更新返回空JSON []。
     - 强调从对话中直接提取/推理值。

**构造细节**：
- 在MultiWOZ训练集<10个对话上手动试错（trial-and-error）调整描述，直至稳定。
- P固定，整个对话仅在第一轮发送一次。

#### 3. 多轮交互与处理流程（核心执行步骤）
框架模拟ChatGPT聊天接口，逐轮输入单对utterance，迫使模型自行处理复杂子任务（如共指消解、系统告知值carry-over）。

**输入构建**：
- **第1轮 A1**：  
  A1 = P ⊕ {"system": M1} ⊕ {"user": U1}
- **后续轮 t ≥ 2**：  
  At = {"system": Mt} ⊕ {"user": Ut}  
  （仅单对utterance，无任何额外状态或提示）

**ChatGPT生成**：
- 输出Bt：基于初始P + 全部历史上下文（先前A和B） + **自身隐式维护的对话状态**生成。
- Bt通常包含自然语言解释 + JSON格式的ΔDS_t。
- 与IC-DST（Hu et al., 2022）关键区别：不每轮附加DS_{t-1}作为输入，任务更难。

**后处理**：
- 用正则表达式提取Bt中所有JSON片段作为候选ΔDS_t。
- **归一化操作**（normalize）：手工处理变异表达（大小写、同义词、缩写等，例如 "Saturday" ↔ "saturday"）。
- 累积状态：DS_t = DS_{t-1} ∪ ΔDS_t（后期值覆盖早期）。
- 如果无有效JSON，返回空更新。

**完整流程伪代码式描述**：
```
DS = {}  # 初始空状态
for t in 1 to T:
    if t == 1:
        input = P + system:M_t + user:U_t
    else:
        input = system:M_t + user:U_t
    Bt = ChatGPT.generate(input)  # 同一聊天会话
    ΔDS_t = normalize(extract_JSON(Bt))
    DS = DS ∪ ΔDS_t
return DS
```

#### 4. 实现与评估细节
- **执行环境**：ChatGPT web接口（免费研究预览），2023年1月6-20日处理。
- **限制**：每对话完整处理一次，不使用“regenerate”功能。
- **数据集**：MultiWOZ 2.1测试集（1000对话）。
- **指标**：Joint Goal Accuracy (JGA = 31.5%)。
- **优势来源**：ChatGPT的RLHF对齐 + 大规模预训练，使其在难域（hotel: 多独特槽/布尔；taxi: 多共指）显著优于传统零样本方法。

该框架展示了通用大模型通过**单次自然语言提示 + 逐轮最小输入 + 简单后处理**即可实现强零样本结构化预测的核心潜力，同时暴露了不稳定性（幻觉、不一致归一化），适合作为专用DST系统的辅助工具而非完整替代。