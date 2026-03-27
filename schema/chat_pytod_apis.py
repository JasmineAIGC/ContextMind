"""
PyTOD API 函数集合 — 由 chat_schema.json 生成
Service: Chat_Assistant

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
函数体包含真实业务逻辑（基于通用聊天助手业务场景）。
这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()
加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。
"""

from __future__ import annotations

import ast
import datetime
import math
import re


def get_weather(city=None, date=None):
    """查询天气预报，支持今天/明天/后天或指定城市"""
    target_city = city or "北京"
    target_date = date or "今天"
    # 简单的天气模拟（实际应调用天气 API）
    weather_templates = {
        "今天": f"{target_city}今天晴，气温 18-25°C，东南风3级，空气质量良好",
        "明天": f"{target_city}明天多云转阴，气温 15-22°C，有小雨可能，建议携带雨具",
        "后天": f"{target_city}后天小雨，气温 12-18°C，东北风4-5级",
    }
    result = weather_templates.get(target_date, f"{target_city}{target_date}天气以实际情况为准")
    return {
        "weather_result": result,
        "city": target_city,
        "date": target_date,
        "status": "success",
    }


def search_info(query=None, category=None):
    """搜索信息或回答知识类问题"""
    if not query:
        return {"search_result": "请提供搜索关键词", "query": query, "status": "error"}
    cat_note = f"（{category}类）" if category else ""
    result = f"关于「{query}」{cat_note}的搜索结果：这是一个综合性问题，建议参考权威来源获取最新信息。"
    return {
        "search_result": result,
        "query": query,
        "category": category,
        "status": "success",
    }


def tell_joke(topic=None):
    """讲一个笑话，支持程序员/数学/生活/动物等主题"""
    jokes = {
        "程序员": "为什么程序员不喜欢自然界？因为自然界中有太多 bug，而且都是 feature。",
        "数学": "为什么数学书这么悲伤？因为里面有太多的问题（problems）。",
        "生活": "为什么鱼不用电脑？因为它们怕网（网络/渔网）。",
        "动物": "为什么鸡过马路？为了到另一边——这是有史以来最古老的笑话！",
    }
    selected_topic = topic or "程序员"
    joke = jokes.get(selected_topic, f"关于{selected_topic}的笑话：…（咳咳）这个嘛，让我想想~")
    return {
        "joke_result": joke,
        "topic": selected_topic,
        "status": "success",
    }


def translate_text(text=None, target_language=None, source_language=None):
    """翻译文本到指定目标语言"""
    if not text:
        return {"translation_result": "", "status": "error", "message": "缺少待翻译文本"}
    if not target_language:
        return {"translation_result": text, "status": "error", "message": "缺少目标语言"}
    src = source_language or "自动检测"
    # 模拟翻译结果（实际应调用翻译 API）
    translation_result = f"[{target_language}翻译]: {text}"
    return {
        "translation_result": translation_result,
        "text": text,
        "target_language": target_language,
        "source_language": src,
        "status": "success",
    }


def calculate(expression=None):
    """计算数学表达式，支持加减乘除、百分比等基础运算"""
    if not expression:
        return {"calculation_result": "", "status": "error", "message": "缺少计算表达式"}
    expr = str(expression).strip()
    # 安全地处理百分比: 50% → 0.5, 50%*200 → 0.5*200
    expr_safe = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr)
    # 只允许数字、运算符、括号、空格
    if not re.match(r"^[\d\s\+\-\*/\(\)\.\,\^]+$", expr_safe.replace("/100", "")):
        return {"calculation_result": "无法计算", "expression": expression,
                "status": "error", "message": "表达式包含不支持的字符"}
    try:
        # Replace ^ with ** for power
        expr_safe = expr_safe.replace("^", "**")
        # Use ast.parse to validate the expression before eval
        # (regex already filters dangerous chars; this adds a second check)
        parsed = ast.parse(expr_safe, mode="eval")
        # Whitelist: only allow numbers, arithmetic ops, function calls to math module
        for node in ast.walk(parsed):
            if isinstance(node, ast.Call):
                # Only allow math.func() calls
                if not (isinstance(node.func, ast.Attribute) and
                        isinstance(node.func.value, ast.Name) and
                        node.func.value.id == "math"):
                    return {"calculation_result": "不支持此类函数调用", "expression": expression,
                            "status": "error", "message": "仅支持基础运算和 math 模块函数"}
        result = eval(compile(parsed, "<expr>", "eval"), {"__builtins__": {}}, {"math": math})  # noqa: S307
        result_str = str(int(result)) if isinstance(result, float) and result.is_integer() else str(round(result, 6))
        return {
            "calculation_result": f"{expression} = {result_str}",
            "expression": expression,
            "result_value": result_str,
            "status": "success",
        }
    except Exception as exc:
        return {"calculation_result": "计算出错", "expression": expression,
                "status": "error", "message": str(exc)}


def get_current_time(city=None, timezone=None):
    """查询当前时间，支持按城市或时区查询"""
    now = datetime.datetime.now()
    # Simplified timezone offset map
    tz_offsets = {
        "北京": 8, "上海": 8, "广州": 8, "深圳": 8, "成都": 8,
        "东京": 9, "首尔": 9, "纽约": -5, "洛杉矶": -8, "伦敦": 0,
        "巴黎": 1, "迪拜": 4, "悉尼": 11, "莫斯科": 3,
        "UTC": 0, "UTC+8": 8, "UTC-5": -5, "UTC+9": 9,
    }
    tz_key = city or timezone or "北京"
    offset = tz_offsets.get(tz_key, 8)
    target_time = now + datetime.timedelta(hours=offset - 8)  # base: CST UTC+8
    time_str = target_time.strftime("%Y年%m月%d日 %H:%M:%S")
    location = city or timezone or "北京（UTC+8）"
    return {
        "time_result": f"{location}当前时间：{time_str}",
        "city": city,
        "timezone": timezone,
        "formatted_time": time_str,
        "status": "success",
    }


def convert_units(value=None, from_unit=None, to_unit=None):
    """单位换算，支持长度、重量、温度等"""
    if value is None or not from_unit or not to_unit:
        return {"conversion_result": "", "status": "error", "message": "缺少换算参数"}
    try:
        num = float(str(value).replace(",", ""))
    except ValueError:
        return {"conversion_result": "", "status": "error", "message": "数值格式错误"}

    # Conversion table: (from, to) → factor (multiply from_val by factor to get to_val)
    conversions = {
        # Length
        ("km", "m"): 1000, ("m", "km"): 0.001, ("m", "cm"): 100, ("cm", "m"): 0.01,
        ("mile", "km"): 1.60934, ("km", "mile"): 0.621371,
        ("ft", "m"): 0.3048, ("m", "ft"): 3.28084,
        ("inch", "cm"): 2.54, ("cm", "inch"): 0.393701,
        # Weight
        ("kg", "g"): 1000, ("g", "kg"): 0.001, ("kg", "lb"): 2.20462, ("lb", "kg"): 0.453592,
        ("t", "kg"): 1000, ("kg", "t"): 0.001,
        # Temperature handled separately
    }
    fu = from_unit.lower().strip()
    tu = to_unit.lower().strip()

    # Temperature special handling
    if fu in ("c", "celsius", "摄氏度") and tu in ("f", "fahrenheit", "华氏度"):
        result = num * 9 / 5 + 32
    elif fu in ("f", "fahrenheit", "华氏度") and tu in ("c", "celsius", "摄氏度"):
        result = (num - 32) * 5 / 9
    elif fu in ("c", "celsius", "摄氏度") and tu in ("k", "kelvin", "开尔文"):
        result = num + 273.15
    elif fu in ("k", "kelvin", "开尔文") and tu in ("c", "celsius", "摄氏度"):
        result = num - 273.15
    elif (fu, tu) in conversions:
        result = num * conversions[(fu, tu)]
    else:
        return {
            "conversion_result": f"暂不支持 {from_unit} → {to_unit} 的换算",
            "value": value, "from_unit": from_unit, "to_unit": to_unit,
            "status": "error", "message": "不支持的换算类型",
        }

    result_str = str(round(result, 4))
    return {
        "conversion_result": f"{value} {from_unit} = {result_str} {to_unit}",
        "value": value, "from_unit": from_unit, "to_unit": to_unit,
        "result_value": result_str,
        "status": "success",
    }


def recommend_content(content_type=None, genre=None, mood=None):
    """推荐内容（电影、音乐、书籍、播客）"""
    ctype = content_type or "电影"
    recommendations = {
        "电影": {"轻松": "《疯狂动物城》", "悬疑": "《消失的她》", "default": "《肖申克的救赎》"},
        "音乐": {"轻松": "轻音乐精选", "悲伤": "《晴天》- 周杰伦", "default": "流行热歌榜TOP10"},
        "书籍": {"科技": "《人类简史》", "文学": "《活着》- 余华", "default": "《小王子》"},
        "播客": {"科技": "《科技参考》", "故事": "《故事FM》", "default": "得到精品课"},
    }
    cat = recommendations.get(ctype, {"default": f"推荐{ctype}精选内容"})
    key = mood or genre or "default"
    recommendation = cat.get(key, cat.get("default", f"精选{ctype}推荐"))
    return {
        "recommendation_result": f"{ctype}推荐（{key}风格）：{recommendation}",
        "content_type": ctype,
        "genre": genre,
        "mood": mood,
        "status": "success",
    }


def get_recipe(dish_name=None, dietary_restrictions=None, servings=None):
    """查询菜谱，支持按菜名或食材推荐做法"""
    dish = dish_name or "家常菜"
    portions = servings or "2人份"
    diet_note = f"（{dietary_restrictions}饮食）" if dietary_restrictions else ""
    recipe = (
        f"《{dish}》{diet_note}{portions}做法：\n"
        f"1. 准备食材：按{portions}备料\n"
        f"2. 预处理：洗净切块，腌制10分钟\n"
        f"3. 烹饪：热锅冷油，中火翻炒约8分钟\n"
        f"4. 调味：加入适量盐、酱油，出锅前加葱花提香\n"
        f"小贴士：火候控制是关键，保持中火均匀加热"
    )
    return {
        "recipe_result": recipe,
        "dish_name": dish,
        "dietary_restrictions": dietary_restrictions,
        "servings": portions,
        "status": "success",
    }
