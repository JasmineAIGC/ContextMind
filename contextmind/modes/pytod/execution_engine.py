"""
PyTOD 执行引擎（Execution Engine）

对动作解析器生成的程序语句进行安全解析和执行，返回结构化结果。
不使用 eval()；仅允许调用已显式注册的函数；参数类型限制为常量。
"""

from __future__ import annotations

import ast
import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


@dataclass
class ProgramStatement:
    """动作解析器生成的程序语句（解析后的结构化表示）。

    Attributes:
        function_name: 要调用的函数名称（如 ``query_account``）。
        kwargs:        关键字参数字典（仅允许常量值）。
        raw_text:      原始文本，用于调试。
        variable:      本语句结果绑定的变量名（如 ``x1``）；
                       裸调用（无变量绑定）时为空字符串。
    """

    function_name: str
    kwargs: Dict[str, Any]
    raw_text: str = ""
    variable: str = ""          # 绑定变量名（x1 / x2 / ...），裸调用为 ""

    def to_call_text(self) -> str:
        """重新生成可读的函数调用文本。"""
        args_str = ", ".join(
            f"{k}={repr(v)}" for k, v in self.kwargs.items()
        )
        return f"{self.function_name}({args_str})"


@dataclass
class ExecutionResult:
    """执行引擎的单条语句执行结果。"""

    success: bool
    statement: Optional[ProgramStatement] = None
    return_value: Any = None
    error: str = ""

    def to_context_text(self) -> str:
        """将执行结果格式化为可注入对话管理器 prompt 的上下文文本。"""
        import json as _json

        if not self.success:
            return f"[执行结果]\n执行失败: {self.error}"

        call_text = self.statement.to_call_text() if self.statement else "(调用信息不可用)"
        try:
            result_repr = _json.dumps(self.return_value, ensure_ascii=False)
        except (TypeError, ValueError):
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
    """槽位赋值语句（``x1.slot_name = 'value'``）。"""

    variable: str
    slot_name: str
    value: Any
    raw_text: str = ""


@dataclass
class HintStatement:
    """Hint 语句（``x2 Hint('request value: slot_name')``）。"""

    variable: str
    hint_text: str
    raw_text: str = ""


@dataclass
class SayStatement:
    """say 语句（``x3 say(x1, x2)``），组合多个变量生成面向用户的输出。

    arg_variables 中的每个元素可以是：
    - 变量名（如 ``x1``）：取变量整体值
    - 属性引用（如 ``x1.phone_number``）：取变量对应字典键的值
    - Hint 变量名（如 ``x2``）：取 Hint 文本
    - 字符串字面量（如 ``'literal text'``）：直接使用字面内容
    """

    variable: str
    arg_variables: List[str]
    raw_text: str = ""


@dataclass
class ConfirmStatement:
    """confirm 语句（``x2 confirm(x1)``）。

    对应官方 PyTOD 中事务型 API 的确认阶段：
    将 x1 的当前参数状态返回给对话管理器，让用户确认数据正确后再执行。
    result_variable 的值等于 target_variable 的当前已填充参数字典。
    """

    result_variable: str   # 绑定结果的变量（如 x2）
    target_variable: str   # 被确认的事务变量（如 x1）
    raw_text: str = ""


@dataclass
class PerformStatement:
    """perform 语句（``x3 perform(x1)``）。

    对应官方 PyTOD 中事务型 API 的执行阶段：
    以 x1 积累的参数重新调用注册函数，将结果绑定到 result_variable。
    """

    result_variable: str   # 绑定结果的变量（如 x3）
    target_variable: str   # 待执行的事务变量（如 x1）
    raw_text: str = ""


# PyTOD 单条语句的联合类型
AnyStatement = Union[
    ProgramStatement,
    SlotAssignment,
    HintStatement,
    SayStatement,
    ConfirmStatement,
    PerformStatement,
]


@dataclass
class ProgramBlock:
    """PyTOD 多行程序块，包含动作解析器生成的一组有序程序语句。"""

    statements: List[AnyStatement] = field(default_factory=list)
    raw_text: str = ""

    def to_program_text(self) -> str:
        """重新生成程序文本（每条语句一行）。"""
        return "\n".join(s.raw_text for s in self.statements)


@dataclass
class ProgramExecutionResult:
    """多行 PyTOD 程序的执行结果，包含变量值、Hint 消息和 say 输出。"""

    success: bool
    variable_values: Dict[str, Any] = field(default_factory=dict)
    hint_messages: List[str] = field(default_factory=list)
    say_output: str = ""
    errors: List[str] = field(default_factory=list)
    raw_program: str = ""

    def to_context_text(self) -> str:
        """将多语句执行结果格式化为可注入对话管理器 prompt 的上下文文本。"""
        import json as _json

        max_len = ExecutionEngine.MAX_RESULT_LENGTH
        lines = ["[程序执行结果]"]

        if not self.success and self.errors:
            lines.append("执行错误:")
            for err in self.errors:
                lines.append(f"  - {err}")
            return "\n".join(lines)

        api_vars = {
            k: v for k, v in self.variable_values.items()
            if not (self.say_output and v == self.say_output)
        }
        if api_vars:
            lines.append("API 调用结果:")
            for var, value in api_vars.items():
                try:
                    val_repr = _json.dumps(value, ensure_ascii=False)
                except (TypeError, ValueError):
                    val_repr = repr(value)
                if len(val_repr) > max_len:
                    val_repr = val_repr[:max_len] + "...(已截断)"
                lines.append(f"  {var} = {val_repr}")

        if self.hint_messages:
            lines.append("Hint 提示（需要向用户询问的信息）:")
            for hint in self.hint_messages:
                lines.append(f"  - {hint}")

        if self.say_output:
            lines.append(f"say 输出: {self.say_output}")

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 执行引擎
# --------------------------------------------------------------------------- #


class ExecutionEngine:
    """
    PyTOD 风格执行引擎

    支持解析和执行 PyTOD 标准格式的多行程序，包括：
    - API 调用（带变量绑定或裸调用）
    - 槽位赋值（单行及分号分隔的多槽位赋值）
    - Hint 语句
    - say 语句（支持变量、Hint 变量、属性引用 x1.field、字符串字面量）
    - confirm / perform 语句（事务型 API 的确认/执行阶段）
    """

    # 允许解析的 AST 常量节点类型
    _ALLOWED_CONST_TYPES = (str, int, float, bool, type(None))

    #: 执行结果转换为文本时的最大字符数（超出部分截断）
    MAX_RESULT_LENGTH: int = 2000

    # 用于解析 PyTOD 程序语句各行的正则
    _RE_VAR_CALL = re.compile(r"^(x\d+)\s+([A-Za-z_]\w*)\s*\(")
    _RE_SLOT_ASSIGN = re.compile(r"^(x\d+)\.([A-Za-z_]\w*)\s*=\s*(.+)$")
    _RE_HINT = re.compile(r"^(x\d+)\s+Hint\s*\((.+)\)\s*$")
    _RE_SAY = re.compile(r"^(?:(x\d+)\s+)?say\s*\((.*)(?:\))\s*$", re.DOTALL)
    # confirm(x1) 和 perform(x1)：接受变量引用而非常量值
    _RE_CONFIRM = re.compile(r"^(x\d+)\s+confirm\s*\(\s*(x\d+)\s*\)\s*$")
    _RE_PERFORM = re.compile(r"^(x\d+)\s+perform\s*\(\s*(x\d+)\s*\)\s*$")

    def __init__(self) -> None:
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
            sig_str = f"{name}{sig}"
            # Strip quotes around type annotations produced by 'from __future__ import annotations'
            # Target only annotation positions (after ':' or '->'), not string default values.
            sig_str = re.sub(r"(:\s*)'([^']+)'", r"\1\2", sig_str)   # param annotations
            sig_str = re.sub(r"(->\s*)'([^']+)'", r"\1\2", sig_str)  # return annotation
            return sig_str
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

        Args:
            program_text: 动作解析器生成的程序语句文本

        Returns:
            ExecutionResult 实例，包含执行状态和返回值
        """
        statement, parse_error = self.parse(program_text)
        if statement is None:
            return ExecutionResult(success=False, error=f"解析失败: {parse_error}")

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
            # 捕获已注册 API 函数抛出的应用层异常（如 requests.HTTPError、
            # db.OperationalError 等），无需依赖其具体类型。
            # 仅重新抛出不继承自 Exception 的真正系统异常
            # （如 KeyboardInterrupt、SystemExit）。
            return ExecutionResult(
                success=False,
                statement=statement,
                error=f"执行异常: {type(exc).__name__}: {exc}",
            )

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    def _eval_constant(self, node: ast.expr) -> Tuple[Any, str]:
        """从 AST 节点中安全提取常量值（支持 str/int/float/bool/None 及负数）。"""
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

    def parse_program(self, program_text: str) -> Tuple[Optional[ProgramBlock], str]:
        """将多行 PyTOD 程序文本解析为结构化的 ProgramBlock。

        支持分号分隔的多槽位赋值（官方 PyTOD 格式）：
        ``x1.location = 'San Jose'; x1.restaurant_name = 'Sino'``
        会被拆分为两条独立的 SlotAssignment 语句。

        注意：槽位赋值必须直接以 ``xN.slot_name = value`` 形式开头，
        不支持带结果变量前缀的 ``x5 x1.slot = value`` 格式。
        """
        raw_lines = [l.strip() for l in program_text.strip().splitlines()]
        # 1. 过滤注释和空行；2. 将分号分隔的同行多语句展开为独立行
        lines: List[str] = []
        for raw in raw_lines:
            if not raw or raw.startswith("#"):
                continue
            # 仅对"槽位赋值行"展开分号（避免破坏函数参数中可能出现的分号）
            # 槽位赋值特征：以 xN.slot = 开头，或以 xN xM.slot = 开头
            if re.search(r"x\d+\.[A-Za-z_]\w*\s*=", raw) and ";" in raw:
                for part in raw.split(";"):
                    part = part.strip()
                    if part:
                        lines.append(part)
            else:
                lines.append(raw)

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

        Args:
            program_text: 动作解析器生成的多行程序文本

        Returns:
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
        var_values: Dict[str, Any] = {}        # 变量名 → API 返回值
        hint_values: Dict[str, str] = {}       # 变量名 → 提示文本
        # 按变量追踪 kwargs，使槽位赋值可以累积
        var_kwargs: Dict[str, Dict[str, Any]] = {}
        var_func: Dict[str, str] = {}          # 变量名 → 函数名
        errors: List[str] = []
        hint_messages: List[str] = []
        say_output: str = ""
        _anon_counter: int = 0                 # 匿名调用计数器（无变量绑定时用）

        for stmt in block.statements:
            if isinstance(stmt, ProgramStatement):
                # NONE() 和 conversation_pause() 是动作解析器的哨兵值，直接跳过。
                # - NONE(): 本轮无需调用任何 API
                # - conversation_pause(): 暂停并等待用户输入（官方 PyTOD 事务型 API 中用于
                #   多轮槽位填充流程的暂停点；在我们的单轮 AP→EE→DM 模型中等价于 NONE）
                if stmt.function_name.upper() in ("NONE", "CONVERSATION_PAUSE"):
                    continue
                kwargs = dict(stmt.kwargs)
                # 若语句无变量绑定，生成唯一匿名 key，避免多次调用同一函数时覆盖。
                if stmt.variable:
                    var_key = stmt.variable
                else:
                    _anon_counter += 1
                    var_key = f"_anon{_anon_counter}"
                var_kwargs[var_key] = kwargs
                var_func[var_key] = stmt.function_name
                single_result = self._call_registered(stmt.function_name, kwargs)
                if single_result is None:
                    errors.append(
                        f"函数 '{stmt.function_name}' 未注册（变量 {var_key}）"
                    )
                elif isinstance(single_result, Exception):
                    errors.append(
                        f"变量 {var_key}: {type(single_result).__name__}: {single_result}"
                    )
                elif var_key:
                    var_values[var_key] = single_result

            elif isinstance(stmt, SlotAssignment):
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
                hint_values[stmt.variable] = stmt.hint_text
                hint_messages.append(stmt.hint_text)

            elif isinstance(stmt, ConfirmStatement):
                # confirm(x1)：将 x1 的已填充参数返回给 DM，让用户确认后再执行
                target = stmt.target_variable
                confirmed_params = var_kwargs.get(target, {})
                var_values[stmt.result_variable] = {
                    "confirm_target": target,
                    "params": confirmed_params,
                }

            elif isinstance(stmt, PerformStatement):
                # perform(x1)：以 x1 的已积累参数实际执行注册函数（事务型 API）
                target = stmt.target_variable
                if target not in var_func:
                    errors.append(f"perform 目标变量 {target} 未定义")
                else:
                    fn_name = var_func[target]
                    kwargs = var_kwargs.get(target, {})
                    exec_result = self._call_registered(fn_name, kwargs)
                    if exec_result is None:
                        errors.append(f"函数 '{fn_name}' 未注册（perform {target}）")
                    elif isinstance(exec_result, Exception):
                        errors.append(
                            f"perform {target}: {type(exec_result).__name__}: {exec_result}"
                        )
                    else:
                        # 更新原始变量和结果变量，使后续 say(xN.field) 可引用
                        var_values[target] = exec_result
                        var_values[stmt.result_variable] = exec_result

            elif isinstance(stmt, SayStatement):
                parts: List[str] = []
                for arg_var in stmt.arg_variables:
                    stripped = arg_var.strip()
                    # 字符串字面量：使用引号剥离而非 eval()，避免安全风险
                    if len(stripped) >= 2 and (
                        (stripped[0] == '"' and stripped[-1] == '"')
                        or (stripped[0] == "'" and stripped[-1] == "'")
                    ):
                        parts.append(stripped[1:-1])
                    # Hint 变量
                    elif stripped in hint_values:
                        parts.append(hint_values[stripped])
                    # 属性引用：x1.field_name（官方 PyTOD say(x1.phone_number) 格式）
                    elif "." in stripped and not stripped.startswith("."):
                        var_ref, _, attr = stripped.partition(".")
                        val = var_values.get(var_ref)
                        if isinstance(val, dict) and attr in val:
                            parts.append(str(val[attr]))
                        else:
                            parts.append(f"({stripped})")
                    # 普通变量引用
                    elif stripped in var_values:
                        val = var_values[stripped]
                        parts.append(str(val))
                    else:
                        parts.append(f"({stripped})")
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

        LLM 生成的程序可能包含函数签名中不存在的关键字参数；
        调用前先过滤掉未知参数，使演示 API 更健壮。

        返回:
            - 函数返回值（成功时）
            - Exception 实例（执行异常时）
            - None（函数未注册时）
        """
        func = self.registry.get(func_name)
        if func is None:
            return None
        try:
            # 过滤函数不接受的 kwargs，优雅处理 LLM 传入
            # 多余或意外参数的情况。
            sig = inspect.signature(func)
            accepts_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            if not accepts_var_keyword:
                kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return func(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return exc

    @staticmethod
    def _split_say_args(args_str: str) -> List[str]:
        """将 say() 括号内的参数字符串分割为参数列表，正确处理引号内的逗号。

        例如：``'张女士，6,600元', x1`` → ``["'张女士，6,600元'", "x1"]``
        """
        args: List[str] = []
        current: List[str] = []
        in_quote: Optional[str] = None
        for ch in args_str:
            if in_quote:
                current.append(ch)
                if ch == in_quote:
                    in_quote = None
            elif ch in ("'", '"'):
                in_quote = ch
                current.append(ch)
            elif ch == ",":
                token = "".join(current).strip()
                if token:
                    args.append(token)
                current = []
            else:
                current.append(ch)
        token = "".join(current).strip()
        if token:
            args.append(token)
        return args

    def _parse_one_line(self, line: str) -> Tuple[Optional[AnyStatement], str]:
        """解析单行 PyTOD 程序语句。

        按顺序匹配：
        1. 槽位赋值（x1.slot = 'value'）
        2. Hint 语句（x2 Hint('...')）
        3. say 语句（x3 say(...)）
        4. confirm 语句（x4 confirm(x1)）
        5. perform 语句（x5 perform(x1)）
        6. 变量绑定 API 调用（x6 func_name(...)）
        7. 裸 API 调用（func_name(...)）
        """
        # 兼容 Python 赋值语法：将 'x1 = func(...)' 规范化为 'x1 func(...)'
        line = re.sub(r'^(x\d+)\s*=\s*(?=[A-Za-z_])', r'\1 ', line)

        m = self._RE_SLOT_ASSIGN.match(line)
        if m:
            var, slot, raw_val = m.group(1), m.group(2), m.group(3).strip()
            try:
                value = ast.literal_eval(raw_val)
                if not isinstance(value, self._ALLOWED_CONST_TYPES):
                    return None, f"槽位值类型不支持: {type(value).__name__}"
            except (ValueError, SyntaxError) as exc:
                return None, f"槽位值解析失败: {exc}"
            return SlotAssignment(variable=var, slot_name=slot, value=value, raw_text=line), ""

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

        m = self._RE_SAY.match(line)
        if m:
            var = m.group(1) or ""
            arg_vars = self._split_say_args(m.group(2) or "")
            return SayStatement(variable=var, arg_variables=arg_vars, raw_text=line), ""

        # confirm(x1) 和 perform(x1) 必须在通用 _RE_VAR_CALL 之前匹配，
        # 因为它们的参数是变量引用而非常量，通用 parse() 会拒绝变量引用。
        m = self._RE_CONFIRM.match(line)
        if m:
            return ConfirmStatement(
                result_variable=m.group(1), target_variable=m.group(2), raw_text=line
            ), ""

        m = self._RE_PERFORM.match(line)
        if m:
            return PerformStatement(
                result_variable=m.group(1), target_variable=m.group(2), raw_text=line
            ), ""

        m = self._RE_VAR_CALL.match(line)
        if m:
            var_name = m.group(1)
            func_part = line[len(var_name):].strip()
            stmt, err = self.parse(func_part)
            if stmt is None:
                return None, err
            stmt.variable = var_name
            return stmt, ""

        stmt, err = self.parse(line)
        if stmt is not None:
            stmt.variable = ""
            return stmt, ""

        return None, err
