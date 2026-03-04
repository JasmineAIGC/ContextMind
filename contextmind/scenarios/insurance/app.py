"""
InsuranceApplication - 保险应用示例

展示如何使用EvolveEngine构建保险对话应用。
重点展示上下文工程能力：利用历史、记忆和知识提供连贯回复。
"""

import logging
import time
from typing import Optional

from contextmind.modes.evolve import (
    EvolveEngine,
    Message,
    MessageRole,
    ContextResult,
    ContextSource,
    ConversationSummarizer,
    SummarizationConfig,
    get_logger,
)

from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig

# 导入统一的系统提示词
from contextmind.scenarios.prompts import INSURANCE_SYSTEM_PROMPT

# 禁用HTTP/网络层的debug日志，减少噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.INFO)

logger = get_logger(__name__)


class InsuranceApplication:
    """保险应用示例"""
    
    def __init__(
        self,
        evolve_engine: EvolveEngine,
        business_info: str = "",
        history_turns: int = 10,
        system_prompt: str = INSURANCE_SYSTEM_PROMPT,
        llm_client: Optional[SimpleLLMClient] = None,
        llm_config: Optional[LLMConfig] = None,
        use_real_llm: bool = True,
        extraction_method: str = None,  # 知识提取方式 ('rule' 或 'llm')
        **config
    ):
        """初始化保险应用
        
        Args:
            evolve_engine: Evolve 引擎实例
            business_info: 业务信息
            history_turns: 历史轮数
            system_prompt: 系统提示
            llm_client: 已创建的 LLM 客户端实例（优先使用，避免重复创建）
            llm_config: LLM 配置（可选，llm_client 未提供时从环境变量加载）
            use_real_llm: 是否使用真实 LLM（True=调用API，False=模拟回复）
            extraction_method: 知识提取方式 ('rule' 规则提取, 'llm' LLM自动提取)
                如未指定，使用引擎的extraction_method
        """
        self.evolve_engine = evolve_engine
        self.business_info = business_info
        self.history_turns = history_turns
        self.system_prompt = system_prompt
        self.config = config
        self.use_real_llm = use_real_llm
        
        # 记录提取方式
        if extraction_method:
            self.extraction_method = extraction_method
        else:
            self.extraction_method = getattr(evolve_engine, 'extraction_method', 'rule')
        
        # 初始化 LLM 客户端（如果使用真实 LLM）
        if use_real_llm:
            if llm_client is not None:
                # 复用已有客户端，避免重复创建
                self.llm_client = llm_client
                logger.info(
                    f"[InsuranceApplication] ✓ 初始化完成（复用 LLM 客户端, "
                    f"知识提取: {self.extraction_method}）"
                )
            else:
                try:
                    self.llm_client = SimpleLLMClient(llm_config)
                    logger.info(
                        f"[InsuranceApplication] ✓ 初始化完成 "
                        f"(真实LLM: {use_real_llm}, 知识提取: {self.extraction_method})"
                    )
                except Exception as e:
                    logger.warning(f"[InsuranceApplication] ⚠ LLM 客户端初始化失败: {e}")
                    logger.warning("[InsuranceApplication] 将使用模拟回复")
                    self.use_real_llm = False
                    self.llm_client = None
        else:
            self.llm_client = None
            logger.info(
                f"[InsuranceApplication] ✓ 初始化完成 "
                f"(模拟回复, 知识提取: {self.extraction_method})"
            )
        
        # 初始化对话摘要器
        summarization_config = SummarizationConfig(
            summarize_threshold=15,  # 超过15轮触发摘要
            keep_recent_turns=5,  # 保留最近5轮
            method="rule"  # 使用规则摘要（快速）
        )
        self.summarizer = ConversationSummarizer(
            config=summarization_config,
            llm_client=self.llm_client if use_real_llm else None
        )
        logger.debug(f"[InsuranceApplication] ✓ 对话摘要器已初始化 (触发阈值: {summarization_config.summarize_threshold}轮)")

    
    async def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """构建保险场景 Prompt"""
        logger.info("")
        logger.info("=" * 100)
        logger.info("[Prompt] ========== 开始构建 Prompt ==========")
        logger.info("=" * 100)
        logger.info("")
        
        prompt_parts = [self.system_prompt]
        
        # 记忆库日志 - 从items中提取长期记忆
        logger.info("[Prompt] 📚 检查记忆库状态:")
        long_term_items = [item for item in context.items if item.source == ContextSource.MEMORY]
        if long_term_items:
            for i, item in enumerate(long_term_items, 1):
                logger.info(f"  [{i}] {item.content} (score={item.score:.2f})")
            logger.info(f"  总计: {len(long_term_items)} 条")
        else:
            logger.warning("  记忆库为空")
        logger.info("")
        
        # 添加相关记忆到 Prompt
        RELEVANCE_THRESHOLD = 0.3
        
        if long_term_items:
            relevant_memories = [
                item for item in long_term_items
                if item.score >= RELEVANCE_THRESHOLD
            ]
            
            if relevant_memories:
                used_memories = relevant_memories[:5]
                memory_text = "\n".join(
                    f"- {item.content}"
                    for item in used_memories
                )
                prompt_parts.append(f"\n## 长期记忆\n{memory_text}")
                logger.info(f"[Prompt] ✓ 添加长期记忆到 Prompt ({len(used_memories)} 条):")
                for i, item in enumerate(used_memories, 1):
                    logger.info(f"  ✓ [{i}] {item.content} (score={item.score:.2f})")
            else:
                logger.info(f"[Prompt] ⚠ 无相关记忆 (score < {RELEVANCE_THRESHOLD:.2f})")
        else:
            logger.warning("[Prompt] ⚠ 无长期记忆")
        logger.info("")
        
        # 添加对话历史 - 从items中提取
        # 使用对话摘要器智能处理历史
        history_items = [item for item in context.items if item.source == ContextSource.HISTORY]
        if history_items:
            total_turns = len(history_items)
            
            # 使用摘要器判断是否需要摘要
            # 注意：get_summary_and_recent 是 async 方法
            summary, recent_history = await self.summarizer.get_summary_and_recent(history_items)
            
            if summary:
                # 有摘要：添加摘要 + 最近对话
                prompt_parts.append(f"\n## 早期对话摘要\n{summary}")
                logger.info(f"[Prompt] ✓ 添加对话摘要 (总共{total_turns}轮，前{total_turns - len(recent_history)}轮已摘要)")
                
                # 添加最近对话
                if recent_history:
                    history_text = "\n".join(item.content for item in recent_history)
                    prompt_parts.append(f"\n## 最近对话\n{history_text}")
                    logger.info(f"[Prompt] ✓ 添加最近对话 ({len(recent_history)} 轮)")
            else:
                # 无摘要：使用传统方式（最多10轮）
                MAX_HISTORY_TURNS = min(self.history_turns, 10)  # 最多10轮
                relevant_history = history_items[-MAX_HISTORY_TURNS:]
                history_text = "\n".join(item.content for item in relevant_history)
                prompt_parts.append(f"\n## 对话历史\n{history_text}")
                logger.info(f"[Prompt] ✓ 添加对话历史 (最近{len(relevant_history)}轮，共{len(history_items)}轮可用)")
                if len(history_items) > MAX_HISTORY_TURNS:
                    logger.debug(f"[Prompt] 提示: 共{len(history_items)}轮对话，仅使用最近{MAX_HISTORY_TURNS}轮（其余{len(history_items)-MAX_HISTORY_TURNS}轮已省略）")
        else:
            logger.info("[Prompt] ⚠ 无对话历史")
        logger.info("")
        
        # 添加当前输入
        prompt_parts.append(f"\n## 当前问题\n{user_input}")
        logger.info(f"[Prompt] ✓ 添加当前用户输入")
        logger.info("")
        
        final_prompt = "\n".join(prompt_parts)
        
        logger.info("-" * 100)
        logger.info(f"[Prompt] ✓ Prompt 构建完成 (总长度: {len(final_prompt)} 字符)")
        logger.info("-" * 100)
        logger.info("")
        
        return final_prompt
    
    async def process_turn(self, user_input: str, debug: bool = False):
        """处理一轮对话
        
        完整的对话处理流程：
        1. 优化上下文（获取相关历史和记忆）
        2. 构建 Prompt
        3. 调用 LLM 生成回复（模拟）
        4. 更新上下文
        5. 提取知识
        
        Args:
            user_input: 用户输入
            debug: 是否返回调试信息
            
        Returns:
            助手回复，或 (助手回复, 调试信息字典) 当debug=True时
        """
        # 初始化步骤计时
        self.step_timings = {}
        
        debug_info = {} if debug else None
        
        # 步骤1: 优化上下文
        step_start = time.time()
        if debug:
            # 保存优化前的记忆库状态
            memory_cache = self.evolve_engine.memory_bank.get_memory_cache()
            debug_info['memory_before'] = [
                {
                    "content": m.content, 
                    "type": m.metadata.get('type', 'UNKNOWN') if hasattr(m, 'metadata') else 'UNKNOWN',
                    "confidence": m.score  # ContextItem 使用 score 而不是 confidence
                }
                for m in memory_cache
            ]
        
        context_result = await self.evolve_engine.optimize(
            user_input=user_input,
            include_session=True,
            include_memory=True,
        )
        self.step_timings['上下文检索'] = time.time() - step_start
        
        if debug:
            # 保存召回结果
            debug_info['context_result'] = {
                'items': [
                    {
                        'content': item.content,
                        'source': str(item.source),
                        'score': item.score,
                        'metadata': item.metadata
                    }
                    for item in context_result.items
                ],
                'total_items': len(context_result.items),
                'compressed': context_result.compressed
            }
        
        # 步骤2: 构建 Prompt
        step_start = time.time()
        prompt = await self.build_prompt(user_input, context_result)
        self.step_timings['上下文整合'] = time.time() - step_start
        
        if debug:
            debug_info['prompt'] = prompt
        
        # 步骤3: 调用 LLM（v7.1: LLM 调用是外部的）
        step_start = time.time()
        if self.use_real_llm and self.llm_client:
            try:
                # 调用真实 LLM
                reasoning, response = await self.llm_client.generate_async(prompt)
                if reasoning:
                    logger.debug(f"[LLM Reasoning] {reasoning[:200]}...")
            except Exception as e:
                logger.error(f"[LLM Error] {e}")
                response = f"[LLM调用失败] {str(e)}"
        else:
            # 模拟回复（仅用于测试）
            response = f"[模拟回复] 收到您的问题：{user_input}。这是一个示例回复，实际应用中需要调用真实的LLM。"
        self.step_timings['LLM生成'] = time.time() - step_start
        
        # 步骤4: 更新上下文
        step_start = time.time()
        await self.evolve_engine.update(
            user_input=user_input,
            assistant_response=response
        )
        self.step_timings['对话更新'] = time.time() - step_start
        
        # 步骤5: 提取知识（如果需要）
        step_start = time.time()
        extracted_knowledge = []
        try:
            knowledge_list = await self.evolve_engine.extract_knowledge(auto_store=True)
            if debug and knowledge_list:
                extracted_knowledge = [
                    {
                        'content': k.content,
                        'type': str(k.knowledge_type),
                        'confidence': k.confidence
                    }
                    for k in knowledge_list
                ]
        except Exception as e:
            logger.warning(f"知识提取失败: {e}")
        self.step_timings['知识提取'] = time.time() - step_start
        
        if debug:
            debug_info['extracted_knowledge'] = extracted_knowledge
            return response, debug_info
        
        return response
    
    @classmethod
    def create_from_config(cls, llm_client, scenario_config):
        """
        从场景配置创建InsuranceApplication实例的工厂方法
        
        这个方法封装了从demo文件中提取的初始化逻辑，使得demo文件只需要简单调用即可。
        
        参数:
            llm_client: LLM客户端实例
            scenario_config: 场景配置对象（来自scenarios模块）
            
        返回:
            配置好的InsuranceApplication实例
            
        示例:
            from contextmind.scenarios.insurance.app import InsuranceApplication
            from contextmind.scenarios import get_insurance_scenario
            from contextmind.infra.llm_client import SimpleLLMClient
            
            llm_client = SimpleLLMClient()
            config = get_insurance_scenario()
            app = InsuranceApplication.create_from_config(
                llm_client=llm_client,
                scenario_config=config
            )
        """
        # 创建EvolveEngine
        engine = EvolveEngine(
            app_name=f"demo_{scenario_config.name}",
            user_id="demo_user",
            llm_client=llm_client
        )
        
        # 创建并返回Application实例
        return cls(
            evolve_engine=engine,
            system_prompt=scenario_config.system_prompt,
            llm_client=llm_client,
            use_real_llm=True
        )
