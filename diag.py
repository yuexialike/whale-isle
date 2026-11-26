"""自己查一遍：新家现在到底哪儿通了、哪儿没通，一条一条摊开给人看。

月下 19:25：「人格和记忆我们是做了，但是没有做展示，还有诊断。」——Coop 那边
诊断页里有「运行 / 运行日志 / 数据清理 / 配置」，我这边先做最要紧的两件：
**跑一遍看哪儿坏了**，和**把这份结果导出成一张纸**（发给月下看，或者贴到聊天里）。

每条三样：状态（好 / 看一眼 / 坏了）、名字、细说。
全是本地能查的，只有「脑子」那一行会去碰一下端口；不真发请求——
真发在设置页「开始」里那颗「试一下能不能通」，别在这儿偷偷花他的 token。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import shutil
import socket
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import memory

OK = "ok"
WARN = "warn"
BAD = "bad"

Check = tuple[str, str, str]          # (状态, 名字, 细说)


def _port_open(url: str, timeout: float = 0.5) -> bool:
    """从 http://127.0.0.1:8899/... 里抠出 host:port，试着连一下。"""
    try:
        rest = url.split("//", 1)[-1].split("/", 1)[0]
        host, _, port = rest.partition(":")
        if not port:
            port = "443" if url.startswith("https") else "80"
        with socket.create_connection((host or "127.0.0.1", int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def _mask(key: str) -> str:
    if not key:
        return "（空）"
    if len(key) <= 12:
        return key[:2] + "…"
    return f"{key[:6]}…{key[-4:]}（{len(key)} 位）"


def _lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def checks(cfg: dict | None = None) -> list[Check]:
    cfg = cfg or memory.load_config()
    out: list[Check] = []

    # 1. 我自己跑在什么上面
    where = "打包好的 exe" if getattr(sys, "frozen", False) else "python 直接跑"
    out.append((OK, "本体", f"{platform.python_version()} · {where} · {platform.machine()}"))

    # 2. 家门和配置
    cfg_path = memory.HOME / "config.json"
    if cfg_path.exists():
        out.append((OK, "配置", f"{cfg_path.name} · {len(cfg)} 项 · {cfg_path.stat().st_size} 字节"))
    else:
        out.append((BAD, "配置", "config.json 不见了，下次改设置会重新铺一份"))

    ws = memory.workspace(cfg)
    out.append((OK if ws.exists() else BAD, "工作区",
                str(ws) if ws.exists() else f"{ws}（没有这个文件夹）"))

    # 3. 脑子（只看配没配，不真发；真发在「开始」页那颗按钮）
    base = str(cfg.get("api_base", "")).strip()
    model = str(cfg.get("api_model", "")).strip()
    key = str(cfg.get("api_key", "")).strip()
    if not base or not model:
        out.append((BAD, "脑子", "地址或模型名空着，接不上"))
    elif not key:
        out.append((WARN, "脑子", f"{model} @ {base} · 没填 key（等环境变量）"))
    else:
        out.append((OK, "脑子", f"{model} @ {base} · key {_mask(key)}"))

    # 4. 记忆：人格那三份 + 这个月的日志
    ws = memory.workspace(cfg)
    for name in ("CONSTITUTION.md", "PARTNER.md", "STATE.md"):
        p = ws / name
        if p.exists():
            n = _lines(p)
            good = n > 0
            out.append((OK if good else WARN, name, f"{n} 行 · {p.stat().st_size} 字节"))
        else:
            out.append((WARN, name, "还没有这份（开机时会铺模板）"))
    today = _dt.date.today()
    logp = ws / "log" / f"{today:%Y-%m}.md"
    if logp.exists():
        when = _dt.datetime.fromtimestamp(logp.stat().st_mtime)
        out.append((OK, "日志", f"{logp.name} · {_lines(logp)} 行 · 最后改于 {when:%m-%d %H:%M}"))
    else:
        out.append((WARN, "日志", f"{today:%Y-%m}.md 还没开，今天没记东西"))

    # 5. 嗓子 / 耳朵
    tts_url = str(cfg.get("tts_url", "http://127.0.0.1:8899/v1/audio/speech"))
    if not cfg.get("speak_aloud"):
        out.append((WARN, "嗓子", "关着（config.speak_aloud=false）"))
    elif _port_open(tts_url):
        out.append((OK, "嗓子", f"说话服务在 · {tts_url.split('//')[-1].split('/')[0]}"))
    else:
        out.append((BAD, "嗓子", f"说话服务没起来 · {tts_url}"))
    if cfg.get("ears"):
        mode = {"hold": "按住说话", "always": "一直听着", "off": "关"}.get(str(cfg.get("ear_mode", "hold")), str(cfg.get("ear_mode")))
        out.append((OK, "耳朵", f"开着 · {mode} · 键 {cfg.get('ear_key', 'f9').upper()}"))
    else:
        out.append((WARN, "耳朵", "关着"))

    # 6. 权限
    try:
        import permissions as perm
        granted, timed = [], []
        for pid, name, _why, kind in perm.ROSTER:
            st = perm.state(cfg, pid)
            if st == perm.ALWAYS:
                granted.append(name)
            elif st == perm.TIMED:
                timed.append(f"{name}（还剩 {perm.left_minutes(cfg, pid)} 分钟）")
        bits = []
        if granted:
            bits.append("一直允许：" + "、".join(granted))
        if timed:
            bits.append("借出去：" + "、".join(timed))
        out.append((OK, "权限", "；".join(bits) if bits else "一格都没给（最安全）"))
    except Exception as e:                                          # noqa: BLE001
        out.append((WARN, "权限", f"读不出来：{type(e).__name__} {e}"))

    # 7. 闹钟
    try:
        data = json.loads((memory.data_dir(cfg) / "alarms.json").read_text(encoding="utf-8") or "[]")
        n = len(data) if isinstance(data, list) else len(data.get("alarms", []))
        out.append((OK if n else WARN, "闹钟", f"{n} 条"))
    except Exception:
        out.append((WARN, "闹钟", "还没有闹钟文件"))

    # 8. 插件
    try:
        import plug
        have = plug.available()
        want = cfg.get("plugins") or []
        if isinstance(want, str):
            want = [want]
        out.append((OK, "插件", f"装着 {len(want)} 个（{ '、'.join(map(str, want)) or '空' }）"
                               f" · 文件夹里 {len(have)} 个"))
    except Exception as e:                                          # noqa: BLE001
        out.append((WARN, "插件", f"读不出来：{type(e).__name__} {e}"))

    # 9. 封印（门 / 权限 / 插件那几项有没有被人动过）
    try:
        import guard
        ok, why = guard.check(cfg, memory.HOME)
        if cfg.get("_locked"):
            out.append((BAD, "封印", "对不上，已经锁回默认（门关、权限空、插件不装）——"
                                     "改过 config.json 的会看到这一条"))
        elif ok:
            out.append((OK, "封印", "对上了：门、权限、插件三样没被动过"))
        elif guard.dev_ok(memory.HOME):
            out.append((WARN, "封印", "这台是开发机（data/dev.marker），不锁"))
        else:
            out.append((WARN, "封印", why))
    except Exception as e:                                          # noqa: BLE001
        out.append((WARN, "封印", f"查不了：{type(e).__name__} {e}"))

    # 10. 磁盘
    try:
        free = shutil.disk_usage(memory.HOME).free / (1024 ** 3)
        out.append((OK if free > 2 else WARN, "磁盘", f"{memory.HOME.drive} 还剩 {free:.1f} GB"))
    except Exception:
        pass

    return out


def summary(rows: list[Check]) -> str:
    """一行汇总：几条、几个好、几个看一眼、几个坏。

    11-04 19:50 清单第 3 项「诊断页汇总计数偶尔对不上」：以前页面上是按
    `len(rows) - good - bad` 反推「看一眼」的，而且导出时会把这句话 **覆盖掉**
    换成「✓ 存好了：…」，回来就看不见计数了——两处都算「对不上」。
    现在汇总只走这一个函数，页面和导出文件用的是同一份 rows。
    """
    tally = {OK: 0, WARN: 0, BAD: 0}
    other = 0
    for s, _n, _d in rows:
        if s in tally:
            tally[s] += 1
        else:
            other += 1
    text = f"{len(rows)} 条：{tally[OK]} 好 · {tally[WARN]} 看一眼 · {tally[BAD]} 坏了"
    if other:
        text += f"（另有 {other} 条状态不明）"
    return text


def report(cfg: dict | None = None, rows: list[Check] | None = None) -> str:
    """整份诊断抄成文字，能存成文件发给月下。

    rows 给了就用给的（页面上正摊着的那一份），免得导出的文件和眼前的对不上。
    """
    if rows is None:
        rows = checks(cfg)
    mark = {OK: "✓", WARN: "!", BAD: "×"}
    now = _dt.datetime.now()
    head = [f"鲸屿诊断 · {now:%Y-%m-%d %H:%M:%S}", ""]
    body = [f"{mark[s]} {name}：{detail}" for s, name, detail in rows]
    tail = ["", f"（共 {summary(rows)}）"]
    return "\n".join(head + body + tail)


def save_report(cfg: dict | None = None, rows: list[Check] | None = None) -> Path:
    """写到工作区根上，名字带时间，不覆盖旧的。"""
    ws = memory.workspace(cfg)
    ws.mkdir(parents=True, exist_ok=True)
    path = ws / f"诊断-{_dt.datetime.now():%Y%m%d-%H%M}.txt"
    path.write_text(report(cfg, rows) + "\n", encoding="utf-8")
    return path


def _windows(pid: int) -> list[str]:
    try:
        import ctypes
        import ctypes.wintypes as wt
        u = ctypes.WinDLL("user32")
        out: list[str] = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(h, _l):
            if not u.IsWindowVisible(h):
                return True
            p = wt.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value != pid:
                return True
            n = ctypes.create_unicode_buffer(128)
            u.GetWindowTextW(h, n, 128)
            r = wt.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            out.append(f"{n.value} ({r.left},{r.top})-({r.right},{r.bottom})")
            return True

        u.EnumWindows(cb, 0)
        return out
    except Exception:                            # noqa: BLE001
        return []


def pack(cfg: dict | None = None, days: float = 3, max_bytes: int = 5 * 1024 * 1024,
         out: str | Path | None = None) -> Path:
    """一键诊断包：报告 + 近 N 天日志 + 遮过的 config 副本 + 窗口/进程 + manifest。只读原文件。"""
    cfg = cfg or memory.load_config()
    data = memory.data_dir(cfg)
    tmp = Path(tempfile.mkdtemp(prefix="diag_"))
    try:
        (tmp / "report.txt").write_text(report(cfg) + "\n", encoding="utf-8")
        logs = tmp / "logs"
        logs.mkdir()
        cutoff = time.time() - days * 86400
        for p in sorted(data.glob("*.log")):
            try:
                if p.stat().st_mtime < cutoff:
                    continue
                raw = p.read_bytes()
            except OSError:
                continue
            if len(raw) > max_bytes:
                raw = raw[:max_bytes] + b"\n...[truncated]\n"
            (logs / p.name).write_bytes(raw)
        safe = json.loads(json.dumps(cfg, ensure_ascii=False))
        for key in ("api_key", "token", "secret", "password", "passwd"):
            if key in safe:
                safe[key] = "***"
        text = memory.mask_secrets(json.dumps(safe, ensure_ascii=False, indent=2))
        (tmp / "config.json").write_text(text + "\n", encoding="utf-8")
        (tmp / "env.txt").write_text(
            f"pid={os.getpid()}\nversion={__import__('version').VERSION}\n"
            f"platform={platform.platform()}\n"
            + "\n".join("window: " + w for w in _windows(os.getpid())) + "\n",
            encoding="utf-8")
        rows = []
        for p in sorted(tmp.rglob("*")):
            if p.is_file():
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                rows.append(f"{p.relative_to(tmp).as_posix()}  {p.stat().st_size}  {h}")
        (tmp / "manifest.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
        dest = Path(out) if out else data / f"诊断-{_dt.datetime.now():%Y%m%d-%H%M}.zip"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(tmp.rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(tmp).as_posix())
        return dest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print(report())
