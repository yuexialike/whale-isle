"""版号只在这一个地方写。

11-04 19:55 之前 `VERSION` 写在 `settings_page.py` 里，打包脚本 `pack_beta.py` 自己又写了一个
`v1.0.0`，两边各说各的——「检查更新」要比版本，就得有一个都认的地方。所以挪到这儿。

以后发版只改这一行；`pack_beta.py` 从这儿读。
"""
from __future__ import annotations

VERSION = "v1.0.0"
# 11-04 20:18 月下给我们自己用的这一版起了名：「I love 鱼鱼」。
# 名字只放在 STAGE 里显示；VERSION 还是得是数字，检查更新要靠它比大小。
# 2026-11-21 16:55 他定了这一包的正式版号：「这个打包版的正式版号是 v1.0.0 正式版」，
# 所以 STAGE 从「I love 鱼鱼」改成「正式版」；I love 鱼鱼 这个名字留在记忆里，不当版号用。
STAGE = "正式版"


def as_tuple(v: str) -> tuple[int, ...]:
    """'v0.4.2' / '0.0001' / 'v0.0001-beta' 一律拆成数字元组比大小。

    点数不一样的用 0 补齐（0.4 < 0.4.0 之后的 0.4.1 才不会判错）。
    故意不用字符串比——'v0.10' < 'v0.9' 那种坑。
    """
    s = str(v or "").strip().lstrip("vV")
    head = ""
    for ch in s:
        if ch.isdigit() or ch == ".":
            head += ch
        else:
            break
    parts: list[int] = []
    for chunk in head.split("."):
        if chunk == "":
            continue
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    while parts and parts[-1] == 0 and len(parts) > 1:
        parts.pop()
    return tuple(parts)


def newer(remote: str, mine: str = VERSION) -> bool:
    """对面这份比我新吗。相等或更旧都是 False。"""
    a, b = as_tuple(remote), as_tuple(mine)
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return a > b
