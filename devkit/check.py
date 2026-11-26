"""插件体检 —— 装进鲸屿之前先跑这个。

    py -3 devkit\\check.py plugins\\你的插件.py

只读文件、不执行它。全绿（退出码 0）才往 plugins/ 里放。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

BANNED_CALLS = {
    "eval", "exec", "compile", "__import__", "os.system", "os.popen",
    "subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_output",
    "shutil.rmtree", "pickle.loads", "builtins.__import__",
}
BANNED_MODULES = {"subprocess", "ctypes", "socket", "telnetlib", "ftplib"}
SETTING_KINDS = {"text", "int", "bool", "lines"}


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def check(path: Path) -> list[tuple[str, str]]:
    """返回 [(等级, 话)]，等级是 ok / warn / fail。"""
    out: list[tuple[str, str]] = []
    try:
        src = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        return [("fail", f"读不了：{e}")]

    lines = src.count("\n") + 1
    if lines > 500:
        out.append(("warn", f"{lines} 行，超过 500——一个文件塞太多了"))

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [("fail", f"语法不对：第 {e.lineno} 行 {e.msg}")]

    names: dict[str, ast.AST] = {}
    imports: list[str] = []
    tool_names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name in BANNED_CALLS:
                out.append(("fail", f"不许调 {name}（第 {getattr(node, 'lineno', '?')} 行）"))
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])

    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    names[t.id] = node.value

    for mod in sorted(set(imports)):
        base = mod.split(".")[0]
        if base in BANNED_MODULES:
            out.append(("fail", f"不许 import {base}"))
        elif base not in sys.stdlib_module_names and base not in ("__future__",):
            out.append(("warn", f"import 了非标准库 {base}——要么写进文档，要么去掉"))

    if "TOOLS" not in names and "setup" not in names:
        out.append(("fail", "既没有 TOOLS 也没有 setup()——这插件什么也不干"))
    if "NAME" not in names:
        out.append(("warn", "没写 NAME，列表里只能显示文件名"))
    if "ABOUT" not in names:
        out.append(("warn", "没写 ABOUT，别人不知道它是干什么的"))

    node = names.get("TOOLS")
    if isinstance(node, ast.List):
        for elt in node.elts:
            if not (isinstance(elt, ast.Tuple) and len(elt.elts) == 2):
                out.append(("fail", "TOOLS 的每一条都得是 (schema, 函数)"))
                continue
            try:
                schema = ast.literal_eval(elt.elts[0])
                nm = schema["function"]["name"]
                schema["function"]["description"]
                schema.get("parameters", {})
            except Exception:
                out.append(("fail", "有一条 schema 读不出来（得是字面量字典）"))
                continue
            if nm in tool_names:
                out.append(("fail", f"工具名重复：{nm}"))
            tool_names.append(nm)
            if not isinstance(elt.elts[1], ast.Name):
                out.append(("warn", f"{nm}：第二个位置该直接写函数名"))
        if not node.elts:
            out.append(("warn", "TOOLS 是空的"))

    node = names.get("SETTINGS")
    if isinstance(node, ast.List):
        try:
            for row in ast.literal_eval(node):
                if row.get("kind") not in SETTING_KINDS:
                    out.append(("fail", f"设置项 {row.get('key')} 的 kind 只能是 {'/'.join(sorted(SETTING_KINDS))}"))
                if not row.get("key") or not row.get("label"):
                    out.append(("fail", "设置项少 key 或 label"))
        except Exception:
            out.append(("fail", "SETTINGS 得是字面量列表"))

    if not out:
        out.append(("ok", f"干净：{lines} 行，{len(tool_names)} 个工具" + (f"（{', '.join(tool_names)}）" if tool_names else "")))
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("用法：py -3 devkit\\check.py plugins\\你的插件.py")
        return 2
    bad = 0
    for raw in argv:
        path = Path(raw)
        print(f"\n== {path} ==")
        for level, msg in check(path):
            print(f"  [{level}] {msg}")
            if level == "fail":
                bad += 1
    print()
    print("全绿，可以装。" if bad == 0 else f"有 {bad} 处硬伤，先改。")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
