#!/usr/bin/env python3
"""
Evolution 统一Gradio Web Demo

v0.4.1 - 直接使用 ADK Agent

支持三个场景：chat（闲聊）、callcenter（客服）、insurance（保险）
支持两种模式：DST对话状态追踪模式、Evolution记忆进化模式

使用方式:
    python gradio_demo.py
    python gradio_demo.py --log-level DEBUG --port 8080
    python gradio_demo.py --max-history-turns 20 --share
"""

import argparse
import asyncio
from typing import List, Tuple, Optional
from datetime import datetime
from pathlib import Path

# 直接使用各模式的 ADK Agent
from dst import DSTAgent
from evolution import EvolutionAgent

from dst import DialogueStateTracker, PromptManager
from evolution import EvolutionEngine
from scenarios import get_chat_scenario, get_callcenter_scenario, get_insurance_scenario
from apps.chat_app import ChatApplication
from apps.callcenter_app import CallCenterApplication
from apps.insurance_app import InsuranceApplication
from ui_components import create_gradio_ui, CUSTOM_CSS
from utils.logger import get_logger, setup_logging, LogLevel

# 使用统一的logger
logger = get_logger(__name__)
logger.info("v0.4.1 - 直接使用 ADK Agent")


class UnifiedGradioDemo:
    """统一的Gradio Demo类"""
    
    def __init__(self, max_history_turns: int = 10):
        """
        初始化Demo
        
        Args:
            max_history_turns: DST模式的最大历史轮数
        """
        self.current_scenario = None
        self.current_mode = None
        self.config = None
        self.llm_client = None
        self.tracker = None
        self.max_history_turns = max_history_turns
        self.app = None
        self.initialized = False
        self.history = []
        # 存储用户输入处理后、机器人回复前的对话状态
        self.post_user_state = None
        logger.info("Demo实例创建完成（延迟初始化）")
    
    def initialize_scenario(self, scenario: str, mode: str):
        """初始化场景和模式"""
        self.current_scenario = scenario
        self.current_mode = mode
        
        # 加载场景配置
        if scenario == "chat":
            self.config = get_chat_scenario()
        elif scenario == "callcenter":
            self.config = get_callcenter_scenario()
        elif scenario == "insurance":
            self.config = get_insurance_scenario()
        else:
            raise ValueError(f"未知场景: {scenario}")
        
        # 根据模式初始化
        if mode == "dst":
            self._init_dst_mode()
        else:
            self._init_evolution_mode()
        
        logger.info(f"✅ 场景初始化完成: {scenario}, 模式: {mode}")
    
    def _init_dst_mode(self):
        """初始化DST模式"""
        try:
            if self.llm_client is None:
                self.llm_client = DSTAgent()  # 直接使用 DST Agent
                logger.info("✅ DST Agent 初始化成功")
        except Exception as e:
            error_msg = f"❌ DST Agent 初始化失败: {str(e)}\n\n"
            if "API" in str(e).upper() or "KEY" in str(e).upper():
                error_msg += "📝 请检查以下配置：\n"
                error_msg += "1. 确认.env文件存在\n"
                error_msg += "2. 配置 API Key (GOOGLE_API_KEY 或 OPENAI_API_KEY)\n"
                error_msg += "3. 安装依赖: pip install google-adk litellm\n"
                error_msg += "4. 重启程序\n"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # 创建PromptManager，使用自定义模板（如果提供）
        pm = PromptManager(
            domain=self.config.name,
            enable_dynamic_slots=self.config.enable_dynamic_slots,  # 使用场景配置
            custom_template=getattr(self.config, 'dst_prompt_template', None)  # 使用自定义模板
        )
        
        # 添加预定义槽位
        for slot_name, slot_desc in self.config.dst_slots.items():
            # 检查是否有分类约束
            categorical_values = None
            if self.config.dst_categorical_slots and slot_name in self.config.dst_categorical_slots:
                categorical_values = self.config.dst_categorical_slots[slot_name]
            pm.add_slot(slot_name, slot_desc, categorical_values=categorical_values)
        
        # 创建DialogueStateTracker
        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=10,
            enable_history_summary=True,
            use_llm_summary=False
        )
        
        logger.info("DST模式初始化完成")
    
    def _init_evolution_mode(self):
        """初始化Evolution模式"""
        try:
            if self.llm_client is None:
                self.llm_client = EvolutionAgent()  # 直接使用 Evolution Agent
                logger.info("✅ Evolution Agent 初始化成功")
        except Exception as e:
            error_msg = f"❌ Evolution Agent 初始化失败: {str(e)}\n\n"
            if "API" in str(e).upper() or "KEY" in str(e).upper():
                error_msg += "📝 请配置.env文件中的 API Key (GOOGLE_API_KEY 或 OPENAI_API_KEY)\n"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # 创建EvolutionEngine - 使用正确的参数
        engine = EvolutionEngine(
            app_name=f"gradio_demo_{self.current_scenario}",
            user_id="gradio_user",
            llm_client=self.llm_client
        )
        
        # 创建对应的Application - 使用正确的参数名
        if self.current_scenario == "chat":
            self.app = ChatApplication(context_engine=engine, system_prompt=self.config.system_prompt)
        elif self.current_scenario == "callcenter":
            self.app = CallCenterApplication(context_engine=engine, system_prompt=self.config.system_prompt)
        elif self.current_scenario == "insurance":
            self.app = InsuranceApplication(context_engine=engine, system_prompt=self.config.system_prompt)
        
        logger.info("Evolution模式初始化完成")
    
    async def chat(self, message: str, history: List) -> List:
        """处理对话"""
        import time
        
        try:
            # 首次使用时初始化
            if not self.initialized:
                self.initialize_scenario("chat", "evolution")
                self.initialized = True
            
            if not message or not message.strip():
                return history
            
            # 开始计时 - 从接收输入到生成结果
            start_time = time.time()
            
            # 用于记录各步骤耗时
            timing_breakdown = {}
            
            # 处理对话
            if self.current_mode == "dst":
                # DST模式
                # 获取上一轮系统回复
                # history格式: [{user_msg}, {assistant_msg}, {user_msg}, {assistant_msg}, ...]
                # 安全地获取上一轮的assistant回复内容
                system_utterance = next(
                    (msg.get('content', '你好！') for msg in reversed(history) if msg.get('role') == 'assistant'),
                    '你好！'
                )
                
                # 确保system_utterance是字符串类型（防止list等其他类型）
                if not isinstance(system_utterance, str):
                    if isinstance(system_utterance, list):
                        # 如果是列表，提取第一个元素或转换为字符串
                        system_utterance = str(system_utterance[0]) if system_utterance else '你好！'
                    else:
                        # 其他类型转换为字符串
                        system_utterance = str(system_utterance) if system_utterance else '你好！'
                
                # 移除耗时标记，避免影响DST提取和历史累积
                # 格式: "\n\n<small style='color: #888;'>⏱️ 生成耗时: X.XX秒</small>"
                import re
                system_utterance = re.sub(r'\n\n<small style=.*?生成耗时:.*?</small>', '', system_utterance)
                
                # 步骤1: 槽位提取（包含DST内部的多个步骤）
                step_start = time.time()
                state = await self.tracker.process_turn(
                    system_utterance=system_utterance,
                    user_utterance=message
                )
                timing_breakdown['槽位提取'] = time.time() - step_start
                
                # 收集DST内部的详细步骤耗时
                if hasattr(self.tracker, 'step_timings'):
                    timing_breakdown.update(self.tracker.step_timings)
                    # 移除重复的'槽位提取'（使用DST内部的详细步骤）
                    if '槽位提取' in timing_breakdown and len(self.tracker.step_timings) > 0:
                        del timing_breakdown['槽位提取']
                
                # 步骤2: 状态捕获
                step_start = time.time()
                self._capture_post_user_state()
                timing_breakdown['状态捕获'] = time.time() - step_start
                
                # 步骤3: 回复生成
                step_start = time.time()
                system_prompt = self.config.system_prompt
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ]
                
                # chat_async returns a string directly, not a dict
                reply = await self.llm_client.chat_async(messages=messages)
                timing_breakdown['回复生成'] = time.time() - step_start
                
            else:
                # Evolution模式
                step_start = time.time()
                reply = await self.app.process_turn(message)
                timing_breakdown['对话处理'] = time.time() - step_start
                
                # 收集Evolution内部的详细步骤耗时
                if hasattr(self.app, 'step_timings'):
                    timing_breakdown.update(self.app.step_timings)
                    # 移除重复的'对话处理'（使用Evolution内部的详细步骤）
                    if '对话处理' in timing_breakdown and len(self.app.step_timings) > 0:
                        del timing_breakdown['对话处理']
                
                # 关键修改：在bot回复后立即捕获状态
                # 注意：Evolution的process_turn是原子操作，包含了提取和回复
                # 所以我们在其完成后立即捕获，这个状态反映了用户输入的理解
                step_start = time.time()
                self._capture_post_user_state()
                timing_breakdown['状态捕获'] = time.time() - step_start
            
            # 计算总耗时（从接收输入到生成结果）
            elapsed_time = time.time() - start_time
            
            # 添加总计到timing_breakdown
            timing_breakdown['总计'] = elapsed_time
            
            # 构建一行显示的详细耗时信息
            if timing_breakdown:
                # 将所有步骤按顺序排列（总计放最后）
                ordered_timings = []
                for key, value in timing_breakdown.items():
                    if key != '总计':
                        ordered_timings.append(f"{key}{value:.2f}s")
                # 添加总计
                if '总计' in timing_breakdown:
                    ordered_timings.append(f"总计{timing_breakdown['总计']:.2f}s")
                
                timing_display = " | ".join(ordered_timings)
                timing_display = f"⏱️ 耗时: {timing_display}"
            else:
                timing_display = f"⏱️ 生成耗时: {elapsed_time:.2f}秒"
            
            # 在回复中添加耗时信息（小号灰色文本）
            reply_with_timing = f"{reply}\n\n<small style='color: #888;'>{timing_display}</small>"
            
            # 更新历史 - 使用Gradio 6.0格式 (flat list)
            return history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": reply_with_timing}
            ]
            
        except ValueError as e:
            # API密钥错误
            if "API" in str(e).upper() or "KEY" in str(e).upper():
                error_msg = "⚠️ 配置错误：缺少API密钥\n\n" + \
                           "请配置.env文件中的以下变量之一：\n" + \
                           "- QWEN3_API_KEY\n" + \
                           "- EVOLUTION_API_KEY\n" + \
                           "- LLM_API_KEY\n" + \
                           "- OPENAI_API_KEY\n\n" + \
                           f"详细错误: {str(e)}"
                return history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": error_msg}
                ]
            else:
                return history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": f"❌ 错误: {str(e)}"}
                ]
        except Exception as e:
            logger.error(f"对话处理错误: {e}", exc_info=True)
            return history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": f"❌ 系统错误: {str(e)}"}
            ]
    
    def _capture_post_user_state(self):
        """
        捕获用户输入处理后的对话状态（在bot回复生成之前）
        
        此方法在以下时机调用：
        - DST模式：process_turn()之后，LLM生成回复之前
        - Evolution模式：process_turn()之后（因为是原子操作）
        
        捕获的状态反映了系统对用户输入的理解，而不是完整对话轮次结束后的状态
        """
        try:
            # 直接构建状态字典，避免调用get_state造成循环
            self.post_user_state = self._build_state_dict()
        except Exception as e:
            logger.warning(f"捕获对话状态时出错: {e}")
            # 如果捕获失败，设置为None，get_state会使用实时状态
            self.post_user_state = None
    
    def _build_state_dict(self) -> dict:
        """构建状态字典（内部方法）
        
        累积状态说明：
        - 累积状态显示从对话开始到当前轮次，所有已提取槽位的最新值
        - 本轮提取显示最近一轮对话中新提取或更新的槽位
        - 累积状态会随着对话进行不断更新，反映整个对话的完整信息
        """
        if self.current_mode == "dst" and self.tracker:
            # DST模式：显示详细的对话状态信息（纯文本，无表情符号）
            state_info = {
                "模式": "DST (对话状态追踪)",
                "场景": self._get_scenario_name(self.current_scenario),
                "对话轮数": len(self.tracker.dialogue_history),
            }
            
            # 显示本轮对话提取的槽位（如果有的话）
            if self.tracker.dialogue_history:
                last_turn = self.tracker.dialogue_history[-1]
                if last_turn.turn_updates:
                    state_info["本轮提取"] = "以下是本轮新提取/更新的槽位"
                    for slot_name, slot_value in last_turn.turn_updates.items():
                        state_info[f"  {slot_name}"] = slot_value
                    state_info["  本轮提取数"] = len(last_turn.turn_updates)
                else:
                    state_info["本轮提取"] = "本轮未提取到新槽位"
            
            # 分隔线
            if self.tracker.current_state:
                state_info["---"] = "---"
            
            # 显示累积的所有槽位信息（精简版，只显示非空槽位）
            if self.tracker.current_state:
                # 过滤掉空值槽位，只显示有意义的信息
                non_empty_slots = {k: v for k, v in self.tracker.current_state.items() 
                                  if v and str(v).strip()}
                
                if non_empty_slots:
                    state_info["累积状态"] = f"已提取 {len(non_empty_slots)} 个槽位"
                    # 简化显示，只显示槽位名和值，不显示额外的缩进和计数
                    for slot_name, slot_value in non_empty_slots.items():
                        # 限制值的长度，避免显示过长
                        display_value = str(slot_value)
                        if len(display_value) > 50:
                            display_value = display_value[:47] + "..."
                        state_info[f"{slot_name}"] = display_value
                else:
                    state_info["累积状态"] = "暂无槽位信息"
            else:
                state_info["累积状态"] = "暂无槽位信息"
            
            return state_info
        elif self.current_mode == "evolution" and self.app:
            # Evolution模式：显示引擎状态和记忆库信息（纯文本，无表情符号）
            engine = self.app.context_engine
            state_info = {
                "模式": "Evolution (基于记忆进化)",
                "场景": self._get_scenario_name(self.current_scenario),
                "记忆功能": "已启用",
                "进化学习": "已启用",
                "应用ID": engine.app_name if hasattr(engine, 'app_name') else "N/A",
                "用户ID": engine.user_id if hasattr(engine, 'user_id') else "N/A",
            }
            
            # 显示记忆库详细信息
            if hasattr(engine, 'memory_bank'):
                memory_cache = engine.memory_bank.get_memory_cache()
                total_memories = len(memory_cache)
                state_info["记忆总数"] = total_memories
                
                # 显示本轮对话后的记忆库内容
                if memory_cache:
                    state_info["---"] = "---"
                    state_info["记忆库内容"] = "以下是记忆库中的所有记忆"
                    
                    # 显示最近的记忆（最多10条，完整显示）
                    recent_count = min(10, total_memories)
                    recent_memories = memory_cache[-recent_count:] if total_memories > 0 else []
                    
                    for i, mem in enumerate(recent_memories, 1):
                        # ContextItem has a 'content' attribute
                        content = mem.content if hasattr(mem, 'content') else str(mem)
                        
                        # 尝试获取记忆类型
                        mem_type = getattr(mem, 'type', 'unknown')
                        
                        # 格式化显示记忆内容（限制长度以保持可读性）
                        if len(str(content)) > 100:
                            display_content = str(content)[:100] + '...'
                        else:
                            display_content = str(content)
                        
                        # 显示记忆编号、类型和内容
                        state_info[f"  记忆{i} [{mem_type}]"] = display_content
                    
                    # 如果记忆超过10条，显示省略提示
                    if total_memories > 10:
                        state_info["  提示"] = f"共{total_memories}条记忆，仅显示最近10条"
            
            # 显示会话信息
            if hasattr(engine, 'session_manager'):
                state_info["----"] = "----"
                state_info["会话ID"] = getattr(engine.session_manager, 'session_id', 'N/A')
            
            return state_info
        else:
            return {"状态": "未初始化", "提示": "请先应用场景配置"}
    
    def get_state(self) -> dict:
        """
        获取对话状态
        
        返回用户输入处理后的状态（在bot回复生成之前捕获的状态）
        这样显示的状态反映了系统对用户输入的理解，而不是完整对话轮次结束后的状态
        
        如果尚未捕获状态（如第一次调用），则返回当前实时状态
        """
        if self.post_user_state is not None:
            return self.post_user_state
        else:
            # 如果还没有捕获的状态，返回当前实时状态
            return self._build_state_dict()
    
    def _get_scenario_name(self, scenario: str) -> str:
        """获取场景中文名称"""
        scenario_names = {
            "chat": "💬 闲聊对话",
            "callcenter": "📞 智能客服",
            "insurance": "🏥 保险咨询"
        }
        return scenario_names.get(scenario, scenario)
    
    def reset_conversation(self):
        """重置对话"""
        if self.current_mode == "dst" and self.tracker:
            self.tracker.current_state = {}
            self.tracker.dialogue_history = []
        elif self.current_mode == "evolution" and self.app:
            # 重新初始化app
            self.initialize_scenario(self.current_scenario, self.current_mode)
        
        logger.info("对话已重置")
        return []
    
    def change_scenario_or_mode(self, scenario: str, mode: str):
        """切换场景或模式"""
        self.initialize_scenario(scenario, mode)
        self.initialized = True
        
        scenario_names = {
            "chat": "闲聊对话",
            "callcenter": "智能客服",
            "insurance": "保险咨询"
        }
        
        status = f"📌 当前配置: 场景={scenario_names.get(scenario, scenario)}, 模式={mode}"
        logger.info(f"配置已更新: {scenario}, {mode}")
        return [], status
    
    
    def update_settings(self, max_history_turns: int, enable_summary: bool, use_llm_summary: bool,
                        enable_memory: bool, enable_evolution: bool):
        """更新设置"""
        self.max_history_turns = max_history_turns
        
        # 如果当前是DST模式且已初始化，更新追踪器设置
        if self.current_mode == "dst" and self.tracker:
            self.tracker.max_history_turns = max_history_turns
            self.tracker.enable_history_summary = enable_summary
            self.tracker.use_llm_summary = use_llm_summary
            logger.info(f"DST设置已更新: max_history_turns={max_history_turns}, enable_summary={enable_summary}, use_llm_summary={use_llm_summary}")
            
            summary_status = "启用" if enable_summary else "禁用"
            llm_summary_status = "LLM" if use_llm_summary else "模板"
            return f"⚙️ DST设置: 历史={max_history_turns}轮, 摘要={summary_status}, 方式={llm_summary_status}"
        
        elif self.current_mode == "evolution" and self.app:
            # Evolution模式的设置（记忆和进化是在初始化时设置的）
            logger.info(f"Evolution设置: 记忆={enable_memory}, 进化={enable_evolution}")
            
            memory_status = "启用" if enable_memory else "禁用"
            evolution_status = "启用" if enable_evolution else "禁用"
            return f"⚙️ Evolution设置: 记忆={memory_status}, 进化={evolution_status}, 最大事件={max_history_turns}"
        
        return "⚙️ 请先应用场景配置"


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Evolution Gradio Web Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python gradio_demo.py
  python gradio_demo.py --log-level DEBUG
  python gradio_demo.py --port 8080 --share
  python gradio_demo.py --max-history-turns 20 --log-level INFO
        """
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别 (默认: INFO)'
    )
    
    parser.add_argument(
        '--max-history-turns',
        type=int,
        default=10,
        help='DST模式的最大历史轮数 (默认: 10)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=7860,
        help='Web服务器端口 (默认: 7860)'
    )
    
    parser.add_argument(
        '--share',
        action='store_true',
        help='创建公共分享链接'
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    # 使用setup_logging配置日志系统
    log_level = LogLevel.DEBUG if args.log_level == "DEBUG" else LogLevel.INFO
    setup_logging(level=log_level, save_to_file=True, log_dir="logs")
    
    logger.info("[__main__] 启动Evolution统一Gradio Demo")
    logger.info(f"参数配置: 日志级别={args.log_level}, 最大历史轮数={args.max_history_turns}, 端口={args.port}, 分享={args.share}")
    
    # 创建Demo实例
    try:
        demo_instance = UnifiedGradioDemo(max_history_turns=args.max_history_turns)
        logger.info("✅ Demo实例创建成功")
    except Exception as e:
        logger.error(f"❌ Demo初始化失败: {e}")
        print(f"\n{'='*60}")
        print(f"❌ 错误: {e}")
        print(f"{'='*60}\n")
        raise
    
    # 创建UI（传入demo_instance以绑定事件）
    try:
        app, components = create_gradio_ui(demo_instance)
        logger.info("✅ UI创建成功")
    except Exception as e:
        logger.error(f"❌ UI创建失败: {e}", exc_info=True)
        print(f"\n{'='*60}")
        print(f"❌ UI创建错误: {e}")
        print(f"请检查是否安装了gradio包: pip install gradio")
        print(f"{'='*60}\n")
        raise
    
    # 启动应用（CSS参数移到这里，兼容Gradio 6.0）
    logger.info(f"启动Gradio应用... (端口: {args.port}, 分享: {args.share})")
    app.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share,
        css=CUSTOM_CSS
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"程序启动失败: {e}", exc_info=True)
        print(f"\n{'='*60}")
        print(f"❌ 程序启动失败")
        print(f"错误信息: {e}")
        print(f"\n常见问题排查:")
        print(f"1. 检查是否安装gradio: pip install gradio")
        print(f"2. 检查是否配置.env文件")
        print(f"3. 检查日志文件获取详细信息")
        print(f"{'='*60}\n")
        raise
