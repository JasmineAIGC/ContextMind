python examples/web_demo.py --port 8080
📝 日志将自动保存到: logs/contextmind_20260319_155339.log
[2026-03-19 15:53:39] INFO - [__main__] [__main__] 启动 ContextMind Gradio Demo
[2026-03-19 15:53:39] INFO - [__main__] 参数配置: 日志级别=INFO, 最大历史轮数=10, 端口=8080, 分享=False
[2026-03-19 15:53:39] INFO - [__main__] Demo实例创建完成（延迟初始化）
[2026-03-19 15:53:39] INFO - [__main__] ✅ Demo实例创建成功
/share/airesearch/data/yejiang.zhou/workspace/ContextMind/contextmind/ui/components.py:37: UserWarning: The parameters have been moved from the Blocks constructor to the launch() method in Gradio 6.0: theme, css. Please pass these parameters to launch() instead.
  with gr.Blocks(
[2026-03-19 15:53:39] INFO - [__main__] ✅ UI创建成功
[2026-03-19 15:53:39] INFO - [__main__] 启动Gradio应用... (端口: 8080, 分享: False)
* Running on local URL:  http://0.0.0.0:8080
* To create a public link, set `share=True` in `launch()`.

Provider List: https://docs.litellm.ai/docs/providers


Provider List: https://docs.litellm.ai/docs/providers

[2026-03-19 15:53:43] INFO - [contextmind.infra.llm_client] [AdkLLMClient] 初始化完成，model=Qwen3-32B
[2026-03-19 15:53:43] INFO - [__main__] ✅ LLM客户端初始化成功
[2026-03-19 15:53:43] INFO - [contextmind.modes.evolve.memory.extractor] [LLMBasedExtractor] 初始化完成 - 使用LLM自动提取
[2026-03-19 15:53:43] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✅ LLMBasedExtractor 已初始化用于知识提取
[2026-03-19 15:53:43] INFO - [contextmind.modes.evolve.pipeline.response_handler] [ResponseHandler] 初始化完成
[2026-03-19 15:53:43] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ResponseHandler 已初始化
[2026-03-19 15:53:43] INFO - [contextmind.modes.evolve.engine] EvolveEngine 已初始化 app=gradio_demo_chat, user=gradio_demo_user
[2026-03-19 15:53:43] INFO - [contextmind.modes.evolve.pipeline.summarizer] [Summarizer] ✅ 使用基于规则的摘要策略
[2026-03-19 15:53:43] INFO - [contextmind.modes.evolve.pipeline.summarizer] [Summarizer] 初始化完成 - 策略: RuleBasedSummarizer, 窗口: 10, 增量模式启用
[2026-03-19 15:53:43] INFO - [contextmind.scenarios.app] [EvolveApplication] 初始化完成 (LLM: ✓, 摘要阈值: 15 轮)
[2026-03-19 15:53:43] INFO - [__main__] Evolve模式初始化完成
[2026-03-19 15:53:43] INFO - [__main__] ✅ 场景初始化完成: chat, 模式: evolve
[2026-03-19 15:53:43] INFO - [__main__] 配置已更新: chat, evolve
[2026-03-19 15:53:45] INFO - [contextmind.modes.dst.prompts] 初始化PromptManager (领域=闲聊, 动态槽位=True, 意图预测=True)
[2026-03-19 15:53:45] INFO - [contextmind.modes.dst.tracker] 初始化DialogueStateTracker (领域=general, 动态槽位=True, 历史轮数=10, 摘要=True, LLM摘要=False)
[2026-03-19 15:53:45] INFO - [__main__] DST模式初始化完成
[2026-03-19 15:53:45] INFO - [__main__] ✅ 场景初始化完成: chat, 模式: dst
[2026-03-19 15:53:45] INFO - [__main__] 配置已更新: chat, dst
15:53:48 - LiteLLM:INFO: utils.py:3874 - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:53:48] INFO - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:53:53] INFO - [contextmind.modes.dst.tracker] 处理轮次 #1: 更新={'intent_level1': '闲聊', 'intent_level2': '询问身份', 'topic': '身份介绍', 'emotion': '平静'}, 意图=闲聊
15:53:53 - LiteLLM:INFO: utils.py:3874 - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:53:53] INFO - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:54:17] INFO - [contextmind.modes.pytod.tracker] 已为场景 '闲聊' 注册 API: ['get_weather', 'search_info', 'tell_joke', 'translate_text', 'calculate']
[2026-03-19 15:54:17] INFO - [contextmind.modes.pytod.tracker] adk_tools_from_engine: 共 5 个工具: ['get_weather', 'search_info', 'tell_joke', 'translate_text', 'calculate']
[2026-03-19 15:54:17] INFO - [contextmind.modes.pytod.tracker] AdkPyTODTracker 初始化完成 (model=Qwen3-32B, 工具: ['get_weather', 'search_info', 'tell_joke', 'translate_text', 'calculate'])
[2026-03-19 15:54:17] INFO - [__main__] PyTOD模式初始化完成
[2026-03-19 15:54:17] INFO - [__main__] ✅ 场景初始化完成: chat, 模式: pytod
[2026-03-19 15:54:17] INFO - [__main__] 配置已更新: chat, pytod
[2026-03-19 15:54:19] INFO - [contextmind.modes.pytod.tracker] AdkPyTODTracker 第 1 轮: 你是谁
15:54:19 - LiteLLM:INFO: utils.py:3874 - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:54:19] INFO - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:54:23] INFO - [contextmind.modes.pytod.tracker] [AdkPyTODTracker] 回复: 我是pytod_agent，一个任务型对话助手。我优先通过调用工具来完成任务，然后会用自然语言给出友好、简洁的回复。有什么我可以帮你的吗？
[2026-03-19 15:54:44] INFO - [contextmind.modes.fnctod.function_manager] FunctionManager 初始化完成
[2026-03-19 15:54:44] INFO - [contextmind.modes.fnctod.tracker] adk_tools_from_function_manager: 共 1 个工具: ['chat']
[2026-03-19 15:54:44] INFO - [contextmind.modes.fnctod.tracker] FnCTODTracker 初始化完成 (model=Qwen3-32B, domains=['chat'])
[2026-03-19 15:54:44] INFO - [__main__] FnCTOD模式初始化完成
[2026-03-19 15:54:44] INFO - [__main__] ✅ 场景初始化完成: chat, 模式: fnctod
[2026-03-19 15:54:44] INFO - [__main__] 配置已更新: chat, fnctod
15:54:48 - LiteLLM:INFO: utils.py:3874 - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:54:48] INFO - 
LiteLLM completion() model= Qwen3-32B; provider = openai
15:54:53 - LiteLLM:INFO: utils.py:3874 - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:54:53] INFO - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:54:59] INFO - [contextmind.modes.fnctod.tracker] [turn 1] 更新: {'intent_level1': '闲聊', 'intent_level2': '询问身份', 'keywords': '你是谁', 'emotion': '平静', 'attitude': '友好', 'conversation_style': '随意', 'conversation_depth': '浅层闲聊', 'follow_up_needed': '否'}, 累积: {'intent_level1': '闲聊', 'intent_level2': '询问身份', 'keywords': '你是谁', 'emotion': '平静', 'attitude': '友好', 'conversation_style': '随意', 'conversation_depth': '浅层闲聊', 'follow_up_needed': '否'}
[2026-03-19 15:55:06] INFO - [contextmind.modes.evolve.memory.extractor] [LLMBasedExtractor] 初始化完成 - 使用LLM自动提取
[2026-03-19 15:55:06] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✅ LLMBasedExtractor 已初始化用于知识提取
[2026-03-19 15:55:06] INFO - [contextmind.modes.evolve.pipeline.response_handler] [ResponseHandler] 初始化完成
[2026-03-19 15:55:06] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ResponseHandler 已初始化
[2026-03-19 15:55:06] INFO - [contextmind.modes.evolve.engine] EvolveEngine 已初始化 app=gradio_demo_chat, user=gradio_demo_user
[2026-03-19 15:55:06] INFO - [contextmind.modes.evolve.pipeline.summarizer] [Summarizer] ✅ 使用基于规则的摘要策略
[2026-03-19 15:55:06] INFO - [contextmind.modes.evolve.pipeline.summarizer] [Summarizer] 初始化完成 - 策略: RuleBasedSummarizer, 窗口: 10, 增量模式启用
[2026-03-19 15:55:06] INFO - [contextmind.scenarios.app] [EvolveApplication] 初始化完成 (LLM: ✓, 摘要阈值: 15 轮)
[2026-03-19 15:55:06] INFO - [__main__] Evolve模式初始化完成
[2026-03-19 15:55:06] INFO - [__main__] ✅ 场景初始化完成: chat, 模式: evolve
[2026-03-19 15:55:06] INFO - [__main__] 配置已更新: chat, evolve
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] ====================================================================================================
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ========== 开始上下文优化 ==========
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] 📝 用户输入: '你是谁'
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] ====================================================================================================
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✓ 预处理完成
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] 🔍 步骤 2/5: 召回相关上下文
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine]   - 会话历史: 0 条消息
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.memory.bank] [MemoryBank] 开始检索记忆 - 查询: '你是谁'
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.memory.bank] [MemoryBank] 从本地缓存检索 - 查询: '你是谁', 缓存大小: 0
[2026-03-19 15:55:18] WARNING - [contextmind.modes.evolve.memory.bank] [MemoryBank] ✗ 本地缓存为空 - 无法检索记忆
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine]   - 长期记忆: 0 条知识
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✓ 召回完成 - 共检索到 0 条上下文
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] 📦 步骤 3/5: 构建上下文
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✓ 上下文构建完成 - 0 条上下文项
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] 🗜️  步骤 4/5: 上下文压缩
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine]   - 上下文项数量适中(0条)，无需压缩
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✅ 步骤 5/5: 生成最终上下文结果
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] ----------------------------------------------------------------------------------------------------
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] 🎯 上下文优化完成 - 共 0 条上下文项 (会话: 0, 记忆: 0)
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] ----------------------------------------------------------------------------------------------------
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ========== 上下文优化结束 ==========
[2026-03-19 15:55:18] INFO - [contextmind.modes.evolve.engine] 
15:55:18 - LiteLLM:INFO: utils.py:3874 - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:55:18] INFO - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] 💾 更新会话历史 - 添加新对话轮次
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] [EvolveEngine]   - 用户消息: 3 字符
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] [EvolveEngine]   - 助手回复: 63 字符
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✓ 会话历史更新完成
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] ====================================================================================================
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ========== 🧠 开始知识提取 ==========
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] 📖 从 2 条对话中提取知识...
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] ====================================================================================================
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:21] INFO - [contextmind.modes.evolve.memory.extractor] [LLMBasedExtractor] 开始LLM知识提取 - 处理 2 条消息
15:55:21 - LiteLLM:INFO: utils.py:3874 - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:55:21] INFO - 
LiteLLM completion() model= Qwen3-32B; provider = openai
[2026-03-19 15:55:32] INFO - [contextmind.infra.embedding] [EmbeddingConfig] 使用本地 embedding 模型: /share/airesearch/data/aowen.xiao/models/BAAI/bge-large-zh-v1.5
[2026-03-19 15:55:32] INFO - [contextmind.infra.embedding] [EmbeddingClient] 正在加载本地模型: /share/airesearch/data/aowen.xiao/models/BAAI/bge-large-zh-v1.5
[2026-03-19 15:55:32] INFO - Use pytorch device_name: cuda:0
[2026-03-19 15:55:32] INFO - Load pretrained SentenceTransformer: /share/airesearch/data/aowen.xiao/models/BAAI/bge-large-zh-v1.5
Loading weights: 100%|████████████████████████████████████████████████████████████| 391/391 [00:00<00:00, 7714.00it/s, Materializing param=pooler.dense.weight]
BertModel LOAD REPORT from: /share/airesearch/data/aowen.xiao/models/BAAI/bge-large-zh-v1.5
Key                     | Status     |  | 
------------------------+------------+--+-
embeddings.position_ids | UNEXPECTED |  | 

Notes:
- UNEXPECTED    :can be ignored when loading from different task/architecture; not ok if you expect identical arch.
[2026-03-19 15:55:33] INFO - [contextmind.infra.embedding] [EmbeddingClient] 本地模型加载成功 - bge-large-zh-v1.5
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.memory.extractor] [LLMBasedExtractor] ✓ 知识提取完成 - 总计 1 条有效知识
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] ----------------------------------------------------------------------------------------------------
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✓ 知识提取完成 - 共提取 1 条知识
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] 
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] 📥 入库: 存储知识到长期记忆...
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.memory.bank] [MemoryBank] 开始存储知识 - 收到 1 条知识项
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.memory.bank] 
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.memory.updater] [SimpleUpdater] 开始存储知识 - 收到 1 条知识项
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.memory.updater] [SimpleUpdater] ✓ 存储完成 - 新增 1 条知识, 合并/更新 0 条
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.memory.updater] [SimpleUpdater] 当前记忆库总计: 1 条记忆
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.memory.bank] 
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ✓ 知识入库完成
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] ----------------------------------------------------------------------------------------------------
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] [EvolveEngine] ========== 知识提取结束 ==========
[2026-03-19 15:55:34] INFO - [contextmind.modes.evolve.engine] 
