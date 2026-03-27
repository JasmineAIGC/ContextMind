"""
PyTOD API 函数集合 — 由 chat_schema.json 生成
Service: Chat_Assistant
Generated at: 2026-03-27T07:02:59.761624+00:00

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots。函数体由 SchemaDataBuilder 规则引擎生成，
包含输入参数校验、工单号生成、布尔推导、回调时间计算等计算逻辑。

如需更贴近真实生产逻辑的函数体，请使用 LLM 模式重新生成：
  python examples/build_schema_data.py --with-llm
这些函数运行时通过 load_pytod_api_module() 加载并注册到 ExecutionEngine，
供 PyTOD AP 生成的程序调用。
"""

from __future__ import annotations

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
