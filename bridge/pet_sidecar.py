"""一个只靠「一行一条文字」跟外面说话的小程序（后面叫它侧车）。

谁用它：`bridge/src/index.ts`（Coop 那边的 World 壳）负责把它启动起来，然后
一封一封地发请求；`test_sidecar.py` 也直接跟它对话来手测。

它认的格式（一行就是一条）：
    发：{"id":1,"op":"tools"}                  「你有哪些工具？」
    回：{"id":1,"ok":true,"tools":[...]}       一张清单
    发：{"id":2,"op":"call","name":"list_memory","args":{}}
                                              「帮我用 list_memory 这个工具」
    回：{"id":2,"ok":true,"result":{"text":"...","failed":false}}

三条规矩：
  · stdout 只准出一行行的回复。启动后把 sys.stdout 指到 stderr，这样任何 import
    进来的 print 都跑到 stderr，不会把回复冲乱。
  · 「门」在这里装上（ask=False：这个小程序没有界面，没法问人）。
  · 出错就回 {"ok":false,"error":"..."}，不把 Python 报错原文打到 stdout。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # newhouse/bridge/
CORE = HERE.parent                              # newhouse/
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

_OUT = sys.stdout
sys.stdout = sys.stderr                          # 协议行只走 _OUT

import gate            # noqa: E402
import memory          # noqa: E402
import tools           # noqa: E402
import world_tools     # noqa: E402


def _bind() -> None:
    """侧车里的门：来源是 plugin，看/动/终端会被拒；没有界面，所以 ask 一律不答应。"""
    tools.bind(gate.Gate(
        ask=lambda question: False,
        log=lambda line: memory.note_file("gate.log", line),
        cfg=None,
    ))


def _reply(obj: dict) -> None:
    _OUT.write(json.dumps(obj, ensure_ascii=False) + "\n")
    _OUT.flush()


def _handle(req: dict) -> dict:
    rid = req.get("id")
    op = str(req.get("op") or "")
    if op == "ping":
        return {"id": rid, "ok": True, "pong": True, "pid": os.getpid()}
    if op == "tools":
        return {"id": rid, "ok": True, "tools": world_tools.describe()}
    if op == "call":
        name = str(req.get("name") or "")
        args = req.get("args") or {}
        if not isinstance(args, dict):
            return {"id": rid, "ok": False, "error": "args 得是对象"}
        return {"id": rid, "ok": True, "result": world_tools.call(name, args)}
    return {"id": rid, "ok": False, "error": f"不认识的 op：{op!r}"}


def main() -> int:
    _bind()
    sys.stderr.write(f"[sidecar] pid={os.getpid()} ready\n")
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("请求得是对象")
            resp = _handle(req)
        except Exception as exc:                # noqa: BLE001
            resp = {"id": None, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        _reply(resp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
