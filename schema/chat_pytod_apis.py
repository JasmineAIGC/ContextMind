"""
PyTOD API 函数集合 — 由 chat_schema.json 生成
Service: Chat_Assistant
Generated at: 2026-03-27T08:04:28.946789+00:00
Generation mode: 规则引擎生成（含共享工具函数调用）

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
文件头部定义了共享工具函数（_parse_amount、_ticket_id 等），
意图函数通过调用这些工具函数实现真实计算逻辑。
运行时通过 load_pytod_api_module() 加载并注册到 ExecutionEngine。
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 共享工具函数 — 由 SchemaDataBuilder 自动生成，所有 API 函数均可调用
# ---------------------------------------------------------------------------

import datetime as _dt
import math as _math
import re as _re


def _parse_amount(value) -> float:
    """将字符串金额（如 '21900元'、'两万一千九百'）解析为浮点数，无法解析时返回 0.0。"""
    if value is None:
        return 0.0
    s = _re.sub(r"[^\d.]", "", str(value).replace(",", "").replace("，", ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _ticket_id(prefix: str = "TICKET") -> str:
    """生成工单编号，格式：{PREFIX}-YYYYMMDD-001。适用于投诉、申请、纠纷等意图。"""
    today = _dt.date.today().strftime("%Y%m%d")
    return f"{prefix}-{today}-001"


def _calc_monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    """等额还款月供计算（PMT 公式）。

    Args:
        principal: 贷款本金（元）
        annual_rate: 年化利率（小数，如 0.24 表示 24%）
        months: 还款期数（月）
    """
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r == 0:
        return principal / months
    return principal * r / (1.0 - (1.0 + r) ** (-months))


def _next_work_day() -> str:
    """返回下一个工作日日期字符串（格式 YYYY-MM-DD），跳过周末。"""
    d = _dt.date.today() + _dt.timedelta(days=1)
    while d.weekday() >= 5:   # 5=Saturday, 6=Sunday
        d += _dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")

def get_weather(city=None, date=None):
    """查询天气预报，支持今天/明天/后天或指定城市"""
    return {
        "weather_result": "[get_weather执行成功]",
        "city": city,
        "date": date,
        "status": "success",
    }

def search_info(query=None, category=None):
    """搜索信息或回答知识类问题"""
    return {
        "search_result": "[search_info执行成功]",
        "query": query,
        "category": category,
        "status": "success",
    }

def tell_joke(topic=None):
    """讲一个笑话，支持程序员/数学/生活/动物等主题"""
    return {
        "joke_result": True,
        "topic": topic,
        "status": "success",
    }

def translate_text(text=None, target_language=None, source_language=None):
    """翻译文本到指定目标语言"""
    if not ((text is not None) and (target_language is not None)):
        return {"status": "error", "message": "缺少必填参数: text, target_language"}
    return {
        "translation_result": "[translate_text执行成功]",
        "text": text,
        "target_language": target_language,
        "source_language": source_language,
        "status": "success",
    }

def calculate(expression=None):
    """计算数学表达式，支持加减乘除、百分比等基础运算"""
    if not ((expression is not None)):
        return {"status": "error", "message": "缺少必填参数: expression"}
    return {
        "calculation_result": "[calculate执行成功]",
        "expression": expression,
        "status": "success",
    }

def get_current_time(city=None, timezone=None):
    """查询当前时间，支持按城市或时区查询"""
    return {
        "time_result": "2024-01-15",
        "city": city,
        "timezone": timezone,
        "status": "success",
    }

def convert_units(value=None, from_unit=None, to_unit=None):
    """单位换算，支持长度、重量、温度等"""
    if not ((value is not None) and (from_unit is not None) and (to_unit is not None)):
        return {"status": "error", "message": "缺少必填参数: value, from_unit, to_unit"}
    return {
        "conversion_result": "[convert_units执行成功]",
        "value": value,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "status": "success",
    }

def recommend_content(content_type=None, genre=None, mood=None):
    """推荐内容（电影、音乐、书籍、播客）"""
    return {
        "recommendation_result": "[recommend_content执行成功]",
        "content_type": content_type,
        "genre": genre,
        "mood": mood,
        "status": "success",
    }

def get_recipe(dish_name=None, dietary_restrictions=None, servings=None):
    """查询菜谱，支持按菜名或食材推荐做法"""
    return {
        "recipe_result": "[get_recipe执行成功]",
        "dish_name": dish_name,
        "dietary_restrictions": dietary_restrictions,
        "servings": servings,
        "status": "success",
    }

# ---------------------------------------------------------------------------
# INTENT_REGISTRY — intent 名称到函数的映射，供外部代码通过名称调用意图函数
# ---------------------------------------------------------------------------

INTENT_REGISTRY: dict = {
    "get_weather": get_weather,
    "search_info": search_info,
    "tell_joke": tell_joke,
    "translate_text": translate_text,
    "calculate": calculate,
    "get_current_time": get_current_time,
    "convert_units": convert_units,
    "recommend_content": recommend_content,
    "get_recipe": get_recipe,
}
