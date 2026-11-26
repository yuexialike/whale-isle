"""出问题的时候，一键把该看的打包成一个压缩包。

月下 20:08 清单第 8 项：「出错日志一键打包」。
为什么要它：别人（以后买了鲸屿的人）说「它不动了」，我们能问的只有一句——
「把日志发我」。可日志散在 `data/` 里好几个文件、还有一堆他看不懂的路径，
让他一个个找、一个个拖，等于没要。所以做一颗按钮：点一下，桌面上出现
`反馈-20261104-2015.zip`，他拖进聊天窗口就行。

包里放什么（都是**只读**的，不改任何东西）：

  · `诊断.txt`      —— 跟设置页「诊断」里那份一模一样（`diag.report`）；
  · `logs/*.log`    —— `data/` 下每个日志的**尾巴**（默认每个文件最后 300 行）；
  · `系统.txt`      —— 版号、Windows 版本、Python、屏幕、装着的插件、权限授予情况；
  · `说明.txt`      —— 这包里是什么、从哪儿来、别删什么。

包里**不放**什么：

  · 不放 `config.json` 原件（里面有 API key）。只放一份抹过的摘要，key 只剩 `sk-abc…1234`；
  · 不放聊天正文、不放记忆（CONSTITUTION / STATE 那些是人的私事，不往包里塞）；
  · 不联网、不上传——只是打成 zip 放在他自己桌面上，发不发由他自己决定。

日志尾巴里万一混进了 `sk-` 开头的串（有的报错会把整个请求抄出来），也在这儿抹掉。
"""
from __future__ import annotations

import datetime as _dt
import json
import platform
import re
import sys
import zipfile
from pathlib import Path

import memory

TAIL_LINES = 300                 # 每个日志留最后多少行
KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")   # 万一日志里抄出了 key，抹掉


def _mask_keys(text: str) -> str:
    return KEY_RE.sub(lambda m: m.group(0)[:5] + "…（抹掉）", text)


def _tail(path: Path, n: int = TAIL_LINES) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"（读不出来：{exc}）"
    cut = lines[-n:]
    head = f"（共 {len(lines)} 行，这里是最后 {len(cut)} 行）\n" if len(lines) > len(cut) else ""
    return head + _mask_keys("\n".join(cut))


def desktop_dir() -> Path:
    """桌面。中文 Windows 上文件夹叫「桌面」，不是 Desktop——两个都试。"""
    home = Path.home()
    for name in ("Desktop", "桌面", "OneDrive/Desktop", "OneDrive/桌面"):
        p = home / name
        if p.is_dir():
            return p
    return home


def _sysinfo(cfg: dict) -> str:
    try:
        from version import STAGE, VERSION
    except Exception:                                  # noqa: BLE001
        VERSION, STAGE = "?", "?"
    lines = [f"鲸屿 {VERSION}（{STAGE}）", f"打好包的时间：{_dt.datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    lines.append(f"系统：Windows {platform.release()} {platform.version()}")
    lines.append(f"Python：{platform.python_version()}"
                 f"（{'打包好的 exe' if getattr(sys, 'frozen', False) else 'python 直接跑'}）")
    lines.append(f"机器：{platform.machine()}")

    # 屏幕（有几个屏、多大）——「点偏了」「站错屏」这类问题全靠这个看
    try:
        import screen
        w, h = screen.display_size()
        lines.append(f"主屏：{w}×{h}")
    except Exception:                                  # noqa: BLE001
        pass

    # 模型（地址和模型名可以给，key 不行）
    base = str(cfg.get("api_base", "") or "（空）")
    lines.append(f"模型：{cfg.get('api_model', '（空）')} @ {base}")
    lines.append(f"key：{diag_mask(cfg.get('api_key', ''))}")

    lines.append(f"形象：{cfg.get('figure_image', '')}")
    lines.append(f"权限块：{json.dumps(cfg.get('permissions', {}), ensure_ascii=False)}")
    lines.append(f"插件：{cfg.get('plugins', [])}")
    lines.append(f"闹钟：{cfg.get('alarms', '（看 data/alarms.json）')}")
    lines.append(f"激活门：{'开着' if cfg.get('license_required') else '关着'}")
    lines.append(f"工作区：{memory.workspace(cfg)}")
    return "\n".join(lines)


def diag_mask(key) -> str:
    key = str(key or "")
    if not key:
        return "（空）"
    if len(key) <= 12:
        return key[:2] + "…"
    return f"{key[:6]}…{key[-4:]}（{len(key)} 位）"


def _readme(where: str) -> str:
    return f"""这是鲸屿的反馈包。

从哪来：{where} 上「设置 › 诊断」里的「打包日志」按钮，{_dt.datetime.now():%Y-%m-%d %H:%M} 打的。
里面有什么：
  · 诊断.txt   —— 一条一条自己查的结果（哪儿通了、哪儿没通）
  · 系统.txt   —— 版号、Windows 版本、屏幕、插件、权限（API key 已经抹掉了）
  · logs/      —— 各个日志的最后 {TAIL_LINES} 行

里面没有：聊天记录、记忆文件、config.json 原件、API key。
要发给谁、发不发，都由你自己决定；这个包只放在你桌面上，没联网、没上传。
"""


def make_zip(cfg: dict | None = None, home: Path | None = None,
             dest_dir: Path | None = None) -> Path:
    """打一个包，返回它的路径。参数都能省：默认按本机配置、丢桌面。"""
    cfg = cfg or memory.load_config()
    home = Path(home or memory.HOME)
    dest_dir = Path(dest_dir or desktop_dir())
    dest_dir.mkdir(parents=True, exist_ok=True)

    stamp = _dt.datetime.now()
    out = dest_dir / f"反馈-{stamp:%Y%m%d-%H%M}.zip"
    n = 1
    while out.exists():                                # 一分钟内点两次也不覆盖前一个
        out = dest_dir / f"反馈-{stamp:%Y%m%d-%H%M}-{n}.zip"
        n += 1

    import diag
    # 20:20 修：以前这里用 `memory.data_dir(cfg)`，它读的是**真的** data 目录——
    # 测试传了临时 home 也没用，会把真日志打进测试的包（而且真的包里也会混进别处）。
    # 传了 home 就认 home，只有没传才回去问 memory。
    if cfg.get("data_dir"):
        data = Path(cfg["data_dir"])
    elif home != memory.HOME:
        data = Path(home) / "data"
    else:
        data = memory.data_dir(cfg)
    logs = sorted(p for p in data.glob("*.log") if p.is_file()) if data.exists() else []

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("诊断.txt", diag.report(cfg) + "\n")
        z.writestr("系统.txt", _sysinfo(cfg) + "\n")
        z.writestr("说明.txt", _readme(str(platform.node() or "这台电脑")))
        for p in logs:
            z.writestr(f"logs/{p.name}", _tail(p) + "\n")
        if not logs:
            z.writestr("logs/（没有日志）.txt", "data 目录下一个 .log 都没有。\n")
    memory.note_file("startup.log", f"打包反馈：{out.name}（{len(logs)} 个日志）")
    return out


if __name__ == "__main__":
    p = make_zip()
    print(p)
    print(f"{p.stat().st_size / 1024:.0f} KB")
