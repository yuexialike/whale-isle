"""4-5 单实例：Windows 命名互斥量，第二个实例自己退出，不扫命令行、不 taskkill。"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path

import memory

_ERROR_ALREADY_EXISTS = 183
_handle = None


def name(workspace: str | Path | None = None) -> str:
    ws = Path(workspace) if workspace else memory.workspace()
    h = hashlib.sha1(str(ws).lower().encode("utf-8")).hexdigest()[:12]
    return f"Local\\WhaleIsle-{h}"


def acquire(workspace: str | Path | None = None) -> bool:
    """拿到返回 True；已经有一个在跑返回 False（不抢、不杀）。"""
    global _handle
    if _handle:
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    h = k32.CreateMutexW(None, True, name(workspace))
    if not h:
        return False
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        k32.CloseHandle(ctypes.c_void_p(h))
        return False
    _handle = h
    return True


def release() -> None:
    global _handle
    if _handle:
        ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(_handle))
        _handle = None
