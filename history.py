"""5-4 记忆历史：按天把「记忆类文件」快照到 updates/history/<日期>/，带 sha256 清单。

不用 git（工作区几十个 G，视频/ref/games 不该进版本库）。只快照记忆：
log/、STATE.md、PARTNER.md、CONSTITUTION.md、people/、handoffs/、memory/、todo.md。
data/ 里的日志大文件不碰。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import shutil
from pathlib import Path

import memory

PATHS = ("log", "STATE.md", "PARTNER.md", "CONSTITUTION.md",
         "people", "handoffs", "memory", "todo.md")
DEFAULT_KEEP = 30


def _root(root_dir: str | Path | None = None) -> Path:
    return Path(root_dir) if root_dir else Path(__file__).resolve().parent / "updates" / "history"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(cfg: dict | None = None, root_dir: str | Path | None = None,
             keep: int | None = None, day: str | None = None) -> Path:
    """做一份当天的快照；同一天再跑就刷新（不堆重复目录）。"""
    ws = memory.workspace(cfg)
    root = _root(root_dir)
    day = day or _dt.date.today().strftime("%Y-%m-%d")
    dest = root / day
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []
    for name in PATHS:
        src = ws / name
        if not src.exists():
            continue
        items = [src] if src.is_file() else [p for p in src.rglob("*") if p.is_file()]
        for p in items:
            rel = p.relative_to(ws)
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
            files.append({"path": rel.as_posix(), "size": out.stat().st_size,
                          "sha256": _sha256(out)})
    manifest = {"date": day, "created": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "files": files}
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = int(keep if keep is not None else (cfg or {}).get("history_keep_days", DEFAULT_KEEP) or DEFAULT_KEEP)
    keep_days(root, n)
    return dest


def keep_days(root_dir: str | Path | None = None, keep: int = DEFAULT_KEEP) -> list[str]:
    """只留最近 keep 个日期目录，返回被删的。"""
    root = _root(root_dir)
    if not root.exists():
        return []
    days = sorted([p.name for p in root.iterdir() if p.is_dir() and len(p.name) == 10],
                  reverse=True)
    removed: list[str] = []
    for name in days[int(keep):]:
        shutil.rmtree(root / name, ignore_errors=True)
        removed.append(name)
    return removed


def snapshot_if_due(cfg: dict | None = None, root_dir: str | Path | None = None) -> Path | None:
    """今天还没快照就做一份；已经做过就跳过（每天最多一份）。"""
    root = _root(root_dir)
    today = _dt.date.today().strftime("%Y-%m-%d")
    if (root / today / "manifest.json").is_file():
        return None
    return snapshot(cfg, root)
