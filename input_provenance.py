"""字是谁敲的：分「物理键」还是「程序塞进来的键」。

为什么要有这一层：
  2-1 验完发现一件难堪的事——DSH 用 `SendInput` 往对话页里打字，
  闸门照样把它当成「月下打的字」，键鼠工具全放行。来源标对了，人却可能不是人。

做法：
  装两个低级钩子（`WH_KEYBOARD_LL` / `WH_MOUSE_LL`），只看**按下**事件，
  从 `KBDLLHOOKSTRUCT.flags` / `MSLLHOOKSTRUCT.flags` 里读系统给的
  `LLKHF_INJECTED` / `LLMHF_INJECTED` 标记。`SendInput` / `keybd_event` /
  自动化工具发出的键都带这个标记；真键盘、真鼠标不带。

  `turn.open(source="typed")` 时问一次 `classify()`，把结果记进这一轮的
  `meta["input"]`：`physical` / `injected` / `unknown` / `provenance_unavailable`。
  闸门只认 `physical`：`injected`（程序塞的）、`unknown`（拿不出证据）、
  `provenance_unavailable`（钩子没起来）一律拒。

边界（别把它当沙箱）：
  - 钩子没装上（权限、异常）时记 `provenance_unavailable`，不是 `unknown`——
    闸门对这两种都拒，但日志里必须分得清「有人冒充」和「探针挂了」。
  - 它认的是「最近一次输入事件」：物理键/真实鼠标按键 5 秒内按过，就算 physical。
    所以打完字停一会儿再点「发送」也算（那次点击是物理的）；
    **右键菜单粘贴、点「图」按钮选文件**这类纯鼠标操作，右键/左键按下也会记 physical，
    不会被当成「没有键盘证据」误伤。
  - 屏幕键盘、辅助输入、别的自动化工具发出来的键同样算 injected。
    这是这条规矩的代价，写在明处。
  - 别指望它能挡「改代码」的人：改一行 `classify` 就绕过去了。
    它挡的是「用 SendInput 冒充人打字」这一种。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time
from collections import deque

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_XBUTTONDOWN = 0x020B

LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01

# 最近多少秒内有过输入，才拿它当「这一轮是怎么来的」
WINDOW_SEC = 5.0
# 只留最近这些事件，够 classify 用
KEEP = 200

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wt.POINT),
        ("mouseData", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wt.DWORD]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p

_events: deque[tuple[float, str]] = deque(maxlen=KEEP)
_lock = threading.Lock()
_started = False
_start_error = ""
_thread: threading.Thread | None = None
_hk_kb = None
_hk_ms = None
_kb_proc = None
_ms_proc = None


# ---------------------------------------------------------------- 记录

def _note(kind: str) -> None:
    with _lock:
        _events.append((time.monotonic(), kind))


def _prov_log(text: str) -> None:
    """启动诊断：钩子到底装没装上，写 data/prov.log（不改程序行为）。"""
    try:
        from pathlib import Path
        p = Path(__file__).resolve().parent / "data" / "prov.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
    except Exception:                       # noqa: BLE001
        pass


def available() -> bool:
    """钩子真起来了没有。区分「探针没起来」和「最近没输入」——两者在日志里不能混。"""
    return bool(_started and _thread is not None and _thread.is_alive())


def classify(window: float = WINDOW_SEC) -> str:
    """最近一次输入是物理的还是注入的；太久没输入就 unknown。"""
    with _lock:
        if not _events:
            return "unknown"
        t, kind = _events[-1]
    if time.monotonic() - t > window:
        return "unknown"
    return kind


def last_age() -> float | None:
    with _lock:
        if not _events:
            return None
        t, _kind = _events[-1]
    return time.monotonic() - t


def counts(window: float = WINDOW_SEC) -> dict:
    """最近 window 秒里物理/注入各几次（给自检和日志看）。"""
    now = time.monotonic()
    out = {"physical": 0, "injected": 0}
    with _lock:
        for t, kind in _events:
            if now - t <= window:
                out[kind] = out.get(kind, 0) + 1
    return out


# ---------------------------------------------------------------- 钩子

def _kb_cb(n_code: int, w_param: int, l_param: int) -> int:
    if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
        try:
            kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            _note("injected" if kb.flags & LLKHF_INJECTED else "physical")
        except Exception:                       # noqa: BLE001
            pass
    return user32.CallNextHookEx(_hk_kb, n_code, w_param, l_param)


def _ms_cb(n_code: int, w_param: int, l_param: int) -> int:
    if n_code == 0 and w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN):
        try:
            ms = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            _note("injected" if ms.flags & LLMHF_INJECTED else "physical")
        except Exception:                       # noqa: BLE001
            pass
    return user32.CallNextHookEx(_hk_ms, n_code, w_param, l_param)


def _loop() -> None:
    global _hk_kb, _hk_ms, _start_error
    try:
        hmod = kernel32.GetModuleHandleW(None)
        _prov_log(f"loop 起：hmod={hmod!r}，开始装键盘/鼠标低层钩子")
        _hk_kb = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _kb_proc, hmod, 0)
        err_kb = ctypes.get_last_error()
        _hk_ms = user32.SetWindowsHookExW(WH_MOUSE_LL, _ms_proc, hmod, 0)
        err_ms = ctypes.get_last_error()
        _prov_log(f"钩子句柄：键盘={_hk_kb!r}(err={err_kb}) 鼠标={_hk_ms!r}(err={err_ms})")
        if not _hk_kb:
            _start_error = f"键盘钩子没装上（err={err_kb}）"
            _prov_log(_start_error)
            return
        if not _hk_ms:
            _prov_log(f"鼠标钩子没装上（err={err_ms}）；右键粘贴这类纯鼠标输入会拿不到证据")
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except Exception as exc:                    # noqa: BLE001
        _start_error = f"{type(exc).__name__}: {exc}"
        import traceback
        _prov_log("loop 异常：\n" + traceback.format_exc())


def start() -> bool:
    """装钩子。重复调用无害；返回 False 表示没装上（不影响程序跑）。"""
    global _started, _thread, _kb_proc, _ms_proc
    if _started:
        return _thread is not None and _thread.is_alive()
    _started = True
    _kb_proc = HOOKPROC(_kb_cb)
    _ms_proc = HOOKPROC(_ms_cb)
    _thread = threading.Thread(target=_loop, name="input-provenance", daemon=True)
    _thread.start()
    time.sleep(0.25)
    _prov_log(f"start() 回来：available={available()} hk_kb={_hk_kb!r} "
              f"err={_start_error or '-'} 线程活着={_thread.is_alive()}")
    return _hk_kb is not None


def stop() -> None:
    global _started, _hk_kb, _hk_ms
    if _hk_kb:
        user32.UnhookWindowsHookEx(_hk_kb)
    if _hk_ms:
        user32.UnhookWindowsHookEx(_hk_ms)
    _hk_kb = _hk_ms = None
    _started = False


def status() -> str:
    if _hk_kb is None:
        return _start_error or "没装"
    c = counts()
    return f"钩上了（近 {int(WINDOW_SEC)} 秒：物理 {c['physical']} / 注入 {c['injected']}；最近={classify()}）"
