python examples/build_kb_demo.py --demo
/share/airesearch/data/yejiang.zhou/workspace/ContextMind/examples/build_kb_demo.py:70: DeprecationWarning: contextmind.kb 已迁移至 contextmind.knowledge，请将 'from contextmind.kb import ...' 更新为 'from contextmind.knowledge import ...'。contextmind.kb 将在未来版本中移除。
  from contextmind.kb import KnowledgeBaseBuilder
======================================================================
  ContextMind 知识库构建演示
  第一步：建立知识库 → 完整 SGD 数据集
======================================================================

内嵌演示对话：4 条（格式多样，涵盖 4 种输入格式）
场景名称: 银行贷款外呼
场景描述: 银行客服主动致电老客户推介个人贷款产品
输出目录: data/kb_output

──────────────────────────────────────────────────────────────────────
▶ 初始化 KnowledgeBaseBuilder …
▶ 执行知识库构建（生成完整 SGD 数据集）…
  Phase 1 — 发现阶段：LLM + langextract 逐轮提取槽位和意图（含溯源）
  Phase 2 — 合成阶段：LLM 将发现结果合成为规范 SGD Schema
  Phase 3 — 转换阶段：将对话转换为 SGD 格式对话文件


Provider List: https://docs.litellm.ai/docs/providers


Provider List: https://docs.litellm.ai/docs/providers

ERROR:absl:Extraction text must be a string, integer, or float. Found: <class 'dict'>
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第1轮提取失败: Extraction text must be a string, integer, or float.
ERROR:absl:Extraction text must be a string, integer, or float. Found: <class 'dict'>
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第2轮提取失败: Extraction text must be a string, integer, or float.
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第3轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第4轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第5轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第6轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
ERROR:absl:Extraction text must be a string, integer, or float. Found: <class 'dict'>
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第9轮提取失败: Extraction text must be a string, integer, or float.
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第10轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
ERROR:absl:Extraction text must be a string, integer, or float. Found: <class 'dict'>
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第1轮提取失败: Extraction text must be a string, integer, or float.
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第3轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第4轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第8轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第9轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第3轮提取失败: Failed to parse JSON content: Expecting value: line 1 column 1 (char 0)
ERROR:absl:Extraction text must be a string, integer, or float. Found: <class 'dict'>
WARNING:contextmind.knowledge.discoverer:[contextmind.knowledge.discoverer] [GenericDialogueDiscoverer] 第1轮提取失败: Extraction text must be a string, integer, or float.

──────────────────────────────────────────────────────────────────────
✓ 知识库构建完成！

服务名称: BankLoan_OutboundCall
服务描述: 银行客服主动致电老客户，推介个人贷款产品并处理相关请求

槽位（slots）共 8 个：
  - customer_name: 客户姓名
  - credit_limit: 客户的信用额度上限
  - available_credit: 客户当前可用的信用额度
  - loan_range: 贷款金额范围
  - annual_interest_rate: 年利率
  - daily_interest_rate: 日利率
  - monthly_payment_per_10000: 每万元贷款的月供金额
  - credit_assessment: 信用评估结果

意图（intents）共 4 个：
  - request_credit_increase: 客户请求提高信用额度
    必填槽位: ['customer_name', 'credit_limit', 'available_credit']
    可选槽位: ['credit_assessment']
  - confirm_identity: 客服确认客户身份
    必填槽位: ['customer_name']
  - inquire_loan_details: 客户询问贷款产品详情
    可选槽位: ['loan_range', 'annual_interest_rate', 'daily_interest_rate', 'monthly_payment_per_10000']
  - decline_loan: 客户明确表示近期不需要贷款

发现统计（发现阶段 raw 数据）：
  Top-10 槽位: [('credit_limit', 1), ('loan_range', 1), ('daily_interest_rate', 1), ('annual_interest_rate', 1), ('monthly_payment_per_10000', 1), ('customer_name', 1), ('available_credit', 1), ('credit_assessment', 1)]
  Top-10 意图: [('request_credit_increase', 2), ('confirm_identity', 1), ('verify_identity', 1), ('decline_loan', 1), ('inquire_loan_details', 1)]

SGD 对话文件统计：
  对话数: 4
  总轮次: 34

✓ SGD 数据集已保存至: /share/airesearch/data/yejiang.zhou/workspace/ContextMind/data/kb_output
  ├── schema.json           (服务 schema)
  ├── dialogues_001.json    (SGD 格式对话，4 条)
  └── conversion_summary.json
──────────────────────────────────────────────────────────────────────

下一步：使用此 schema.json 运行 PyTOD 对话：
  from contextmind.modes.pytod import AdkPyTODTracker, ServiceSchema
  schema = ServiceSchema.from_json(open('data/kb_output/schema.json').read())[0]
  tracker = AdkPyTODTracker(engine=engine, schema=schema)
