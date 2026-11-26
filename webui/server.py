"""新家的网页壳（最小版）：网页上一句话进，一句话出。

为什么要有这一层：月下 10-31 11:57 说，要的是「一个像 Coop 那种页面、别人也能操作」的
东西——同一套脑子，换张脸换个人就能用。所以脑子（`llm.talk`）不动，这里只做**一张脸**：
  GET  /            一个气泡 + 一个输入框
  POST /api/say     {"text": "…"} -> {"text": "它回的话"}
  GET  /api/who     {"name", "headline"}  给页面写标题、开场白

2026-10-31 11:57 月下说：「先拿自己做实验」。

安全：网页来的话**不是**月下在桌宠这边说的，所以这一轮开成 `source="web"`——
闸门不认它，工具只能读记忆，不许动电脑。要放行得先改闸门的规矩，那件事得他点头。
"""
from __future__ import annotations

import http.server
import json
import os
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent                      # newhouse/
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import gate as gatemod   # noqa: E402
import llm          # noqa: E402
import memory       # noqa: E402
import tools        # noqa: E402

PORT = int(os.environ.get("PETWEB_PORT", "8900"))
BIND = os.environ.get("PETWEB_BIND", "127.0.0.1")


def bind_gate() -> None:
    """网页这一路也要过闸门：这一轮的来源是 web，门应当按来源拒。

    网页里没有「做吗」的卡，所以 ask 一律不答应——真要对网页放行，
    得先有一张它看得见、点得着的卡，那是另一件事。
    cfg 传 None：每次现读 config，权限页改了立刻生效。
    """
    tools.bind(gatemod.Gate(
        ask=lambda question: False,
        log=lambda line: memory.note_file("gate.log", line),   # 拒了要有记录，任务表要验这个
        cfg=None,
    ))

_history: list[dict] = []
_lock = threading.Lock()
_busy = threading.Lock()                # 一次只让一句话进脑子，免得两句话搅在一起


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "petweb/0.1"

    def log_message(self, fmt, *args):  # 别把每句话都打到控制台
        pass

    # ---------- 小工具 ----------
    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", code)

    # ---------- GET ----------
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            page = HERE / "index.html"
            if not page.exists():
                return self._json({"error": "页面不在了"}, 500)
            return self._send(page.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/who":
            cfg = memory.load_config()
            return self._json({
                "name": cfg.get("name", "鱼鱼"),
                "headline": memory.state_headline(cfg),
                "model": cfg.get("api_model", "deepseek-chat"),
            })
        if path == "/api/ping":
            return self._json({"ok": True, "port": PORT})
        return self._json({"error": "没有这个地址"}, 404)

    # ---------- POST ----------
    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != "/api/say":
            return self._json({"error": "没有这个地址"}, 404)

        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json({"error": "听不懂发来的东西"}, 400)

        text = str(body.get("text") or "").strip()[:2000]
        if not text:
            return self._json({"error": "空话"}, 400)

        cfg = memory.load_config()
        if not _busy.acquire(timeout=90):
            return self._json({"error": "还在想上一句，等会儿"}, 429)
        try:
            with _lock:
                history = list(_history)
            # source 是程序自己标的，不是请求带来的——网页来的就写死 web，
            # 不从 body 读，客户端报什么都不算。
            answer = llm.talk(text, history, cfg, source="web", entry="web")
            with _lock:
                _history.append({"role": "user", "content": text})
                _history.append({"role": "assistant", "content": answer})
                del _history[:-24]       # 只留最近 12 轮
        finally:
            _busy.release()

        return self._json({"text": answer})


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    bind_gate()                       # 门先装上，再开门迎客
    srv = Server((BIND, PORT), Handler)
    print(f"网页壳开着：http://{BIND}:{PORT}/  （Ctrl+C 停）", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
