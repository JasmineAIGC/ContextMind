"""
PyTOD 场景 API 注册表

为各内置场景（闲聊、客服、保险）提供演示 API 函数的注册逻辑，
以及按场景名称查找注册函数的辅助工具。

扩展方法：
    1. 在本文件中定义新的 ``_register_<scenario>_apis(engine)`` 函数
    2. 将场景名称映射添加到 ``SCENARIO_API_REGISTRY``

本模块与 ``PyTODTracker`` 解耦：追踪器无需关心 API 实现细节，
只需调用 ``get_scenario_key`` + ``SCENARIO_API_REGISTRY`` 完成注册。
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from .execution_engine import ExecutionEngine


# ---------------------------------------------------------------------------
# 闲聊场景 API
# ---------------------------------------------------------------------------

def _register_chat_apis(engine: ExecutionEngine) -> None:
    """为闲聊场景注册演示 API 函数。"""

    @engine.register
    def get_weather(city=None, date=None):
        """查询天气预报。支持今天/明天/后天，或指定城市。"""
        if not city:
            return {"hint": "请提供城市名称"}
        weather_map = {
            "北京": {"condition": "晴", "temp_high": 12, "temp_low": 2, "wind": "西北风3级"},
            "上海": {"condition": "多云", "temp_high": 16, "temp_low": 8, "wind": "东南风2级"},
            "广州": {"condition": "小雨", "temp_high": 22, "temp_low": 15, "wind": "南风1级"},
        }
        w = weather_map.get(city, {"condition": "晴转多云", "temp_high": 15, "temp_low": 5, "wind": "微风"})
        return {
            "city": city,
            "date": date or "今天",
            "condition": w["condition"],
            "temp_high": w["temp_high"],
            "temp_low": w["temp_low"],
            "wind": w["wind"],
            "message": f"{city}{date or '今天'}天气：{w['condition']}，{w['temp_low']}~{w['temp_high']}℃，{w['wind']}",
        }

    @engine.register
    def search_info(query=None, category=None):
        """搜索信息或回答知识类问题。category 可选：news（新闻）、wiki（百科）、general（通用）。"""
        if not query:
            return {"hint": "请提供搜索关键词"}
        return {
            "query": query,
            "category": category or "general",
        }

    @engine.register
    def tell_joke(topic=None):
        """讲一个笑话。topic 可选：程序员、数学、生活、动物。"""
        jokes = {
            "程序员": "一个程序员妻子让他去超市：'买一斤鸡蛋，如果有苹果就买两斤。'程序员回来带了两斤鸡蛋，因为超市有苹果。",
            "数学": "老师问：x = 1 的话，x + x 等于几？学生答：等于 2 + 2，老师问为什么？学生说：因为 x = 1，所以 2x = 2。",
            "生活": "闹钟响了，我问自己：'再睡五分钟？'自己说：'好的。'——三小时后，我迟到了。",
            "动物": "狗对猫说：'你喜欢主人吗？'猫说：'喜欢。'狗问：'那你为什么总是无视他？'猫说：'因为这样他才会更宠我。'",
        }
        joke_text = jokes.get(topic, jokes.get("生活"))
        return {"topic": topic or "生活", "joke": joke_text}

    @engine.register
    def translate_text(text=None, target_language=None, source_language=None):
        """翻译文本。target_language 为目标语言（中文/英文/日文/韩文等）。"""
        if not text:
            return {"hint": "请提供要翻译的文本"}
        if not target_language:
            return {"hint": "请提供目标语言"}
        return {
            "original": text,
            "source_language": source_language or "自动检测",
            "target_language": target_language,
        }

    @engine.register
    def calculate(expression=None):
        """计算数学表达式。支持加减乘除、百分比等基础运算。"""
        if not expression:
            return {"hint": "请提供计算表达式，如：100*0.85 或 1200/12"}
        try:
            # 只允许数字和安全运算符
            import re as _re
            safe = _re.sub(r'[^0-9+\-*/.() %]', '', str(expression))
            result = eval(safe)  # nosec — expression filtered to safe chars only
            return {"expression": expression, "result": result, "message": f"{expression} = {result}"}
        except Exception:
            return {"expression": expression, "error": "表达式格式有误，请检查后重试"}

    @engine.register
    def get_current_time(city=None, timezone=None):
        """查询当前时间。支持按城市或时区（如 Asia/Shanghai、America/New_York）查询。"""
        import datetime as _dt
        tz_map = {
            "北京": "Asia/Shanghai", "上海": "Asia/Shanghai", "东京": "Asia/Tokyo",
            "纽约": "America/New_York", "伦敦": "Europe/London", "巴黎": "Europe/Paris",
            "悉尼": "Australia/Sydney", "洛杉矶": "America/Los_Angeles",
        }
        tz_name = timezone or tz_map.get(city or "", "Asia/Shanghai")
        now = _dt.datetime.now(_dt.timezone.utc)
        offset_hours = {
            "Asia/Shanghai": 8, "Asia/Tokyo": 9, "Europe/London": 0,
            "Europe/Paris": 1, "America/New_York": -5, "America/Los_Angeles": -8,
            "Australia/Sydney": 11,
        }.get(tz_name, 8)
        local_time = now + _dt.timedelta(hours=offset_hours)
        return {
            "city": city or "北京",
            "timezone": tz_name,
            "current_time": local_time.strftime("%Y-%m-%d %H:%M:%S"),
            "date": local_time.strftime("%Y年%m月%d日"),
            "time": local_time.strftime("%H:%M"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][local_time.weekday()],
        }

    @engine.register
    def convert_units(value=None, from_unit=None, to_unit=None):
        """单位换算。支持长度（米/英尺/英里/公里）、重量（千克/磅/斤）、温度（摄氏/华氏）等。"""
        if value is None:
            return {"hint": "请提供要换算的数值"}
        if not from_unit:
            return {"hint": "请提供原始单位"}
        if not to_unit:
            return {"hint": "请提供目标单位"}
        try:
            val = float(value)
        except (TypeError, ValueError):
            return {"error": f"无效数值：{value}"}
        # 统一到 SI 单位再转目标
        to_si: dict = {
            "米": 1, "m": 1, "公里": 1000, "km": 1000,
            "英尺": 0.3048, "ft": 0.3048, "英里": 1609.344, "mile": 1609.344,
            "千克": 1, "kg": 1, "斤": 0.5, "磅": 0.453592, "lb": 0.453592,
        }
        temp_pairs = {
            ("摄氏", "华氏"): lambda c: c * 9 / 5 + 32,
            ("华氏", "摄氏"): lambda f: (f - 32) * 5 / 9,
            ("℃", "℉"): lambda c: c * 9 / 5 + 32,
            ("℉", "℃"): lambda f: (f - 32) * 5 / 9,
        }
        pair = (from_unit, to_unit)
        if pair in temp_pairs:
            result = round(temp_pairs[pair](val), 4)
        elif from_unit in to_si and to_unit in to_si:
            result = round(val * to_si[from_unit] / to_si[to_unit], 6)
        else:
            return {"error": f"不支持的单位组合：{from_unit} → {to_unit}"}
        return {
            "original_value": val,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "result": result,
            "message": f"{val} {from_unit} = {result} {to_unit}",
        }

    @engine.register
    def recommend_content(content_type=None, genre=None, mood=None):
        """推荐内容（电影、音乐、书籍、播客）。content_type 可选：电影、音乐、书籍、播客。"""
        if not content_type:
            return {"hint": "请告诉我您想要什么类型的推荐：电影、音乐、书籍还是播客？"}
        catalog: dict = {
            "电影": {
                "喜剧": [{"title": "疯狂动物城", "rating": 9.2, "year": 2016}, {"title": "夏洛特烦恼", "rating": 8.1, "year": 2015}],
                "科幻": [{"title": "星际穿越", "rating": 9.3, "year": 2014}, {"title": "流浪地球2", "rating": 8.3, "year": 2023}],
                "剧情": [{"title": "肖申克的救赎", "rating": 9.7, "year": 1994}, {"title": "我不是药神", "rating": 9.0, "year": 2018}],
                "default": [{"title": "流浪地球2", "rating": 8.3, "year": 2023}, {"title": "封神第一部", "rating": 7.8, "year": 2023}],
            },
            "音乐": {
                "流行": [{"title": "晴天", "artist": "周杰伦"}, {"title": "平凡之路", "artist": "朴树"}],
                "古典": [{"title": "月光奏鸣曲", "artist": "贝多芬"}, {"title": "二泉映月", "artist": "华彦钧"}],
                "轻音乐": [{"title": "River Flows In You", "artist": "Yiruma"}, {"title": "天空之城", "artist": "久石让"}],
                "default": [{"title": "晴天", "artist": "周杰伦"}, {"title": "平凡之路", "artist": "朴树"}],
            },
            "书籍": {
                "科技": [{"title": "人工智能简史", "author": "尼克"}, {"title": "代码大全", "author": "Steve McConnell"}],
                "文学": [{"title": "百年孤独", "author": "加西亚·马尔克斯"}, {"title": "活着", "author": "余华"}],
                "default": [{"title": "活着", "author": "余华"}, {"title": "三体", "author": "刘慈欣"}],
            },
        }
        items = catalog.get(content_type, {})
        recs = items.get(genre or mood or "", items.get("default", []))
        return {
            "content_type": content_type,
            "genre": genre or mood or "综合",
            "recommendations": recs,
            "count": len(recs),
        }

    @engine.register
    def get_news_headlines(category=None, count=None):
        """获取新闻头条。category 可选：科技、财经、体育、娱乐、社会、国际。"""
        news_map: dict = {
            "科技": [
                {"title": "AI大模型迎来新突破，多模态能力显著提升", "source": "科技日报"},
                {"title": "国产芯片出货量创历史新高", "source": "半导体行业观察"},
                {"title": "开源AI框架用户数突破亿级", "source": "InfoQ"},
            ],
            "财经": [
                {"title": "A股三大指数集体上涨，科技板块领跑", "source": "财联社"},
                {"title": "人民币汇率保持稳定，外资持续流入", "source": "中国证券报"},
                {"title": "新能源汽车出口同比增长40%", "source": "经济日报"},
            ],
            "体育": [
                {"title": "中国乒乓球队世锦赛卫冕成功", "source": "新华社体育"},
                {"title": "CBA季后赛首轮赛程确定", "source": "腾讯体育"},
                {"title": "国足世预赛备战顺利，主帅称状态良好", "source": "懂球帝"},
            ],
        }
        headlines = news_map.get(category or "科技", news_map["科技"])
        n = min(int(count or 3), len(headlines))
        return {
            "category": category or "科技",
            "headlines": headlines[:n],
            "count": n,
        }

    @engine.register
    def get_recipe(dish_name=None, dietary_restrictions=None, servings=None):
        """获取菜谱。dish_name 为菜名，dietary_restrictions 为饮食限制（素食/低糖/低脂等）。"""
        if not dish_name:
            return {"hint": "请告诉我您想做什么菜？"}
        recipes: dict = {
            "番茄炒蛋": {
                "ingredients": ["鸡蛋3个", "番茄2个", "盐适量", "糖少许", "食用油", "葱花"],
                "steps": ["鸡蛋打散加盐搅匀", "番茄切块", "热锅炒鸡蛋至七成熟盛出", "重新热锅炒番茄出汁", "加入鸡蛋翻炒，加盐糖调味", "出锅撒葱花"],
                "time_minutes": 15,
                "difficulty": "简单",
            },
            "红烧肉": {
                "ingredients": ["五花肉500g", "老抽2勺", "生抽3勺", "冰糖50g", "料酒", "姜片", "八角"],
                "steps": ["五花肉切块焯水", "锅中炒糖色至棕红", "加入肉块翻炒上色", "加生抽、老抽、料酒", "加水没过肉，大火烧开转小火", "炖40分钟至软烂，大火收汁"],
                "time_minutes": 60,
                "difficulty": "中等",
            },
        }
        recipe = recipes.get(dish_name, {
            "ingredients": ["根据菜名准备相应食材"],
            "steps": ["按照标准做法烹饪"],
            "time_minutes": 30,
            "difficulty": "中等",
        })
        n = int(servings or 2)
        return {
            "dish_name": dish_name,
            "servings": n,
            "dietary_restrictions": dietary_restrictions or "无",
            "ingredients": recipe["ingredients"],
            "steps": recipe["steps"],
            "cook_time": f"{recipe['time_minutes']}分钟",
            "difficulty": recipe["difficulty"],
        }


# ---------------------------------------------------------------------------
# 客服场景 API
# ---------------------------------------------------------------------------

def _register_callcenter_apis(engine: ExecutionEngine) -> None:
    """为客服场景注册演示 API 函数。"""

    @engine.register
    def lookup_order(order_id=None, customer_id=None, product_name=None, purchase_date=None):
        """查询订单信息。支持按订单号、客户ID、商品名称或购买日期查询。"""
        if not any([order_id, customer_id, product_name, purchase_date]):
            return {"error": "请提供至少一项查询条件：订单号、客户ID、商品名称或购买日期"}
        oid = order_id or "ORD-20260220-8851"
        return {
            "order_id": oid,
            "product_name": product_name or "智能扫地机器人",
            "purchase_date": purchase_date or "2026-02-20",
            "status": "已发货",
            "shipping_date": "2026-02-21",
            "estimated_delivery": "2026-02-28",
            "carrier": "顺丰快递",
            "tracking_number": f"SF{oid[-10:].replace('-', '')}",
        }

    @engine.register
    def submit_complaint(complaint_type=None, description=None, order_id=None, urgency=None):
        """提交投诉或反馈。适用于服务不满意、产品问题、物流问题等场景。"""
        urgency_map = {"高": "12小时内", "紧急": "4小时内"}
        return {
            "ticket_id": "CMP-20260226-5842",
            "complaint_type": complaint_type or "服务投诉",
            "description_received": bool(description),
            "order_id": order_id,
            "urgency": urgency or "普通",
            "status": "已受理",
            "expected_response_time": urgency_map.get(urgency or "", "24小时内"),
        }

    @engine.register
    def process_refund(order_id=None, reason=None, amount=None, product_name=None):
        """申请退款。需要提供订单号（或商品名称）及退款原因。"""
        if not (order_id or product_name):
            return {"hint": "请提供订单号或商品名称，以便为您办理退款"}
        ref_base = order_id or product_name or "UNKNOWN"
        return {
            "refund_id": f"REF-{ref_base[:8].upper()}-001",
            "order_id": order_id or "(待确认)",
            "product_name": product_name,
            "status": "受理中",
            "expected_time": "3-5个工作日",
            "amount": f"{amount}元" if amount else "全额退款",
            "reason": reason or "用户申请",
        }

    @engine.register
    def check_refund_status(refund_id=None, order_id=None):
        """查询退款进度。支持按退款单号或原订单号查询。"""
        if not (refund_id or order_id):
            return {"error": "请提供退款单号或订单号"}
        return {
            "refund_id": refund_id or f"REF-{order_id}-001",
            "order_id": order_id,
            "status": "审核中",
            "submitted_date": "2026-02-22",
            "expected_completion": "2026-02-27",
            "refund_method": "原路退回",
            "notes": "退款审核通过后将在1-3个工作日内到账。",
        }

    @engine.register
    def check_logistics(order_id=None, tracking_number=None):
        """查询物流轨迹。按订单号或快递单号查询实时物流状态。"""
        if not (order_id or tracking_number):
            return {"hint": "请提供订单号或快递单号"}
        return {
            "tracking_number": tracking_number or "SF1234567890",
            "carrier": "顺丰快递",
            "status": "运输中",
            "current_location": "上海中转仓",
            "last_update": "2026-02-25 18:30",
            "estimated_delivery": "2026-02-27",
        }

    @engine.register
    def transfer_to_agent(department=None, issue_type=None, priority=None):
        """转接人工客服。复杂问题或客户强烈要求时使用。"""
        wait_map = {"紧急": "约1分钟", "高": "约3分钟"}
        return {
            "status": "转接中",
            "department": department or "综合客服",
            "issue_type": issue_type,
            "priority": priority or "普通",
            "estimated_wait": wait_map.get(priority or "", "约5分钟"),
            "ticket_id": "TKT-20260226-001",
        }

    @engine.register
    def check_account_status(customer_id=None, account_type=None):
        """查询账户状态与余额。account_type 可选：普通账户、会员账户、企业账户。"""
        if not customer_id:
            return {"hint": "请提供客户ID或手机号以查询账户状态"}
        return {
            "customer_id": customer_id,
            "account_type": account_type or "普通账户",
            "status": "正常",
            "balance": 1280.50,
            "available_credit": 5000.00,
            "points": 3200,
            "membership_level": "银卡会员",
            "registered_date": "2023-06-15",
            "last_login": "2026-03-19",
        }

    @engine.register
    def query_points_balance(customer_id=None):
        """查询积分余额及可兑换商品/优惠券列表。"""
        if not customer_id:
            return {"hint": "请提供客户ID或手机号以查询积分"}
        return {
            "customer_id": customer_id,
            "points_balance": 3200,
            "points_expiring_soon": 500,
            "expiry_date": "2026-12-31",
            "redeemable_rewards": [
                {"name": "20元优惠券", "cost_points": 500, "valid_days": 30},
                {"name": "50元优惠券", "cost_points": 1000, "valid_days": 30},
                {"name": "免运费券（5次）", "cost_points": 300, "valid_days": 90},
                {"name": "会员月卡", "cost_points": 2000, "valid_days": 30},
            ],
        }

    @engine.register
    def apply_discount_coupon(order_id=None, coupon_code=None, customer_id=None):
        """为订单应用优惠券或折扣码。"""
        if not (order_id or customer_id):
            return {"hint": "请提供订单号或客户ID"}
        if not coupon_code:
            return {"hint": "请提供优惠券码"}
        valid_coupons = {"SAVE20": 20, "VIP50": 50, "NEW10": 10}
        discount = valid_coupons.get(coupon_code.upper(), 0)
        if discount == 0:
            return {"error": f"优惠券码 {coupon_code} 无效或已过期"}
        return {
            "order_id": order_id or "(待关联)",
            "coupon_code": coupon_code.upper(),
            "discount_amount": discount,
            "status": "已应用",
            "message": f"优惠券应用成功，已优惠 {discount} 元",
        }

    @engine.register
    def update_delivery_address(order_id=None, new_address=None, recipient_name=None, phone=None):
        """修改订单配送地址（仅限未发货订单）。"""
        if not order_id:
            return {"hint": "请提供需要修改地址的订单号"}
        if not new_address:
            return {"hint": "请提供新的配送地址"}
        return {
            "order_id": order_id,
            "status": "修改成功",
            "new_address": new_address,
            "recipient_name": recipient_name or "(保持原收件人)",
            "phone": phone or "(保持原手机号)",
            "message": "地址已更新，请注意商家发货后将使用新地址派送",
        }

    @engine.register
    def schedule_callback(customer_id=None, preferred_time=None, issue_description=None, phone=None):
        """预约客服回拨。在客户无法等待时，安排客服在指定时间主动联系。"""
        if not (customer_id or phone):
            return {"hint": "请提供您的客户ID或联系电话"}
        return {
            "callback_id": "CB-20260320-0042",
            "customer_id": customer_id or "(未提供)",
            "contact_phone": phone or "(使用账户绑定号码)",
            "preferred_time": preferred_time or "工作日09:00-18:00",
            "issue_summary": issue_description or "(未填写)",
            "status": "已预约",
            "expected_callback": preferred_time or "下一个工作日内",
            "message": "回拨预约成功，客服专员将在指定时间联系您",
        }

    @engine.register
    def query_product_info(product_name=None, product_id=None, attribute=None):
        """查询商品详情、规格、库存及评价。attribute 可选：规格/库存/评价/价格。"""
        if not (product_name or product_id):
            return {"hint": "请提供商品名称或商品编号"}
        catalog: dict = {
            "智能扫地机器人": {
                "product_id": "SKU-ROBOT-001",
                "price": 1999,
                "stock": "有货（100+）",
                "rating": 4.8,
                "review_count": 2341,
                "specs": {"功率": "25W", "噪音": "≤65dB", "续航": "120分钟", "吸力": "2700Pa"},
                "warranty": "1年整机保修",
            },
        }
        product = catalog.get(product_name or "", {
            "product_id": product_id or "N/A",
            "price": "(请查询官网)",
            "stock": "请联系客服确认",
            "rating": "N/A",
            "specs": {},
            "warranty": "详见产品说明书",
        })
        if attribute and attribute in ("规格", "specs"):
            return {"product_name": product_name, "specs": product.get("specs", {})}
        return {
            "product_name": product_name or product_id,
            **product,
        }


# 拒保风险关键词（保险健康告知校验）
_EXCLUDED_CONDITIONS = ["癌症", "艾滋", "精神", "肝硬化"]


# ---------------------------------------------------------------------------
# 保险场景 API
# ---------------------------------------------------------------------------

def _register_insurance_apis(engine: ExecutionEngine) -> None:
    """为保险场景注册演示 API 函数。"""

    @engine.register
    def query_insurance(insurance_type=None, customer_age=None, coverage_type=None):
        """查询保险产品信息。insurance_type 可选：癌症险、重疾险、寿险、医疗险、意外险。"""
        product_map = {
            "癌症险": {
                "monthly_premium_base": 114.0,
                "coverage_amount": 1000000,
                "coverage_items": ["确诊即赔100万", "恶性肿瘤住院津贴每日200元", "身故保额赔付"],
                "waiting_period": "90天",
                "max_age": 60,
                "description": "专项癌症保障，确诊即赔，适合30-60岁健康人群",
            },
            "重疾险": {
                "monthly_premium_base": 280.0,
                "coverage_amount": 500000,
                "coverage_items": ["100种重大疾病", "60种中症", "20种轻症", "保费豁免", "身故赔付"],
                "waiting_period": "90天",
                "max_age": 55,
                "description": "涵盖100种重大疾病，含轻中症分级赔付，可附加保费豁免",
            },
            "医疗险": {
                "monthly_premium_base": 50.0,
                "coverage_amount": 2000000,
                "coverage_items": ["住院医疗100%报销", "门诊手术", "特殊门诊", "质子重离子治疗"],
                "waiting_period": "30天",
                "max_age": 65,
                "description": "200万保额，住院医疗报销比例高，含免赔额1万元",
            },
            "意外险": {
                "monthly_premium_base": 30.0,
                "coverage_amount": 500000,
                "coverage_items": ["意外身故/残疾赔付", "意外医疗报销", "住院津贴"],
                "waiting_period": "无等待期",
                "max_age": 70,
                "description": "覆盖日常意外及交通意外，无等待期，次日生效",
            },
            "寿险": {
                "monthly_premium_base": 150.0,
                "coverage_amount": 1000000,
                "coverage_items": ["身故赔付100万", "全残赔付", "保费豁免"],
                "waiting_period": "90天",
                "max_age": 60,
                "description": "定期寿险，身故或全残赔付，适合有家庭责任的人群",
            },
        }
        ptype = insurance_type or "重疾险"
        product = product_map.get(ptype, product_map["重疾险"])
        age = int(customer_age) if customer_age is not None else None
        if age is not None and age > product["max_age"]:
            return {"error": f"{ptype}投保年龄上限为{product['max_age']}岁，您目前超出投保范围"}
        return {
            "insurance_type": ptype,
            "coverage_type": coverage_type or "全面保障",
            "monthly_premium_reference": product["monthly_premium_base"],
            "coverage_amount": product["coverage_amount"],
            "coverage_items": product["coverage_items"],
            "waiting_period": product["waiting_period"],
            "description": product["description"],
        }

    @engine.register
    def calculate_premium(insurance_type=None, customer_age=None, coverage_amount=None, gender=None):
        """精算保费。根据险种、年龄、保额（及性别）计算月保费和年保费。"""
        base_rate_map = {
            "癌症险": 0.000228,
            "重疾险": 0.00056,
            "医疗险": 0.0001,
            "意外险": 0.00006,
            "寿险": 0.0003,
        }
        ptype = insurance_type or "重疾险"
        base_rate = base_rate_map.get(ptype, 0.00056)
        amount = float(coverage_amount or 500000)
        age = int(customer_age or 35)
        # 年龄系数：30岁以下1.0，每满5岁增加0.15（阶梯式计算）
        age_factor = 1.0 + max(0, (age - 30) // 5) * 0.15
        gender_factor = 1.1 if gender in ("男", "male", "M") else 1.0
        monthly = round(amount * base_rate * age_factor * gender_factor, 2)
        return {
            "insurance_type": ptype,
            "customer_age": age,
            "gender": gender or "未指定",
            "coverage_amount": int(amount),
            "monthly_premium": monthly,
            "annual_premium": round(monthly * 12, 2),
            "payment_term": "20年缴清",
            "note": "以上为参考保费，实际以核保结果为准",
        }

    @engine.register
    def compare_products(product_a=None, product_b=None, customer_age=None):
        """对比两款保险产品的保障范围和性价比。"""
        if not product_a or not product_b:
            return {"hint": "请提供要对比的两款保险产品名称"}
        return {
            "product_a": product_a,
            "product_b": product_b,
            "comparison_dimensions": ["保障范围", "保费水平", "等待期", "理赔便利性"],
            "recommendation": f"根据{customer_age or '您'}的情况，两款产品各有优势，建议结合自身健康状况和预算选择。",
        }

    @engine.register
    def check_health_requirements(insurance_type=None, condition=None):
        """查询投保健康告知要求，判断某种健康状况是否影响投保。"""
        if not insurance_type:
            return {"hint": "请提供险种名称（如重疾险、医疗险）"}
        if not condition:
            return {"hint": "请描述需要核查的健康状况或既往病史"}
        has_risk = any(kw in condition for kw in _EXCLUDED_CONDITIONS)
        return {
            "insurance_type": insurance_type,
            "condition": condition,
            "risk_level": "高风险（可能拒保）" if has_risk else "低风险（建议如实告知）",
            "advice": "如实填写健康告知，具体是否可投保以保险公司核保结果为准。",
        }

    @engine.register
    def get_policy_details(policy_number=None, customer_name=None):
        """查询保单详情。需要保单号或客户姓名。"""
        if not (policy_number or customer_name):
            return {"hint": "请提供保单号或客户姓名以查询保单信息"}
        return {
            "policy_number": policy_number or "POL-20240315-0042",
            "customer_name": customer_name or "张先生",
            "insurance_type": "重疾险",
            "coverage_amount": 500000,
            "monthly_premium": 280,
            "effective_date": "2024-03-15",
            "expiry_date": "2044-03-15",
            "payment_term": "20年缴清",
            "status": "有效",
            "beneficiary": "配偶",
        }

    @engine.register
    def submit_claim(policy_number=None, claim_type=None, incident_date=None, description=None):
        """提交理赔申请。需要保单号、理赔类型和事故/诊断日期。"""
        if not policy_number:
            return {"hint": "请提供保单号以提交理赔"}
        if not claim_type:
            return {"hint": "请提供理赔类型（如：重疾确诊、住院医疗、意外伤害）"}
        doc_map = {
            "重疾确诊": ["医院诊断证明（加盖公章）", "病理报告", "出院小结", "银行账户信息"],
            "住院医疗": ["住院病历", "医疗费用总清单", "费用发票原件", "出院小结"],
            "意外伤害": ["意外事故说明", "诊断证明", "费用发票", "银行账户信息"],
        }
        docs = doc_map.get(claim_type, ["医院诊断证明", "费用发票", "银行账户信息"])
        return {
            "claim_id": "CLM-20260226-0089",
            "policy_number": policy_number,
            "claim_type": claim_type,
            "incident_date": incident_date or "待确认",
            "status": "已受理",
            "required_documents": docs,
            "expected_review_time": "5-10个工作日",
        }

    @engine.register
    def check_claim_status(claim_id=None, policy_number=None):
        """查询理赔进度。支持按理赔单号或保单号查询。"""
        if not (claim_id or policy_number):
            return {"hint": "请提供理赔单号或保单号"}
        return {
            "claim_id": claim_id or "CLM-2026-001",
            "policy_number": policy_number,
            "status": "审核中",
            "current_step": "医疗材料核查（第2步，共4步）",
            "submitted_date": "2026-02-01",
            "expected_completion": "2026-03-01",
        }

    @engine.register
    def recommend_insurance(age=None, gender=None, budget=None, needs=None):
        """个性化保险推荐。根据年龄、性别、预算和保障需求推荐合适险种。"""
        if not age:
            return {"hint": "请提供您的年龄以便为您推荐合适的保险产品"}
        age_val = int(age)
        budget_val = float(budget or 200)
        needs_str = str(needs or "").lower()
        recs = []
        if age_val < 35:
            recs.append({"type": "重疾险", "reason": "年轻投保费率低，保障期长，性价比高", "estimated_monthly": round(budget_val * 0.4, 0)})
            recs.append({"type": "意外险", "reason": "工作压力大，出行频繁，意外保障必备", "estimated_monthly": 30})
            if "医疗" in needs_str or budget_val >= 100:
                recs.append({"type": "医疗险", "reason": "百万医疗险保费低、保额高，可覆盖住院大额医疗费", "estimated_monthly": 50})
        elif age_val < 50:
            recs.append({"type": "重疾险", "reason": "中年是重疾高发期，及早配置防患于未然", "estimated_monthly": round(budget_val * 0.5, 0)})
            recs.append({"type": "医疗险", "reason": "住院及特殊门诊费用保障", "estimated_monthly": 80})
            if "寿险" in needs_str or "家庭" in needs_str:
                recs.append({"type": "定期寿险", "reason": "为家庭责任提供身故保障", "estimated_monthly": round(budget_val * 0.3, 0)})
        else:
            recs.append({"type": "医疗险", "reason": "中老年医疗费用较高，医疗险可减轻负担", "estimated_monthly": 120})
            recs.append({"type": "意外险", "reason": "老年跌倒风险增加，意外险保障必要", "estimated_monthly": 50})
            if "癌症" in needs_str or "重疾" in needs_str:
                recs.append({"type": "癌症险", "reason": "专项癌症保障，确诊即赔", "estimated_monthly": 150})
        return {
            "age": age_val,
            "gender": gender or "未指定",
            "monthly_budget": budget_val,
            "needs": needs or "综合保障",
            "recommendations": recs,
            "note": "以上为参考推荐，实际产品及费率以投保时为准",
        }

    @engine.register
    def query_renewal_options(policy_number=None):
        """查询保单续保方案与到期提醒。"""
        if not policy_number:
            return {"hint": "请提供保单号以查询续保信息"}
        return {
            "policy_number": policy_number,
            "expiry_date": "2026-06-30",
            "days_until_expiry": 102,
            "renewal_options": [
                {"option": "原保额续保", "new_annual_premium": 3360, "change": "无变化"},
                {"option": "提额续保（+50万）", "new_annual_premium": 4200, "change": "保额增加50万"},
                {"option": "不续保", "consequence": "到期后保障终止，已缴保费不退"},
            ],
            "recommendation": "建议尽早续保，避免保障中断及重新核保",
            "auto_renewal_status": "未开启",
        }

    @engine.register
    def lookup_hospital(city=None, hospital_name=None, insurance_type=None):
        """查询医院是否在保险直付/定点网络中。"""
        if not (city or hospital_name):
            return {"hint": "请提供城市或医院名称以查询定点医院信息"}
        hospitals_demo = [
            {"name": "北京协和医院", "city": "北京", "level": "三甲", "direct_billing": True},
            {"name": "上海瑞金医院", "city": "上海", "level": "三甲", "direct_billing": True},
            {"name": "广州南方医院", "city": "广州", "level": "三甲", "direct_billing": True},
        ]
        if hospital_name:
            match = next((h for h in hospitals_demo if hospital_name in h["name"]), None)
            if match:
                return {**match, "insurance_type": insurance_type or "医疗险", "status": "定点医院，支持直付"}
            return {
                "hospital_name": hospital_name,
                "city": city or "未知",
                "direct_billing": False,
                "status": "非直付医院，需先垫付后报销",
                "tips": "就诊后保留发票和病历，提交理赔材料可申请报销",
            }
        return {
            "city": city,
            "insurance_type": insurance_type or "医疗险",
            "nearby_hospitals": [h for h in hospitals_demo if not city or city in h["city"]] or hospitals_demo[:2],
            "total_in_network": 1280,
        }

    @engine.register
    def suspend_or_resume_policy(policy_number=None, action=None):
        """暂停或恢复保单（部分险种支持）。action 可选：suspend（暂停）、resume（恢复）。"""
        if not policy_number:
            return {"hint": "请提供需要操作的保单号"}
        if not action:
            return {"hint": "请告知您是要暂停保单还是恢复保单（suspend/resume）"}
        action_lower = str(action).lower()
        if action_lower in ("suspend", "暂停", "中止"):
            return {
                "policy_number": policy_number,
                "action": "暂停",
                "status": "操作成功",
                "effective_date": "2026-03-20",
                "note": "保单暂停期间保障暂停，恢复前请重新核保，最长暂停期为6个月",
            }
        return {
            "policy_number": policy_number,
            "action": "恢复",
            "status": "操作成功",
            "effective_date": "2026-03-20",
            "note": "保单已恢复，保障从今日生效，如有疑问请联系客服",
        }


# ---------------------------------------------------------------------------
# 公共注册表
# ---------------------------------------------------------------------------

#: 场景名称 → API 注册函数映射
SCENARIO_API_REGISTRY: Dict[str, Callable[[ExecutionEngine], None]] = {
    "chat": _register_chat_apis,
    "闲聊": _register_chat_apis,
    "callcenter": _register_callcenter_apis,
    "客服": _register_callcenter_apis,
    "insurance": _register_insurance_apis,
    "保险": _register_insurance_apis,
    "保险挽回": _register_insurance_apis,
}


def get_scenario_key(scenario_name: str) -> Optional[str]:
    """从场景名称（可能含中文别名）查找注册表键，找不到时返回 None。"""
    if scenario_name in SCENARIO_API_REGISTRY:
        return scenario_name
    for key in SCENARIO_API_REGISTRY:
        if key in scenario_name or scenario_name in key:
            return key
    return None
