"""5-5 重启预算：只在子进程**自己退出**后重启，不 kill 任何进程。

状态写 `data/guard.json`，每次退出/重启写 `data/guard.log`。
退避：第 1 次 30s、第 2 次 2m、第 3 次 10m；第 4 次超预算，停手留「要人看一眼」。
正常跑够 300 秒后计数清零（偶发崩一次不会攒到死区）。
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
import time
from pathlib import Path

import memory

DELAYS = (30, 120, 600)
LONG_RUN = 300.0
MAX_FAILS = 3


def _path() -> Path:
    return memory.data_dir() / "guard.json"


def load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except Exception:                            # noqa: BLE001
        return {"fails": 0, "delay": 0, "exhausted": False, "last_exit": None}


def _save(st: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def _log(line: str) -> None:
    memory.note_file("guard.log", line)


def record_exit(exit_code: int, ran_sec: float, now: float | None = None) -> dict:
    """子进程退出后调：正常退出或跑够 5 分钟就清零，否则累计退避。"""
    st = load()
    if exit_code == 0 or ran_sec >= LONG_RUN:
        st.update({"fails": 0, "delay": 0, "exhausted": False})
        _log(f"exit={exit_code} ran={int(ran_sec)}s → 计数清零，下次正常起")
    else:
        fails = int(st.get("fails", 0)) + 1
        if fails > MAX_FAILS:
            st.update({"fails": fails, "delay": 0, "exhausted": True})
            _log(f"exit={exit_code} ran={int(ran_sec)}s → 连续崩 {fails} 次，超预算，停手")
        else:
            delay = DELAYS[min(fails - 1, len(DELAYS) - 1)]
            st.update({"fails": fails, "delay": delay, "exhausted": False})
            _log(f"exit={exit_code} ran={int(ran_sec)}s → 第 {fails} 次异常，退避 {delay}s")
    st["last_exit"] = int(exit_code)
    st["at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(st)
    return st


def can_start() -> tuple[bool, str]:
    st = load()
    if st.get("exhausted"):
        return False, f"上次连续崩 {st.get('fails')} 次，要人看一眼（guard.log）"
    return True, ""


def run_child(cmd: list[str]) -> int:
    """跑一次子进程并记账；返回退出码。不杀进程，只等它自己退。"""
    started = time.monotonic()
    code = subprocess.run(cmd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
    record_exit(code, time.monotonic() - started)
    return code


def main(argv: list[str]) -> int:
    import os
    import single_instance
    if not single_instance.acquire():
        memory.note_file("startup.log", "guardian: 已有一个在跑（互斥量），自己退")
        return 0
    os.environ["WHALE_ISLE_SUPERVISED"] = "1"     # 子进程别重复抢锁
    cmd = argv[1:] or [sys.executable, "main.py"]
    try:
        while True:
            ok, why = can_start()
            if not ok:
                _log(why)
                print(why)
                return 0
            st = load()
            if st.get("delay"):
                time.sleep(float(st["delay"]))
            code = run_child(cmd)
            st = load()
            if st.get("exhausted"):
                print(f"连续崩 {st['fails']} 次，停手；要人看一眼（见 data/guard.log）")
                return 0
            if code == 0 and st.get("fails", 0) == 0:
                return 0
    finally:
        single_instance.release()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
