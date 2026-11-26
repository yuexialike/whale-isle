"""壳：跟「我是谁」无关的那一层。

只管四件事,每件都跟「活着」有关,不跟性格有关:
  1. 崩了要留证据(c 层崩溃 / Python 异常 / stderr)
  2. 开机先把上一个还活着的自己送走(只认 data/pid.txt,并确认它真是 python)
  3. 把自己记下来(下次按这个 PID 送走)
  4. 心跳:没人说话也醒一下

之所以单独一层:哪天换壳(从 PySide6 换到别的),换的是这个文件,
persona / gate / tools 一个字都不用动。
"""
from __future__ import annotations

import os
import subprocess
import sys

import memory


def arm_crash_log(data) -> None:
    """崩了也要留下证据:faulthandler(c 层) + stderr + excepthook。"""
    try:
        import faulthandler
        _crash = open(data / "crash.log", "a", encoding="utf-8")
        faulthandler.enable(file=_crash)
        sys.stderr = open(data / "stderr.log", "a", encoding="utf-8", buffering=1)

        def _hook(t, v, tb):
            import traceback
            memory.note_file("startup.log", "崩了: " + "".join(
                traceback.format_exception(t, v, tb))[:600])

        sys.excepthook = _hook
    except Exception:
        pass


def _lookalike_pids(script: str) -> list[int]:
    """找出还活着的「另一个我」：python/pythonw 跑着同一个 main.py 的那些。

    11-04 18:57：桌上同时跑过三份（源码一份、D:\\fish\\home 两份），三份都往同一个
    data 里写，看着就像「屏幕上两个我」。只认 pid.txt 的 retire_old 拦不住——
    pid.txt 里只有一个号，别的照样活着。
    """
    ps = ("Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" "
          "| ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }")
    quiet = 0x08000000
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, text=True, creationflags=quiet,
                             timeout=20).stdout
    except Exception:
        return []
    me = os.getpid()
    kin = _ancestor_pids(me)          # 11-08 21:1x：自己的祖宗不能杀，见下面那段注释
    hits: list[int] = []
    for line in out.splitlines():
        pid_s, _, cmd = line.partition("|")
        if not pid_s.strip().isdigit():
            continue
        pid = int(pid_s.strip())
        if pid == me or pid in kin or "main.py" not in cmd:
            continue
        if script.lower() in cmd.lower().replace("/", "\\"):
            hits.append(pid)
    return hits


def _ancestor_pids(pid: int) -> set[int]:
    """我这根进程链条上的老祖宗，一个都不许送走。

    11-08 21:07：月下点「鱼鱼的新家」打不开。查下来是这样的——venv 里的
    python.exe 起手会再拉一个真解释器，两个进程的命令行都带 main.py；
    扫同类把自己**爹**（外面那个 launcher 进程）认成了「另一个我」，
    taskkill 一枪把爹打死，自己跟着陪葬。所以先把自己往上数一遍，
    链条上的 PID 全部排除。
    """
    kin: set[int] = set()
    try:
        ps = ("Get-CimInstance Win32_Process "
              "| ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)\" }")
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, text=True, creationflags=0x08000000,
                             timeout=20).stdout
        parent: dict[int, int] = {}
        for line in out.splitlines():
            a, _, b = line.partition("|")
            if a.strip().isdigit() and b.strip().isdigit():
                parent[int(a.strip())] = int(b.strip())
        cur = pid
        for _ in range(8):
            par = parent.get(cur)
            if not par or par == cur or par in kin:
                break
            kin.add(par)
            cur = par
    except Exception:
        pass
    return kin


def retire_old(data) -> None:
    """开机先把上一个还活着的自己送走。

    只认 data/pid.txt 里那一个 PID,而且**先确认它真是 python.exe** 再动手——
    别的 python(TTS、画图)一根毛都不碰。这样外面的 .bat 就不必再管杀进程。
    """
    old = ""
    try:
        old = (data / "pid.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return
    if not old.isdigit() or int(old) == os.getpid():
        return
    quiet = 0x08000000  # CREATE_NO_WINDOW
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {old}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, creationflags=quiet, timeout=10).stdout
        head = out.splitlines()[0].lower() if out.strip() else ""
        if not head:
            return                       # 旧 pid 早没了：不写噪声
        if head.startswith('"python') and "python" in head:
            subprocess.run(["taskkill", "/F", "/PID", old],
                           capture_output=True, text=True, creationflags=quiet, timeout=10)
            memory.note_file("startup.log", f"送走旧实例 pid={old}")
        else:
            memory.note_file("startup.log", f"旧 pid={old} 不是 python({head[:40]}),不动")
    except Exception as e:
        memory.note_file("startup.log", f"送走旧实例失败: {type(e).__name__} {e}")


def retire_lookalikes(script) -> None:
    """把别的「我」也送走：跑着同一个 main.py 的 python/pythonw（不含自己）。"""
    try:
        pids = _lookalike_pids(str(script))
    except Exception as e:                                   # noqa: BLE001
        memory.note_file("startup.log", f"扫同类失败: {type(e).__name__} {e}")
        return
    memory.note_file("startup.log", f"扫同类: 我={os.getpid()} 找到 {pids}")
    quiet = 0x08000000
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, text=True, creationflags=quiet, timeout=10)
            memory.note_file("startup.log", f"送走同类实例 pid={pid}")
        except Exception as e:                               # noqa: BLE001
            memory.note_file("startup.log", f"送走同类 {pid} 失败: {type(e).__name__} {e}")
    memory.note_file("startup.log", "扫同类: 完了")


def claim_pid(data) -> None:
    try:
        (data / "pid.txt").write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def start_heartbeat(minutes: float, on_beat=None):
    """每 minutes 分钟醒一次。返回 QTimer(要留着,不然被回收就不跳了)。"""
    from PySide6.QtCore import QTimer

    def beat() -> None:
        memory.note_file("heartbeat.log", "醒了一下")
        if on_beat:
            try:
                on_beat()
            except Exception as e:
                memory.note_file("heartbeat.log", f"心跳里出错: {type(e).__name__} {e}")

    hb = QTimer()
    hb.timeout.connect(beat)
    hb.start(int(max(1.0, minutes) * 60 * 1000))
    return hb
