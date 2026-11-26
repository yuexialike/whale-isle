"""对外发送的草稿-确认：一轮只出草稿，人下一句确认了才真发。

为什么要有：`qq_send` 以前打一句就发出去。发出去收不回来，所以 T1/T3 的收件人
（名单内的群/私聊、公告/群发）这一轮只建草稿，等**人**在输入框里发一句
「确认 d-xxxx」才发。确认只从人说话的那条路进来（`chat.py`/`page.py` 调
`llm.talk` 之前），模型自己发的字到不了这里。

草稿只在内存里，最多 3 条，10 分钟过期；进程重启就没了（宁可重来，不让旧草稿被误确认）。
"""
from __future__ import annotations

import re
import threading
import time
import uuid

DRAFT_TTL = 600.0          # 10 分钟
MAX_DRAFTS = 3

_confirm_re = re.compile(r"^\s*确认\s+(d-[0-9a-f]{4})\s*[。.!！]?\s*$", re.IGNORECASE)

_lock = threading.Lock()
_drafts: dict[str, dict] = {}
_sender = None             # qq 插件接上：send_draft(draft) -> 回执字符串


def set_sender(fn) -> None:
    """qq 插件装好后调：真正发草稿的函数。"""
    global _sender
    _sender = fn


def _prune(now: float | None = None) -> None:
    now = now if now is not None else time.time()
    for did, d in list(_drafts.items()):
        if d.get("expires", 0) <= now:
            _drafts.pop(did, None)


def create(*, to: str, kind: str, ident: str, text: str,
           images: list[str], tier: str) -> dict:
    """建一张草稿；超过 3 张就把最旧的挤掉。"""
    with _lock:
        _prune()
        while len(_drafts) >= MAX_DRAFTS:
            oldest = next(iter(_drafts))
            _drafts.pop(oldest, None)
        now = time.time()
        did = "d-" + uuid.uuid4().hex[:4]
        d = {"id": did, "to": to, "kind": kind, "ident": ident, "text": text,
             "images": list(images or []), "tier": tier,
             "created": now, "expires": now + DRAFT_TTL, "status": "pending"}
        _drafts[did] = d
        return dict(d)


def pending() -> list[dict]:
    with _lock:
        _prune()
        return [dict(d) for d in _drafts.values() if d.get("status") == "pending"]


def get(did: str) -> dict | None:
    with _lock:
        _prune()
        d = _drafts.get(did)
        return dict(d) if d else None


def confirm_if_any(text: str, source: str) -> str | None:
    """人说了「确认 d-xxxx」才发。返回要回给用户的话；不是确认句就回 None。

    只有 human 来源算；模型/网页/插件传来的字一律不认（这条就是防冒充）。
    """
    if source not in ("typed", "voice"):
        return None
    m = _confirm_re.match(str(text or ""))
    if not m:
        return None
    did = m.group(1).lower()
    with _lock:
        d = _drafts.get(did)          # 先拿原样，别先 prune：过期/非 pending 的话术要分开
        if d is None:
            return "没有这张草稿（可能已经发过、过期，或者 id 不对）。"
        if d.get("status") != "pending":
            return "这张草稿不是待确认状态，不发。"
        if d.get("expires", 0) <= time.time():
            _drafts.pop(did, None)
            return "草稿过期了（超过 10 分钟），要发请重新起草。"
        if _sender is None:
            return "发送通道没接上，发不了。"
        d["status"] = "sending"
    try:
        msg = _sender(d)
    except Exception as e:                    # noqa: BLE001
        with _lock:
            if did in _drafts:
                _drafts[did]["status"] = "pending"
        return f"发送失败：{type(e).__name__} {e}"
    with _lock:
        _drafts.pop(did, None)
    return msg
