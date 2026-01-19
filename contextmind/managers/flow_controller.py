"""
FlowController - 流程控制器

根据不同的场景动态决定处理流程：
- 简单查询：快速路径
- 复杂查询：完整流水线
- 特殊场景：自定义流程
"""

from typing import Dict, Any, Callable, Awaitable
from enum import Enum

from ..logger import get_logger

logger = get_logger(__name__)


class QueryType(Enum):
    """查询类型"""
    SIMPLE = "simple"  # 简单查询
    COMPLEX = "complex"  # 复杂查询
    FACTUAL = "factual"  # 事实查询
    CONVERSATIONAL = "conversational"  # 对话查询


class FlowController:
    """
    流程控制器
    
    根据查询特征动态决定执行路径。
    
    使用示例：
        ```python
        controller = FlowController()
        
        # 分析查询类型
        query_type = controller.analyze_query("你好")
        
        # 决定是否需要执行某个阶段
        if controller.should_run_stage("ranking", query_type):
            # 执行ranking
            pass
        ```
    """
    
    def __init__(self):
        """初始化流程控制器"""
        # 阶段启用规则
        self.stage_rules: Dict[str, Dict[QueryType, bool]] = {
            "query_analysis": {
                QueryType.SIMPLE: False,
                QueryType.COMPLEX: True,
                QueryType.FACTUAL: True,
                QueryType.CONVERSATIONAL: False,
            },
            "ranking": {
                QueryType.SIMPLE: False,
                QueryType.COMPLEX: True,
                QueryType.FACTUAL: True,
                QueryType.CONVERSATIONAL: True,
            },
            "budget_management": {
                QueryType.SIMPLE: True,
                QueryType.COMPLEX: True,
                QueryType.FACTUAL: True,
                QueryType.CONVERSATIONAL: True,
            },
            "entropy_compression": {
                QueryType.SIMPLE: False,
                QueryType.COMPLEX: True,
                QueryType.FACTUAL: False,
                QueryType.CONVERSATIONAL: True,
            },
            "layout_assembly": {
                QueryType.SIMPLE: False,
                QueryType.COMPLEX: True,
                QueryType.FACTUAL: True,
                QueryType.CONVERSATIONAL: False,
            },
        }
    
    def analyze_query(self, query: str) -> QueryType:
        """
        分析查询类型
        
        Args:
            query: 用户查询
            
        Returns:
            查询类型
        """
        # 简单的规则判断（可以用更复杂的NLP模型）
        query_lower = query.lower().strip()
        
        # 简单查询：短文本，常见问候
        if len(query) < 10 or query_lower in ["你好", "hello", "hi", "嗨"]:
            return QueryType.SIMPLE
        
        # 事实查询：包含疑问词
        factual_keywords = ["什么", "为什么", "如何", "怎么", "哪里", "when", "what", "why", "how", "where"]
        if any(kw in query_lower for kw in factual_keywords):
            return QueryType.FACTUAL
        
        # 复杂查询：长文本
        if len(query) > 100:
            return QueryType.COMPLEX
        
        # 默认：对话查询
        return QueryType.CONVERSATIONAL
    
    def should_run_stage(self, stage_name: str, query_type: QueryType) -> bool:
        """
        判断是否应该执行某个阶段
        
        Args:
            stage_name: 阶段名称
            query_type: 查询类型
            
        Returns:
            是否执行该阶段
        """
        if stage_name not in self.stage_rules:
            # 未定义的阶段，默认执行
            return True
        
        return self.stage_rules[stage_name].get(query_type, True)
    
    def get_execution_plan(self, query: str) -> Dict[str, bool]:
        """
        获取完整的执行计划
        
        Args:
            query: 用户查询
            
        Returns:
            各阶段是否执行的字典
        """
        query_type = self.analyze_query(query)
        
        plan = {}
        for stage_name in self.stage_rules.keys():
            plan[stage_name] = self.should_run_stage(stage_name, query_type)
        
        logger.debug(f"Query type: {query_type.value}, Execution plan: {plan}")
        
        return plan
