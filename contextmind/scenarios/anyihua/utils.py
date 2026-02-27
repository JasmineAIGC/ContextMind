"""
安逸花外呼促活场景 · 数据解析工具

提供中文数字转换与 用户信息 字段解析两项核心功能。

数据结构说明（来自 chat_test_100.json）：
    用户信息 字段以 "#" 分隔，字段数量为 20~33（非固定），
    部分会话 [0] 为 "登录安逸花APP"，导致客户姓名在 [2] 而非 [1]，
    必须按内容关键词识别字段语义，不能依赖位置索引。

基于 docs/analysis/pytod-on-chat-test-100.md §3 实现。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# 中文数字解析
# --------------------------------------------------------------------------- #


def cn2int(s: str) -> int:
    """
    将中文数字字符串转换为整数。

    支持：零~九、十、百、千、万，以及"两"（等价于"二"）。

    参数:
        s: 中文数字字符串，例如 '二万三千九百八十八'

    返回:
        对应整数，例如 23988

    示例::

        >>> cn2int('二万三千九百八十八')
        23988
        >>> cn2int('一万八千')
        18000
        >>> cn2int('七千零四十一')
        7041
        >>> cn2int('二十四')
        24

    注意:
        不支持的字符（如英文数字、亿）会被忽略。
        输入为空字符串时返回 0。
    """
    s = s.replace("两", "二")
    digits = {
        "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    num = 0
    wan = 0
    bai = 0
    for c in s:
        if c in digits:
            num = digits[c]
        elif c == "万":
            wan = (bai + num) * 10000
            bai = num = 0
        elif c == "千":
            bai += (num if num else 1) * 1000
            num = 0
        elif c == "百":
            bai += (num if num else 1) * 100
            num = 0
        elif c == "十":
            bai += (num if num else 1) * 10
            num = 0
    return wan + bai + num


def extract_amounts(text: str) -> List[Tuple[str, int]]:
    """
    从文本中提取所有中文金额（"元"或"块钱"结尾）。

    仅返回整数值 > 500 的金额，过滤日常小额数字（如"三元"）。

    参数:
        text: 包含中文金额的字符串

    返回:
        [(中文文本, 整数值), ...] 列表，按出现顺序排列

    示例::

        >>> extract_amounts('您的可提现额度为两万三千九百八十八元')
        [('两万三千九百八十八', 23988)]
        >>> extract_amounts('借款利率是百分之二十四')
        []  # 24 < 500
    """
    pattern = r"([零一二三四五六七八九十百千万亿两]+)(?:元|块钱)"
    return [
        (m, cn2int(m))
        for m in re.findall(pattern, text)
        if cn2int(m) > 500
    ]


# --------------------------------------------------------------------------- #
# 用户信息解析
# --------------------------------------------------------------------------- #


def parse_user_info(user_info_str: str) -> Dict[str, Any]:
    """
    将 用户信息 字段（"#" 分隔）解析为结构化字典。

    字段数量为 20~33（非均匀），字段位置不固定：
    - 通常 [0] 为通话时间（"现在是上午十一点…"）
    - 部分会话 [0] 为 "登录安逸花APP"，通话时间在 [1]，客户姓名在 [2]
    - 因此所有字段必须按内容关键词识别，不能硬编码位置索引

    参数:
        user_info_str: 用户信息原始字符串，例如：
            "现在是上午十一点二十一分#高先生#手机尾号是六七八#..."

    返回:
        包含以下键的字典：

        - raw_fields (list):    原始字段列表
        - customer_name (str|None): 客户姓名（如 "高先生"）
        - call_time (str|None): 通话时间描述
        - phone_suffix (str|None): 手机尾号
        - available_credit (int): 可提现额度（元），核心字段
        - temp_credit (int):    临时额度上限（元）
        - temp_expired (bool):  临时额度是否已过期
        - temp_active_days (int): 临时额度剩余有效天数
        - annual_rate_pct (int): 年化利率（%），通常为 24
        - loan_count (int):     当前未还清借款笔数
        - last_loan_date (str): 最近一次借款日期（中文格式）
        - outstanding_amount (int): 未还款金额（元）
        - loan_outstanding (bool): 是否有未还款项
        - bound_bank (str):     绑定银行名称
    """
    fields = user_info_str.split("#")
    info: Dict[str, Any] = {
        "raw_fields": fields,
        "customer_name": None,
        "call_time": None,
        "phone_suffix": None,
        "available_credit": 0,
        "temp_credit": 0,
        "temp_expired": True,
        "temp_active_days": 0,
        "annual_rate_pct": 24,
        "loan_count": 0,
        "last_loan_date": "",
        "outstanding_amount": 0,
        "loan_outstanding": False,
        "bound_bank": "",
    }

    for f in fields:
        # 客户姓名（先生/女士，排除坐席自称、手机号相关描述）
        if (
            (f.endswith("先生") or f.endswith("女士"))
            and "手机" not in f
            and "经理" not in f
        ):
            info["customer_name"] = f

        elif "现在是" in f:
            info["call_time"] = f

        elif "手机尾号是" in f:
            info["phone_suffix"] = f.replace("手机尾号是", "").strip()

        elif "可提现额度为" in f:
            ams = extract_amounts(f)
            if ams:
                info["available_credit"] = ams[0][1]

        elif "临时额度为" in f and "临时提额为" not in f:
            ams = extract_amounts(f)
            if ams:
                info["temp_credit"] = ams[0][1]

        elif "临时提额已过期" in f:
            info["temp_expired"] = True

        elif "临时提额还有" in f:
            info["temp_expired"] = False
            m = re.search(r"([零一二三四五六七八九十百千]+)天", f)
            if m:
                info["temp_active_days"] = cn2int(m.group(1))

        elif "借款利率是" in f:
            m = re.search(r"([零一二三四五六七八九十百千]+)", f)
            if m:
                info["annual_rate_pct"] = cn2int(m.group(1))

        elif "现有" in f and "笔借款" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)笔", f)
            if m:
                info["loan_count"] = cn2int(m.group(1))

        elif "最近一次借款是" in f:
            info["last_loan_date"] = f.replace("最近一次借款是", "").strip()

        elif "未还款" in f and "未还清" not in f:
            ams = extract_amounts(f)
            if ams:
                info["outstanding_amount"] = ams[0][1]

        elif "借款未还清" in f:
            info["loan_outstanding"] = True

        elif "绑定" in f and "银行" in f:
            info["bound_bank"] = f.replace("绑定", "").strip()

    return info
