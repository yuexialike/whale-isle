"""闹钟：自己的，不靠外面平台。

照 Coop 的 `alarms.ts` 学的是**结构**：一条闹钟 = 什么时候 + 说什么 + 一天一次还是就一次。
代码没抄——他那套带时区、重复规则、错过补发，我这儿先只做最小能用的那种：

  set_alarm(when, note, daily)
      when   "22:30"      今天这个点（过了就是明天）
             "2026-10-31 08:30"
             "in 30m" / "30m"  多少分钟之后
      daily  true = 每天这个点

到点了怎么办：`due()` 把它交出来，主程序冒气泡、记账，然后标成已响。
断电那会儿错过的，开机第一次 `due()` 会补——一句话说清「这条本来是几点的」。

存在 data/alarms.json，人能直接改，我也能直接改。
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

import memory


def _path() -> Path:
    return memory.data_dir() / "alarms.json"


def _now() -> _dt.datetime:
    return _dt.datetime.now()


def load() -> list[dict]:
    p = _path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save(items: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_when(when: str, now: _dt.datetime) -> _dt.datetime:
    """把几种写法都吃下去，回来一个具体时刻。写不对就抛 ValueError。"""
    s = (when or "").strip()

    # in 30m / 30m / 30 分钟
    m = re.fullmatch(r"(?:in\s*)?(\d+)\s*(m|min|分钟)", s, re.I)
    if m:
        return now + _dt.timedelta(minutes=int(m.group(1)))

    # 2026-10-31 08:30
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return _dt.datetime.strptime(s, fmt)
        except ValueError:
            pass

    # 22:30 —— 过了就是明天
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        t = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if t <= now:
            t += _dt.timedelta(days=1)
        return t

    raise ValueError(f"看不懂这个时间：{when}")


def add(when: str, note: str, daily: bool = False, **extra) -> dict:
    """extra 是给自己留的附注，原样写进那一条。

    现在用到的：`voice=True` 到点除了冒泡，还往 `to`（如 private:1000000000）
    发一条 QQ 语音；`prompt` 是交给脑子那句嘱咐（不给就用 note）。
    """
    now = _now()
    at = _parse_when(when, now)
    items = load()
    nid = 1 + max([int(a.get("id", 0)) for a in items] or [0])
    item = {
        "id": nid,
        "at": at.strftime("%Y-%m-%d %H:%M"),
        "clock": at.strftime("%H:%M"),
        "daily": bool(daily),
        "note": (note or "").strip(),
        "fired": "",
    }
    for k, v in extra.items():
        if v not in (None, "", False):
            item[k] = v
    items.append(item)
    save(items)
    return item


def cancel(nid: int) -> bool:
    items = load()
    keep = [a for a in items if int(a.get("id", 0)) != int(nid)]
    if len(keep) == len(items):
        return False
    save(keep)
    return True


def listing() -> list[dict]:
    return sorted(load(), key=lambda a: (a.get("at", ""), int(a.get("id", 0))))


def due(now: _dt.datetime | None = None) -> list[dict]:
    """到点的闹钟交出来，并标成已响。错过的也交，但会写明它是几点的。"""
    now = now or _now()
    stamp = now.strftime("%Y-%m-%d %H:%M")
    out, items, changed = [], load(), False

    for a in items:
        at = a.get("at", "")
        if not at or at > stamp:
            continue
        if a.get("daily"):
            # 每天一次：上次响过的时间跟今天不是同一天，就该响
            if a.get("fired") == now.strftime("%Y-%m-%d"):
                continue
            a["fired"] = now.strftime("%Y-%m-%d")
            # 明天的同一个点
            try:
                t = _dt.datetime.strptime(at, "%Y-%m-%d %H:%M") + _dt.timedelta(days=1)
                while t.strftime("%Y-%m-%d %H:%M") <= stamp:
                    t += _dt.timedelta(days=1)
                a["at"] = t.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        else:
            if a.get("fired"):
                continue
            a["fired"] = now.strftime("%Y-%m-%d %H:%M")

        a["_late"] = at != stamp
        out.append(a)
        changed = True

    if changed:
        # 一次性的响过就删掉；每天的留着。`_late` 只是这一趟说的话，不落到盘上。
        items = [a for a in items if a.get("daily") or a.get("fired") == ""]
        save([{k: v for k, v in a.items() if k != "_late"} for a in items])
    return out


def describe(items: list[dict] | None = None) -> str:
    items = listing() if items is None else items
    if not items:
        return "一个闹钟也没有。"
    rows = []
    for a in items:
        flag = "每天" if a.get("daily") else "一次"
        rows.append(f"#{a.get('id')} {a.get('at')} （{flag}）{a.get('note', '')}")
    return "\n".join(rows)
