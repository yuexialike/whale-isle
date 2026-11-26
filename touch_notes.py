"""把「被戳 / 被摸 / 被甩 / 被拎起放下 / 摔晕」记成一本小账，等下一次真开口时一句带过。

它替谁挡什么：
  · 挡住「每碰一下就叫醒模型」——碰触只记账，绝不触发一轮模型；
  · 挡住「攒 50 条原始记录」——按种类合并，最多 5 条（世界上只有这 5 种碰触），
    只涨次数，不新增条目。过界也只是数字变大，不会把账本撑爆。

谁调它：
  · `body.py` 在戳、摸、甩出去、拎起放下、摔晕时 `record()`；
  · `hooks.Hooks.take()` 在模型那一轮开头把攒的账取走（取完清空），
    所以它只出现在真正要开口的那一轮，不会自己叫醒谁。
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

# 只有这五种：和 Coop 的 desktop-pet.touch 的 kind 对齐（戳/摸/甩/拎放/摔晕）。
KINDS = ("poke", "pet", "throw", "drop", "crash")

_WORDS = {
    "poke": "被戳了",
    "pet": "被摸了",
    "throw": "被甩出去",
    "drop": "被拎起放下",
    "crash": "摔晕",
}

# 每个 kind 的次数上限：只是为了别把数字涨成天文数字，正常一辈子到不了。
MAX_COUNT = 9999

_lock = threading.Lock()
_counts: dict[str, int] = {}


def record(kind: str, count: int = 1) -> None:
    """记一笔。不认识的 kind 直接忽略（插件/以后新加的碰触不往这里塞）。"""
    if kind not in KINDS:
        return
    n = max(0, min(MAX_COUNT, int(count or 0)))
    if n <= 0:
        return
    with _lock:
        _counts[kind] = min(MAX_COUNT, _counts.get(kind, 0) + n)
        if os.environ.get("JINGYU_TOUCH_LOG"):
            # 只给真机验收用：每个进程一个文件，重启自然从新文件开始（账本来就不跨重启）。
            try:
                p = Path(__file__).resolve().parent / "data" / f"touch-{os.getpid()}.log"
                p.parent.mkdir(parents=True, exist_ok=True)
                line = " ".join(f"{k}={_counts.get(k, 0)}" for k in KINDS)
                with p.open("a", encoding="utf-8") as fh:
                    fh.write(f"{time.strftime('%H:%M:%S')} {kind} {line}\n")
            except Exception:                    # noqa: BLE001
                pass


def summary() -> str:
    """攒着的账压成一句话；没有就回空串。"""
    with _lock:
        if not _counts:
            return ""
        parts = [f"{_WORDS[k]} {_counts[k]} 次" for k in KINDS if _counts.get(k)]
    return "刚才" + "、".join(parts)


def take() -> str:
    """取走并清空（像信箱）。模型那一轮开头由 hooks 调。"""
    with _lock:
        if not _counts:
            return ""
        parts = [f"{_WORDS[k]} {_counts[k]} 次" for k in KINDS if _counts.get(k)]
        _counts.clear()
    return "刚才" + "、".join(parts)


def counts() -> dict:
    """现在账本里各项几次（测试/诊断用）。"""
    with _lock:
        return dict(_counts)


def reset() -> None:
    """清空（测试用）。"""
    with _lock:
        _counts.clear()
