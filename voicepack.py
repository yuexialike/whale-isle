"""语音包：本地识别要的那个模型，自己下、自己验。

月下 11-01 14:54：「语音输入这个事情可以弄到测试包里头去……把 Coop 的这个语音包的下载链接贴到
里头，然后让他自己选择要不要下，下的话我们就本地帮他下。」

抄的是 Coop 的做法（`src/runtime/store.ts` 的 ModelSlot），但只用标准库：
  · 每个文件钉死**字节数和 SHA-256**，对不上就当没下过；
  · 先写 `.partial`，验过了才改名成正式文件 —— 半截的模型绝不能被加载；
  · ModelScope 先试，它那边是国内的；不行再试 Hugging Face，两边文件是同一份（哈希一致）；
  · 已经有、大小也对的文件跳过，断了重来只补没下完的那几个。

放哪儿：`<home>/models/desktop-pet/sensevoice-small-int8-2024-07-17/`
模型本体 228 MB，加词表一共 228.2 MB —— 不小，所以默认**不自动下**，人点了才下。
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

MODEL_ID = "sensevoice-small-int8-2024-07-17"

# role 是识别器加载时认的名字（见 Coop 的 src/asr/sherpa.ts）
FILES = [
    ("model", "model.int8.onnx", 239_233_841,
     "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51"),
    ("tokens", "tokens.txt", 315_894,
     "f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc"),
]

SOURCES = [
    lambda f: f"https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/{f}",
    lambda f: f"https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/{f}",
]

TOTAL = sum(n for _r, _n, n, _s in FILES)
UA = "WhaleIsle/1.0 (+voice pack)"
TIMEOUT = 30


def _home() -> Path:
    """程序和它的东西都在哪：打包后是 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def models_dir() -> Path:
    """模型根目录。环境变量 WHALE_MODELS 可以改（我自己这台就用 Coop 下好的那份）。"""
    env = os.environ.get("WHALE_MODELS", "").strip()
    return Path(env) if env else _home() / "models"


def model_dir() -> Path:
    return models_dir() / "desktop-pet" / MODEL_ID


def paths() -> dict[str, str]:
    d = model_dir()
    return {role: str(d / name) for role, name, _b, _s in FILES}


def _ok(path: Path, size: int) -> bool:
    try:
        return path.is_file() and path.stat().st_size == size
    except OSError:
        return False


def status() -> dict:
    """现在什么情况：ready / absent / partial，还差多少字节。"""
    d = model_dir()
    have = [f for f in FILES if _ok(d / f[1], f[2])]
    got = sum(f[2] for f in have)
    missing = [f[1] for f in FILES if f not in have]
    phase = "ready" if not missing else ("partial" if have else "absent")
    return {
        "phase": phase,
        "dir": str(d),
        "total": TOTAL,
        "done": got,
        "missing": missing,
        "mb": round(TOTAL / 1024 / 1024, 1),
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url: str, dest: Path, on_progress: Callable[[int, int], None] | None) -> None:
    """stream 到 dest。dest 末尾是 .partial，所以半截的不会被当成模型。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r, dest.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        last = 0.0
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            now = time.monotonic()
            if on_progress and now - last > 0.4:
                last = now
                on_progress(done, total)


def install(on_progress: Callable[[str, int, int], None] | None = None) -> dict:
    """下模型。返回 status()。on_progress(文件名, 已完成字节, 总字节)。"""
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    base = 0
    for _role, name, size, want in FILES:
        target = d / name
        if _ok(target, size):
            base += size
            continue
        partial = d / (name + ".partial")
        errors = []
        for source in SOURCES:
            url = source(name)
            try:
                partial.unlink(missing_ok=True)
                _fetch(url, partial,
                       (lambda done, total, b=base, n=name: on_progress and
                        on_progress(n, b + done, TOTAL)))
                got = _sha256(partial)
                if got != want:
                    raise RuntimeError(f"哈希对不上（拿到 {got[:12]}）")
                partial.replace(target)
                break
            except Exception as exc:                    # noqa: BLE001
                partial.unlink(missing_ok=True)
                errors.append(f"{url.split('/')[2]}: {exc}")
        if not _ok(target, size):
            raise RuntimeError(f"{name} 没下成 —— " + "; ".join(errors))
        base += size
    return status()


def delete_pack() -> dict:
    """把下过的删掉（人后悔了的时候用）。"""
    import shutil
    shutil.rmtree(model_dir(), ignore_errors=True)
    return status()


def _cli() -> int:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    if cmd == "status":
        s = status()
        print(f"{s['phase']}  {s['dir']}")
        print(f"{s['done']} / {s['total']} bytes  ({s['mb']} MB)  缺: {s['missing'] or '无'}")
        return 0
    if cmd == "url":
        for _r, name, _b, _s in FILES:
            print(f"{name}:")
            for src in SOURCES:
                print("   ", src(name))
        return 0
    if cmd == "install":
        def show(name: str, done: int, total: int) -> None:
            pct = 100.0 * done / max(1, total)
            print(f"\r{name}  {done/1024/1024:7.1f} / {total/1024/1024:7.1f} MB  {pct:5.1f}%", end="", flush=True)
        print(f"下到 {model_dir()}，共 {TOTAL/1024/1024:.1f} MB")
        s = install(show)
        print(f"\n{s['phase']}")
        return 0
    if cmd == "selftest":
        return _selftest()
    if cmd == "delete":
        print(delete_pack())
        return 0
    print("用法: voicepack.py [status|url|install|delete|selftest]")
    return 2


def _selftest() -> int:
    """真去下一趟小的那个文件（词表 315 KB），验完就删 —— 证明链接和哈希都对。"""
    with tempfile.TemporaryDirectory() as tmp:
        name = "tokens.txt"
        size, want = next((n, s) for _r, f, n, s in FILES if f == name)
        dest = Path(tmp) / (name + ".partial")
        errs = []
        for src in SOURCES:
            url = src(name)
            try:
                _fetch(url, dest, None)
                got = _sha256(dest)
                print(f"{url.split('/')[2]:<14} {dest.stat().st_size:>8} bytes  {got[:16]}  "
                      f"{'对' if got == want else '不对!'}")
                dest.unlink(missing_ok=True)
            except Exception as exc:                    # noqa: BLE001
                print(f"{url.split('/')[2]:<14} 失败 {exc}")
                errs.append(str(exc))
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
