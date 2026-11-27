"""检查更新：只读一份清单，不下载、不安装、不改东西。

月下 19:33：「以后要做更多，更新版本是不是很麻烦？好像没办法直接传给他们。」
整件事拆成三步（见 `计划-新家更新与分发.md`）：①知道有新版 ②拿到新版 ③换上新版。
这个文件只管第①步，而且是**最保守的那种**：

- 只拉一份 JSON（静态地址就行：网盘直链 / GitHub / Gitee，不要服务器）；
- 比 `version.VERSION`，有新版本就把说明和链接**摆出来给人看**，不偷偷下；
- 出什么都不抛异常，全变成一句话交给界面；网线没插、地址没配，就直说。

清单长这样：
    {
      "version": "0.4.2",
      "date": "2026-11-02",
      "notes": "修了权限页文案；扩展能搜索了",
      "url": "https://…/jingyu-0.4.2.zip",
      "sha256": "…",
      "min_from": "0.3.0"
    }

隐私：只在人点「检查更新」的时候发一次 GET，带出去的信息只有这条请求本身；
清单里的地址是我们自己的静态空间，不上传任何本机内容。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

import version

NO_URL = "还没配更新地址（config.update_url）"
# 2026-11-27：以前 update_url 默认是空的，人装完「检查更新」永远得到「还没配」。
# 现在给一个默认的：GitHub 仓里那份 update.json。config 里填了就用填的，没填就走这儿——
# 所以**已经装出去的 v1.0.0 也能靠这次之后的版本自己更新**（它们那一版还是老逻辑，第一次得手动）。
DEFAULT_MANIFEST = "https://raw.githubusercontent.com/yuexialike/whale-isle/main/update.json"
TIMEOUT = 6.0

# 5-3：装的时候这些顶层东西一律不覆盖（用户的配置、记忆、插件、模型）
PROTECT = {
    "config.json", "config.backup.json", "config.seal", "dev.marker",
    "data", "log", "people", "plugins", "models", "updates", "skin",
}


def manifest_url(cfg: dict | None = None) -> str:
    cfg = cfg or {}
    return str(cfg.get("update_url") or "").strip() or DEFAULT_MANIFEST


def _read(url: str, timeout: float = TIMEOUT) -> str:
    """http(s) 或本地文件都认（本地那份是给自己试清单格式用的）。"""
    u = str(url)
    if u.startswith(("http://", "https://")):
        req = urllib.request.Request(u, headers={"User-Agent": "JingYu-update-check"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(200_000).decode("utf-8", "replace")
    p = Path(u[7:]) if u.startswith("file://") else Path(u)
    return p.read_text(encoding="utf-8", errors="replace")


def parse(text: str) -> dict:
    """清单得像个清单：version 必须有，别的缺了也能凑合看。"""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("清单不是一个对象")
    ver = str(data.get("version") or "").strip()
    if not ver:
        raise ValueError("清单里没有 version")
    out = {
        "version": ver,
        "date": str(data.get("date") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
        "url": str(data.get("url") or "").strip(),
        "sha256": str(data.get("sha256") or "").strip().lower(),
        "min_from": str(data.get("min_from") or "").strip(),
    }
    return out


def check(cfg: dict | None = None, url: str | None = None) -> dict:
    """跑一次检查。永远不抛，返回：

    state: "no-url" / "bad-json" / "offline" / "new" / "latest"
    message: 一句话，能直接摆到界面上（带版号，别让人猜）
    manifest: 解析出来的清单（没有就是 None）
    """
    target = (url or manifest_url(cfg)).strip()
    if not target:
        return {"state": "no-url", "message": NO_URL, "manifest": None}
    try:
        text = _read(target)
    except Exception as exc:                                     # noqa: BLE001
        return {"state": "offline", "message": f"拉不到清单：{type(exc).__name__} {exc}",
                "manifest": None}
    try:
        man = parse(text)
    except Exception as exc:                                     # noqa: BLE001
        return {"state": "bad-json", "message": f"清单看不懂：{type(exc).__name__} {exc}",
                "manifest": None}

    mine = version.VERSION
    if not version.newer(man["version"], mine):
        return {"state": "latest", "message": f"已经是最新的（{mine}）", "manifest": man, }

    bits = [f"有新版本 {man['version']}（现在是 {mine}）"]
    if man["date"]:
        bits[0] += f" · {man['date']}"
    msg = "，".join(bits)
    if man["notes"]:
        msg += "\n" + man["notes"]
    if man["url"]:
        msg += "\n" + man["url"]
    else:
        msg += "\n（清单里没给下载链接）"
    if man["min_from"] and version.newer(man["min_from"], mine):
        msg += f"\n⚠ 这一版要求从 {man['min_from']} 往上，太旧的要整包重装"
    return {"state": "new", "message": msg, "manifest": man}


def sha256_of(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 5-3 下 + 装

def download(man: dict, dest_dir: str | Path | None = None) -> dict:
    try:
        import permissions as _perm
        _perm.audit(None, "install", "下载更新包")
    except Exception:  # noqa: BLE001
        pass
    """把清单里的 zip 拉下来，校验 sha256；不执行、不解压。返回路径和哈希。"""
    url = str((man or {}).get("url") or "").strip()
    if not url:
        raise ValueError("清单里没给下载链接")
    ver = str((man or {}).get("version") or "new").strip()
    dest = Path(dest_dir) if dest_dir else Path(__file__).resolve().parent / "updates" / "downloads"
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"jingyu-{ver}.zip"
    tmp = target.with_suffix(".zip.part")
    try:
        with urllib.request.urlopen(url, timeout=60) as src, open(tmp, "wb") as out:
            shutil.copyfileobj(src, out)
        got = sha256_of(tmp)
        want = str((man or {}).get("sha256") or "").strip().lower()
        if want and got != want:
            raise ValueError(f"下载下来的文件哈希对不上（要 {want[:12]}…，拿到 {got[:12]}…）")
        os.replace(tmp, target)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return {"path": str(target), "sha256": got, "size": target.stat().st_size}


def stage(zip_path: str | Path, dest_root: str | Path | None = None) -> Path:
    """解压到 updates/staged-<名字>，挡 zip-slip（成员不许跑出目标目录）。"""
    zpath = Path(zip_path)
    root = Path(dest_root) if dest_root else zpath.parent / "staged"
    root = root / zpath.stem
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as zf:
        for info in zf.infolist():
            rel = Path(info.filename)
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(f"压缩包里有越界路径：{info.filename}")
            target = (root / rel).resolve()
            if not str(target).startswith(str(root.resolve()) + os.sep) and target != root.resolve():
                raise ValueError(f"压缩包里有越界路径：{info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return root


def apply(staged: str | Path, home: str | Path | None = None, dry: bool = False) -> dict:
    """把 staged 里的文件铺到 home；受保护的东西跳过，旧文件先备份。

    不删 home 里包外的东西，也不重启/不 taskkill——换完由外面决定什么时候重启。
    """
    src = Path(staged)
    dst = Path(home) if home else Path(".")
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = dst / "updates" / f"backup-{stamp}"
    copied: list[str] = []
    skipped: list[str] = []
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if rel.parts and rel.parts[0] in PROTECT:
            skipped.append(str(rel))
            continue
        copied.append(str(rel))
        if dry:
            continue
        out = dst / rel
        if out.exists():
            b = backup / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, b)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)
    return {"copied": copied, "skipped": skipped, "backup": str(backup) if copied and not dry else ""}


def rollback(backup: str | Path, home: str | Path | None = None) -> dict:
    """把某次 apply 的 backup 目录铺回去（只覆盖 backup 里有的文件）。"""
    src = Path(backup)
    dst = Path(home) if home else Path(__file__).resolve().parent
    restored: list[str] = []
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)
        restored.append(str(rel))
    return {"restored": restored, "from": str(src)}


def make_manifest(zip_path: str | Path | None = None, *, ver: str | None = None,
                  notes: str = "", url: str = "", min_from: str = "",
                  date: str = "") -> dict:
    """打一份清单（发版时用）。给了 zip 就把它的 sha256 算进去。"""
    import datetime as _dt

    out = {
        "version": (ver or version.VERSION).lstrip("vV"),
        "date": date or f"{_dt.date.today():%Y-%m-%d}",
        "notes": notes,
        "url": url,
        "sha256": sha256_of(zip_path) if zip_path else "",
        "min_from": min_from,
    }
    return out


def write_manifest(path: str | Path, **kw) -> Path:
    p = Path(path)
    p.write_text(json.dumps(make_manifest(**kw), ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return p
