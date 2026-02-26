"""
PyTOD 执行引擎（Execution Engine）

对动作解析器（Action Parser）生成的程序语句进行安全解析和执行，
返回结构化结果，供对话管理器（Dialogue Manager）生成自然语言回复。

PyTOD 算法流程中的第二步：

    动作解析器 → 程序语句 → [执行引擎] → 执行结果 → 对话管理器

执行引擎职责：
    1. 维护已注册的 API 函数列表（函数注册表）
    2. 解析多行 PyTOD 程序语句
    3. 安全调用对应的 Python 函数
    4. 返回结构化的执行结果

PyTOD 程序支持以下四种语句形式（与官方算法一致）：

    1. API 函数调用（带变量绑定）：
       x1 hotels_1_search_hotel(city='San Jose')

    2. 槽位赋值（补充或更新已声明的 API 调用参数）：
       x1.location = 'San Jose'

    3. Hint 语句（请求用户提供缺失的槽位信息）：
       x2 Hint('request value: check_in_date')

    4. say 语句（组合 Hint 输出，生成面向用户的提示）：
       x3 say(x1, x2)

安全保证：
    - 不使用 ``eval()``；使用 Python ``ast`` 模块和正则解析程序语句
    - 只允许调用已显式注册的函数
    - 参数类型限制为 str、int、float、bool、None（拒绝执行任意代码）

使用示例::

    engine = ExecutionEngine()

    # 注册 API 函数
    @engine.register
    def hotels_1_search_hotel(city=None, check_in_date=None):
        return [{"name": "Sino", "rating": 4.5}]

    # 执行多行 PyTOD 程序
    program = '''
    x1 hotels_1_search_hotel(city='San Jose')
    x2 Hint('request value: check_in_date')
    x3 say(x2)
    '''
    result = engine.execute_program(program)
    print(result.variable_values["x1"])   # [{"name": "Sino", "rating": 4.5}]
    print(result.say_output)              # "request value: check_in_date"
"""

from __future__ import annotations

import ast
import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class ProgramStatement:
    """
    动作解析器生成的程序语句（解析后的结构化表示）。

    对应 PyTOD 论文中的程序化动作表示，例如：
        ``restaurants_1_find(cuisine='火锅', location='望京')``

    属性:
        function_name: 函数名称（对应注册表中的函数）
        kwargs:        关键字参数字典
        raw_text:      原始程序语句文本
    """

    function_name: str
    kwargs: Dict[str, Any]
    raw_text: str = ""

    def to_call_text(self) -> str:
        """
        重新生成可读的函数调用文本。

        返回:
            格式化的调用字符串，例如：
            ``restaurants_1_find(cuisine='火锅', location='望京')``
        """
        args_str = ", ".join(
            f"{k}={repr(v)}" for k, v in self.kwargs.items()
        )
        return f"{self.function_name}({args_str})"


@dataclass
class ExecutionResult:
    """
    执行引擎的执行结果。

    属性:
        success:        是否执行成功
        statement:      解析后的程序语句（解析失败时为 None）
        return_value:   函数的返回值（任意类型，由注册函数决定）
        error:          失败时的错误描述（成功时为空字符串）
    """

    success: bool
    statement: Optional[ProgramStatement] = None
    return_value: Any = None
    error: str = ""

    def to_context_text(self) -> str:
        """
        将执行结果格式化为可注入对话管理器 prompt 的上下文文本。

        返回:
            格式化的结果说明，例如：

            [执行结果]
            函数调用: restaurants_1_find(cuisine='火锅')
            结果: [{"name": "海底捞", "rating": 4.8}]
        """
        if not self.success:
            return f"[执行结果]\n执行失败: {self.error}"

        call_text = self.statement.to_call_text() if self.statement else "(未知调用)"
        result_repr = repr(self.return_value)
        # 超长结果截断，避免 context 过大
        max_len = ExecutionEngine.MAX_RESULT_LENGTH
        if len(result_repr) > max_len:
            result_repr = result_repr[:max_len] + "...(已截断)"
        return f"[执行结果]\n函数调用: {call_text}\n结果: {result_repr}"


# --------------------------------------------------------------------------- #
# PyTOD 多行程序语句类型
# --------------------------------------------------------------------------- #


@dataclass
class SlotAssignment:
    """
    槽位赋值语句（``x1.slot_name = 'value'``）。

    为已声明的 API 调用变量补充或更新一个槽位值，对应 PyTOD 论文中的
    属性赋值程序行。

    例如：
        ``x1.location = 'San Jose'``

    属性:
        variable:  变量名（如 "x1"）
        slot_name: 槽位名称（如 "location"）
        value:     槽位值（仅支持常量）
        raw_text:  原始语句文本
    """

    variable: str
    slot_name: str
    value: Any
    raw_text: str = ""


@dataclass
class HintStatement:
    """
    Hint 语句（``x2 Hint('request value: slot_name')``）。

    请求用户提供缺失的槽位信息，对应 PyTOD 中的 ``Hint()`` 原语。
    通常与 ``say()`` 语句配合，将提示输出给用户。

    例如：
        ``x2 Hint('request value: check_in_date')``

    属性:
        variable:  变量名（如 "x2"）
        hint_text: Hint 内容（如 "request value: check_in_date"）
        raw_text:  原始语句文本
    """

    variable: str
    hint_text: str
    raw_text: str = ""


@dataclass
class SayStatement:
    """
    say 语句（``x3 say(x1, x2)``）。

    组合多个 Hint 或 API 结果变量，生成面向用户的输出，
    对应 PyTOD 中的 ``say()`` 原语。

    例如：
        ``x4 say(x2, x3)``

    属性:
        variable:      变量名（如 "x4"）
        arg_variables: 参与组合的变量名列表（如 ["x2", "x3"]）
        raw_text:      原始语句文本
    """

    variable: str
    arg_variables: List[str]
    raw_text: str = ""


# PyTOD 单条语句的联合类型
AnyStatement = Union[ProgramStatement, SlotAssignment, HintStatement, SayStatement]


@dataclass
class ProgramBlock:
    """
    PyTOD 多行程序块。

    包含动作解析器生成的一组有序程序语句，由执行引擎统一执行。

    例如::

        x1 hotels_1_search_hotel(city='San Jose')
        x2 Hint('request value: check_in_date')
        x3 say(x2)

    属性:
        statements: 有序语句列表（每条为 AnyStatement 之一）
        raw_text:   原始多行程序文本
    """

    statements: List[AnyStatement] = field(default_factory=list)
    raw_text: str = ""

    def to_program_text(self) -> str:
        """重新生成程序文本（每条语句一行）。"""
        return "\n".join(s.raw_text for s in self.statements)


@dataclass
class ProgramExecutionResult:
    """
    多行 PyTOD 程序的执行结果。

    属性:
        success:         是否全部执行成功（有错误时为 False）
        variable_values: 各变量名到 API 返回值的映射
        hint_messages:   所有 Hint 语句收集到的提示文本列表
        say_output:      say() 语句组合后面向用户的输出文本
        errors:          执行过程中的错误信息列表
        raw_program:     原始程序文本
    """

    success: bool
    variable_values: Dict[str, Any] = field(default_factory=dict)
    hint_messages: List[str] = field(default_factory=list)
    say_output: str = ""
    errors: List[str] = field(default_factory=list)
    raw_program: str = ""

    def to_context_text(self) -> str:
        """
        将多语句执行结果格式化为可注入对话管理器 prompt 的上下文文本。

        返回:
            格式化的结果说明，例如：

            [程序执行结果]
            API 调用结果:
              x1 = [{"name": "Sino", "rating": 4.5}]
            Hint 提示:
              - request value: check_in_date
            say 输出: request value: check_in_date
        """
        max_len = ExecutionEngine.MAX_RESULT_LENGTH
        lines = ["[程序执行结果]"]

        if not self.success and self.errors:
            lines.append("执行错误:")
            for err in self.errors:
                lines.append(f"  - {err}")
            return "\n".join(lines)

        # API 调用结果
        if self.variable_values:
            lines.append("API 调用结果:")
            for var, value in self.variable_values.items():
                val_repr = repr(value)
                if len(val_repr) > max_len:
                    val_repr = val_repr[:max_len] + "...(已截断)"
                lines.append(f"  {var} = {val_repr}")

        # Hint 提示
        if self.hint_messages:
            lines.append("Hint 提示:")
            for hint in self.hint_messages:
                lines.append(f"  - {hint}")

        # say 输出
        if self.say_output:
            lines.append(f"say 输出: {self.say_output}")

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 执行引擎
# --------------------------------------------------------------------------- #


class ExecutionEngine:
    """
    PyTOD 风格执行引擎

    支持解析和执行 PyTOD 标准格式的多行程序，以及向后兼容的单语句执行。

    PyTOD 程序语句格式（与官方算法一致）：

    1. API 函数调用（带变量绑定）::

           x1 hotels_1_search_hotel(city='San Jose')

    2. 槽位赋值（补充或更新 API 调用参数）::

           x1.check_in_date = '2024-03-01'

    3. Hint 语句（请求用户补充缺失信息）::

           x2 Hint('request value: check_in_date')

    4. say 语句（组合 Hint 输出给用户）::

           x3 say(x2)

    使用示例::

        engine = ExecutionEngine()

        @engine.register
        def hotels_1_search_hotel(city=None, check_in_date=None):
            return [{"name": "Sino", "rating": 4.5}]

        program = '''
        x1 hotels_1_search_hotel(city='San Jose')
        x2 Hint('request value: check_in_date')
        x3 say(x2)
        '''
        result = engine.execute_program(program)
        print(result.variable_values["x1"])  # [{"name": "Sino", "rating": 4.5}]
        print(result.say_output)             # "request value: check_in_date"

    属性:
        registry:           已注册函数字典，键为函数名，值为 callable
        max_result_length:  执行结果文本化时的最大字符数（超长部分截断）
    """

    # 允许解析的 AST 常量节点类型
    _ALLOWED_CONST_TYPES = (str, int, float, bool, type(None))

    #: 执行结果转换为文本时的最大字符数（超出部分截断）
    MAX_RESULT_LENGTH: int = 2000

    # ------------------------------------------------------------------ #
    # 正则：用于解析 PyTOD 程序语句各行
    # ------------------------------------------------------------------ #

    # x1 func_name(...) — 变量绑定的 API 调用
    _RE_VAR_CALL = re.compile(r"^(x\d+)\s+([A-Za-z_]\w*)\s*\(")
    # x1.slot_name = 'value'  — 槽位赋值
    _RE_SLOT_ASSIGN = re.compile(r"^(x\d+)\.([A-Za-z_]\w*)\s*=\s*(.+)$")
    # x2 Hint('...') — Hint 语句
    _RE_HINT = re.compile(r"^(x\d+)\s+Hint\s*\((.+)\)\s*$")
    # x3 say(x1, x2, ...) — say 语句
    _RE_SAY = re.compile(r"^(x\d+)\s+say\s*\(([^)]*)\)\s*$")

    def __init__(self) -> None:
        """初始化执行引擎（空函数注册表）。"""
        self.registry: Dict[str, Callable] = {}

    # ------------------------------------------------------------------ #
    # 注册接口
    # ------------------------------------------------------------------ #

    def register(self, func: Callable) -> Callable:
        """
        将函数注册到执行引擎。

        可用作装饰器或直接调用：

        ::

            # 装饰器用法
            @engine.register
            def restaurants_1_find(cuisine=None, location=None):
                ...

            # 直接调用
            engine.register(my_api_function)

        参数:
            func: 待注册的 Python callable

        返回:
            原函数（装饰器语义，不修改原函数）
        """
        self.registry[func.__name__] = func
        return func

    def register_as(self, name: str) -> Callable:
        """
        以指定名称将函数注册到执行引擎。

        适合将现有函数以 PyTOD 命名约定（如 ``service_1_intent``）注册：

        ::

            @engine.register_as("restaurants_1_find")
            def find_restaurants(cuisine=None, location=None):
                ...

        参数:
            name: 注册用函数名称（动作解析器输出中使用的名称）

        返回:
            装饰器函数
        """
        def decorator(func: Callable) -> Callable:
            self.registry[name] = func
            return func
        return decorator

    def list_functions(self) -> List[str]:
        """返回所有已注册函数的名称列表。"""
        return list(self.registry.keys())

    def get_function_signature(self, name: str) -> Optional[str]:
        """
        获取已注册函数的签名文本，用于生成 prompt。

        参数:
            name: 函数名称

        返回:
            函数签名字符串（如 ``restaurants_1_find(cuisine, location)``），
            函数不存在时返回 None
        """
        func = self.registry.get(name)
        if func is None:
            return None
        try:
            sig = inspect.signature(func)
            return f"{name}{sig}"
        except (ValueError, TypeError):
            return f"{name}(...)"

    def to_prompt_text(self) -> str:
        """
        将所有已注册函数的签名列表生成为适合注入 prompt 的文本块。

        返回:
            格式化的可用 API 函数说明，例如：

            ### 可用 API 函数
              - restaurants_1_find(cuisine=None, location=None, price_range=None)
              - restaurants_1_reserve(name, date_time, party_size, ...)
        """
        if not self.registry:
            return "### 可用 API 函数\n  (无已注册函数)"
        lines = ["### 可用 API 函数"]
        for name in sorted(self.registry):
            sig = self.get_function_signature(name) or f"{name}(...)"
            lines.append(f"  - {sig}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 解析与执行
    # ------------------------------------------------------------------ #

    def parse(self, program_text: str) -> Tuple[Optional[ProgramStatement], str]:
        """
        将程序语句文本解析为结构化的 ProgramStatement。

        使用 Python ``ast`` 模块解析，不执行任何代码。
        仅支持单个函数调用表达式，参数仅限于常量值。

        参数:
            program_text: 程序语句文本，如
                          ``"restaurants_1_find(cuisine='火锅', location='望京')"``

        返回:
            (ProgramStatement, error_message) 元组：
            - 解析成功：(ProgramStatement实例, "")
            - 解析失败：(None, 错误描述)
        """
        text = program_text.strip()
        if not text:
            return None, "程序语句为空"

        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError as exc:
            return None, f"语法错误: {exc}"

        if not isinstance(tree.body, ast.Call):
            return None, "程序语句必须是函数调用表达式（如 func(arg=value)）"

        call = tree.body

        # 提取函数名
        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            # 支持 module.func 形式（取属性名）
            func_name = call.func.attr
        else:
            return None, "无法解析函数名称"

        # 不支持位置参数
        if call.args:
            return None, "程序语句只支持关键字参数，不支持位置参数"

        # 提取关键字参数（仅允许常量）
        kwargs: Dict[str, Any] = {}
        for kw in call.keywords:
            if kw.arg is None:
                return None, "不支持 **kwargs 展开语法"
            value, err = self._eval_constant(kw.value)
            if err:
                return None, f"参数 '{kw.arg}' 的值不是常量: {err}"
            kwargs[kw.arg] = value

        return ProgramStatement(
            function_name=func_name,
            kwargs=kwargs,
            raw_text=text,
        ), ""

    def execute(self, program_text: str) -> ExecutionResult:
        """
        解析并执行程序语句，返回执行结果。

        执行流程：
            1. 解析程序语句
            2. 检查函数是否已注册
            3. 调用注册函数
            4. 返回执行结果

        参数:
            program_text: 动作解析器生成的程序语句文本

        返回:
            ExecutionResult 实例，包含执行状态和返回值
        """
        # Step 1: 解析
        statement, parse_error = self.parse(program_text)
        if statement is None:
            return ExecutionResult(success=False, error=f"解析失败: {parse_error}")

        # Step 2: 查找注册函数
        func = self.registry.get(statement.function_name)
        if func is None:
            registered = ", ".join(sorted(self.registry.keys())) or "(无)"
            return ExecutionResult(
                success=False,
                statement=statement,
                error=(
                    f"函数 '{statement.function_name}' 未注册。"
                    f"已注册函数: {registered}"
                ),
            )

        # Step 3: 执行
        try:
            return_value = func(**statement.kwargs)
            return ExecutionResult(
                success=True,
                statement=statement,
                return_value=return_value,
            )
        except TypeError as exc:
            return ExecutionResult(
                success=False,
                statement=statement,
                error=f"参数错误: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 — registered functions may raise any exception type
            # Catch-all for application-level exceptions raised by registered API functions
            # (e.g. requests.HTTPError, db.OperationalError, etc.) without depending on
            # their specific types here.  Re-raise only truly unexpected system exceptions
            # (KeyboardInterrupt, SystemExit) which do not inherit from Exception.
            return ExecutionResult(
                success=False,
                statement=statement,
                error=f"执行异常: {type(exc).__name__}: {exc}",
            )

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    def _eval_constant(self, node: ast.expr) -> Tuple[Any, str]:
        """
        从 AST 节点中安全提取常量值。

        支持的类型：str、int、float、bool、None、
        以及带负号前缀的数值（如 -1、-3.14）。

        参数:
            node: AST 表达式节点

        返回:
            (value, error_message) 元组
        """
        # Python 3.8+ Constant 节点
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, self._ALLOWED_CONST_TYPES):
                return None, f"不支持的常量类型 {type(node.value).__name__}"
            return node.value, ""

        # 负数：UnaryOp(-，数值)
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float))
        ):
            return -node.operand.value, ""

        return None, f"不支持的 AST 节点类型 {type(node).__name__}"

    # ------------------------------------------------------------------ #
    # PyTOD 多行程序解析与执行
    # ------------------------------------------------------------------ #

    def parse_program(self, program_text: str) -> Tuple[Optional[ProgramBlock], str]:
        """
        将多行 PyTOD 程序文本解析为结构化的 ProgramBlock。

        支持的语句格式（每行一条）：

        1. ``x1 func_name(key='value', ...)``  — 带变量绑定的 API 调用
        2. ``x1.slot_name = 'value'``           — 槽位赋值
        3. ``x2 Hint('hint text')``             — Hint 语句
        4. ``x3 say(x1, x2)``                   — say 语句

        参数:
            program_text: 动作解析器生成的多行程序文本

        返回:
            (ProgramBlock, error_message) 元组：
            - 解析成功：(ProgramBlock实例, "")
            - 解析失败：(None, 错误描述)
        """
        lines = [l.strip() for l in program_text.strip().splitlines()]
        lines = [l for l in lines if l and not l.startswith("#")]
        if not lines:
            return None, "程序文本为空"

        statements: List[AnyStatement] = []
        for line in lines:
            stmt, err = self._parse_one_line(line)
            if stmt is None:
                return None, f"无法解析语句 '{line}': {err}"
            statements.append(stmt)

        return ProgramBlock(statements=statements, raw_text=program_text.strip()), ""

    def execute_program(self, program_text: str) -> ProgramExecutionResult:
        """
        解析并执行完整的多行 PyTOD 程序，返回聚合结果。

        执行流程：
            1. 解析多行程序为 ProgramBlock
            2. 顺序执行各语句，维护变量环境
            3. API 调用结果绑定到对应变量
            4. 槽位赋值更新变量的参数并重新执行 API
            5. Hint 语句收集提示信息
            6. say 语句组合 Hint 输出

        参数:
            program_text: 动作解析器生成的多行程序文本

        返回:
            ProgramExecutionResult 实例，包含所有变量值和 say 输出
        """
        block, parse_error = self.parse_program(program_text)
        if block is None:
            return ProgramExecutionResult(
                success=False,
                errors=[f"解析失败: {parse_error}"],
                raw_program=program_text,
            )

        # 运行时环境
        var_values: Dict[str, Any] = {}        # variable → API return value
        hint_values: Dict[str, str] = {}       # variable → hint text
        # Track kwargs per variable so slot assignments can accumulate
        var_kwargs: Dict[str, Dict[str, Any]] = {}
        var_func: Dict[str, str] = {}          # variable → function name
        errors: List[str] = []
        hint_messages: List[str] = []
        say_output: str = ""

        for stmt in block.statements:
            if isinstance(stmt, ProgramStatement):
                # x1 api_func(key=val, ...)
                kwargs = dict(stmt.kwargs)
                var_kwargs[stmt._variable] = kwargs  # type: ignore[attr-defined]
                var_func[stmt._variable] = stmt.function_name  # type: ignore[attr-defined]
                single_result = self._call_registered(stmt.function_name, kwargs)
                if single_result is None:
                    errors.append(
                        f"函数 '{stmt.function_name}' 未注册（变量 {stmt._variable}）"  # type: ignore[attr-defined]
                    )
                elif isinstance(single_result, Exception):
                    errors.append(
                        f"变量 {stmt._variable}: {type(single_result).__name__}: {single_result}"  # type: ignore[attr-defined]
                    )
                else:
                    var_values[stmt._variable] = single_result  # type: ignore[attr-defined]

            elif isinstance(stmt, SlotAssignment):
                # x1.slot = value — update kwargs and re-execute
                if stmt.variable not in var_func:
                    errors.append(
                        f"槽位赋值 '{stmt.raw_text}' 引用了未声明的变量 {stmt.variable}"
                    )
                    continue
                var_kwargs.setdefault(stmt.variable, {})[stmt.slot_name] = stmt.value
                fn_name = var_func[stmt.variable]
                new_result = self._call_registered(fn_name, var_kwargs[stmt.variable])
                if new_result is None:
                    errors.append(f"函数 '{fn_name}' 未注册（变量 {stmt.variable}）")
                elif isinstance(new_result, Exception):
                    errors.append(f"变量 {stmt.variable}: {type(new_result).__name__}: {new_result}")
                else:
                    var_values[stmt.variable] = new_result

            elif isinstance(stmt, HintStatement):
                # x2 Hint('...') — collect hint
                hint_values[stmt.variable] = stmt.hint_text
                hint_messages.append(stmt.hint_text)

            elif isinstance(stmt, SayStatement):
                # x3 say(x1, x2) — compose output
                parts: List[str] = []
                for arg_var in stmt.arg_variables:
                    if arg_var in hint_values:
                        parts.append(hint_values[arg_var])
                    elif arg_var in var_values:
                        parts.append(repr(var_values[arg_var]))
                    else:
                        parts.append(f"({arg_var})")
                say_output = "; ".join(parts)
                var_values[stmt.variable] = say_output

        return ProgramExecutionResult(
            success=len(errors) == 0,
            variable_values=var_values,
            hint_messages=hint_messages,
            say_output=say_output,
            errors=errors,
            raw_program=program_text,
        )

    def _call_registered(self, func_name: str, kwargs: Dict[str, Any]) -> Any:
        """
        调用已注册函数，返回结果或异常。

        返回:
            - 函数返回值（成功时）
            - Exception 实例（执行异常时）
            - None（函数未注册时）
        """
        func = self.registry.get(func_name)
        if func is None:
            return None
        try:
            return func(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return exc

    def _parse_one_line(self, line: str) -> Tuple[Optional[AnyStatement], str]:
        """
        解析单行 PyTOD 程序语句。

        按以下顺序尝试：
          1. 槽位赋值（``x1.slot = value``）
          2. Hint 语句（``x2 Hint('text')``）
          3. say 语句（``x3 say(x1, x2)``）
          4. 带变量绑定的 API 调用（``x1 func(key=val)``）
          5. 裸函数调用（无变量前缀，向后兼容）

        参数:
            line: 单行程序语句文本（已去除首尾空白）

        返回:
            (statement, error_message) 元组
        """
        # 1. 槽位赋值: x1.slot_name = 'value'
        m = self._RE_SLOT_ASSIGN.match(line)
        if m:
            var, slot, raw_val = m.group(1), m.group(2), m.group(3).strip()
            # 解析值（ast literal）
            try:
                value = ast.literal_eval(raw_val)
                if not isinstance(value, self._ALLOWED_CONST_TYPES):
                    return None, f"槽位值类型不支持: {type(value).__name__}"
            except (ValueError, SyntaxError) as exc:
                return None, f"槽位值解析失败: {exc}"
            return SlotAssignment(variable=var, slot_name=slot, value=value, raw_text=line), ""

        # 2. Hint 语句: x2 Hint('...')
        m = self._RE_HINT.match(line)
        if m:
            var = m.group(1)
            raw_arg = m.group(2).strip()
            try:
                hint_text = ast.literal_eval(raw_arg)
                if not isinstance(hint_text, str):
                    return None, "Hint 参数必须是字符串"
            except (ValueError, SyntaxError) as exc:
                return None, f"Hint 参数解析失败: {exc}"
            return HintStatement(variable=var, hint_text=hint_text, raw_text=line), ""

        # 3. say 语句: x3 say(x1, x2)
        m = self._RE_SAY.match(line)
        if m:
            var = m.group(1)
            arg_vars = [v.strip() for v in m.group(2).split(",") if v.strip()]
            return SayStatement(variable=var, arg_variables=arg_vars, raw_text=line), ""

        # 4. 带变量绑定的 API 调用: x1 func(key=val, ...)
        m = self._RE_VAR_CALL.match(line)
        if m:
            var_name = m.group(1)
            # 去掉变量前缀后用 ast 解析函数调用部分
            func_part = line[len(var_name):].strip()
            stmt, err = self.parse(func_part)
            if stmt is None:
                return None, err
            # 附加变量名属性（用 object.__setattr__ 避免 dataclass 冲突）
            stmt._variable = var_name  # type: ignore[attr-defined]
            return stmt, ""

        # 5. 向后兼容：裸函数调用（无变量前缀）
        stmt, err = self.parse(line)
        if stmt is not None:
            stmt._variable = "_"  # type: ignore[attr-defined]
            return stmt, ""

        return None, err
