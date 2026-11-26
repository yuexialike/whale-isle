"""管形象包：告诉 `figure_web` 去哪儿找包、包里哪几个文件是入口。

它替谁挡什么：挡「包目录缺了 / 清单坏了 / 入口文件不在 / export 没写」时，
悄悄起一个空白小人。这里先把问题说清楚（`PackError`），再由调用方决定回落——
回落到老壳也要把理由写进日志，不许不吭声。

谁调它：
  · `main.py` 开机把 config 里的 `figure_pack` 告诉它（`set_current`）；
  · `figure_web.FigureWeb` 用它读入口、拿到包目录；
  · `test_figure_pack.py` 直接测它。

包长这样（以后换成月下自己画的分层部件图，只换这个目录，代码不动）：
    skin/figures/<id>/figure.json   —— 清单：id、entry（figure.js）、export、model、vocab
    skin/figures/<id>/figure.js     —— 画小人的代码
    skin/figures/<id>/...           —— 贴图、配色、服装
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKS_DIR = HERE / "skin" / "figures"
DEFAULT = "whale"

_current = DEFAULT


class PackError(Exception):
    """包不能用。消息里必须写清是缺目录、缺清单、还是入口/export 不在。"""


def packs_dir() -> Path:
    """所有形象包放在哪个目录（不负责创建：缺了要报错，不是悄悄建空目录）。"""
    return PACKS_DIR


def set_current(name: str | None) -> None:
    """开机时由 main 调：config 写了哪个包就用哪个，没写用默认的 whale。"""
    global _current
    _current = str(name or DEFAULT).strip() or DEFAULT


def current() -> str:
    """现在用的是哪个包（FigureWeb 不传包名时读这个）。"""
    return _current


def read_pack(name: str | None = None) -> dict:
    """读一个包的清单，返回入口、词表和目录；坏在哪就抛 `PackError` 说明白。

    返回的 `base` 是给页面用的相对路径（`packs/<id>/`），不是磁盘路径。
    """
    pid = str(name or _current).strip() or DEFAULT
    d = packs_dir() / pid
    if not d.is_dir():
        raise PackError(f"形象包目录不在：{d}")
    fj = d / "figure.json"
    if not fj.is_file():
        raise PackError(f"形象包缺 figure.json：{d}")
    try:
        data = json.loads(fj.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:                           # noqa: BLE001
        raise PackError(f"figure.json 读不出来（{type(e).__name__}: {e}）：{fj}") from e
    if not isinstance(data, dict):
        raise PackError(f"figure.json 不是一个对象：{fj}")

    entry = str(data.get("entry") or "").strip()
    if not entry:
        raise PackError(f"figure.json 里没写 entry（入口 js 文件名）：{fj}")
    if not (d / entry).is_file():
        raise PackError(f"清单写了 entry={entry}，可这个文件不在：{d / entry}")

    export = str(data.get("export") or "").strip()
    if not export:
        raise PackError(f"figure.json 里没写 export（figure.js 的导出函数名）：{fj}")

    model = data.get("model")
    if model and not (d / str(model)).is_file():
        raise PackError(f"清单写了 model={model}，可这个文件不在：{d / model}")

    vocab = data.get("vocab") or []
    if not isinstance(vocab, list):
        vocab = []
    return {
        "id": pid,
        "dir": d,
        "entry": entry,
        "export": export,
        "model": model,
        "base": f"packs/{pid}/",
        "vocab": vocab,
        "raw": data,
    }


def list_packs() -> list[str]:
    """skin/figures 里有哪些包（只看目录，坏包也会列出来，读的时候再报）。"""
    root = packs_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def vocab_counts(vocab: list) -> dict:
    """数一下词表里表情/动作各几个（给测试和诊断用）。"""
    out = {"expression": 0, "motion": 0, "other": 0}
    for item in vocab:
        kind = str((item or {}).get("kind") or "")
        out[kind if kind in out else "other"] += 1
    return out
