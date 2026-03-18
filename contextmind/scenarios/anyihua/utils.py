"""
安逸花外呼促活场景 · 数据解析工具

提供中文数字转换、用户信息字段解析，以及供 engine.py 和 detectors.py
共享使用的质量标签检测常量三项核心功能。

数据结构说明（用户信息字段）：
    用户信息 字段以 "#" 分隔，字段数量不固定，
    部分会话首字段为系统状态描述，导致客户姓名字段位置不固定，
    必须按内容关键词识别字段语义，不能依赖位置索引。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


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
    从文本中提取所有中文金额。

    支持多种后缀：
    - "元"/"块钱"（明确货币单位）
    - "左右"（约数表达，如"四万五千一百左右"）
    - 额度上下文词（"的额度"/"元的额度"/"元左右"等）

    仅返回整数值 > 500 的金额，过滤日常小额数字（如"三元"）。

    参数:
        text: 包含中文金额的字符串

    返回:
        [(中文文本, 整数值), ...] 列表，按出现顺序排列，去重

    示例::

        >>> extract_amounts('您的可提现额度为两万三千九百八十八元')
        [('两万三千九百八十八', 23988)]
        >>> extract_amounts('借款利率是百分之二十四')
        []  # 24 < 500
        >>> extract_amounts('额度呢是四万五千一百左右')
        [('四万五千一百', 45100)]
    """
    _CN_AMOUNT = r"[零一二三四五六七八九十百千万亿两]+"
    # 匹配：明确货币单位（元/块钱）或约数表达（左右）
    pattern = rf"({_CN_AMOUNT})(?:元|块钱|左右)"
    seen: set = set()
    results: List[Tuple[str, int]] = []
    for m in re.findall(pattern, text):
        val = cn2int(m)
        if val > 500 and m not in seen:
            seen.add(m)
            results.append((m, val))
    return results


# --------------------------------------------------------------------------- #
# 用户信息解析
# --------------------------------------------------------------------------- #


def parse_user_info(user_info_str: str) -> Dict[str, Any]:
    """
    将 用户信息 字段（"#" 分隔）解析为结构化字典。

    字段数量不固定，字段位置不固定：
    - 通常首字段为通话时间（"现在是上午十一点…"）
    - 部分会话首字段为系统状态描述，通话时间和客户姓名字段位置后移
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
        - registration_date (str): 注册时间（中文格式，如 "二零一八年九月二十日"）
        - authorized_days (int): 已授信天数
        - initial_credit (int): 初始授信额度（元）
        - authorized_credit (int): 当前授信额度（含提额后，元）
        - cash_ratio_pct (int): 取现比例（%，通常为 100）
        - last_credit_increase_date (str): 末次提额时间（中文格式）
        - days_since_last_credit_increase (int): 距离上次提额天数
        - last_credit_increase_amount (int): 末次提额金额（元）
        - billing_day (int):    账单日（每月几号，0 表示未知）
        - repayment_date (str): 最近还款日期（中文格式）
        - total_withdrawals (int): 累计提现笔数
        - coupon_count (int):   优惠券数量
        - last_login_date (str): 最近登录时间（中文格式）
        - days_since_last_login (int): 距离上次登录天数
        - monthly_logins (int): 近 30 天登录次数
        - call_count (int):     历史电话接通次数
        - days_since_last_call (int): 距离上次接通天数
        - days_since_last_loan (int): 距离上次借款天数
        - loan_cleared_date (str): 借款还清日期（中文格式，无则为空）
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
        # 新增字段
        "registration_date": "",
        "authorized_days": 0,
        "initial_credit": 0,
        "authorized_credit": 0,
        "cash_ratio_pct": 100,
        "last_credit_increase_date": "",
        "days_since_last_credit_increase": 0,
        "last_credit_increase_amount": 0,
        "billing_day": 0,
        "repayment_date": "",
        "total_withdrawals": 0,
        "coupon_count": 0,
        "last_login_date": "",
        "days_since_last_login": 0,
        "monthly_logins": 0,
        "call_count": 0,
        "days_since_last_call": 0,
        "days_since_last_loan": 0,
        "loan_cleared_date": "",
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

        elif "注册时间是" in f:
            info["registration_date"] = f.replace("注册时间是", "").strip()

        elif "最近登录时间是" in f:
            info["last_login_date"] = f.replace("最近登录时间是", "").strip()

        elif "距离上次登录" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)天", f)
            if m:
                info["days_since_last_login"] = cn2int(m.group(1))

        elif "近" in f and "天登录" in f:
            m = re.search(r"([零一二三四五六七八九十百千两\d]+)次", f)
            if m:
                raw = m.group(1)
                try:
                    info["monthly_logins"] = int(raw)
                except ValueError:
                    info["monthly_logins"] = cn2int(raw)

        elif "电话接通过" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)次", f)
            if m:
                info["call_count"] = cn2int(m.group(1))

        elif "距离上次接通" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)天", f)
            if m:
                info["days_since_last_call"] = cn2int(m.group(1))

        elif "已授信" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)天", f)
            if m:
                info["authorized_days"] = cn2int(m.group(1))

        elif "初始额度为" in f:
            m = re.search(r"([零一二三四五六七八九十百千万两]+)元", f)
            if m:
                info["initial_credit"] = cn2int(m.group(1))

        elif "授信额度为" in f:
            m = re.search(r"([零一二三四五六七八九十百千万两]+)元", f)
            if m:
                info["authorized_credit"] = cn2int(m.group(1))

        elif "取现比例是百分之" in f:
            m = re.search(r"百分之([零一二三四五六七八九十百]+)", f)
            if m:
                info["cash_ratio_pct"] = cn2int(m.group(1))

        elif "提额时间是" in f:
            info["last_credit_increase_date"] = f.replace("提额时间是", "").strip()

        elif "距离上次提额" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)天", f)
            if m:
                info["days_since_last_credit_increase"] = cn2int(m.group(1))

        elif "末次提额" in f:
            m = re.search(r"末次提额([零一二三四五六七八九十百千万两]+)元", f)
            if m:
                info["last_credit_increase_amount"] = cn2int(m.group(1))

        elif "账单日是每月" in f:
            m = re.search(r"每月([零一二三四五六七八九十]+)号", f)
            if m:
                info["billing_day"] = cn2int(m.group(1))

        elif "还款日是" in f:
            info["repayment_date"] = f.replace("还款日是", "").strip()

        elif "累计提现" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)笔", f)
            if m:
                info["total_withdrawals"] = cn2int(m.group(1))

        elif "优惠券有" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)张", f)
            if m:
                info["coupon_count"] = cn2int(m.group(1))

        elif "距离上次借款" in f:
            m = re.search(r"([零一二三四五六七八九十百千两]+)天", f)
            if m:
                info["days_since_last_loan"] = cn2int(m.group(1))

        elif "借款还清日期是" in f:
            info["loan_cleared_date"] = f.replace("借款还清日期是", "").strip()

    return info


# --------------------------------------------------------------------------- #
# 质量标签检测共享常量
# （由 engine.py 的标签预测 API 和 detectors.py 的检测函数共同使用）
# --------------------------------------------------------------------------- #

#: 对话历史角色前缀（供 engine.py 和 detectors.py 共用）
AGENT_PREFIX: str = "坐席："
USER_PREFIX: str = "用户："

#: 告别话术关键词（命中 2 个以上则判定为告别语）
FAREWELL_KEYWORDS: List[str] = [
    "不打扰您了",
    "祝您生活愉快",
    "再见",
    "感谢您的接听",
    "感谢接听",
    "祝您一切顺利",
    "祝您工作顺利",
]

#: 委婉告别词（单个即可触发告别判断，与 FAREWELL_KEYWORDS 任一结合使用）
FAREWELL_SOFT_PATTERNS: List[str] = [
    "先不打扰",
    "不打扰了",
    "打扰到您了",
    "先挂了",
    "就先这样",
]

#: 用户诉求关键词（出现在最近历史轮次中则视为有未解决问题）
USER_CONCERN_WORDS: List[str] = [
    "为什么", "怎么", "没有", "借不出", "借不了", "不对", "投诉",
    "能不能", "可不可以", "怎么办", "解冻", "申请", "问一下",
    "还想问", "什么意思", "干啥", "不行", "显示", "反映",
    "搞清楚", "说清楚", "有问题", "出问题", "怎么回事",
    # 补充：用户表达疑惑/追问/质疑位置或身份的诉求词
    "哪里", "谁",
]

#: 答非所问弱信号规则：用户疑问词 → 坐席回复中出现则为离题初步信号
#:
#: 设计原则（通用外呼质检）：
#:   · 值中只保留通用性强的信号词，不硬编码特定产品话术或测试数据中的具体语句
#:   · 最显著的离题场景：用户有明确问题，坐席却执行告别 → 直接使用通用告别词
#:   · 域内常见离题场景：用户追问原因，坐席忽略原因直接催促操作 → 使用通用操作推介词
#:   · 结构性离题检测（用户询问金额但坐席介绍品牌/反问等）在 engine.py 中通过
#:     _AGENT_INTRO_RE / _AGENT_ECHO_RE 模式进行，以实现更精准的信号生成
#:   · 语义层的细粒度判断（如坐席回复是否切题）由 LLM 负责，规则只提供初步提示
OFFTOPIC_SIGNALS: Dict[str, List[str]] = {
    # 用户询问具体金额/数量，坐席直接告别而不解释 → 离题弱信号
    "多少": ["再见", "不打扰", "感谢接听", "感谢您的接听", "祝您生活愉快"],
    # 用户追问原因，坐席忽视原因直接催促操作 → 离题弱信号
    "为什么": ["再见", "不打扰", "感谢接听", "立即借款", "去借款", "按需借款"],
    # 用户询问可行性，坐席不正面回应直接告别 → 离题弱信号
    "能不能": ["再见", "不打扰", "感谢接听", "感谢您的接听"],
    "可不可以": ["再见", "不打扰", "感谢接听"],
    # 用户追问操作方法，坐席直接告别 → 离题弱信号
    "怎么": ["再见", "不打扰", "感谢接听"],
    # 用户对账户显示数据有疑问，坐席直接告别 → 离题弱信号
    "显示": ["再见", "不打扰", "感谢接听"],
    # 用户追问含义或缘由，坐席直接告别 → 离题弱信号
    "什么意思": ["再见", "不打扰", "感谢接听"],
    "怎么回事": ["再见", "不打扰", "感谢接听"],
}
