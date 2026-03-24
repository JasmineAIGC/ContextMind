python examples/context_pipeline_demo.py --demo-exec --schema data/kb_output/schema.json
=================================================================
  ContextMind — 上下文工程流水线演示
  ContextPipeline: Phase 1（建立知识库）+ Phase 2（执行）
=================================================================

使用内嵌演示对话（3 条，涵盖 3 种输入格式）

初始化 ContextPipeline（模式=pytod，场景=银行贷款外呼）...

Provider List: https://docs.litellm.ai/docs/providers


Provider List: https://docs.litellm.ai/docs/providers

✓ LLM 客户端初始化成功

─────────────────────────────────────────────────────────────────
▶ Phase 2：对话上下文提取（基于知识库，逐轮提取有效上下文）
  模式: PYTOD
─────────────────────────────────────────────────────────────────

已加载 Schema: AnYiHua_OutboundCall
  槽位: ['loan_amount', 'date', 'monthly_payment', 'current_credit_limit', 'credit_limit', 'loan_date', 'repayment_status', 'borrowing_date', 'overdue_days', 'loan_limit', 'borrow_date', 'borrow_amount', 'remaining_quota', 'application_date', 'usage_duration', 'available_amount', 'term_years', 'total_interest', 'daily_interest', 'interest_total', 'monthly_payment_amount', 'monthly_interest_amount', 'amount', 'account_usage_status', 'temporary_credit_limit', 'temporary_limit', 'requested_amount', 'actual_amount']
  意图: ['confirm_terms', 'verify_identity', 'complain_repayment_process', 'complain_interest_rate', 'confirm_awareness', 'dispute_loan', 'confirm_borrowing_history', 'decline_usage', 'inquire_concerns_quota_interest', 'express_future_intent', 'inquire_repayment_type', 'complain_repayment_difficulty', 'complain_monthly_payment', 'inquire_expected_interest_rate', 'inquire_annual_interest_rate', 'inform_credit_limit_increase', 'confirm_application', 'complain_limit_denied', 'confirm_account_status', 'inquire_amount_discrepancy', 'complain_discrepancy', 'suggest_contact_customer_service']

开始对话（5 轮）：

[Turn 1] 用户: 你好，我是李明，想了解一下贷款情况
[contextmind.modes.pytod.tracker] [EE] 执行错误: ["函数 'verify_identity' 未注册（变量 x1）", "函数 'confirm_borrowing_history' 未注册（变量 x2）"]
         系统: 您好，李明先生，很高兴为您服务。目前系统正在维护中，暂时无法查询身份信息和借款记录。为了不影响您的业务办理，请您稍后再次致电或前往银行柜台咨询。感谢您的理解与支持！
         程序: x1 verify_identity(name='李明')  
x2 confirm_borrowing_history()  
x3 say(x1, x2)

[Turn 2] 用户: 我的手机尾号是 6789
         系统: 好的，李明先生，为了保障您的账户安全，建议您稍后致电银行客服热线95090进行咨询，感谢您的理解与支持！
         程序: x4 say('好的，李明先生，为了保障您的账户安全，建议您稍后致电银行客服热线95090进行咨询，感谢您的理解与支持！')

[Turn 3] 用户: 我想知道我的可用额度是多少
         系统: 您好，目前系统正在维护中，暂时无法查询身份信息和借款记录。为了不影响您的业务办理，请您稍后再次致电或前往银行柜台咨询。感谢您的理解与支持！
         程序: x5 say('您好，目前系统正在维护中，暂时无法查询身份信息和借款记录。为了不影响您的业务办理，请您稍后再次致电或前往银行柜台咨询。感谢您的理解与支持！')

[Turn 4] 用户: 如果分 12 期，月供大概是多少？
         系统: 目前系统正在维护中，暂时无法查询相关贷款信息。为了不影响您的业务办理，请您稍后再次致电或前往银行柜台咨询。感谢您的理解与支持！
         程序: x6 say('目前系统正在维护中，暂时无法查询相关贷款信息。为了不影响您的业务办理，请您稍后再次致电或前往银行柜台咨询。感谢您的理解与支持！')

[Turn 5] 用户: 好的，我考虑一下，谢谢
         系统: 不客气，如果您有任何其他问题或需要进一步帮助，欢迎随时联系我们。祝您生活愉快，再见！
         程序: x7 say('不客气，如果您有任何其他问题或需要进一步帮助，欢迎随时联系我们。祝您生活愉快，再见！')


=== ContextPipeline 状态摘要 ===
  模式:     pytod
  场景:     银行贷款外呼
  Schema:   AnYiHua_OutboundCall
  槽位数:   28
  意图数:   22
  追踪器:   AdkPyTODTracker (已初始化)

=================================================================
  演示结束
=================================================================