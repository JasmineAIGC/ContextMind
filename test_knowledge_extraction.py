"""
知识提取测试 - Knowledge Extraction Test

从多轮对话中提取知识、经验和策略的测试代码。

使用场景：
1. 从对话历史中提取用户偏好
2. 识别对话模式和策略
3. 总结经验和教训
4. 构建知识库
"""

import asyncio
import os
import sys
from typing import List, Dict

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import SimpleLLMClient, LLMConfig, get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class KnowledgeExtractor:
    """知识提取器 - 从多轮对话中提取结构化知识"""
    
    def __init__(self, llm_client: SimpleLLMClient = None):
        """
        初始化知识提取器
        
        Args:
            llm_client: LLM 客户端（如果为 None，将创建新实例）
        """
        self.llm_client = llm_client or SimpleLLMClient()
    
    async def extract_knowledge(self, dialogue: List[Dict[str, str]]) -> Dict:
        """
        从多轮对话中提取知识
        
        Args:
            dialogue: 对话列表，每项包含 {"role": "user/assistant", "content": "..."}
            
        Returns:
            提取的知识字典，包含：
            - user_preferences: 用户偏好
            - facts: 事实性知识
            - patterns: 对话模式
            - strategies: 策略和建议
            - experiences: 经验总结
        """
        # 构建提取提示词
        dialogue_text = self._format_dialogue(dialogue)
        
        prompt = f"""请从以下多轮对话中提取结构化知识。

对话内容：
{dialogue_text}

请分析对话并提取以下几类知识，以JSON格式返回：

1. user_preferences（用户偏好）：用户表达的兴趣、喜好、需求等
2. facts（事实知识）：对话中提到的客观事实、数据、信息
3. patterns（对话模式）：对话的结构特征、常见流程等
4. strategies（策略建议）：有效的对话策略、应对方法等
5. experiences（经验总结）：可以从对话中学到的经验教训

返回JSON格式：
{{
    "user_preferences": ["偏好1", "偏好2"],
    "facts": ["事实1", "事实2"],
    "patterns": ["模式1", "模式2"],
    "strategies": ["策略1", "策略2"],
    "experiences": ["经验1", "经验2"]
}}

请确保返回的是有效的JSON格式。"""

        # 调用 LLM 提取知识
        logger.info("[KnowledgeExtractor] 开始提取知识...")
        response = await self.llm_client.chat_async([
            {"role": "user", "content": prompt}
        ])
        
        # 解析 JSON 响应
        import json
        import re
        
        # 尝试提取 JSON
        try:
            # 方法1: 直接解析
            knowledge = json.loads(response)
        except json.JSONDecodeError:
            try:
                # 方法2: 使用正则提取 JSON
                match = re.search(r'\{.*\}', response, re.DOTALL)
                if match:
                    knowledge = json.loads(match.group(0))
                else:
                    raise ValueError("无法从响应中提取JSON")
            except Exception as e:
                logger.error(f"[KnowledgeExtractor] JSON解析失败: {e}")
                # 返回空结构
                knowledge = {
                    "user_preferences": [],
                    "facts": [],
                    "patterns": [],
                    "strategies": [],
                    "experiences": []
                }
        
        logger.info("[KnowledgeExtractor] 知识提取完成")
        return knowledge
    
    def _format_dialogue(self, dialogue: List[Dict[str, str]]) -> str:
        """
        格式化对话为文本
        
        Args:
            dialogue: 对话列表
            
        Returns:
            格式化的对话文本
        """
        lines = []
        for i, turn in enumerate(dialogue, 1):
            role = "用户" if turn["role"] == "user" else "助手"
            lines.append(f"[轮次 {i}] {role}: {turn['content']}")
        return "\n".join(lines)
    
    def print_knowledge(self, knowledge: Dict):
        """
        打印提取的知识（美化格式）
        
        Args:
            knowledge: 知识字典
        """
        print("\n" + "="*60)
        print("提取的知识总结".center(60))
        print("="*60 + "\n")
        
        sections = [
            ("用户偏好", "user_preferences", "💡"),
            ("事实知识", "facts", "📚"),
            ("对话模式", "patterns", "🔄"),
            ("策略建议", "strategies", "🎯"),
            ("经验总结", "experiences", "✨")
        ]
        
        for title, key, icon in sections:
            items = knowledge.get(key, [])
            if items:
                print(f"{icon} {title}:")
                for i, item in enumerate(items, 1):
                    print(f"   {i}. {item}")
                print()


async def test_customer_service_dialogue():
    """测试场景1：客服对话 - 提取客户需求和问题解决策略"""
    
    print("\n" + "="*60)
    print("测试场景1：客服对话知识提取".center(60))
    print("="*60)
    
    dialogue = [
        {"role": "user", "content": "你好，我的订单还没发货，已经3天了"},
        {"role": "assistant", "content": "您好，非常抱歉给您带来不便。请告诉我您的订单号，我马上为您查询。"},
        {"role": "user", "content": "订单号是20240129001"},
        {"role": "assistant", "content": "好的，我查到了。您的订单因为春节假期物流暂停，预计2月5日发货。我们已为您申请了优先发货，并赠送20元优惠券作为补偿。"},
        {"role": "user", "content": "好的，谢谢。下次能不能选择顺丰？我比较急"},
        {"role": "assistant", "content": "当然可以。我已在您的账户备注中添加了偏好顺丰快递。下次下单时您也可以在配送方式中直接选择顺丰。"},
        {"role": "user", "content": "好的，那我等发货通知"},
        {"role": "assistant", "content": "好的，发货后我们会第一时间通知您。感谢您的理解和支持！"}
    ]
    
    extractor = KnowledgeExtractor()
    knowledge = await extractor.extract_knowledge(dialogue)
    extractor.print_knowledge(knowledge)


async def test_technical_support_dialogue():
    """测试场景2：技术支持对话 - 提取问题诊断流程和解决方案"""
    
    print("\n" + "="*60)
    print("测试场景2：技术支持对话知识提取".center(60))
    print("="*60)
    
    dialogue = [
        {"role": "user", "content": "软件打不开了，点击图标没反应"},
        {"role": "assistant", "content": "您好，请问您使用的是什么操作系统？最近有没有更新过系统？"},
        {"role": "user", "content": "Windows 11，昨天刚更新了"},
        {"role": "assistant", "content": "明白了。这可能是系统更新导致的兼容性问题。请尝试以下步骤：1. 右键软件图标，选择'以管理员身份运行' 2. 如果还不行，尝试卸载重装"},
        {"role": "user", "content": "以管理员身份运行可以了！谢谢"},
        {"role": "assistant", "content": "太好了！为了避免每次都需要手动操作，您可以：右键图标 -> 属性 -> 兼容性 -> 勾选'以管理员身份运行此程序'。这样以后双击就能正常打开了。"},
        {"role": "user", "content": "已经设置好了，非常感谢！"},
        {"role": "assistant", "content": "不客气！如果以后还有问题，随时联系我们。"}
    ]
    
    extractor = KnowledgeExtractor()
    knowledge = await extractor.extract_knowledge(dialogue)
    extractor.print_knowledge(knowledge)


async def test_consultation_dialogue():
    """测试场景3：咨询对话 - 提取用户需求和专业建议"""
    
    print("\n" + "="*60)
    print("测试场景3：咨询对话知识提取".center(60))
    print("="*60)
    
    dialogue = [
        {"role": "user", "content": "我想学习Python，但不知道从哪里开始"},
        {"role": "assistant", "content": "很好的选择！请问您之前有编程基础吗？学习Python的目的是什么？"},
        {"role": "user", "content": "没有编程基础，想做数据分析"},
        {"role": "assistant", "content": "明白了。建议您按照这个路线学习：1. 先学Python基础语法（2-3周） 2. 学习NumPy和Pandas库（1-2周） 3. 学习数据可视化（Matplotlib、Seaborn） 4. 最后学习统计分析和机器学习基础"},
        {"role": "user", "content": "有什么好的学习资源推荐吗？我每天能学2小时"},
        {"role": "assistant", "content": "推荐以下资源：1. 《Python Crash Course》适合零基础 2. Kaggle的数据分析教程很实用 3. 每天2小时的话，大约3个月能掌握基础。建议配合实际项目练习，比如分析一些公开数据集。"},
        {"role": "user", "content": "好的，我先从这本书开始。谢谢！"},
        {"role": "assistant", "content": "加油！学习过程中有问题随时来问我。"}
    ]
    
    extractor = KnowledgeExtractor()
    knowledge = await extractor.extract_knowledge(dialogue)
    extractor.print_knowledge(knowledge)


async def main():
    """主函数 - 运行所有测试场景"""
    
    # 设置日志
    setup_logging(level=LogLevel.INFO, save_to_file=False)
    
    print("\n" + "="*60)
    print("知识提取测试程序".center(60))
    print("="*60)
    print("\n该程序展示如何从多轮对话中自动提取：")
    print("  • 用户偏好和需求")
    print("  • 事实性知识")
    print("  • 对话模式和流程")
    print("  • 有效的策略和方法")
    print("  • 经验和教训总结")
    print()
    
    try:
        # 测试场景1：客服对话
        await test_customer_service_dialogue()
        
        # 测试场景2：技术支持
        await test_technical_support_dialogue()
        
        # 测试场景3：咨询对话
        await test_consultation_dialogue()
        
        print("\n" + "="*60)
        print("所有测试完成！".center(60))
        print("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
