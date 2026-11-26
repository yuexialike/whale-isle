"""日报插件：每天睡前把今天收成一页纸。

为什么要有它：手写 `log/2026-11.md` 是一条一条 append，又碎又慢，这件事机械。
所以交给它——每天 22:55 把 chat / heartbeat / tool 三份日志收成
`workspace/log/日记-YYYY-MM-DD.md`，一天一页，同一天重跑就覆盖。

规矩（写的时候定的）：
  · 数据只读，一行都不改别人的日志；
  · 后台线程出什么事都不许把主程序带崩，错写 `data/daily.log`；
  · 配置只改 `daily` 那一格，先 load 再 update，别把 api_key 冲掉；
  · 程序关着错过的那天不补，只在 daily.log 里记一句「错过了」。
"""
from __future__ import annotations

import datetime as _dt
import threading
import time
from pathlib import Path as _P

NAME = "日报"
ABOUT = "每天 22:55 把今天收成一页纸（说了几句、醒了几次、动过什么、最后一句话）。两个工具：daily_build、daily_read。"

_WEEK = "一二三四五六日"
DEFAULT_AT = "22:55"        # 11-05 09:42：原来是 23:00，正好撞断电，11-04 那页没写出来

# setup() 里填：工具函数只拿得到 args，拿不到 ctx
_DATA: _P = _P(".")
_WORK: _P = _P(".")
_CFG: dict = {}
_STOP = threading.Event()      # 3-2：卸插件时置位，让看表线程收工

_STATE = {
    "last_day": "",     # 已经写过的日期（YYYY-MM-DD），同一天不再写第二次
    "missed": "",       # 已经报过「错过了」的日期，别天天重复报
    "checking": False,  # 线程起没起
}


# ── 小工具 ────────────────────────────────────────────────

def _stamp(t: _dt.datetime | None = None) -> str:
    return (t or _dt.datetime.now()).strftime("%H:%M:%S")


def _log(text: str) -> None:
    """自己的账本：data/daily.log。写不进去就算了，绝不再抛。"""
    try:
        p = _DATA / "daily.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"[{_stamp()}] {text}\n")
    except Exception:                                   # noqa: BLE001
        pass


def _lines(name: str) -> list[str]:
    """读一份日志的全部行；没有就返回空表。"""
    p = _DATA / name
    try:
        if not p.exists():
            return []
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:                              # noqa: BLE001
        _log(f"读不了 {name}（{type(e).__name__}）")
        return []


def _hhmm(s: str) -> str:
    """从一行里抠时间；抠不到就原样返回空。"""
    s = s.strip()
    if len(s) >= 5 and s[2] == ":" and s[:2].isdigit() and s[3:5].isdigit():
        return s[:5]
    return ""


def _at(cfg: dict) -> str:
    """配置里的「几点写」，坏值一律退回 DEFAULT_AT（现在是 22:55）。"""
    raw = str((cfg or {}).get("at") or DEFAULT_AT).strip()
    parts = raw.split(":")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h < 24 and 0 <= m < 60:
            return f"{h:02d}:{m:02d}"
    return DEFAULT_AT


def _enabled(cfg: dict) -> bool:
    cfg = cfg or {}
    return cfg.get("enabled", True) is not False


# ── 读三份日志 ────────────────────────────────────────────
# chat.log 一行一条：`[20:31:05] 月下: 内容`（时间只有时分秒，没日期）
# 所以「今天」怎么断：日志里最新的那一行算今天，往前遇到「时间比它大」就换天了。
# 简单、不靠文件时间戳（文件时间戳只看得到最后一次写）。

def _parse_chat(rows: list[str]) -> list[dict]:
    out: list[dict] = []
    for raw in rows:
        line = raw.rstrip()
        if not line:
            continue
        t = ""
        body = line
        if line.startswith("[") and "]" in line:
            t = _hhmm(line[1:line.index("]")])
            body = line[line.index("]") + 1:].strip()
        who, _, said = body.partition(":")
        if not _:
            who, said = "", body
        out.append({"t": t, "who": who.strip(), "text": said.strip()})
    return out


def _today_slice(msgs: list[dict]) -> list[dict]:
    """按「时间倒退就换天」切出今天那一截。"""
    if not msgs:
        return []
    cut = 0
    for i in range(len(msgs) - 1, 0, -1):
        a = msgs[i - 1]["t"]
        b = msgs[i]["t"]
        if a and b and b < a:
            cut = i
            break
    return msgs[cut:]


def _chat_today(rows: list[str]) -> dict:
    """今天跟月下说了什么。他说的 / 我说的分开数。"""
    msgs = _today_slice(_parse_chat(rows))
    his = [m for m in msgs if m["who"] and m["who"] not in ("我", "鱼鱼")]
    mine = [m for m in msgs if m not in his]
    times = [m["t"] for m in msgs if m["t"]]
    last_his = next((m["text"] for m in reversed(his) if m["text"]), "")
    return {
        "total": len(msgs),
        "his": len(his),
        "mine": len(mine),
        "first": times[0] if times else "",
        "last": times[-1] if times else "",
        "last_his": last_his,
    }


def _spoke(line: str) -> bool:
    """这一行算不算「开口」。

    心跳日志里绝大多数是「醒了一下，选择不说」——「不说」「没说话」里都有「说」字，
    照 `"说" in line` 数，一天能数出几十次假开口。所以先划掉否定的，再认明确的写法。
    """
    if "不说" in line or "没说" in line or "没开口" in line:
        return False
    return any(k in line for k in ("开口", "说过", "出声", "说了", "说："))


def _heartbeat_today(rows: list[str]) -> dict:
    """醒过几次、开口几次。一行里带「说」或「开口」算开口。"""
    woke = 0
    spoke = 0
    for line in rows:
        if "醒" not in line:
            continue
        woke += 1
        if _spoke(line):
            spoke += 1
    return {"woke": woke, "spoke": spoke}


_TOOL_KEYS = ("工具", "tool", "调了", "调用", "run_command", "→")


def _tools_today(rows: list[str]) -> list[str]:
    """今天用过哪些工具，按第一次出现的顺序去重。"""
    seen: list[str] = []

    def add(name: str) -> None:
        name = name.strip().strip("：:，,")
        if name and name not in seen:
            seen.append(name)

    import re

    for line in rows:
        if not line.strip():
            continue
        # 先看有没有 `名字(` 或 `→ 名字` 这种显式写法
        for m in re.finditer(r"(?:调用了|调用|工具|tool)\s*[:：]?\s*([A-Za-z_][A-Za-z0-9_]{1,40})", line):
            add(m.group(1))
        for m in re.finditer(r"→\s*([A-Za-z_][A-Za-z0-9_]{1,40})", line):
            add(m.group(1))
    return seen


# ── 拼那一页 ──────────────────────────────────────────────

def _today() -> _dt.date:
    return _dt.date.today()


def _dow(d: _dt.date) -> str:
    return "星期" + _WEEK[d.weekday()]


def build(day: _dt.date | None = None) -> dict:
    """拼一页日报，写进 workspace/log/日记-YYYY-MM-DD.md。

    返回 {"ok": bool, "path": str, "text": str, "why": str}
    同一份日志重复跑只会覆盖同一个文件，不追加。
    """
    d = day or _today()
    key = d.strftime("%Y-%m-%d")
    try:
        chat = _chat_today(_lines("chat.log"))
        hb = _heartbeat_today(_lines("heartbeat.log"))
        tools = _tools_today(_lines("tool.log"))
    except Exception as e:                              # noqa: BLE001
        _log(f"拼 {key} 时读日志出错：{type(e).__name__}: {e}")
        return {"ok": False, "path": "", "text": "", "why": f"读日志出错：{e}"}

    out: list[str] = []
    out.append(f"# {key} {_dow(d)}")
    out.append("")

    # 一、说了几句
    out.append("## 说了几句")
    if chat["total"]:
        out.append(f"- 一共 {chat['total']} 句：他说 {chat['his']}，我说 {chat['mine']}")
        if chat["first"] and chat["last"]:
            if chat["first"] == chat["last"]:
                out.append(f"- 差不多就 {chat['first']} 那会儿聊的")
            else:
                out.append(f"- 从 {chat['first']} 说到 {chat['last']}")
    else:
        out.append("- 今天没说话。")
    out.append("")

    # 二、醒了几次
    out.append("## 醒了几次")
    if hb["woke"]:
        line = f"- 醒了 {hb['woke']} 次"
        if hb["spoke"]:
            line += f"，其中开口 {hb['spoke']} 次"
        out.append(line)
    else:
        out.append("- 心跳日志里没有今天的记录。")
    out.append("")

    # 三、动过什么
    out.append("## 动过什么")
    if tools:
        out.append("- " + "、".join(tools[:20]))
        if len(tools) > 20:
            out.append(f"- （还有 {len(tools) - 20} 个没列）")
    else:
        out.append("- 今天没动电脑。")
    out.append("")

    # 四、他最后一句
    out.append("## 他最后一句")
    last = chat["last_his"]
    if last:
        if len(last) > 200:
            last = last[:200] + "…"
        out.append("> " + last.replace("\n", " "))
    else:
        out.append("- （今天他没留下话）")
    out.append("")
    out.append("---")
    out.append(f"*{_stamp()} 收的*")
    out.append("")

    text = "\n".join(out)

    # 落盘：workspace/log/ 下一天一页
    try:
        folder = _WORK / "log"
        folder.mkdir(parents=True, exist_ok=True)
        p = folder / f"日记-{key}.md"
        p.write_text(text, encoding="utf-8")
    except Exception as e:                              # noqa: BLE001
        _log(f"写 {key} 的日报失败：{type(e).__name__}: {e}")
        return {"ok": False, "path": "", "text": text, "why": f"写文件失败：{e}"}

    _STATE["last_day"] = key
    _log(f"写好 {key}（他说 {chat['his']} 句，我 {chat['mine']} 句，醒 {hb['woke']} 次）")
    return {"ok": True, "path": str(p), "text": text, "why": ""}


# ── 后台线程：每 20 秒看一眼表 ───────────────────────────

def _tick() -> None:
    """到点就写；一天只写一次。"""
    now = _dt.datetime.now()
    cfg = _CFG if isinstance(_CFG, dict) else {}
    if not _enabled(cfg):
        return
    at = _at(cfg)
    if now.strftime("%H:%M") != at:
        return
    key = now.strftime("%Y-%m-%d")
    if _STATE.get("last_day") == key:
        return                                    # 今天已经写过了
    r = build(now.date())
    if r["ok"]:
        _STATE["last_day"] = key
    else:
        # 没写成也别每 20 秒重试一遍；记一次，等下一分钟
        _log(f"{at} 到点没写成：{r['why']}")


def _loop() -> None:
    while not _STOP.is_set():
        try:
            _tick()
        except Exception as e:                          # noqa: BLE001
            _log(f"线程里出事了：{type(e).__name__}: {e}")
        if _STOP.wait(20):
            break


def _start_watcher() -> None:
    _STOP.clear()
    if _STATE.get("checking"):
        return
    _STATE["checking"] = True
    t = threading.Thread(target=_loop, name="daily-watcher", daemon=True)
    t.start()
    _log(f"看表线程起了（每天 {_at(_CFG)} 写一页）")


# ── 工具 ─────────────────────────────────────────────────

def _tool_build(args: dict) -> str:
    """手动写今天的（或指定某天）。"""
    day = None
    raw = str((args or {}).get("date") or "").strip()
    if raw:
        try:
            day = _dt.datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return f"日期看不懂：{raw}（要 YYYY-MM-DD）"
    r = build(day)
    if not r["ok"]:
        return f"没写成：{r['why']}"
    return f"写好了：{r['path']}"


def _tool_read(args: dict) -> str:
    """读已写好的某一页；不给日期就是今天。"""
    raw = str((args or {}).get("date") or "").strip()
    d = raw or _today().strftime("%Y-%m-%d")
    try:
        _dt.datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        return f"日期看不懂：{d}（要 YYYY-MM-DD）"
    p = _WORK / "log" / f"日记-{d}.md"
    try:
        if not p.exists():
            return f"{d} 还没有日报。要的话我可以现在收一份。"
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:                              # noqa: BLE001
        return f"读不了：{e}"


TOOLS = [
    {
        "name": "daily_build",
        "desc": "把今天的聊天、心跳、工具日志收成一页日报，存 workspace/log/日记-YYYY-MM-DD.md。同一天重跑会覆盖。",
        "args": {"date": "可选，YYYY-MM-DD，不给就是今天"},
        "run": _tool_build,
    },
    {
        "name": "daily_read",
        "desc": "读某一页已经写好的日报。不给日期就读今天的。",
        "args": {"date": "可选，YYYY-MM-DD"},
        "run": _tool_read,
    },
]


# plug.py 要的是「(给模型看的声明, 干活的函数)」两元组，上面那份是给人看的简写，这里转过去。
_TOOLS_META = TOOLS
TOOLS = [
    (
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["desc"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string", "description": v} for k, v in t["args"].items()
                    },
                },
            },
        },
        t["run"],
    )
    for t in _TOOLS_META
]


# ── 挂载 ─────────────────────────────────────────────────

def _ctx_get(ctx, key: str):
    """ctx 是主程序给的字典（main.py 里 plug_ctx），也兼容对象写法。"""
    if isinstance(ctx, dict):
        return ctx.get(key)
    return getattr(ctx, key, None)


def setup(ctx) -> dict:
    """主程序调这个。ctx 给 data_dir / workspace_dir / config。

    只改 config 里的 daily 那一格，先 load 再 update，别冲掉 api_key。
    """
    global _DATA, _WORK, _CFG
    try:
        _DATA = _P(_ctx_get(ctx, "data_dir") or _DATA)
    except Exception:                                   # noqa: BLE001
        pass
    try:
        # 主程序给的键叫 workspace，测试里的 Ctx 叫 workspace_dir，两个都认。
        _WORK = _P(_ctx_get(ctx, "workspace") or _ctx_get(ctx, "workspace_dir") or _WORK)
    except Exception:                                   # noqa: BLE001
        pass

    cfg = _ctx_get(ctx, "config")
    if isinstance(cfg, dict):
        _CFG = cfg.setdefault("daily", {})
    else:
        _CFG = {}

    _CFG.setdefault("enabled", True)
    _CFG.setdefault("at", DEFAULT_AT)

    _start_watcher()
    return {"name": NAME, "about": ABOUT,
            "tools": [t[0]["function"]["name"] for t in TOOLS]}


def stop() -> None:
    """3-2：卸日报时调——让看表线程下一轮醒来就退出。

    为什么存在：以前卸载只挪文件，daily-watcher 还每隔 20 秒 tick 一次；
    这个 stop 置位后，_loop 里的 _STOP.wait(20) 立刻返回并 break。
    """
    _STOP.set()
