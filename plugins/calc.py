"""自带扩展示例：算一下。

脑子心算常常差一点，问它一句更稳。只认数字和 + - * / ( ) %，别的字符一律不接——
不用 eval，自己走一遍语法树，省得哪天被人塞进一句 import os。
"""
from __future__ import annotations

import ast as _ast
import operator as _op

NAME = "算一下"
ABOUT = "加减乘除、括号、百分比。一个工具：calc。"

_BIN = {
    _ast.Add: _op.add,
    _ast.Sub: _op.sub,
    _ast.Mult: _op.mul,
    _ast.Div: _op.truediv,
    _ast.Mod: _op.mod,
    _ast.Pow: _op.pow,
    _ast.FloorDiv: _op.floordiv,
}
_UN = {_ast.UAdd: _op.pos, _ast.USub: _op.neg}


def _run(node):
    if isinstance(node, _ast.Expression):
        return _run(node.body)
    if isinstance(node, _ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("只算数字")
    if isinstance(node, _ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_run(node.left), _run(node.right))
    if isinstance(node, _ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_run(node.operand))
    raise ValueError("只认 + - * / ( ) %")


def _calc(args: dict) -> str:
    expr = str(args.get("expr", "")).strip().replace("×", "*").replace("÷", "/")
    if not expr:
        return "要算哪个式子？"
    if len(expr) > 200:
        return "式子太长了，拆开算。"
    try:
        tree = _ast.parse(expr, mode="eval")
        val = _run(tree)
    except ZeroDivisionError:
        return "除不了零。"
    except Exception as e:                           # noqa: BLE001
        return f"算不动：{e}"
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    elif isinstance(val, float):
        val = round(val, 10)
    return f"{expr} = {val}"


TOOLS = [
    (
        {
            "type": "function",
            "function": {
                "name": "calc",
                "description": "算一道算术题（+ - * / % 括号）。",
                "parameters": {
                    "type": "object",
                    "properties": {"expr": {"type": "string", "description": "式子，如 (3+5)*2"}},
                    "required": ["expr"],
                },
            },
        },
        _calc,
    ),
]
