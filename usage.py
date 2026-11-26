"""工具使用小账本：谁被调了多少次、最近一次什么时候、出没出错。

只给「扩展」页看，**不进日志、不进记忆**。文件是 data 目录下的 `usage.json`。

形状：
    {"since": "2026-11-01",
     "tools": {"qq_send": {"n": 34, "ok": 33, "fail": 1,
                           "day": "2026-11-01", "today": 12,
                           "last": "2026-11-01 21:37", "err": "最近一条错误"}},
     "days": {"2026-11-01": 42}}

为什么要它（月下 2026-11-01 21:39 说的）：插件要能单独成一页，
那第一件得看得见的事就是「它交给我的工具，今天用了没有、用了几次」。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

_LOCK = threading.Lock()
MAX_ERR = 200


def path() -> Path:
    try:
        import memory

        d = Path(memory.data_dir())
    except Exception:                                # noqa: BLE001
        d = Path(__file__).resolve().parent / "data"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d / "usage.json"


def _blank() -> dict:
    return {"since": datetime.now().strftime("%Y-%m-%d"), "tools": {}, "days": {}}


def _load() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("tools", {})
            data.setdefault("days", {})
            data.setdefault("since", datetime.now().strftime("%Y-%m-%d"))
            return data
    except Exception:                                # noqa: BLE001
        pass
    return _blank()


def _save(data: dict) -> None:
    try:
        p = path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except Exception:                                # noqa: BLE001
        pass


def note(name: str, ok: bool = True, error: str = "") -> None:
    """记一笔。名字空着就不记。写盘坏了也不吵人——这账本不该影响干活。"""
    if not name:
        return
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    with _LOCK:
        data = _load()
        row = data["tools"].setdefault(name, {})
        row["n"] = int(row.get("n", 0)) + 1
        if ok:
            row["ok"] = int(row.get("ok", 0)) + 1
        else:
            row["fail"] = int(row.get("fail", 0)) + 1
            row["err"] = (error or "")[:MAX_ERR]
        if row.get("day") != day:                     # 换天了，今天的数从 0 起
            row["day"] = day
            row["today"] = 0
        row["today"] = int(row.get("today", 0)) + 1
        row["last"] = now.strftime("%Y-%m-%d %H:%M")
        days = data.setdefault("days", {})
        days[day] = int(days.get(day, 0)) + 1
        for k in sorted(days)[:-90]:                  # 只留最近 90 天
            days.pop(k, None)
        _save(data)


def read() -> dict:
    with _LOCK:
        return _load()


def newest(names=None) -> str:
    """这组工具里最近一次被调用是什么时候（原样的 'YYYY-MM-DD HH:MM'）。"""
    rows = read().get("tools", {})
    picked = rows.values() if names is None else (rows.get(n) or {} for n in names)
    stamps = [str(r.get("last", "")) for r in picked if r]
    return max(stamps) if stamps else ""


def stats(names=None) -> dict:
    """合计：总次数 / 今天几次 / 失败几次 / 最近一次 / 那条错误。"""
    data = read()
    rows = data.get("tools", {})
    day = datetime.now().strftime("%Y-%m-%d")
    picked = list(rows.values()) if names is None else [rows.get(n) or {} for n in names]
    out = {"total": 0, "today": 0, "fail": 0, "last": "", "err": ""}
    for row in picked:
        if not row:
            continue
        out["total"] += int(row.get("n", 0))
        out["fail"] += int(row.get("fail", 0))
        out["today"] += int(row.get("today", 0)) if row.get("day") == day else 0
        if str(row.get("last", "")) > out["last"]:
            out["last"] = str(row.get("last", ""))
        if row.get("err"):
            out["err"] = str(row["err"])
    return out


def describe(names=None) -> str:
    """一句话版本，给日志和自检用。"""
    s = stats(names)
    if not s["total"]:
        return "还没被调过"
    tail = f"，最近 {s['last'][11:]}" if s["last"] else ""
    bad = f"，失败 {s['fail']} 次" if s["fail"] else ""
    return f"共 {s['total']} 次（今天 {s['today']}）{tail}{bad}"
