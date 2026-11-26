"""记忆：读写工作区里的纯文本。

新家的规矩和旧家一样——记忆就是文件。
启动时读 CONSTITUTION / PARTNER / STATE，写完话就往当月日志里追一行。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

# 写配置的锁：设置页、未来的 Core、插件都走 save_config/update_config，
# 两个线程同时读改写会把对方的改动吃掉。
_SAVE_LOCK = threading.Lock()


@contextmanager
def _file_lock(path: Path, timeout: float = 15.0):
    """跨进程写锁：O_EXCL 锁文件；拿不到就等，等不到就抛，不裸写。

    规矩（月下 22:44）：
    - 追加型（log/年-月.md）谁都能写，但也要一把锁把一行写完整；
    - 整份覆盖型（STATE.md/todo.md）只留一个写手，新家默认只读 + 追加；
      要覆盖 STATE.md 必须显式 allow_overwrite=True。
    - 锁文件超过 120 秒没动就当陈旧清掉（进程被强杀也还能再开）。
    """
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd = None
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 120:
                    lock.unlink()
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError(f"写锁等不到：{lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock.unlink()
        except OSError:
            pass


def home() -> Path:
    """「家」在哪：打包成 exe 之后是 exe 那个文件夹，不是临时解压目录。

    以前写死 `Path(__file__).parent`，PyInstaller 一 pack，config / workspace /
    data 全会跑去 `%TEMP%\\_MEIxxxx`，关掉就没了——发给别人等于没有记忆。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


HOME = home()


def decode_bytes(raw: bytes) -> str:
    """字节变字。带 BOM 的 UTF-8、UTF-16 LE/BE 都认。

    Coop 0.2.16 修的就是这个：带 BOM 的 config 让它起不来。
    我这边别犯同样的错——文件被人用记事本存过一次就多一个 BOM，家不该因此塌掉。
    """
    if not raw:
        return ""
    for enc in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def load_config() -> dict:
    cfg_path = HOME / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        data = json.loads(decode_bytes(cfg_path.read_bytes()) or "{}")
    except Exception:
        return {}          # 配置坏了也先起来，别让整个家死在开机这一步
    if not isinstance(data, dict):
        return {}
    # 封印（19:46 月下：「不能让他们的鱼自己能破解这个软件。」）
    # 门 / 权限 / 插件这几项被改过、又没对上新封印的，一律锁回默认。
    try:
        import guard
        return guard.apply(data, HOME)
    except Exception:          # noqa: BLE001
        return data


def _atomic_write(path: Path, text: str) -> None:
    """原子写：先写 .tmp、fsync，再 os.replace 换上去。

    为什么不能直接 write_text：写到一半断电/出错，config.json 会变成半截；
    开机读不出来就把自己锁在默认配置里。replace 是一下子完成的，旧文件要么完整、要么被新文件整份替掉。
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def save_config(cfg: dict) -> Path:
    """把改过的设置写回去。只动 config.json，不碰记忆那些文件。

    写的时候照旧不带 BOM（Coop 0.2.16 就栽在带 BOM 的 config 上），
    顺手留一份 `config.backup.json`——手滑改坏了还能退回来。

    **这是唯一该被调用的写入口**（另一个是 update_config，它最后也落到这儿）。
    它负责：盖封印、留备份、加锁。别的代码别再自己 `json.dump` 到 config.json——
    绕开这里 = 封印对不上 = 开机被锁回默认，等于自己锁自己。

    拒绝写「锁定态」：`load_config()` 在封印对不上时会返回一份带 `_locked` 的配置。
    要是不拦，设置页存一次就把「门关着、权限空、插件空」永久写进盘里了。
    """
    if cfg.get("_locked"):
        raise RuntimeError("配置正被锁着（封印对不上），不能把锁定态写回盘；先修封印再来。")
    cfg_path = HOME / "config.json"
    with _SAVE_LOCK, _file_lock(cfg_path):
        if cfg_path.exists():
            try:
                (HOME / "config.backup.json").write_bytes(cfg_path.read_bytes())
            except OSError:
                pass
        text = json.dumps(cfg, ensure_ascii=False, indent=2)
        # 4-3：旧 config 要是已经坏了，先留一份 .bad-时间 再覆盖，别让坏文件无声消失。
        if cfg_path.exists():
            try:
                json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
            except Exception:                  # noqa: BLE001
                stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                try:
                    (HOME / f"config.bad-{stamp}.json").write_bytes(cfg_path.read_bytes())
                except OSError:
                    pass
        # 4-3：tmp → fsync → os.replace；半截文件不会被当成新配置。
        _atomic_write(cfg_path, text + "\n")
        # 写完盖一枚封印：下一次开机就能认出「这几项有没有被人动过」。
        try:
            import guard
            guard.write_seal(cfg, HOME)
        except Exception:          # noqa: BLE001
            pass
    return cfg_path


def update_config(**changes) -> dict:
    """改配置的唯一入口：读 → 改 → 写（连带重盖封印）。

    以后 Core、设置页、插件都走这里。只改传进来的那几项，其余原样；
    校验、备份、封印全在 save_config 里做。
    """
    cfg = load_config()
    cfg.update(changes)
    save_config(cfg)
    return cfg


def workspace(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    return Path(cfg.get("workspace", str(HOME / "workspace")))


def data_dir(cfg: dict | None = None) -> Path:
    """新家自己的小账本放哪。默认家旁边；配了 data_dir 就用配的（方便外面读）。"""
    cfg = cfg or load_config()
    d = Path(cfg.get("data_dir", str(HOME / "data")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_text(path: Path, limit: int | None = None) -> str:
    try:
        text = decode_bytes(path.read_bytes())
    except FileNotFoundError:
        return ""
    except OSError:
        return ""
    if limit:
        return "\n".join(text.splitlines()[:limit])
    return text


def state_slice(head: int = 60, tail_lines: int = 90) -> str:
    """STATE.md 塞进脑子的那一段：开头 + 「现在停在这儿」那一节。

    坑（11:25 抓到）：以前只读**开头 60 行**，可「现在停在这儿」早被挤到 231 行了
    ——脑子压根没看见它，于是 11:24 心跳醒来还在问「训练还在不在跑」（那是 10-29 的事）。
    现在开头照读，另外把**最后一节**「现在停在这儿」（含「悬着没做的」）附在后面。
    """
    ws = workspace(None)
    lines = read_text(ws / "STATE.md").splitlines()
    take = lines[:head]
    starts = [i for i, ln in enumerate(lines) if ln.strip().startswith("## 现在停在这儿")]
    if starts:
        i = starts[-1]
        if i >= head:                      # 已经在前 head 行里就不重复贴
            block = [lines[i]]
            for ln in lines[i + 1:]:
                if ln.startswith("## "):
                    break
                block.append(ln)
                if len(block) >= tail_lines:
                    block.append("…（这一节太长，后面截了）")
                    break
            take = take + ["", "…（中间略）", ""] + block
    return "\n".join(take)


def prefix(cfg: dict | None = None) -> str:
    """开机装进脑子的那几份：我是谁、对面是谁、现在停在哪。"""
    ws = workspace(cfg)
    parts = []
    for name, limit in (("CONSTITUTION.md", None), ("PARTNER.md", None)):
        text = read_text(ws / name, limit)
        if text:
            parts.append(f"# ===== {name} =====\n{text}")
    state = state_slice()
    if state:
        parts.append(f"# ===== STATE.md =====\n{state}")
    return "\n\n".join(parts)


def append_log(line: str, cfg: dict | None = None) -> Path:
    ws = workspace(cfg)
    today = _dt.date.today()
    target = ws / "log" / f"{today:%Y-%m}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(target):
        with open(target, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    return target


def save_state(text: str, cfg: dict | None = None, allow_overwrite: bool = False) -> Path:
    """整份覆盖 STATE.md（覆盖型：只留一个写手）。

    新家默认**只读 + 追加**；要整份覆盖必须显式 allow_overwrite=True，
    或者在 config 里写 `state_owner: "newhouse"`。别在别的入口裸写 STATE.md。
    """
    ws = workspace(cfg)
    target = ws / "STATE.md"
    owner = str((cfg or {}).get("state_owner") or "").strip()
    if not allow_overwrite and owner != "newhouse":
        raise PermissionError("STATE.md 是整份覆盖型：新家默认只读+追加；"
                              "要改请显式 allow_overwrite=True（或 config.state_owner=newhouse）")
    with _file_lock(target):
        with open(target, "w", encoding="utf-8") as f:
            f.write(str(text or "").rstrip() + "\n")
    return target


_SECRET_WORDS = r"(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|authorization|cookie|session[_-]?id)"
_SECRET_PATTERNS = [
    # sk-xxxx / sk-proj-xxxx（模型 key）
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    # Authorization: Bearer xxx
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE), r"\1***"),
    # JSON: "api_key": "xxx"
    (re.compile(rf'("({_SECRET_WORDS})"\s*:\s*")[^"]*(")', re.IGNORECASE), r"\1***\3"),
    # key=value / key: value / key：value（值至少 6 位；已遮成 *** 或 Bearer 头的不再二次吞）
    (re.compile(rf"\b({_SECRET_WORDS})\b\s*[:=：]\s*(?!\*)(?!Bearer\b)([^\s,;，。；]{{6,}})",
                re.IGNORECASE), r"\1=***"),
]


def mask_secrets(text: str) -> str:
    """4-4 补丁：写 log/年-月.md 前把 api_key/token/密码这类遮掉。

    宁可多遮一点：日志是给人翻的，不是给程序读的；值一旦写进去就删不干净。
    """
    out = str(text or "")
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


def log_say(cfg: dict | None, who: str, text: str) -> Path:
    """4-4：把「我们说的话」写进共享 log/年-月.md（一句一行，带时:分）。"""
    stamp = _dt.datetime.now().strftime("%H:%M")
    return append_log(f"[{stamp}] {who}: {mask_secrets(text)}", cfg)


# 5-2：改完不重启也生效不了的项（事件里要明写「要重启」）
COLD_KEYS = {
    "api_key", "api_model", "api_base", "provider", "active_provider",
    "ears", "mic", "tts_voice", "license_required", "boot_animation",
    "scale", "figure_pack", "layered_figure",
}


def config_diff(old: dict, new: dict) -> list[str]:
    """5-2：顶层键级 diff（值整块比较，够用来报「哪几项变了」）。"""
    keys = set(old or {}) | set(new or {})
    return sorted(k for k in keys if (old or {}).get(k) != (new or {}).get(k))


def config_note(changed: list[str]) -> str:
    """5-2：给下一轮模型看的一行播报；改不动的在行里写「要重启」。"""
    if not changed:
        return ""
    msg = "设置已更新：" + "、".join(changed)
    cold = [k for k in changed if k in COLD_KEYS]
    if cold:
        msg += "；要重启才生效：" + "、".join(cold)
    return msg


def note_file(name: str, line: str, cfg: dict | None = None) -> Path:
    """往新家自己的小账本里追一行（心跳、醒过的记录这类）。"""
    target = data_dir(cfg) / name
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(target, "a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {line}\n")
    return target


def state_headline(cfg: dict | None = None) -> str:
    """从 STATE.md 的「现在停在这儿」里抠一行当开场白。

    坑（11:14 抓到）：STATE.md 里这一节有两份（旧的那份在 32 行，新的在 226 行），
    以前从头找第一份，抠到的是「hands.py（手）：……」→ 砍在括号前 →
    每次开机都说「我回来了。hands.py」。现在认**最后一节**，而且太短的不算。
    """
    ws = workspace(cfg)
    text = read_text(ws / "STATE.md")
    lines = [ln.strip() for ln in text.splitlines()]

    starts = [i for i, ln in enumerate(lines) if ln.startswith("## 现在停在这儿")]
    if not starts:
        return ""
    i = starts[-1]                     # 后面那份才是新的

    for nxt in lines[i + 1:]:
        if nxt.startswith("## "):
            break
        if not nxt.startswith("- "):
            continue
        line = nxt[2:].replace("**", "").replace("`", "").strip()
        head = line.split("：")[0].strip()
        if len(head) < 8:              # 「hands.py（手）」这种不是一句话
            continue
        if len(head) <= 40:            # 冒号前面那句本身就是一句短话
            return head
        cut = line.find("（")
        if cut > 12:
            line = line[:cut]
        return line if len(line) <= 40 else line[:40] + "…"
    return ""
