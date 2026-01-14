"""
Call Center Application

客服对话应用 - 演示如何在应用层管理业务逻辑。
"""

from typing import Dict, Optional
import re
from .base import BaseApplication
from contextmind.data_models import ContextResult


class CallCenterApp(BaseApplication):
    """客服对话应用 - 演示如何在应用层管理业务逻辑
    
    该应用展示了如何使用 ContextMind 构建一个客服对话系统。
    业务逻辑（用户画像、业务规则等）由应用层管理，而上下文优化
    由 ContextMind 负责。
    
    Attributes:
        user_profile: 用户画像信息
        business_rules: 业务规则信息
    """
    
    def __init__(
        self,
        context_engine,
        llm_client,
        user_profile: Optional[Dict] = None,
        business_rules: Optional[Dict] = None,
        **config
    ):
        """初始化客服应用
        
        Args:
            context_engine: ContextMind 引擎实例
            llm_client: LLM 客户端实例
            user_profile: 用户画像信息（可选）
            business_rules: 业务规则信息（可选）
            **config: 额外配置参数
        """
        system_prompt = "你是优逸花客服，负责电话外呼。你的回复必须专业、简洁、直接，严格遵守客服话术规范。"
        super().__init__(context_engine, llm_client, system_prompt, **config)
        
        # 业务信息由应用层管理
        self.user_profile = user_profile or {}
        self.business_rules = business_rules or {}
    
    def build_prompt(
        self,
        user_input: str,
        context: ContextResult
    ) -> str:
        """构建客服专用的 Prompt
        
        组织各类信息的优先级：
        1. 系统角色
        2. 用户画像
        3. 业务规则
        4. 业务信息（预置信息）
        5. 长期记忆（来自 ContextMind）- 优先级最高
        6. 对话历史（来自 ContextMind）
        7. 当前用户输入
        8. 回复要求
        
        Args:
            user_input: 用户输入
            context: ContextMind 优化后的上下文
            
        Returns:
            str: 构建好的 Prompt
        """
        parts = []
        
        # 1. 系统角色
        parts.append(f"# 系统角色\n{self.system_prompt}")
        
        # 2. 用户画像
        if self.user_profile:
            profile_lines = [f"- {k}: {v}" for k, v in self.user_profile.items()]
            parts.append(f"\n# 用户画像\n" + "\n".join(profile_lines))
        
        # 3. 业务规则
        if self.business_rules:
            rules_lines = [f"- {k}: {v}" for k, v in self.business_rules.items()]
            parts.append(f"\n# 业务规则\n" + "\n".join(rules_lines))
        
        # 4. 业务信息（预置信息）
        preset_info = self._get_preset_info()
        if preset_info:
            parts.append(f"\n# 业务信息\n{preset_info}")
        
        # 5. 长期记忆（来自 ContextMind）- 优先级最高
        if context.long_term_memory:
            memory_lines = [
                f"- {mem.content} (相关性: {mem.score:.2f})"
                for mem in context.long_term_memory
            ]
            parts.append(f"\n# ⚠️ 重要记忆（必读）\n" + "\n".join(memory_lines))
        
        # 6. 对话历史（来自 ContextMind）
        if context.recent_history:
            history_lines = [
                f"{msg.role}: {msg.content}"
                for msg in context.recent_history
            ]
            parts.append(f"\n# 对话历史\n" + "\n".join(history_lines))
        
        # 7. 当前用户输入
        parts.append(f"\n# 当前用户输入\n{user_input}")
        
        # 8. 回复要求
        parts.append("\n# 回复要求\n- 严格按照客服身份直接回复\n- 不要使用任何格式标记\n- 回复简洁专业")
        
        return "\n".join(parts)
    
    def _get_preset_info(self) -> str:
        """获取业务预置信息
        
        Returns:
            str: 业务预置信息
        """
        return """- 电话目的：提醒用户申请优逸花预留额度
- 额度特点：
  * 限时预留额度
  * 无需下载APP
  * 微信小程序人脸识别完成
  * 无需填资料
  * 额度不用不产生任何费用
  * 后续资金周转时更方便
- 服务名称：优逸花
- 公司名称：马上消费"""
    
    def post_process_response(self, response: str) -> str:
        """客服专用的响应后处理
        
        清理 LLM 输出中的分析性内容，提取实际回复。
        
        Args:
            response: LLM 的原始输出
            
        Returns:
            str: 清理后的回复
        """
        response = super().post_process_response(response)
        
        # 提取实际回复内容（移除分析性内容）
        response = self._extract_actual_response(response)
        
        return response
    
    def _extract_actual_response(self, response: str) -> str:
        """从模型输出中提取实际回复内容
        
        移除分析性关键词开头的内容，提取引号中的内容等。
        
        Args:
            response: LLM 的原始输出
            
        Returns:
            str: 提取后的实际回复
        """
        # 移除分析性关键词开头的内容
        analysis_keywords = [
            '首先', '然后', '分析', '检查', '根据', '因此', '所以',
            '用户提到', '历史行为', '情绪', '风险等级', '需要',
            '我应该', '可以', '建议', '考虑', '注意', '确保'
        ]
        
        lines = response.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not any(line.startswith(kw) for kw in analysis_keywords):
                clean_lines.append(line)
        
        response = '\n'.join(clean_lines).strip()
        
        # 提取引号中的内容
        quoted_matches = re.findall(r'["""]([^"""]+)["""]', response)
        if quoted_matches:
            return quoted_matches[-1].strip()
        
        return response
