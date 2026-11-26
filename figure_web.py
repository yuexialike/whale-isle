"""分层形象：把 Coop 那套 figure-frame 用 QWebEngineView 嵌进新家。

月下 11-01 14:38 说「直接把你现在用的这套 L2D 插件装到那个新版里头」，14:42 选了
「Coop 里我这个形象+表情动作那套」。计划见工作区 `计划-分层形象搬进新家.md`。

做法（方案 A，不重画一像素）：
  · `figure/` 里放的是 Coop 的 `web/figure-frame.{html,js}` + `whale/`（模型和贴图）+ `kit/`，
    原样搬过来，以后 Coop 改了模型跟着换文件就行。
  · 起一个只在本机转的小 HTTP 服务（`http://127.0.0.1:<随机端口>/`），因为
    figure-frame 是 ES module + fetch + 跨域图片，`file://` 直接跑不起来。
  · `QWebEngineView` 加载 `figure-frame-local.html`（比原版只改了脚本路径），
    背景透明，鼠标穿透（戳/拖还是由 body.py 接）。
  · 帧要靠外面推：每 33 ms 发一条 `{t:'tick', dt}`；它回 `frame`（含 layout）。
    Python 这边 5 Hz 拉一次 layout，够用来判「点在不在身上」。

对外（给 body.py 用）：
    fig = FigureWeb(scheme="deepseek-cape")
    fig.ready / fig.layout / fig.do("jump") / fig.set_scheme("kimi-cape")
    fig.place(x, facing) / fig.walk(x) / fig.pointer("move", {x, y})
    fig.set_size(w, h) —— 舞台尺寸变了要调，图会跟着缩放
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver
import threading
import time
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

import figure_pack

HERE = Path(__file__).resolve().parent
FIG_DIR = HERE / "figure"

# frame.log 只留现场，不当账本：单文件 2MB，最多留 .1 / .2 两份。
FRAME_LOG_LIMIT = 2 * 1024 * 1024
FRAME_LOG_KEEP = 2


def _now() -> float:
    """单独包一层：测试能把时间拨快，不用真等一分钟。"""
    return time.time()


def _frame_log_path() -> Path:
    p = HERE / "data" / "frame.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _trim_oversized(path: Path) -> None:
    """轮转前把超大的旧日志按整行截到最后 LIMIT 字节（旧的诊断行可以丢，新的不能丢）。"""
    try:
        if not path.exists() or path.stat().st_size <= FRAME_LOG_LIMIT * 2:
            return
        raw = path.read_bytes()[-FRAME_LOG_LIMIT:]
        cut = raw.find(b"\n")
        if cut >= 0:
            raw = raw[cut + 1:]
        path.write_bytes(raw)
    except Exception:                                  # noqa: BLE001
        pass


def _rotate_frame_log(path: Path | None = None) -> bool:
    """Frame.log 超过上限就挪成 .1、旧的 .1 挪成 .2，.2 丢掉。

    只在文件已经关掉之后调用；任何一步失败都只返回 False，不抛出去。
    """
    p = Path(path) if path is not None else _frame_log_path()
    try:
        if not p.exists() or p.stat().st_size < FRAME_LOG_LIMIT:
            return False
    except OSError:
        return False
    try:
        for i in range(FRAME_LOG_KEEP, 1, -1):
            prev = Path(str(p) + f".{i - 1}")
            nxt = Path(str(p) + f".{i}")
            if prev.exists():
                _trim_oversized(prev)
                if nxt.exists():
                    nxt.unlink()
                os.replace(prev, nxt)
        first = Path(str(p) + ".1")
        _trim_oversized(p)
        if first.exists():
            first.unlink()
        os.replace(p, first)
        return True
    except Exception:                                  # noqa: BLE001
        return False


def _append_frame_log(line: str) -> bool:
    """写一行再按大小轮转；写失败/轮转失败都不影响界面。"""
    try:
        p = _frame_log_path()
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line if line.endswith("\n") else line + "\n")
            fh.flush()
    except Exception:                                  # noqa: BLE001
        return False
    try:
        _rotate_frame_log(p)
    except Exception:                                  # noqa: BLE001
        pass
    return True


def entry_for(pack: dict) -> str:
    """包里 figure.js 的页面路径：必须带 `packs/<id>/` 前缀。

    为什么：kit 的 `entry` 是相对页面根解析的，写 `./figure.js` 会去
    `http://127.0.0.1:端口/figure.js` 取，报 Failed to fetch（L4 真机踩过）。
    """
    return "./" + pack["base"] + pack["entry"]

# kit 的约定（figure-frame.js 里写的）：小人画在**一个 256 单位的正方形**里，
# S 就是「1 单位 = 几像素」。所以舞台给窄了、或者只按高度算 S，人就会被左右裁掉。
UNITS_BOX = 256.0


class _Quiet(http.server.SimpleHTTPRequestHandler):
    """只服务两个根：`/frame/` 给运行壳（figure/），`/packs/<id>/` 给形象包；日志丢掉。"""

    def __init__(self, *args, frame_root: Path, packs_root: Path, **kwargs) -> None:
        self._frame_root = Path(frame_root)
        self._packs_root = Path(packs_root)
        super().__init__(*args, directory=str(self._frame_root), **kwargs)

    def log_message(self, *_a):        # noqa: D401 - silence is the point
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        """把网址翻成磁盘路径：/packs/<id>/… 去包目录，其余去 figure/。

        路径里出现 `..`、或者指到根外面，一律拒绝（返回一个不存在的 __forbidden__），
        不然 `http://127.0.0.1:<端口>/packs/../../config.json` 能把配置读走。
        """
        clean = unquote(str(path or "")).split("?", 1)[0].split("#", 1)[0]
        parts = [p for p in clean.split("/") if p]
        if parts[:1] == ["packs"]:
            if len(parts) < 2:
                return str(self._frame_root / "__missing_pack__")
            root = self._packs_root / parts[1]
            rest = parts[2:]
        else:
            root = self._frame_root
            rest = parts[1:] if parts[:1] == ["frame"] else parts
        target = root
        for seg in rest:
            target = target / seg
        try:
            resolved = target.resolve()
            resolved.relative_to(root.resolve())       # 指到根外面就抛 ValueError
        except (OSError, ValueError):
            return str(self._frame_root / "__forbidden__")
        return str(resolved)


class _Server:
    def __init__(self, frame_root: Path, packs_root: Path) -> None:
        handler = functools.partial(_Quiet, frame_root=frame_root, packs_root=packs_root)
        self.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path: str = "") -> str:
        return f"http://127.0.0.1:{self.port}/{path}"

    def stop(self) -> None:
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:                                  # noqa: BLE001
            pass


class FigureWeb(QWidget):
    """一个装着分层小人的方框。尺寸就是舞台，脚下那条件在底边。"""

    def __init__(self, scheme: str = "deepseek-cape", parent: QWidget | None = None,
                 theme: str = "dark", fps: int = 30) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")

        self.scheme = scheme
        self.theme = theme
        self.layout_state: dict | None = None
        self.world_words: list[str] | None = None
        self.error: str | None = None
        self.probe: str | None = None
        self._init_msg: dict | None = None
        self._inited = False
        self.ready = False
        self._pending: list[dict] = []      # 页面还没挂上 __send 之前的消息，先排队

        # 3-4：形象从 skin/figures/<包>/ 来；包坏了要说清楚再回落到老的 figure/whale，
        # 不许静默起一个空白小人（验收第 1 条）。
        self.pack: dict | None = None
        self.pack_error: str | None = None
        try:
            self.pack = figure_pack.read_pack()
            # entry 是相对页面根解析的（kit 用 importShim 直接吃这个字符串），
            # 所以得带包前缀：./packs/<id>/figure.js；base 仍给包目录，贴图/模型从那儿取。
            self._entry = entry_for(self.pack)
            self._export = self.pack["export"]
            self._base = self.pack["base"]
            self._model = self.pack.get("model")
        except figure_pack.PackError as e:
            self.pack_error = str(e)
            self._note_pack_error(str(e))
            self._entry = "./whale/figure.js"        # 老壳的入口，和 11-01 搬进来时一样
            self._export = "createWhaleBody"
            self._base = "whale/"
            self._model = None

        self._server = _Server(FIG_DIR, figure_pack.packs_dir())
        self._view = QWebEngineView(self)
        self._view.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._view.setFocusPolicy(Qt.NoFocus)
        self._view.setContextMenuPolicy(Qt.NoContextMenu)
        self._view.page().setBackgroundColor(Qt.transparent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self._view)

        self._view.loadFinished.connect(self._on_loaded)
        self._view.load(QUrl(self._server.url("figure-frame-local.html")))

        self._tick = QTimer(self)
        self._tick.setInterval(max(10, int(1000 / max(1, fps))))
        self._tick.timeout.connect(self._on_tick)

        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._on_poll)

    # ---------------------------------------------------------------- 内部
    def _note_pack_error(self, text: str) -> None:
        """包不能用时写一行 frame.log：回落可以，但不能不吭声。"""
        _append_frame_log(f"形象包不能用：{text}；回落到老壳 figure/whale")

    def _diag(self, raw) -> None:
        """只记现场：出错/异常/bounds 明显变化才写；正常最多每分钟一行。"""
        now = _now()
        raw_s = str(raw)[:600]
        err = None
        try:
            data = json.loads(raw) if raw else {}
            if isinstance(data, dict) and data.get("error"):
                err = str(data["error"])[:200]
        except Exception as exc:                       # noqa: BLE001
            err = f"bad poll: {type(exc).__name__}"
        bounds = self._bounds()
        changed = False
        last = getattr(self, "_diag_bounds", None)
        if last:
            try:
                changed = any(
                    abs(float(bounds[k]) - float(last[k])) >= (2.0 if k in ("W", "H", "floorY") else 0.01)
                    for k in bounds)
            except Exception:                          # noqa: BLE001
                changed = True
        if not err and not changed and now - getattr(self, "_diag_at", 0.0) < 60.0:
            return
        if err and err == getattr(self, "_diag_err", None) \
                and now - getattr(self, "_diag_at", 0.0) < 60.0:
            return
        self._diag_at = now
        self._diag_err = err
        self._diag_bounds = bounds
        line = "%s view=%dx%d bounds=%s poll=%s" % (
            time.strftime("%H:%M:%S"), self.width(), self.height(),
            json.dumps(bounds), raw_s)
        if err:
            line += " error=" + err
        _append_frame_log(line)

    def _bounds(self) -> dict:
        # 19:58 第三次修：kit 的约定是「小人画在一个 256 单位的正方形里」，S = 1 单位几像素。
        #  - 只按高度算（S = H/236）时人比舞台宽 → 左右被裁出一条竖线（19:50 看到的）。
        #  - 除 dpr（19:48 那版）更是错的：Qt 的 width() 本来就是逻辑像素。
        # 现在宽高取小的那个再除 256：正方形塞进舞台，人永远整只都在。
        w = max(1.0, float(self.width()))
        h = max(1.0, float(self.height()))
        s = min(w, h) / UNITS_BOX
        return {"W": w, "H": h, "floorY": h, "S": s}

    def _post(self, msg: dict) -> None:
        if not self._inited:
            # 19:09 踩到：window.__send 是页面里挂上去的，比这一步晚。先排队，init 之后再发，
            # 不然控制台报 "window.__send is not a function"，那条消息也就丢了。
            self._pending.append(msg)
            return
        js = "window.__send(%s);" % json.dumps(msg, ensure_ascii=False)
        self._view.page().runJavaScript(js)

    def _flush(self) -> None:
        queued, self._pending = self._pending, []
        for msg in queued:
            self._post(msg)

    def _on_loaded(self, ok: bool) -> None:
        if not ok:
            self.error = "figure frame 没加载出来"
            return
        # init 要等 frame 里的模块跑起来（它跑完才挂上 message 监听），所以先挂着，轮询里再发
        self._init_msg = {
            "t": "init",
            "entry": self._entry,
            "export": self._export,
            "base": self._server.url(self._base),
            "model": None,
            "scheme": self.scheme,
            "start": {"x": self.width() * 0.5, "facing": -1, "enter": None, "skin": None},
            "theme": self.theme,
            "bounds": self._bounds(),
            "language": "zh-CN",
        }
        self._tick.start()
        self._poll.start()

    def _on_tick(self) -> None:
        dt = self._tick.interval() / 1000.0
        self._view.page().runJavaScript(f"window.__tick({dt});")

    def _on_poll(self) -> None:
        def got(value) -> None:
            self._diag(value)
            if not value:
                return
            try:
                data = json.loads(value)
            except (TypeError, ValueError):
                return
            ready, err = data.get("ready"), data.get("error")
            self.probe = data.get("probe")
            if data.get("loaded") and self._init_msg is not None and not self._inited:
                self._inited = True
                self._post(self._init_msg)
                self._flush()
            if err:
                self.error = err
            if ready and not self.ready:
                self.ready = True
                self.world_words = data.get("words")
            frame = data.get("frame")
            if frame and isinstance(frame, dict):
                self.layout_state = frame.get("layout")

        self._view.page().runJavaScript(
            "JSON.stringify({loaded: window.__loaded, ready: window.__ready, error: window.__err, "
            "frame: window.__f, "
            "layout: (window.__body && typeof window.__body.layout === 'function') ? window.__body.layout() : null, "
            "probe: (typeof window.__send) + '|' + location.href})", got)

    # ---------------------------------------------------------------- 对外
    def set_size(self, w: int, h: int) -> None:
        self.resize(w, h)
        b = self._bounds()
        self._post({"t": "set", "state": {"bounds": b}})
        # 19:52 尺寸一变，舞台中心就变了；人自己不会跟着挪，得重新告诉它站哪。
        self.place(b["W"] * 0.5)

    def do(self, word: str) -> None:
        self._post({"t": "do", "word": word})

    def set_scheme(self, scheme: str, fade: float = 0.25) -> None:
        self.scheme = scheme
        self._post({"t": "scheme", "id": scheme, "fade": fade})

    def place(self, x: float, facing: int = -1) -> None:
        self._post({"t": "place", "x": x, "facing": facing})

    def walk(self, x: float, run: bool = False, walk_id: int = 1) -> None:
        self._post({"t": "walk", "x": x, "run": run, "id": walk_id})

    def set_tread(self, v: float, facing: int | None = None) -> None:
        """20:40 让她「原地迈步」：0 停、1 全速。

        这个界面里她是 Python 搬着窗口走的（页面只有一块 360 宽的舞台），kit 自己的 walk 用不上，
        mode 一直是 idle，脚一动不动 —— 看起来像贴图被拖过去。tread 是 kit 新加的那一档。
        """
        self._post({"t": "set", "state": {"tread": float(v)}})
        if facing in (1, -1):
            lay = self.layout_state or {}
            try:
                x = float(lay.get("x"))
            except (TypeError, ValueError):
                x = float(self.width()) * 0.5
            self._post({"t": "place", "x": x, "facing": facing})

    def pointer(self, kind: str, x: float, y: float) -> None:
        self._post({"t": "pointer", "type": kind, "p": {"x": x, "y": y}})

    def closeEvent(self, event) -> None:                   # noqa: N802 - Qt
        self._tick.stop()
        self._poll.stop()
        self._server.stop()
        super().closeEvent(event)


def preview() -> int:
    """自己开一个窗看看：`python figure_web.py [scheme]`。"""
    import sys

    from PySide6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scheme = args[0] if args else "deepseek-cape"
    autoquit = 0
    demo = '--demo' in sys.argv[1:]
    stage = (600, 560)
    for a in sys.argv[1:]:
        if a.startswith("--seconds="):
            autoquit = int(a.split("=", 1)[1])
        if a.startswith("--stage="):   # 舞台多大，图就多大：--stage=760x1100 看细节
            w, h = a.split("=", 1)[1].lower().split("x")
            stage = (int(w), int(h))

    win = QWidget()
    win.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    win.setAttribute(Qt.WA_TranslucentBackground, True)
    win.resize(*stage)
    fig = FigureWeb(scheme, win)
    lay = QVBoxLayout(win)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(fig)
    fig.set_size(*stage)
    screen = app.primaryScreen().availableGeometry()
    win.move(max(0, screen.right() - stage[0] - 20), max(0, screen.bottom() - stage[1] - 10))
    win.show()

    state = {"n": 0}

    def say() -> None:
        state["n"] += 1
        print(f"ready={fig.ready} err={fig.error} probe={fig.probe} "
              f"layout={fig.layout_state}", flush=True)
        if state["n"] > 40:
            fig._poll.timeout.disconnect(say)
    fig._poll.timeout.connect(say)
    if demo:
        words = ["jump", "wave", "nod", "hop", "shake", "look", "spin", "sit"]
        k = {"i": 0}

        def demo_step() -> None:
            if not fig.ready:
                return
            w = words[k["i"] % len(words)]
            k["i"] += 1
            print(f"do {w}", flush=True)
            fig.do(w)
        d = QTimer(fig)
        d.setInterval(2600)
        d.timeout.connect(demo_step)
        d.start()
    if autoquit:
        QTimer.singleShot(autoquit * 1000, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(preview())
