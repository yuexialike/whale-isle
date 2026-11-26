"""窗口：有哪些窗、哪个在前台、把某个窗拎到前台。

为什么要有这个：截图只知道「前台是谁」，可要真替人办事，缺的是反过来的两步——
**先看看桌上有哪些窗**，再**把要动的那一个拎到前面来**。COOP 那边有
`pet_cua_windows` / `pet_cua_focus`，新家没有，点起来就总是点在别人身上。

句柄写成人能念的样子：十六进制的短 id（`1a2b3c`），跟 Coop 一样。
`focus()` 两种都收：短 id，或者标题里的一段字。

不打开的窗不列；最小化的列出来并标上「最小化」——那种得先还原。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

SW_RESTORE = 9

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value or ""


def _rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return int(r.left), int(r.top), int(r.right), int(r.bottom)


def _short(hwnd: int) -> str:
    return f"{int(hwnd) & 0xFFFFFF:06x}"


def foreground() -> int:
    return int(user32.GetForegroundWindow() or 0)


def list_windows() -> list[dict]:
    """桌面上看得见的窗。前台那个排第一个。"""
    fg = foreground()
    out: list[dict] = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _title(hwnd)
        if not title:                 # 没有标题的多半是壳子/工具条，列出来只会添乱
            return True
        l, t, r, b = _rect(hwnd)
        out.append({
            "hwnd": int(hwnd),
            "id": _short(hwnd),
            "title": title,
            "rect": (l, t, r - l, b - t),
            "minimized": bool(user32.IsIconic(hwnd)),
            "foreground": int(hwnd) == fg,
        })
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    out.sort(key=lambda w: (not w["foreground"], w["minimized"], w["title"].lower()))
    return out


def describe(windows: list[dict] | None = None) -> str:
    ws = windows if windows is not None else list_windows()
    if not ws:
        return "桌上一个看得见的窗都没有（这不正常，先看一眼屏幕）"
    lines = [f"可见窗口 {len(ws)} 个（前台那个在第一行；坐标/大小都是屏幕物理像素）："]
    for w in ws:
        marks = []
        if w["foreground"]:
            marks.append("前台")
        if w["minimized"]:
            marks.append("最小化")
        tag = f"[{'、'.join(marks)}] " if marks else ""
        x, y, wd, ht = w["rect"]
        lines.append(f"- {w['id']} {tag}「{w['title']}」({x}, {y}) {wd}×{ht}")
    return "\n".join(lines)


def find(which: str) -> int:
    """按短 id 或标题里的一段字找窗。找不到抛 LookupError。"""
    key = str(which or "").strip()
    if not key:
        raise LookupError("没说要切哪个窗")
    ws = list_windows()
    low = key.lower()
    for w in ws:                          # 先当短 id 找
        if w["id"].lower() == low or f"{w['hwnd']}" == key:
            return w["hwnd"]
    for w in ws:                          # 再当标题里的一段字找（前台优先，因为已经排好序）
        if low in w["title"].lower():
            return w["hwnd"]
    raise LookupError(f"没找到叫「{key}」的窗。先列一下桌面有哪些窗再说。")


def focus(which: str) -> str:
    """把窗拎到前台；最小化的先还原。"""
    hwnd = find(which)
    title = _title(hwnd)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return f"切到「{title}」（{_short(hwnd)}）"


def self_check() -> str:
    """不动任何窗：只数一数，前台是谁。开机自检用。"""
    ws = list_windows()
    fg = foreground()
    name = _title(fg) or "（没有标题）"
    return f"窗: {len(ws)} 个可见 · 前台「{name}」"
