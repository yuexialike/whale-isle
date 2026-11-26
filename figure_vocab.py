"""词表：把「开心 / 招手」这种词，翻成形象包认的动作 id。

它替谁挡什么：挡住「回复里写了个包不认识的词就乱做动作 / 报错」——对不上就返回 None，
由调用方把原词留成小字、记一行日志；对上了才交给 body.act。

谁调它：
  · `page.py` 在回答落地时，把 `【…】` 和 `<…>` 里的词翻成 id；
  · `body.act()` 用它确认这个词在当前包里有，别把包里没有的词送进 figure.js。

词表从哪来：不是写死在代码里，是当前包 `figure.json` 的 `vocab` 段
（whale 包现在是 19 个表情 + 18 个动作，共 37 个）。换包，词表跟着换。
"""
from __future__ import annotations

import re

import figure_pack

# 【害羞】 或 <wave>；只取里面 1-12 个字，别把整段正文当词。
_MARK_RE = re.compile(r"【([^】]{1,12})】|<([^<>]{1,12})>")

_cache: dict = {"pack": None, "names": {}, "kinds": {}, "ids": set()}


def _load(pack: str | None = None) -> dict:
    """读当前包的词表并缓存；换包（名字变了）就重读。"""
    pid = str(pack or figure_pack.current())
    if _cache["pack"] == pid and _cache["ids"]:
        return _cache
    p = figure_pack.read_pack(pid)
    names: dict[str, str] = {}
    kinds: dict[str, str] = {}
    ids: set[str] = set()
    for item in p.get("vocab") or []:
        if not isinstance(item, dict):
            continue
        wid = str(item.get("id") or "").strip()
        if not wid:
            continue
        ids.add(wid)
        names[wid] = wid
        kinds[wid] = str(item.get("kind") or "")
        by_lang = item.get("names") or {}
        if isinstance(by_lang, dict):
            for lang in ("zh", "zh-Hant", "en"):
                for nm in by_lang.get(lang) or []:
                    nm = str(nm or "").strip()
                    if nm:
                        names.setdefault(nm, wid)
    _cache.update({"pack": pid, "names": names, "kinds": kinds, "ids": ids})
    return _cache


def known(word: str) -> bool:
    """这个词（id 或中文名）在当前包里有没有。"""
    return resolve(word) is not None


def resolve(word: str) -> tuple[str, str] | None:
    """词 → (动作 id, 种类)；对不上返回 None。"""
    text = str(word or "").strip()
    if not text:
        return None
    data = _load()
    wid = data["names"].get(text)
    if wid is None:
        low = text.lower()
        for nm, w in data["names"].items():
            if nm.lower() == low:
                wid = w
                break
    if wid is None:
        return None
    return wid, data["kinds"].get(wid, "")


def ids() -> set[str]:
    """当前包认的所有 id（给诊断/测试）。"""
    return set(_load()["ids"])


def actions_in(text: str) -> list[str]:
    """一段回答里能对上词表的动作 id，按出现顺序；重复的也保留（做两次）。"""
    out: list[str] = []
    for a, b in _MARK_RE.findall(str(text or "")):
        raw = (a or b or "").strip()
        hit = resolve(raw)
        if hit:
            out.append(hit[0])
    return out


def unknown_in(text: str) -> list[str]:
    """一段回答里对不上词表的词（由调用方记日志、留小字）。"""
    out: list[str] = []
    for a, b in _MARK_RE.findall(str(text or "")):
        raw = (a or b or "").strip()
        if raw and resolve(raw) is None:
            out.append(raw)
    return out
