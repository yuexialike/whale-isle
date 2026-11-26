"""开场：铺满整块屏幕放一小段，放完淡出，露出主界面。

月下 19:52：「给这个软件加一个狂拽酷炫牛逼屌炸天的开场动画。」
20:23 又补：要「高端恢宏、大气上档次」。
20:14 他选了「直接开画我们自己的」——素材自己画，那四段只当参考，不进包。
21:02 他发来 B 站那条（07想zZ「也是根据大佬的操作搞了个 Deepseek 开机动画」），
      说「我要的就是这种感觉」——拆开看就是三件事：
        1) 黑场先出，一道斜光扫过去，画面才浮上来（不是一上来就挂着图）；
        2) 字是极细、字距拉得很开的一行，配四角的技术性小字（编号、时间、授权状态）；
        3) 最后落到一句「欢迎回来」，不是孤零零一个 logo。

这个文件只负责**放**，不管画。画面按顺序排在这儿：
    BOOT_FRAMES = [(素材, 毫秒, 起缩放, 止缩放), ...]
素材是 .png 就是静帧（带缓慢推拉），是 .mp4 就是一段视频（用 QMediaPlayer 解到
QVideoSink，再画进同一张画布——这样字和光还能压在上面，不会被 QVideoWidget 盖掉）。
相邻两幕之间自动交叉淡化（并伴一道光扫过）；点一下或按 Esc 直接跳过。

没有 QtMultimedia 或视频缺失时，视频那一幕自动跳过，静帧照放。

接口：
    show_boot(parent=None) -> BootScreen    # 已经 start() 过了
    BootScreen.finished 信号                  # 播完或跳过时发一次
"""
from __future__ import annotations

import math
import random
import sys
import time
from datetime import date
from pathlib import Path

try:                                    # 22:40 加：视频只有 768 方图，放大会发糊，靠它拉一把
    import numpy as np
except Exception:                        # 没装 numpy 就不锐化、不加颗粒，别的照放
    np = None

try:                                    # 22:54 起锐化交给 C 写的库：numpy 版一帧 50ms，卡就卡在这
    import cv2
except Exception:
    cv2 = None

Image = ImageFilter = None
try:                                    # Pillow 通常跟着别的包一起装了，优先用它
    from PIL import Image, ImageFilter
except Exception:
    Image = ImageFilter = None

from PySide6.QtCore import (
    QEasingCurve, QElapsedTimer, QLineF, QPointF, QPropertyAnimation, QRectF, Qt, QTime, QTimer, QUrl,
    Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPen, QPixmap,
    QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "data" / "boot"

VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv")

# (文件名, 停留毫秒, 起缩放, 止缩放)
# 20:39 月下的意思：第一张远山那格不要（每个人自己的鱼长得不一样，用别人家的远景没意义）。
# 21:33 他把正脸那格做成了会动的（Catimind / minimax H3 max，5 秒 768p），当第三幕。
# (文件名, 停留毫秒, 起缩放, 止缩放, 焦点(0~1))
# 焦点是缩放时盯着哪儿——视频第一帧是特写，所以第二幕得往脸上推，
# 推到差不多大了再切进去，不然远景→正脸→特写是两下硬跳（22:06 月下点的）。
# 22:35 月下点的：「最后那个画面和前一个不太符合，逻辑不太通」——07-front 是另一套
# 打光下带电流的近脸，硬接在破水后面像换了个人。所以撤掉它，改成停住视频最后一帧、
# 缓缓推向眼睛，字标压在这上面。HOLD 就是这个「定格」的占位名。
HOLD = "__hold__"
REVEAL = "__reveal__"     # 第一幕：黑场 → 流光线条 → 人像（23:27 月下改的）

REVEAL_LINE = "02-lines.png"        # 线条图（00:19 月下自己做的那张极简线稿）
REVEAL_PHOTO = "06-front.png.png"   # 线条底下要浮出来的那张人像
# 00:18 他说 AI 生成的那个「太垃圾了」，让我用代码做：五颜六色的线条从画面底下升上来、
# 聚成一个人形。所以第一幕不再靠视频，改成把线稿上亮的地方采样成一颗颗粒子，
# 每颗从屏幕底下飞到自己该在的位置——底部的先到、头顶的最后到，人形就从下往上长出来。
REVEAL_RISE_MS = 1000               # 最晚上路的那批延迟多久（错落感）
REVEAL_FLY_MS = 1000                # 一颗粒子从底下飞到位要多久（再乘一点随机）
REVEAL_SHARP_AT = 1700              # 这时真正的线稿开始淡进来，把颗粒收成干净的线
REVEAL_SHARP_MS = 700
REVEAL_PHOTO_AT = 2500              # 人像开始从线里浮出来
REVEAL_PHOTO_MS = 1300
REVEAL_TOTAL_MS = 3900
# 粒子的五种颜色（青、蓝、紫、粉、金）——「五颜六色」
REVEAL_PALETTE = ((120, 230, 255), (92, 150, 255), (176, 126, 255),
                  (255, 132, 200), (255, 214, 140))

BOOT_FRAMES = [
    (REVEAL, REVEAL_TOTAL_MS, 1.00, 1.12, (0.50, 0.44)),  # 第一幕：黑 → 彩色线条从底下聚合 → 人像
    ("08-swimup.mp4", 5000, 1.00, 1.04, (0.50, 0.45)),  # 第二幕：水下上浮 → 破水 → 抬头（22:29）
    (HOLD, 1600, 1.00, 1.22, (0.50, 0.42)),             # 第三幕：停在出水那张脸，慢慢往眼睛推
]

CROSSFADE_MS = 1200      # 两幕之间交叉淡化多久（01:22 从 800 拉到 1200：800 太急，像切开）
INTRO_MS = 1000          # 开头黑场 + 光扫过来的长度
SHARPEN = 0.75           # 视频帧反锐化的量（0 = 不锐化；1 以上开始出白边）
GRAIN_ALPHA = 0.05       # 一层细颗粒，盖住放大后的塑料感
FADE_OUT_MS = 700        # 最后这点时间压成软件底色，接主界面（23:19 他提的「过渡」）
TITLE_AT = 0.70          # 进度到这儿字标开始淡入（落在视频那幕里，不早不晚）
WELCOME_AT = 0.89        # 再往后一点，「欢迎回来」压上来
TITLE = "鲸 屿"
SUBTITLE = "W H A L E   I S L E"
CLOCK = "WHALE ISLE"          # 左上角那行
CLOCK_SUB = "SYNTHETIC COMPANION OS"
FPS_MS = 16

CYAN = QColor(120, 226, 240)


def _arg_size(flag: str) -> tuple[int, int] | None:
    """--size 1920x1080：把窗口固定成这个大小（录片头素材用）。"""
    if flag not in sys.argv:
        return None
    i = sys.argv.index(flag)
    try:
        w, h = sys.argv[i + 1].lower().split("x")
        w, h = int(w), int(h)
        if w > 100 and h > 100:
            return (w, h)
    except Exception:
        pass
    return None


def _arg_ms(flag: str) -> int:
    """--delay 1600：窗口先黑着等这么多毫秒，再让动画的钟走（等录屏起来）。"""
    if flag not in sys.argv:
        return 0
    i = sys.argv.index(flag)
    try:
        return max(0, int(sys.argv[i + 1]))
    except Exception:
        return 0


def _build_reveal_particles(pm: QPixmap, max_n: int = 3600) -> list[tuple]:
    """把线稿上亮的地方采样成一颗颗粒子：归一化坐标 + 颜色 + 起飞延迟。

    先缩到 420 宽再扫——原图 2500×1600 逐像素扫要好几秒，开机会卡在门口。
    """
    if pm is None or pm.isNull():
        return []
    img = pm.toImage().convertToFormat(QImage.Format_RGB32)
    small = img.scaledToWidth(420, Qt.SmoothTransformation)
    sw, sh = small.width(), small.height()
    if sw <= 0 or sh <= 0:
        return []
    pts = []
    try:
        mv = small.constBits()
        if not hasattr(mv, "__getitem__"):            # 老版本 PySide 给的是裸指针
            mv = memoryview(mv)
        for y in range(sh):
            row = y * sw * 4
            for x in range(sw):
                i = row + x * 4
                if mv[i] + mv[i + 1] + mv[i + 2] > 190:      # BGRA 顺序，够亮就当它是线
                    pts.append((x / sw, y / sh))
    except Exception as exc:                          # 采样失败就退化成「线稿直接淡进来」
        print(f"[boot] 线条粒子采样失败（{exc}），第一幕退回淡入")
        return []
    if not pts:
        return []
    if len(pts) > max_n:
        step = len(pts) / max_n
        pts = [pts[int(i * step)] for i in range(max_n)]
    rnd = random.Random(20261101)                        # 固定种子：每次开机同一种长法
    out = []
    for nx, ny in pts:
        # ny=1 在画面底下 → 先上路；ny=0 在头顶 → 最后到。人形就从下往上长出来。
        delay = (1.0 - ny) * REVEAL_RISE_MS * (0.72 + 0.56 * rnd.random())
        fly = REVEAL_FLY_MS * (0.78 + 0.62 * rnd.random())
        out.append((nx, ny,
                    delay, fly,
                    nx + rnd.uniform(-0.13, 0.13),           # 从屏幕底下哪儿冒出来（横向散开）
                    1.05 + rnd.uniform(0.0, 0.28),           # 起跑线在画面外
                    rnd.uniform(0.0, 6.283),                 # 摆动相位
                    rnd.randrange(len(REVEAL_PALETTE))))
    return out


def _edge_name() -> str:
    """这帧是用哪个库锐化的——日志里好认。"""
    if Image is not None:
        return "Pillow"
    if cv2 is not None:
        return "OpenCV"
    if np is not None:
        return "numpy（慢）"
    return "没有，跳过"


class BootScreen(QWidget):
    finished = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.BlankCursor)
        self.setWindowTitle("鲸屿 · 开场")

        self._acts: list[dict] = []
        for name, ms, z0, z1, *rest in BOOT_FRAMES:
            fx, fy = rest[0] if rest else (0.5, 0.5)
            if name == HOLD:
                self._acts.append({"kind": "hold", "ms": ms, "z0": z0, "z1": z1,
                                   "fx": fx, "fy": fy})
                continue
            if name == REVEAL:
                pm_line = QPixmap(str(ASSETS / REVEAL_LINE))
                self._acts.append({"kind": "reveal", "ms": ms, "z0": z0, "z1": z1,
                                   "fx": fx, "fy": fy,
                                   "line": pm_line,
                                   "photo": QPixmap(str(ASSETS / REVEAL_PHOTO)),
                                   "parts": _build_reveal_particles(pm_line)})
                continue
            p = ASSETS / name
            if not p.exists():
                continue
            if p.suffix.lower() in VIDEO_EXT:
                self._acts.append({"kind": "video", "path": p, "ms": ms, "z0": z0, "z1": z1,
                                   "fx": fx, "fy": fy})
            else:
                self._acts.append({"kind": "still", "pm": QPixmap(str(p)), "ms": ms, "z0": z0, "z1": z1,
                                   "fx": fx, "fy": fy})

        self._player = None
        self._sink = None
        self._vids: list[int] = []
        self._cur_vid: int | None = None
        self._frame_pm: QPixmap | None = None
        self._grain = self._make_grain()
        self._overlay: QPixmap | None = None
        self._glow: QImage | None = None                       # 粒子辉光那张 1/3 小图，复用
        self._glow_pen = QPen(QColor(255, 255, 255), 3.0, Qt.SolidLine, Qt.RoundCap)
        self._playing = False
        self._video_done = False

        self._total = sum(a["ms"] for a in self._acts) or 1
        self._t = 0
        self._dbg = "--fps" in sys.argv          # 想量帧间隔就 python boot.py --fps
        # 录素材用（16:0x 加的，给介绍视频当片头）：窗口固定成 --size 那么大、左上角 (0,0)，
        # 再用 gdigrab 录这块区域，出来就是原生 1920×1080，不用裁也不用压扁。
        self._cap = _arg_size("--size")
        self._delay = _arg_ms("--delay")         # 黑着等录屏起来，动画的钟从这会儿才开始走
        self._last_t = 0
        self._gaps: list[int] = []
        self._frame_seq = 0                       # 每来一帧视频 +1，画过就不重复画
        self._painted = (-1, -1, -1)
        self._frame_ms: list[float] = []          # 取一帧并转成 RGB 花多久
        self._sharp_ms: list[float] = []          # 锐化一帧花多久
        self._paint_ms: list[float] = []          # 一次重绘花多久
        self._clock = QElapsedTimer()
        self._done_yet = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ---------------- 对外 ----------------
    def start(self) -> None:
        self._setup_video()
        screen = QGuiApplication.primaryScreen().geometry()
        if self._cap:
            self.setGeometry(0, 0, self._cap[0], self._cap[1])
        else:
            self.setGeometry(screen)
        self.show()
        self.raise_()
        self.activateWindow()
        self._clock.start()
        self._timer.start(FPS_MS)

    def finish(self) -> None:
        """跳过：立刻开始淡出。"""
        if self._done_yet:
            return
        self._timer.stop()
        self._done_yet = True
        self._stop_video()
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(450)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.finished.connect(self._done)
        self._fade = fade
        fade.start()

    # ---------------- 视频 ----------------
    def _setup_video(self) -> None:
        self._vids = [i for i, a in enumerate(self._acts) if a["kind"] == "video"]
        if not self._vids:
            return
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
        except Exception as exc:                      # 没装 QtMultimedia：退回纯静帧
            print(f"[boot] 没有 QtMultimedia（{exc}），视频那幕跳过")
            self._drop_video()
            return
        self._sink = QVideoSink(self)
        self._player = QMediaPlayer(self)
        self._player.setVideoSink(self._sink)
        self._player.setAudioOutput(None)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.durationChanged.connect(self._on_duration)
        self._player.mediaStatusChanged.connect(self._on_status)

        # 22:52：第一段视频在窗口露出来之前就把源塞进去。原来等演到那一幕才 setSource，
        # 解码器初始化把界面卡了 2 秒（量出来 max 2099ms），就是「超级卡」的正主。
        self._cur_vid = self._vids[0]
        try:
            self._player.setSource(QUrl.fromLocalFile(str(self._acts[self._vids[0]]["path"])))
            self._player.pause()
        except Exception as exc:
            print(f"[boot] 预载视频没成（{exc}）")

    def _drop_video(self) -> None:
        self._acts = [a for a in self._acts if a["kind"] != "video"]
        self._vids = []
        self._total = sum(a["ms"] for a in self._acts) or 1

    def _stop_video(self) -> None:
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass

    def _act_at(self, t: int) -> int:
        acc = 0
        for i, a in enumerate(self._acts):
            if t < acc + a["ms"] or i == len(self._acts) - 1:
                return i
            acc += a["ms"]
        return max(0, len(self._acts) - 1)

    def _act_start(self, idx: int) -> int:
        return sum(a["ms"] for a in self._acts[:idx])

    def _on_frame(self, frame) -> None:
        if not frame.isValid():
            return
        t0 = time.perf_counter()
        img = frame.toImage()
        t1 = time.perf_counter()
        if img.isNull():
            return
        self._frame_pm = QPixmap.fromImage(self._sharpen(img))
        self._frame_seq += 1
        if self._dbg:
            self._frame_ms.append((t1 - t0) * 1000.0)                 # 取帧+转 RGB
            self._sharp_ms.append((time.perf_counter() - t1) * 1000.0)  # 锐化+转 QImage

    def _sharpen(self, img: QImage) -> QImage:
        """反锐化掩模：768 方图铺到 2560 上边是软的，只把边拉挺一点，不指望多出细节。"""
        if SHARPEN <= 0:
            return img
        try:
            if Image is not None:                     # Pillow：C 写的，一帧几毫秒
                img = img.convertToFormat(QImage.Format_RGB888)
                w, h, bpl = img.width(), img.height(), img.bytesPerLine()
                im = Image.frombytes("RGB", (w, h), bytes(img.constBits()),
                                     "raw", "RGB", bpl, 0)
                im = im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=68, threshold=3))
                return QImage(im.tobytes(), w, h, w * 3, QImage.Format_RGB888).copy()
            if cv2 is not None:
                img = img.convertToFormat(QImage.Format_RGB32)
                w, h = img.width(), img.height()
                arr = np.frombuffer(img.bits(), dtype=np.uint8).reshape(
                    h, img.bytesPerLine() // 4, 4)[:, :w, :]
                bgra = np.ascontiguousarray(arr)
                blur = cv2.GaussianBlur(bgra, (0, 0), 1.2)
                out = cv2.addWeighted(bgra, 1.0 + SHARPEN, blur, -SHARPEN, 0)
                return QImage(out.data, w, h, out.strides[0], QImage.Format_RGB32).copy()
            if np is None:                            # 都没有：不锐化，宁可糊也别卡
                return img
            img = img.convertToFormat(QImage.Format_RGB32)
            w, h = img.width(), img.height()
            arr = np.frombuffer(img.bits(), dtype=np.uint8).reshape(
                h, img.bytesPerLine() // 4, 4)[:, :w, :]
            rgb = arr[:, :, :3].astype(np.int16)
            blur = (rgb
                    + np.roll(rgb, 1, 0) + np.roll(rgb, -1, 0)
                    + np.roll(rgb, 1, 1) + np.roll(rgb, -1, 1)) * 0.2
            out = np.empty((h, w, 4), dtype=np.uint8)
            out[:, :, :3] = np.clip(rgb + (rgb - blur) * SHARPEN, 0, 255).astype(np.uint8)
            out[:, :, 3] = 255
            out = np.ascontiguousarray(out)
            return QImage(out.data, w, h, out.strides[0], QImage.Format_RGB32).copy()
        except Exception as exc:
            print(f"[boot] 这一帧没锐成（{exc}），原样画")
            return img

    def _make_grain(self) -> QPixmap:
        """一张 256 的噪点，画的时候错位铺满全屏——放大后的塑料感靠它盖。"""
        if np is None:
            return QPixmap()
        n = 256
        rng = np.random.default_rng(7)
        v = rng.integers(0, 256, (n, n), dtype=np.uint8)
        px = np.empty((n, n, 4), dtype=np.uint8)
        px[:, :, 0] = px[:, :, 1] = px[:, :, 2] = v
        px[:, :, 3] = 255
        px = np.ascontiguousarray(px)
        return QPixmap.fromImage(
            QImage(px.data, n, n, n * 4, QImage.Format_ARGB32).copy())

    def _on_duration(self, d: int) -> None:
        if d <= 0 or self._cur_vid is None:
            return
        act = self._acts[self._cur_vid]
        act["ms"] = d                                # 用真时长，别按估的算
        self._total = sum(a["ms"] for a in self._acts) or 1

    def _on_status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer
        if status in (QMediaPlayer.EndOfMedia, QMediaPlayer.InvalidMedia):
            self._video_done = True

    # ---------------- 内部 ----------------
    def _done(self) -> None:
        self._timer.stop()
        if self._dbg and self._gaps:
            pairs = self._gaps[1:]
            g = sorted(x for _, x in pairs)
            n = len(g)
            avg = sum(g) / n
            p95 = g[int(n * 0.95)] if n > 10 else max(g)
            bad = sum(1 for x in g if x > 33)
            print(f"[boot] 帧间隔 {n} 帧  平均 {avg:.1f}ms  p95 {p95}ms  最大 {max(g)}ms  "
                  f"超过 33ms 的 {bad} 帧")
            top = sorted(pairs, key=lambda p: -p[1])[:4]
            print("[boot] 顿住的几处: " + "  ".join(f"{t}ms 处卡 {x}ms" for t, x in top))
            if self._frame_ms:
                f = sorted(self._frame_ms)
                print(f"[boot] 取帧+RGB 平均 {sum(f)/len(f):.1f}ms 最大 {f[-1]:.1f}ms")
            if self._sharp_ms:
                s = sorted(self._sharp_ms)
                print(f"[boot] 锐化 平均 {sum(s)/len(s):.1f}ms 最大 {s[-1]:.1f}ms  "
                      f"({_edge_name()})")
            if self._paint_ms:
                q = sorted(self._paint_ms)
                print(f"[boot] 重绘一次 平均 {sum(q)/len(q):.1f}ms p95 {q[int(len(q)*0.95)]:.1f}ms "
                      f"最大 {q[-1]:.1f}ms  共 {len(q)} 次")
        self._stop_video()
        self.finished.emit()
        self.close()

    def _tick(self) -> None:
        # 用真时钟，不数帧：数帧会越数越快，标题和淡出会提前（20:48 踩的）。
        self._t = max(0, self._clock.elapsed() - self._delay)
        gap = self._t - self._last_t
        self._last_t = self._t
        if self._dbg:
            self._gaps.append((self._t, gap))

        vi = self._act_at(self._t)
        # 01:22 修「过渡像被切开」：下一幕是视频的时候，交叉淡化一开始就让它播，
        # 别等它整张图已经淡到全亮才突然起播——那一下就是「卡住又猛一下动了」。
        if vi + 1 < len(self._acts) and self._acts[vi + 1]["kind"] == "video" \
                and self._acts[vi]["kind"] != "video":
            end = self._act_start(vi) + self._acts[vi]["ms"]
            if self._t >= end - CROSSFADE_MS:
                vi += 1
        if self._player is not None and self._acts[vi]["kind"] == "video":
            if self._cur_vid != vi:                    # 换到别的视频：换源
                self._cur_vid = vi
                self._playing = False
                self._player.setSource(QUrl.fromLocalFile(str(self._acts[vi]["path"])))
            elif not self._playing:                    # 预载好了，到点直接播
                self._playing = True
                self._player.play()

        if self._t >= self._total:
            self.finish()
            return
        # 没新帧、没换幕、距上次画不到 40ms 就不重画：视频 24fps，硬顶着 60fps 画只是烧 CPU
        if (self._frame_seq != self._painted[0] or vi != self._painted[1]
                or self._t - self._painted[2] >= 40):
            self.update()

    def mousePressEvent(self, _ev) -> None:      # noqa: N802
        self.finish()

    def keyPressEvent(self, ev) -> None:         # noqa: N802
        if ev.key() in (Qt.Key_Escape, Qt.Key_Space, Qt.Key_Return):
            self.finish()
        else:
            super().keyPressEvent(ev)

    # ---------------- 画 ----------------
    def _paint_pm(self, p: QPainter, pm: QPixmap, alpha: float, zoom: float,
                  fx: float = 0.5, fy: float = 0.5) -> None:
        if pm is None or pm.isNull() or alpha <= 0.001:
            return
        w, h = self.width(), self.height()
        scale = max(w / pm.width(), h / pm.height()) * zoom
        dw, dh = pm.width() * scale, pm.height() * scale
        # 焦点贴到画面中心，但不许露出边缘
        x = min(0.0, max(w - dw, w / 2 - fx * dw))
        y = min(0.0, max(h - dh, h / 2 - fy * dh))
        p.setOpacity(min(1.0, alpha))
        p.drawPixmap(QRectF(x, y, dw, dh), pm, QRectF(pm.rect()))

    def _paint_pm_clipped(self, p: QPainter, pm: QPixmap, alpha: float, zoom: float,
                          fx: float, fy: float, rect: QRectF) -> None:
        """只画 rect 里那一块——线条从中间往外长、光带扫过都靠它。"""
        if pm is None or pm.isNull() or alpha <= 0.01:
            return
        p.save()
        p.setClipRect(rect)
        self._paint_pm(p, pm, alpha, zoom, fx, fy)
        p.restore()

    def _paint_reveal_particles(self, p: QPainter, act: dict, now: float,
                                ox: float, oy: float, dw: float, dh: float) -> None:
        """五颜六色的光条从画面底下升上来，飞到线稿上自己该在的位置。

        01:22 月下要「线条也有五颜六色的感觉，像粒子光效那种条」——所以不再画点：
        每颗粒子按它自己的弧线算出「现在」和「一小会儿之前」两个位置，拉成一段短光条，
        底下压一层宽的暗光当辉光、上面来一道亮的芯。按颜色分组，一组两次 drawLines。
        """
        parts = act.get("parts") or []
        if not parts:
            return
        w, h = self.width(), self.height()
        _TAIL = 0.085                          # 光条有多「长」（按飞行进度的比例）
        heads = [[] for _ in REVEAL_PALETTE]   # 正在飞的：光条
        settled = [[] for _ in REVEAL_PALETTE]  # 已经落位的：亮点

        def _pos(nx, ny, delay, fly, sx, sy, phase, t):
            e = 1.0 - (1.0 - t) ** 3           # 起手快、落位慢慢贴上去
            wave = math.sin(t * 6.2832 + phase) * 0.018 * (1.0 - e)
            return ((sx + ((ox + nx * dw) / w - sx) * e + wave) * w,
                    (sy + ((oy + ny * dh) / h - sy) * e) * h)

        for nx, ny, delay, fly, sx, sy, phase, ci in parts:
            t = (now - delay) / fly
            if t <= 0.0:
                continue                       # 还没轮到上升
            tx, ty = ox + nx * dw, oy + ny * dh
            if t >= 1.0:
                settled[ci].append(QPointF(tx, ty))
                continue
            hx, hy = _pos(nx, ny, delay, fly, sx, sy, phase, t)
            t0 = max(0.0, t - _TAIL)
            bx, by = _pos(nx, ny, delay, fly, sx, sy, phase, t0)
            heads[ci].append(QLineF(bx, by, hx, hy))

        # 辉光层：1/3 分辨率的小图，画细线再放大，自带柔边
        gw, gh = max(1, w // 3), max(1, h // 3)
        if self._glow is None or self._glow.width() != gw or self._glow.height() != gh:
            self._glow = QImage(gw, gh, QImage.Format_ARGB32_Premultiplied)
        self._glow.fill(Qt.transparent)
        _g = QPainter(self._glow)
        _g.setRenderHint(QPainter.Antialiasing, True)
        _g.scale(gw / float(w), gh / float(h))

        for ci, rgb in enumerate(REVEAL_PALETTE):
            col = QColor(*rgb)
            segs = heads[ci]
            if segs:
                g = QColor(col)
                g.setAlpha(150)
                self._glow_pen.setColor(g)
                _g.setPen(self._glow_pen)
                _g.drawLines(segs)
            pts = settled[ci]
            if pts:
                g = QColor(col)
                g.setAlpha(170)
                self._glow_pen.setColor(g)
                _g.setPen(self._glow_pen)
                _g.drawPoints(pts)
        _g.end()
        p.setOpacity(0.62)
        p.drawImage(QRectF(0.0, 0.0, float(w), float(h)), self._glow)
        p.setOpacity(1.0)

        # 芯：画在屏幕上，细、亮。这一段关掉抗锯齿——五千段短笔画开着 AA 一帧要一百毫秒
        # （01:24 量的），底下已经有柔光了，硬边反而更像「光」。
        p.setRenderHint(QPainter.Antialiasing, False)
        for ci, rgb in enumerate(REVEAL_PALETTE):
            col = QColor(*rgb)
            if heads[ci]:
                core = QColor(col)
                core.setAlpha(215)
                p.setPen(QPen(core, 2.0, Qt.SolidLine, Qt.RoundCap))
                p.drawLines(heads[ci])
            if settled[ci]:
                core = QColor(col)
                core.setAlpha(245)
                p.setPen(QPen(core, 2.6, Qt.SolidLine, Qt.RoundCap))
                p.drawPoints(settled[ci])
        p.setRenderHint(QPainter.Antialiasing, True)

    def _paint_reveal(self, p: QPainter, act: dict, at: float) -> None:
        """黑场 → 彩色线条从底下升上来聚成人形 → 人像从线里浮出来。"""
        w, h = self.width(), self.height()
        now = at * act["ms"]
        line, photo = act["line"], act["photo"]
        fx, fy = act["fx"], act["fy"]
        zoom = act["z0"] + (act["z1"] - act["z0"]) * at

        # 线稿画在哪儿（缩放 + 焦点），粒子得对齐同一个框
        dw, dh = w * zoom, h * zoom
        ox = min(0.0, max(w - dw, w / 2 - fx * dw))
        oy = min(0.0, max(h - dh, h / 2 - fy * dh))

        # 1) 五颜六色的线条从底下升上来、各自飞到位置
        self._paint_reveal_particles(p, act, now, ox, oy, dw, dh)

        # 2) 人形拼好，真正的线稿淡进来，把颗粒收成干净的线
        sk = min(1.0, max(0.0, (now - REVEAL_SHARP_AT) / REVEAL_SHARP_MS))
        if sk > 0:
            sk = sk * sk * (3 - 2 * sk)
            self._paint_pm(p, line, 0.95 * sk, zoom, fx, fy)

        # 3) 人像：从线里浮出来，把线整个盖掉（溶解）。
        #    23:59 去掉了原来「0.42 透明度把线留在人像上当光边」那一层：
        #    线稿和 06-front 是两张不同的画，叠在一起眼睛和轮廓对不齐，像重影。
        pk = min(1.0, max(0.0, (now - REVEAL_PHOTO_AT) / REVEAL_PHOTO_MS))
        if pk > 0:
            pk = pk * pk * (3 - 2 * pk)
            self._paint_pm(p, photo, min(1.0, 0.92 * pk + 0.08 * pk * pk), zoom, fx, fy)

    def _paint_act(self, p: QPainter, idx: int, alpha: float, zoom: float,
                   at: float = 0.0) -> None:
        act = self._acts[idx]
        if act["kind"] == "still":
            self._paint_pm(p, act["pm"], alpha, zoom, act["fx"], act["fy"])
        elif act["kind"] == "reveal":
            self._paint_reveal(p, act, at)
        elif act["kind"] == "hold":          # 定格：接着用视频最后一帧
            if self._frame_pm is not None:
                self._paint_pm(p, self._frame_pm, alpha, zoom, act["fx"], act["fy"])
        else:
            if self._frame_pm is not None:
                self._paint_pm(p, self._frame_pm, alpha, zoom, act["fx"], act["fy"])

    def _paint_sweep(self, p: QPainter, k: float) -> None:
        """一道斜光从左扫到右。k = 0→1；离开这段就什么都不画。"""
        if not 0.0 <= k <= 1.0:
            return
        w, h = self.width(), self.height()
        band = w * 0.16
        cx = -0.5 * w + k * 2.0 * w
        grad = QLinearGradient(cx - band, 0, cx + band, 0)
        a = int(190 * (1.0 - abs(k - 0.5) * 1.4))
        if a <= 0:
            return
        grad.setColorAt(0.00, QColor(150, 235, 255, 0))
        grad.setColorAt(0.45, QColor(205, 248, 255, a))
        grad.setColorAt(0.55, QColor(230, 252, 255, a))
        grad.setColorAt(1.00, QColor(150, 235, 255, 0))
        lean = w * 0.20
        poly = QPolygonF([
            QPointF(cx - band, 0), QPointF(cx + band, 0),
            QPointF(cx + band - lean, h), QPointF(cx - band - lean, h),
        ])
        p.setOpacity(1.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPolygon(poly)

    def _mono(self, p: QPainter, size_frac: float) -> QFont:
        f = QFont("Consolas")
        f.setPixelSize(max(9, int(self.height() * size_frac)))
        f.setLetterSpacing(QFont.AbsoluteSpacing, self.height() * 0.0035)
        p.setFont(f)
        return f

    def _paint_hud(self, p: QPainter, prog: float) -> None:
        """四角的技术性小字 + 底下那条细进度线。"""
        w, h = self.width(), self.height()
        pad = int(w * 0.032)
        box = self.rect().adjusted(pad, pad, -pad, -pad)
        self._mono(p, 0.0125)

        # 左上：系统名
        p.setOpacity(0.55)
        p.setPen(QColor(214, 232, 246))
        p.drawText(box, Qt.AlignLeft | Qt.AlignTop, CLOCK)
        self._mono(p, 0.0092)
        p.setOpacity(0.3)
        p.drawText(box.adjusted(0, int(h * 0.022), 0, 0), Qt.AlignLeft | Qt.AlignTop, CLOCK_SUB)

        # 右上：时钟
        self._mono(p, 0.0125)
        p.setOpacity(0.55)
        p.setPen(QColor(214, 232, 246))
        p.drawText(box, Qt.AlignRight | Qt.AlignTop, QTime.currentTime().toString("HH:mm"))

        # 左下：授权
        self._mono(p, 0.0105)
        p.setOpacity(0.42)
        p.setPen(CYAN)
        p.drawText(box.adjusted(0, 0, 0, -int(h * 0.006)),
                   Qt.AlignLeft | Qt.AlignBottom, "AUTHORIZATION  ·  VERIFIED")

        # 右下：出品
        self._mono(p, 0.0105)
        p.setOpacity(0.32)
        p.setPen(QColor(214, 232, 246))
        p.drawText(box.adjusted(0, 0, 0, -int(h * 0.006)),
                   Qt.AlignRight | Qt.AlignBottom, "POWERED BY  DEEPSEEK")

        # 底下那条线：走到底 = 播完
        y = h - int(h * 0.055)
        x0, x1 = int(w * 0.032), int(w * 0.968)
        p.setOpacity(0.16)
        p.setPen(QColor(180, 220, 240))
        p.drawLine(x0, y, x1, y)
        p.setOpacity(0.55)
        p.setPen(CYAN)
        p.drawLine(x0, y, x0 + int((x1 - x0) * min(1.0, prog)), y)

    def resizeEvent(self, _ev) -> None:          # noqa: N802
        """上下的暗、四角暗角、细颗粒——合成一张，每帧只画一次（22:36：三层分开画会卡）。"""
        w, h = max(1, self.width()), max(1, self.height())
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setPen(Qt.NoPen)

        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(4, 8, 18, 150))
        g.setColorAt(0.42, QColor(4, 8, 18, 0))
        g.setColorAt(0.78, QColor(4, 8, 18, 110))
        g.setColorAt(1.0, QColor(4, 8, 18, 235))
        p.fillRect(0, 0, w, h, QBrush(g))

        v = QRadialGradient(w / 2, h / 2, max(w, h) * 0.72)
        v.setColorAt(0.00, QColor(0, 0, 0, 0))
        v.setColorAt(0.60, QColor(0, 0, 0, 0))
        v.setColorAt(1.00, QColor(2, 6, 14, 170))
        p.fillRect(0, 0, w, h, QBrush(v))

        if not self._grain.isNull():
            p.setOpacity(GRAIN_ALPHA)
            p.drawTiledPixmap(0, 0, w, h, self._grain)
            p.setOpacity(1.0)
        p.end()
        self._overlay = pm

    def paintEvent(self, _ev) -> None:           # noqa: N802
        t0 = time.perf_counter()
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QColor("#05080f"))

        fade_in = min(1.0, self._t / INTRO_MS)
        cur, cur_at, acc = len(self._acts) - 1, 1.0, 0
        if self._acts:
            for i, a in enumerate(self._acts):
                if self._t < acc + a["ms"] or i == len(self._acts) - 1:
                    cur = i
                    cur_at = min(1.0, max(0.0, (self._t - acc) / a["ms"]))
                    break
                acc += a["ms"]
            act = self._acts[cur]
            zoom = act["z0"] + (act["z1"] - act["z0"]) * cur_at
            # 01:22 原来这里是 min(1, cur_at*ms/CROSSFADE_MS)，等于「上一幕已经淡到全亮，
            # 到边界又归零重淡一遍」——中间那一下黑，就是「顿」。当前幕恒为不透明，
            # 进来的那一幕只由 nxt_at 控制。
            alpha = fade_in if cur == 0 else 1.0
            self._paint_act(p, cur, alpha, zoom, cur_at)

            nxt_at = 0.0
            if cur + 1 < len(self._acts):          # 下一幕淡进来
                nxt = self._acts[cur + 1]
                nxt_at = max(0.0, (self._t - (acc + act["ms"] - CROSSFADE_MS)) / CROSSFADE_MS)
                self._paint_act(p, cur + 1, nxt_at, nxt["z0"])

        # 光：开场那一下，和换幕那一下（进视频那幕就不扫了，视频自己有光）
        self._paint_sweep(p, self._t / INTRO_MS)
        if nxt_at > 0.0 and cur + 1 < len(self._acts) and self._acts[cur + 1]["kind"] == "still":
            self._paint_sweep(p, nxt_at)

        # 上下暗、四角暗角、细颗粒都在这一层里，一次画完
        p.setOpacity(1.0)
        if self._overlay is not None:
            p.drawPixmap(0, 0, self._overlay)

        prog = self._t / self._total
        self._paint_hud(p, prog)

        # 字标：最后一段淡进来，细体 + 宽字距，上面压一条细线
        if prog >= TITLE_AT:
            a = min(1.0, (prog - TITLE_AT) / 0.16)
            box = self.rect().adjusted(0, 0, 0, -int(self.height() * 0.10))
            p.setOpacity(a)
            f = QFont("Microsoft YaHei UI")
            f.setPixelSize(max(28, int(self.height() * 0.062)))
            f.setWeight(QFont.Light)
            f.setLetterSpacing(QFont.AbsoluteSpacing, self.height() * 0.012)
            p.setFont(f)
            p.setPen(QColor(236, 244, 255))
            p.drawText(box, Qt.AlignHCenter | Qt.AlignBottom, TITLE)

            f2 = QFont("Consolas")
            f2.setPixelSize(max(10, int(self.height() * 0.015)))
            f2.setLetterSpacing(QFont.AbsoluteSpacing, self.height() * 0.012)
            p.setFont(f2)
            p.setPen(CYAN)
            p.drawText(box.adjusted(0, int(self.height() * 0.046), 0, int(self.height() * 0.006)),
                       Qt.AlignHCenter | Qt.AlignBottom, SUBTITLE)

            # 细线：字标上方，左右各留空，慢慢拉长
            lw = int(self.width() * 0.10 * a)
            cy = box.bottom() - int(self.height() * 0.062)
            p.setOpacity(a * 0.5)
            p.setPen(CYAN)
            p.drawLine(self.width() // 2 - lw, cy, self.width() // 2 + lw, cy)

        # 「欢迎回来」
        if prog >= WELCOME_AT:
            a = min(1.0, (prog - WELCOME_AT) / 0.14)
            p.setOpacity(a * 0.8)
            f3 = QFont("Microsoft YaHei UI")
            f3.setPixelSize(max(12, int(self.height() * 0.018)))
            f3.setLetterSpacing(QFont.AbsoluteSpacing, self.height() * 0.008)
            p.setFont(f3)
            p.setPen(QColor(214, 232, 246))
            p.drawText(self.rect().adjusted(0, int(self.height() * 0.02), 0, 0),
                       Qt.AlignHCenter | Qt.AlignTop, "欢迎回来")

        # 收尾：最后这一小段把画面匀匀地压成软件的底色，主界面从这层暗里浮上来
        left = self._total - self._t
        if left < FADE_OUT_MS and left > 0:
            k = 1.0 - left / FADE_OUT_MS
            p.setOpacity(min(1.0, k ** 1.4))
            p.fillRect(self.rect(), QColor(11, 16, 28))
        p.end()
        self._painted = (self._frame_seq, cur, self._t)
        if self._dbg:
            self._paint_ms.append((time.perf_counter() - t0) * 1000.0)


def show_boot(parent: QWidget | None = None) -> BootScreen | None:
    """主窗口起来之前调一次。返回的对象可以不接，专心的话用 finished。"""
    screen = BootScreen()
    if not screen._acts:
        return None
    if parent is not None:
        screen.setWindowIcon(parent.windowIcon())
    screen.start()
    return screen


def decide_play(cfg: dict, data: Path) -> bool:
    """启动时要不要播开场。**全程序只有这一处判断**（照着 dsh-boot-animation 的 decidePlay 学的）。

    cfg["boot_animation"]：
        "off"   —— 不播
        "start" —— 每次启动都播（默认）
        "daily" —— 每天第一次启动播
    读不到设置、文件坏了、写不进去：一律当 "start"。**绝不因为出过错就永远不播。**
    """
    mode = "start"
    try:
        raw = (cfg or {}).get("boot_animation", "start")
        if raw is not None:
            mode = str(raw).strip().lower()
    except Exception:
        mode = "start"

    if mode in ("off", "no", "false", "0", "关", "不播"):
        return False
    if mode not in ("daily", "day", "每天"):
        return True
    try:
        stamp = (Path(data) / "boot-played.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return True                      # 没这份记录也是「今天没播过」
    return stamp != date.today().isoformat()


def mark_played(data: Path) -> None:
    """真决定要播之后才记一笔。写不进去也不影响播放——最多下次「daily」多播一次。"""
    try:
        (Path(data) / "boot-played.txt").write_text(date.today().isoformat(), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":                        # 单独预览：python boot.py
    app = QApplication(sys.argv)
    s = show_boot()
    if s is None:
        print(f"没找到画面：往 {ASSETS} 里放 02.png / 06-front.png / 07-front.mp4")
        sys.exit(1)
    s.finished.connect(app.quit)
    sys.exit(app.exec())
