"""替聊天记话：每说一句就往 data/sessions/<名字>.jsonl 添一行，下次开机再读回来。

谁调它：
  · chat.py 的输入框——你说一句、她答一句，各添一行；
  · page.py 的对话页——在那边说话也一样；
  · main.py 不直接碰它；
  · webui/server.py 这次**没接**（它的历史还在内存里），别以为它也存了。

为什么要有：以前历史只放在内存的一个 list 里，超过 12 条就被 `del [:-12]`
截掉，程序一关，模型那边就全空了。

文件长这样，一行一条（一行坏了只丢一行，不会整份读不出来）：
    {"ts": "2026-11-20 21:30:01", "role": "user", "content": "在吗",
     "source": "typed", "entry": "chat"}
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import memory

# 同一时刻只让一个入口写：输入框和对话页可能前后脚各添一句。
_LOCK = threading.Lock()

# 文件里最多留多少句；再多就把最老的挤掉（内存和喂模型那边另有更小的窗口）。
MAX_LINES = 200

DEFAULT = "main"          # 桌面这份聊天的名字；以后要分会话再用别的名字


def _dir(cfg: dict) -> Path:
    """会话文件夹在哪：跟别的账本放一起（data/sessions/），没有就建。"""
    d = memory.data_dir(cfg) / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(cfg: dict, name: str) -> Path:
    """某个会话的文件路径；名字只留字母数字下划线横线，防止乱跑。"""
    safe = "".join(ch for ch in str(name) if ch.isalnum() or ch in "_-") or DEFAULT
    return _dir(cfg) / f"{safe}.jsonl"


def _read(path: Path) -> tuple[list[dict], list[str]]:
    """把文件一行行读成列表；读不出的行把原文留下来（只留内存里这一份，不复制文件）。"""
    if not path.exists():
        return [], []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], ["(整个文件读不出来)"]
    msgs: list[dict] = []
    bad: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:                        # noqa: BLE001
            bad.append(line)
            continue
        if (isinstance(obj, dict) and obj.get("role") in ("user", "assistant")
                and isinstance(obj.get("content"), str)):
            msgs.append(obj)
        else:
            bad.append(line)
    return msgs, bad


def _quarantine(path: Path) -> str:
    """整份坏掉时，把原文件改个名留底（不删），让新文件从空白开始。

    为什么改名而不是覆盖：那个坏文件里可能还有能人工捞回来的话；留着它，
    下次 append 才不会把它冲掉。
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.stem}.corrupt-{stamp}.jsonl")
    try:
        path.replace(dest)
        return dest.name
    except OSError:
        return ""


def _backup_before_repair(path: Path) -> Path:
    """把「修坏行之前」的原文件复制一份，返回副本路径。

    为什么要有：append 会把整个文件用读出来的好行重写一遍，坏行自然就没了。
    留一份原样，以后想从坏行里捞点什么都还能捞；复制不出来就抛错，宁可这次
    不重写，也不静默丢掉。
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.stem}.before-repair-{stamp}.jsonl")
    n = 1
    while dest.exists():                        # 同一秒里修两次也不互相盖
        dest = path.with_name(f"{path.stem}.before-repair-{stamp}-{n}.jsonl")
        n += 1
    try:
        dest.write_bytes(path.read_bytes())
    except OSError as e:
        raise OSError(f"坏行留底写不出来，这次先不重写：{e}") from e
    return dest


def _prune_backups(path: Path, keep: int = 5, cfg: dict | None = None) -> None:
    """同一个会话的「修之前副本」最多留 keep 份；多的挪进 sessions/archive/，不删。

    为什么要有：坏行本来就少，正常碰不到几次；但真出事时如果每修一次就多一份，
    目录会被几百份副本塞满。挪走而不是删掉，需要翻旧账时还找得回。
    """
    backups = sorted(path.parent.glob(f"{path.stem}.before-repair-*.jsonl"))
    if len(backups) <= keep:
        return
    arch = path.parent / "archive"
    arch.mkdir(parents=True, exist_ok=True)
    for old in backups[:-keep]:
        dest = arch / old.name
        n = 1
        while dest.exists():
            dest = arch / f"{old.stem}-{n}.jsonl"
            n += 1
        try:
            old.replace(dest)
            memory.note_file("tool.log", f"会话留底超过 {keep} 份，最老的挪进 archive：{dest.name}", cfg)
        except OSError:
            pass


def load(cfg: dict, name: str = DEFAULT, limit: int = 40, repair: bool = True) -> list[dict]:
    """开机把最近的话读回来，让模型不用从空白开始。

    文件坏了（整份读不出、或一行好的都没有）：记一行日志、改名留底、返回空列表，
    绝不把异常抛给启动流程——一个会话文件不许把主程序带崩。
    """
    path = _path(cfg, name)
    msgs, bad = _read(path)
    if bad:
        memory.note_file("tool.log", f"会话文件有 {len(bad)} 行读不出来：{path.name}", cfg)
    if not msgs and bad and repair:
        kept = _quarantine(path)
        memory.note_file("tool.log", f"会话文件整份坏了，已改名留底：{kept or path.name}", cfg)
        return []
    return msgs[-limit:] if limit and limit > 0 else msgs


def load_all(cfg: dict, repair: bool = False) -> dict[str, list[dict]]:
    """把 sessions 里每个文件都试着读一遍（给测试和诊断用）。

    一个文件坏只跳过它，别的照读；**绝不重写、绝不删除**任何文件，
    所以坏掉一个会话不会把另一个会话冲掉。
    """
    out: dict[str, list[dict]] = {}
    for path in sorted(_dir(cfg).glob("*.jsonl")):
        msgs, bad = _read(path)
        if bad and not msgs:
            memory.note_file("tool.log", f"会话文件读不出来，跳过：{path.name}", cfg)
            continue
        out[path.stem] = msgs
    return out


def _atomic_write(path: Path, msgs: list[dict]) -> None:
    """写文件的安全写法：先写 .tmp，写完落盘，再一口气改名替换正式文件。

    为什么不能直接 open(path, "w")：写到一半断电/出错，旧会话就没了；
    rename 是一下子完成的——别人看到的要么是旧的，要么是新的，不会看到半截。
    """
    text = "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs) + ("\n" if msgs else "")
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())          # 让内容真的落到盘上，再改名
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()                   # 失败就把半截临时文件清掉，旧文件原样
        except OSError:
            pass
        raise


def append(cfg: dict, name: str, role: str, content: str,
           source: str = "", entry: str = "") -> None:
    """添一句话：读旧内容 → 接上新的一句 → 原子写回。

    写不进去会抛异常，让叫它的人决定怎么办（聊天那边会记一行「会话没存上」，
    但照常把话回给你——聊天是主，落盘是副）。
    """
    if role not in ("user", "assistant"):
        raise ValueError(f"会话只记人话和回答，不记 {role!r}")
    text = str(content or "").strip()
    if not text:
        return
    row = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "role": role,
           "content": text, "source": str(source or ""), "entry": str(entry or "")}
    with _LOCK:
        path = _path(cfg, name)
        msgs, bad = _read(path)
        if bad:
            if not msgs:
                # 整份坏：先改名留底，再从空白开始，不能把坏文件冲掉。
                _quarantine(path)
                msgs = []
            else:
                # 还有好行、也有坏行：这次重写会把坏行挤掉。
                # 先复制一份「修之前」的原文件，别让那行坏话悄悄没了；
                # 副本写不出来就干脆不重写，让调用方看到错误（聊天会记日志，但照常回话）。
                backup = _backup_before_repair(path)
                _prune_backups(path, keep=5, cfg=cfg)
                memory.note_file(
                    "tool.log",
                    f"会话重写前留底 {backup.name}（原有 {len(bad)} 行坏行）",
                    cfg,
                )
        msgs.append(row)
        _atomic_write(path, msgs[-MAX_LINES:])
