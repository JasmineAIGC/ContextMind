"""
FnCTOD Tracker

主追踪器，实现两阶段function calling的DST
"""

import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from .data_models import FunctionCall, DialogueTurn
from .function_manager import FunctionManager
from .response_parser import FnCTODResponseParser
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class FnCTODTracker:
    """
    FnCTOD 追踪器
    
    实现基于函数调用的对话状态追踪，特点：
    1. 两阶段处理：domain选择 → parameter填充
    2. 自动维护累积状态
    3. 支持多domain场景
    4. 输出结构化function call + 自然语言回复
    
    与DST的主要区别：
    - DST: 直接提取槽位-值
    - FnCTOD: 通过function calling间接提取，更结构化
    """
    
    def __init__(
        self,
        llm_client=None,
        function_manager: Optional[FunctionManager] = None,
        use_two_stage: bool = True,
        max_history_turns: int = 10
    ):
        """
        初始化FnCTOD追踪器
        
        Args:
            llm_client: LLM客户端
            function_manager: 函数管理器
            use_two_stage: 是否使用两阶段处理（默认True）
            max_history_turns: 最大历史轮数
        """
        self.llm_client = llm_client
        self.function_manager = function_manager or FunctionManager()
        self.parser = FnCTODResponseParser()
        self.use_two_stage = use_two_stage
        self.max_history_turns = max_history_turns
        
        # 状态管理
        self.current_state: Dict[str, Any] = {}
        self.dialogue_history: List[DialogueTurn] = []
        self.turn_count = 0
        
        # 性能统计
        self.step_timings: Dict[str, float] = {}
        
        # 加载提示词模板
        self._load_prompt_templates()
        
        logger.info(f"FnCTODTracker 初始化完成 (两阶段模式: {use_two_stage})")
    
    @classmethod
    def from_scenario(cls,
                     llm_client,
                     scenario_config,
                     use_two_stage: bool = True,
                     max_history_turns: int = 10):
        """
        从场景配置创建FnCTODTracker实例的工厂方法
        
        Args:
            llm_client: LLM客户端实例
            scenario_config: 场景配置对象（ScenarioConfig）
            use_two_stage: 是否使用两阶段处理（默认True）
            max_history_turns: 最大历史轮数（默认10）
            
        Returns:
            FnCTODTracker实例
        """
        from contextmind.modes.fnctod import get_function_schema_for_scenario
        
        # 创建FunctionManager并加载schema
        function_manager = FunctionManager()
        try:
            # 使用预定义的函数Schema
            schema = get_function_schema_for_scenario(scenario_config.name)
            function_manager.add_domain(schema)
            logger.info(f"✅ 已加载预定义FnCTOD Schema: {schema.name}")
        except ValueError as e:
            # 如果场景不支持，降级为动态创建
            logger.warning(f"未找到预定义Schema，使用动态创建: {e}")
            function_manager.add_domain_from_slots(
                domain_name=scenario_config.name,
                domain_description=getattr(scenario_config, 'description', f"{scenario_config.name} domain"),
                slots=scenario_config.dst_slots,
                categorical_slots=getattr(scenario_config, 'dst_categorical_slots', None),
                required_slots=[]
            )
        
        # 创建并返回tracker实例
        return cls(
            llm_client=llm_client,
            function_manager=function_manager,
            use_two_stage=use_two_stage,
            max_history_turns=max_history_turns
        )
    
    async def process_turn(
        self,
        user_utterance: str,
        system_utterance: str = ""
    ) -> Dict[str, Any]:
        """
        处理一轮对话
        
        Args:
            user_utterance: 用户输入
            system_utterance: 系统输出（上一轮）
        
        Returns:
            包含state, response, function_call的字典
        """
        self.turn_count += 1
        start_time = time.time()
        
        # 初始化步骤计时字典
        self.step_timings = {}
        
        logger.info(f"\n{'='*60}")
        logger.info(f"处理第 {self.turn_count} 轮对话")
        logger.info(f"用户: {user_utterance}")
        logger.info(f"{'='*60}")
        
        # 步骤1: 历史准备
        step_start = time.time()
        # 准备对话历史用于后续处理（在_select_domains和_call_function中使用）
        self.step_timings['历史准备'] = time.time() - step_start
        
        # 步骤2: 提示词构建（在_select_domains或_call_function中完成）
        # 步骤3: Domain Selection (如果使用两阶段)
        selected_domains = []
        if self.use_two_stage and len(self.function_manager.get_all_domains()) > 1:
            selected_domains = await self._select_domains(user_utterance)
        else:
            # 单阶段或单domain场景，直接使用所有domain
            selected_domains = self.function_manager.get_domain_names()
        
        # 步骤4: Function Calling
        function_call, natural_response = await self._call_function(
            user_utterance,
            selected_domains
        )
        
        # 步骤5: 状态更新
        step_start = time.time()
        if function_call:
            self._update_state(function_call)
        
        # 记录对话轮次
        turn = DialogueTurn(
            turn_id=self.turn_count,
            user_utterance=user_utterance,
            system_utterance=natural_response,
            function_call=function_call,
            state=self.current_state.copy()
        )
        self.dialogue_history.append(turn)
        
        # 限制历史长度
        if len(self.dialogue_history) > self.max_history_turns:
            self.dialogue_history = self.dialogue_history[-self.max_history_turns:]
        
        self.step_timings['状态更新'] = time.time() - step_start
        
        elapsed = time.time() - start_time
        logger.info(f"✅ 对话处理完成 (耗时: {elapsed:.2f}s)")
        
        return {
            "state": self.current_state.copy(),
            "response": natural_response,
            "function_call": function_call.to_dict() if function_call else None,
            "turn_id": self.turn_count
        }
    
    async def _select_domains(self, user_utterance: str) -> List[str]:
        """
        Stage 1: 选择相关的domain
        
        Args:
            user_utterance: 用户输入
        
        Returns:
            domain名称列表
        """
        step_start = time.time()
        logger.info("Stage 1: Domain Selection")
        
        # 构建domain选择提示词
        system_prompt = self.function_manager.generate_system_prompt(include_all_specs=False)
        
        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_utterance}
        ]
        
        # 添加对话历史（最近几轮）
        for turn in self.dialogue_history[-3:]:
            messages.append({"role": "user", "content": turn.user_utterance})
            if turn.system_utterance:
                messages.append({"role": "assistant", "content": turn.system_utterance})
        
        # 添加当前用户输入
        messages.append({"role": "user", "content": user_utterance})
        
        # 记录提示词构建时间
        prompt_time = time.time() - step_start
        
        # 调用LLM
        llm_start = time.time()
        try:
            response = await self.llm_client.chat_async(messages)
            logger.debug(f"Domain选择响应: {response}")
            
            # 解析domain
            domains = self.parser.parse_domain_selection(response)
            
            if not domains:
                # 如果没有检测到domain，使用默认策略
                logger.warning("未检测到domain，使用第一个domain作为默认")
                domains = [self.function_manager.get_domain_names()[0]]
            
            # 记录总时间（包含提示词构建和LLM调用）
            self.step_timings['提示词构建'] = prompt_time
            self.step_timings['领域选择'] = time.time() - llm_start
            logger.info(f"选中的domain: {domains}")
            
            return domains
        except Exception as e:
            logger.error(f"Domain选择失败: {e}")
            # 降级：返回所有domain
            return self.function_manager.get_domain_names()
    
    async def _call_function(
        self,
        user_utterance: str,
        domains: List[str]
    ) -> Tuple[Optional[FunctionCall], str]:
        """
        Stage 2: 调用函数填充参数
        
        Args:
            user_utterance: 用户输入
            domains: 候选domain列表
        
        Returns:
            (FunctionCall对象, 自然语言回复)
        """
        step_start = time.time()
        logger.info(f"Stage 2: Function Calling for domains: {domains}")
        
        # 如果没有提示词构建时间（单阶段模式），记录它
        if '提示词构建' not in self.step_timings:
            prompt_start = time.time()
        
        # 构建完整规格提示词（只包含选中的domain）
        system_prompt = self._build_function_call_prompt(domains)
        
        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 添加对话历史（包含function call和自然语言回复）
        for turn in self.dialogue_history[-self.max_history_turns:]:
            messages.append({"role": "user", "content": turn.user_utterance})
            
            # 构建完整的assistant回复（function call + 自然语言回复）
            if turn.function_call and turn.system_utterance:
                # 包含function call和自然语言回复
                assistant_content = f"{turn.function_call.to_xml()}\n{turn.system_utterance}"
                messages.append({"role": "assistant", "content": assistant_content})
            elif turn.system_utterance:
                # 只有自然语言回复（降级情况）
                messages.append({"role": "assistant", "content": turn.system_utterance})
        
        # 添加当前状态提示（帮助LLM维护累积状态）
        if self.current_state:
            # 将状态转换为更清晰的JSON格式
            import json
            # 将 "domain-param" 格式转换为 domain分组的字典
            state_by_domain = {}
            for key, value in self.current_state.items():
                if '-' in key:
                    domain, param = key.split('-', 1)
                    if domain not in state_by_domain:
                        state_by_domain[domain] = {}
                    state_by_domain[domain][param] = value
            
            state_json = json.dumps(state_by_domain, ensure_ascii=False, indent=2)
            messages.append({
                "role": "system",
                "content": f"Previous cumulative state:\n{state_json}\n\nRemember to include ALL previous parameters in your function call, plus any new ones from the current turn."
            })
        
        # 添加当前用户输入
        messages.append({"role": "user", "content": user_utterance})
        
        # 如果是单阶段模式，记录提示词构建时间
        if '提示词构建' not in self.step_timings:
            self.step_timings['提示词构建'] = time.time() - prompt_start
        
        # 调用LLM
        llm_start = time.time()
        try:
            response = await self.llm_client.chat_async(messages)
            logger.info(f"✅ 收到LLM响应，长度: {len(response)}")
            logger.debug(f"LLM响应前300字符: {response[:300]}...")
            
            # 记录LLM调用时间
            self.step_timings['函数调用'] = time.time() - llm_start
            
            # 解析function call
            parse_start = time.time()
            logger.info("开始解析function call...")
            function_call, natural_response = self.parser.parse_function_call(response)
            
            if not function_call:
                # 如果没有检测到function call，将整个响应作为自然语言回复
                logger.warning("⚠️ 未检测到function call，使用响应作为自然语言回复")
                logger.warning(f"⚠️ 完整响应: {response}")
                natural_response = response
            else:
                logger.info(f"✅ Function call解析成功: {function_call.function_name}")
                logger.info(f"✅ 提取的参数: {function_call.arguments}")
            
            # 记录解析时间
            self.step_timings['响应解析'] = time.time() - parse_start
            
            return function_call, natural_response
        except Exception as e:
            logger.error(f"❌ Function calling失败: {e}", exc_info=True)
            return None, "抱歉，我遇到了一些问题，请重新表述您的需求。"
    
    def _load_prompt_templates(self) -> None:
        """加载提示词模板配置文件"""
        template_path = Path(__file__).parent / "fnctod_prompts.yaml"
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                self.prompt_templates = yaml.safe_load(f)
            logger.debug("成功加载FnCTOD提示词模板")
        except Exception as e:
            logger.warning(f"无法加载提示词模板: {e}，将使用默认配置")
            self.prompt_templates = None
    
    def _get_examples_for_domain(self, domain_name: str) -> dict:
        """
        获取域特定的示例
        
        Args:
            domain_name: 域名称
        
        Returns:
            示例字典（包含single_turn和multi_turn）
        """
        if not self.prompt_templates:
            return {}
        
        # 优先使用场景特定示例
        scenario_examples = self.prompt_templates.get('scenario_examples', {})
        if domain_name in scenario_examples:
            return scenario_examples[domain_name]
        
        # 降级到默认示例
        return self.prompt_templates.get('default_examples', {})
    
    def _build_default_prompt(self, domains: List[str]) -> str:
        """
        构建默认提示词（配置文件不可用时的降级方案）
        
        Args:
            domains: domain列表
        
        Returns:
            提示词文本
        """
        prompt_parts = [
            "You are a task-oriented dialogue assistant with function calling capability.",
            "",
            "Available functions:"
        ]
        
        for domain_name in domains:
            domain = self.function_manager.get_domain(domain_name)
            if domain:
                prompt_parts.append("")
                prompt_parts.append(domain.to_prompt_format())
        
        prompt_parts.extend([
            "",
            "IMPORTANT: You MUST always output a function call for every user input.",
            "",
            "Output format:",
            "<function_call name=\"function_name\">",
            "{\"param1\": \"value1\"}",
            "</function_call>",
            "Natural language response",
            "",
            "Instructions:",
            "- Include ALL parameters from previous turns",
            "- Add any new parameters from current turn",
        ])
        
        return "\n".join(prompt_parts)
    
    def _build_function_call_prompt(self, domains: List[str]) -> str:
        """
        构建function call提示词（从配置文件加载，支持自定义）
        
        使用 fnctod_prompts.yaml 配置文件中的模板和示例，
        实现提示词的可配置化和场景化。
        
        Args:
            domains: domain列表
        
        Returns:
            提示词文本
        """
        # 如果没有加载模板，使用默认提示词
        if not self.prompt_templates:
            return self._build_default_prompt(domains)
        
        templates = self.prompt_templates
        prompt_parts = []
        
        # 1. 系统提示词
        prompt_parts.append(templates.get('system_prompt', ''))
        prompt_parts.append("")
        prompt_parts.append("Available functions:")
        
        # 2. 添加域的函数定义
        for domain_name in domains:
            domain = self.function_manager.get_domain(domain_name)
            if domain:
                prompt_parts.append("")
                prompt_parts.append(domain.to_prompt_format())
        
        # 3. 重要性提示
        output_fmt = templates.get('output_format', {})
        prompt_parts.append("")
        prompt_parts.append(output_fmt.get('importance_note', ''))
        
        # 4. 输出格式说明
        prompt_parts.append("")
        prompt_parts.append(output_fmt.get('format_description', ''))
        
        # 5. 示例（使用场景特定或默认示例）
        domain_name = domains[0] if domains else 'chat'
        examples = self._get_examples_for_domain(domain_name)
        
        if examples:
            # 单轮示例
            if 'single_turn' in examples:
                example = examples['single_turn']
                template = output_fmt.get('single_turn_example_template', '')
                if template:
                    prompt_parts.append("")
                    prompt_parts.append(template.format(
                        domain=example.get('domain', domain_name),
                        example_params=example.get('params', '{}'),
                        example_response=example.get('response', '')
                    ))
            
            # 多轮示例
            if 'multi_turn' in examples:
                example = examples['multi_turn']
                template = output_fmt.get('multi_turn_example_template', '')
                if template:
                    prompt_parts.append("")
                    prompt_parts.append(template.format(
                        domain=example.get('domain', domain_name),
                        turn1_user=example.get('turn1', {}).get('user', ''),
                        turn1_params=example.get('turn1', {}).get('params', '{}'),
                        turn1_response=example.get('turn1', {}).get('response', ''),
                        turn2_user=example.get('turn2', {}).get('user', ''),
                        turn2_params=example.get('turn2', {}).get('params', '{}'),
                        turn2_response=example.get('turn2', {}).get('response', '')
                    ))
        
        # 6. 累积状态指令
        prompt_parts.append("")
        prompt_parts.append(templates.get('cumulative_state_instructions', ''))
        
        return "\n".join(prompt_parts)
    
    def _update_state(self, function_call: FunctionCall):
        """
        更新累积状态
        
        Args:
            function_call: 函数调用对象
        """
        domain = function_call.function_name
        
        for param_name, param_value in function_call.arguments.items():
            state_key = f"{domain}-{param_name}"
            
            # 更新或添加状态
            if param_value:  # 只更新非空值
                self.current_state[state_key] = param_value
                logger.debug(f"状态更新: {state_key} = {param_value}")
    
    def get_current_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        return self.current_state.copy()
    
    def reset(self):
        """重置追踪器状态"""
        self.current_state = {}
        self.dialogue_history = []
        self.turn_count = 0
        self.step_timings = {}
        logger.info("FnCTOD追踪器状态已重置")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "turn_count": self.turn_count,
            "state_size": len(self.current_state),
            "history_size": len(self.dialogue_history),
            "timings": self.step_timings.copy()
        }
    
    @classmethod
    def create_from_config(cls, llm_client, scenario_config,
                          use_two_stage: bool = True,
                          max_history_turns: int = 10):
        """
        从场景配置创建FnCTODTracker实例的工厂方法
        
        这个方法封装了从demo文件中提取的初始化逻辑，使得demo文件只需要简单调用即可。
        
        参数:
            llm_client: LLM客户端实例
            scenario_config: 场景配置对象（来自scenarios模块）
            use_two_stage: 是否使用两阶段处理（domain选择 + function calling）
            max_history_turns: 最大历史轮数
            
        返回:
            配置好的FnCTODTracker实例
            
        示例:
            from contextmind.modes.fnctod import FnCTODTracker
            from scenarios import get_chat_scenario
            from contextmind.infra.llm_client import SimpleLLMClient
            
            llm_client = SimpleLLMClient()
            config = get_chat_scenario()
            tracker = FnCTODTracker.create_from_config(
                llm_client=llm_client,
                scenario_config=config
            )
        """
        from contextmind.modes.fnctod import get_function_schema_for_scenario, FunctionManager
        
        # 创建FunctionManager
        function_manager = FunctionManager()
        
        try:
            # 优先使用预定义的函数Schema
            schema = get_function_schema_for_scenario(scenario_config.name)
            function_manager.add_domain(schema)
            logger.info(f"✅ 已加载预定义FnCTOD Schema: {schema.name}")
        except ValueError as e:
            # 如果场景不支持，降级为动态创建
            logger.warning(f"未找到预定义Schema，使用动态创建: {e}")
            function_manager.add_domain_from_slots(
                domain_name=scenario_config.name,
                domain_description=getattr(scenario_config, 'description', f"{scenario_config.name} domain"),
                slots=scenario_config.dst_slots,
                categorical_slots=getattr(scenario_config, 'dst_categorical_slots', None),
                required_slots=[]
            )
        
        # 创建并返回tracker实例
        return cls(
            llm_client=llm_client,
            function_manager=function_manager,
            use_two_stage=use_two_stage,
            max_history_turns=max_history_turns
        )
