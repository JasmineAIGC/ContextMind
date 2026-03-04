"""
FnCTOD 追踪器（Function Calling for Task-Oriented Dialogue）

基于论文"Large Language Models as Zero-shot Dialogue State Tracker
through Function Calling"的两阶段 DST 实现：

  第一阶段（Domain Selection）：根据用户话语选出候选业务域；
  第二阶段（Function Calling）：对每个候选域调用对应 function，
    由 LLM 以 JSON 参数形式填充槽位，并生成自然语言回复。

与传统 DST 的区别：DST 直接提取"槽位-值"对，FnCTOD 将槽位
提取建模为函数调用，输出更结构化，也更易扩展到新业务域。
"""

import json
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from .function_manager import FunctionCall, DialogueTurn
from .function_manager import FunctionManager
from .parser import FnCTODResponseParser
from .schemas import get_function_schema_for_scenario
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
        scenario_config=None,
        use_two_stage: bool = True,
        max_history_turns: int = 10
    ):
        """
        初始化FnCTOD追踪器
        
        Args:
            llm_client: LLM客户端
            function_manager: 函数管理器
            scenario_config: 场景配置对象（可选，用于优化域选择）
            use_two_stage: 是否使用两阶段处理（默认True）
            max_history_turns: 最大历史轮数
        """
        self.llm_client = llm_client
        self.function_manager = function_manager or FunctionManager()
        self.parser = FnCTODResponseParser()
        self.scenario_config = scenario_config
        self.use_two_stage = use_two_stage
        self.max_history_turns = max_history_turns
        
        self.current_state: Dict[str, Any] = {}
        self.dialogue_history: List[DialogueTurn] = []
        self.turn_count = 0
        self.step_timings: Dict[str, float] = {}
        
        self._load_prompt_templates()
        
        logger.info(f"FnCTODTracker 初始化完成 (两阶段模式: {use_two_stage}, 场景: {scenario_config.name if scenario_config else '未指定'})")
    
    @classmethod
    def from_scenario(cls,
                     llm_client,
                     scenario_config,
                     use_two_stage: bool = True,
                     max_history_turns: int = 10):
        """
        从场景配置创建 FnCTODTracker 实例（推荐入口）。

        优先使用 schemas.py 中预定义的结构化 FunctionSchema；
        若场景未预定义 Schema，则根据 ScenarioConfig.dst_slots 动态构建，
        降级后提取精度可能略低于预定义版本。

        Args:
            llm_client: LLM 客户端实例。
            scenario_config: 场景配置对象（ScenarioConfig）。
            use_two_stage: 是否启用两阶段处理（默认 True）。
            max_history_turns: 保留在 prompt 中的最大历史轮数（默认 10）。

        Returns:
            初始化完成的 FnCTODTracker 实例。
        """
        function_manager = FunctionManager()
        try:
            schema = get_function_schema_for_scenario(scenario_config.name)
            function_manager.add_domain(schema)
            logger.info(f"✅ 已加载预定义FnCTOD Schema: {schema.name}")
        except ValueError as e:
            # 场景无预定义 Schema，根据槽位定义动态构建。
            logger.warning(f"未找到预定义Schema，使用动态创建: {e}")
            function_manager.add_domain_from_slots(
                domain_name=scenario_config.name,
                domain_description=getattr(scenario_config, 'description', f"{scenario_config.name} domain"),
                slots=scenario_config.dst_slots,
                categorical_slots=getattr(scenario_config, 'dst_categorical_slots', None),
                required_slots=[]
            )

        return cls(
            llm_client=llm_client,
            function_manager=function_manager,
            scenario_config=scenario_config,
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
        
        self.step_timings = {}
        
        logger.info(f"\n{'='*60}")
        logger.info(f"处理第 {self.turn_count} 轮对话")
        logger.info(f"用户: {user_utterance}")
        logger.info(f"{'='*60}")
        
        selected_domains = []
        
        # 智能检测：如果场景已确定，跳过域选择
        if self.scenario_config:
            # 注意：使用FunctionManager中实际注册的domain名称，而不是scenario_config.name
            # 因为scenario名称（如"保险挽回"）可能与domain名称（如"insurance"）不同
            available_domains = self.function_manager.get_domain_names()
            if available_domains:
                selected_domains = available_domains
                logger.info(f"✅ 场景已确定，跳过域选择，直接使用domain: {selected_domains}")
            else:
                # 如果没有注册的domain，回退到域选择
                logger.warning("⚠️ 场景已确定但没有注册的domain，执行域选择")
                selected_domains = await self._select_domains(user_utterance)
        elif self.use_two_stage and len(self.function_manager.get_all_domains()) > 1:
            selected_domains = await self._select_domains(user_utterance)
        else:
            # 单阶段或单domain场景，直接使用所有domain
            selected_domains = self.function_manager.get_domain_names()
        
        function_call, natural_response = await self._call_function(
            user_utterance,
            selected_domains
        )
        
        step_start = time.time()
        if function_call:
            self._update_state(function_call)
        
        turn = DialogueTurn(
            turn_id=self.turn_count,
            user_utterance=user_utterance,
            system_utterance=natural_response,
            function_call=function_call,
            state=self.current_state.copy()
        )
        self.dialogue_history.append(turn)
        
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
        Stage 1: 选择相关的domain（FnCTOD论文Fig.2第一阶段）
        
        Args:
            user_utterance: 用户输入
        
        Returns:
            domain名称列表
        """
        logger.info("Stage 1: Domain Selection")
        
        prompt_start = time.time()
        
        # 根据FnCTOD论文，提示词包含所有domain的简要描述
        system_prompt = self.function_manager.build_system_prompt(include_all_specs=False)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_utterance}
        ]
        
        # 添加对话历史（最近几轮）
        for turn in self.dialogue_history[-3:]:
            messages.append({"role": "user", "content": turn.user_utterance})
            if turn.system_utterance:
                messages.append({"role": "assistant", "content": turn.system_utterance})
        
        messages.append({"role": "user", "content": user_utterance})
        
        self.step_timings['提示词构建'] = time.time() - prompt_start
        
        llm_start = time.time()
        try:
            response = await self.llm_client.chat_async(messages)
            logger.debug(f"Domain选择响应: {response}")
            
            domains = self.parser.parse_domain_selection(response)
            
            if not domains:
                # 如果没有检测到domain，使用默认策略
                logger.warning("未检测到domain，使用第一个domain作为默认")
                domains = [self.function_manager.get_domain_names()[0]]
            
            self.step_timings['域选择'] = time.time() - llm_start
            logger.info(f"✅ Domain选择完成: {domains}")
            
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
        Stage 2: 调用函数填充参数（FnCTOD论文Fig.2第二阶段）
        
        Args:
            user_utterance: 用户输入
            domains: 候选domain列表
        
        Returns:
            (FunctionCall对象, 自然语言回复)
        """
        logger.info(f"Stage 2: Function Calling for domains: {domains}")
        
        # 根据FnCTOD论文Fig.3，提示词包含整体指令、函数规格（JSON schema）和few-shot示例
        prompt_start = time.time()
        
        system_prompt = self._build_function_call_prompt(domains)
        
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 添加对话历史（包含function call和自然语言回复）
        for turn in self.dialogue_history[-self.max_history_turns:]:
            messages.append({"role": "user", "content": turn.user_utterance})
            
            # 构建完整的assistant回复（function call + 自然语言回复）
            if turn.function_call and turn.system_utterance:
                assistant_content = f"{turn.function_call.to_xml()}\n{turn.system_utterance}"
                messages.append({"role": "assistant", "content": assistant_content})
            elif turn.system_utterance:
                # 只有自然语言回复（降级情况）
                messages.append({"role": "assistant", "content": turn.system_utterance})
        
        # 添加当前状态提示（帮助LLM维护累积状态）
        if self.current_state:
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
        
        messages.append({"role": "user", "content": user_utterance})
        
        self.step_timings['提示词构建'] = time.time() - prompt_start
        
        # 根据FnCTOD论文，LLM输出 <function_call name="domain">{"param": "value"}</function_call> + 自然语言回复
        llm_start = time.time()
        try:
            response = await self.llm_client.chat_async(messages)
            logger.info(f"✅ 收到LLM响应，长度: {len(response)}")
            logger.debug(f"LLM响应前300字符: {response[:300]}...")
            
            self.step_timings['函数调用'] = time.time() - llm_start
            
            # 根据FnCTOD论文，需要提取：
            # 1. <function_call> 标签内的JSON参数
            # 2. 标签后的自然语言回复
            parse_start = time.time()
            logger.info("开始解析function call...")
            function_call, natural_response = self.parser.parse_function_call(response)
            
            if not function_call:
                logger.warning("⚠️ 未检测到function call，使用响应作为自然语言回复")
                logger.warning(f"⚠️ 完整响应: {response}")
                natural_response = response
            else:
                logger.info(f"✅ Function call解析成功: {function_call.function_name}")
                logger.info(f"✅ 提取的参数: {function_call.arguments}")
            
            self.step_timings['响应解析'] = time.time() - parse_start
            
            return function_call, natural_response
        except Exception as e:
            logger.error(f"❌ Function calling失败: {e}", exc_info=True)
            return None, "抱歉，我遇到了一些问题，请重新表述您的需求。"
    
    def _load_prompt_templates(self) -> None:
        """加载提示词模板配置文件"""
        template_path = Path(__file__).parent / "prompts.yaml"
        
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
    
    def _build_fallback_prompt(self, domains: List[str]) -> str:
        """
        后备提示词（配置文件不可用时使用的内置最小模板）
        
        Args:
            domains: 需要生成提示词的 domain 名称列表
        
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
        
        使用 prompts.yaml 配置文件中的模板和示例，
        实现提示词的可配置化和场景化。
        
        Args:
            domains: domain列表
        
        Returns:
            提示词文本
        """
        if not self.prompt_templates:
            return self._build_fallback_prompt(domains)
        
        templates = self.prompt_templates
        prompt_parts = []
        
        prompt_parts.append(templates.get('system_prompt', ''))
        prompt_parts.append("")
        prompt_parts.append("Available functions:")
        
        for domain_name in domains:
            domain = self.function_manager.get_domain(domain_name)
            if domain:
                prompt_parts.append("")
                prompt_parts.append(domain.to_prompt_format())
        
        output_fmt = templates.get('output_format', {})
        prompt_parts.append("")
        prompt_parts.append(output_fmt.get('importance_note', ''))
        
        prompt_parts.append("")
        prompt_parts.append(output_fmt.get('format_description', ''))
        
        domain_name = domains[0] if domains else 'chat'
        examples = self._get_examples_for_domain(domain_name)
        
        if examples:
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
        """向后兼容别名，请使用 ``from_scenario()``。"""
        return cls.from_scenario(
            llm_client=llm_client,
            scenario_config=scenario_config,
            use_two_stage=use_two_stage,
            max_history_turns=max_history_turns,
        )
