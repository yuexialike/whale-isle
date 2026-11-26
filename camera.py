"""摄像头：拍一张照，存到 data/camera/，交给脑子看。

只做一件事：打开摄像头（默认 0 号，config.camera_index 可改），抓一帧，存 JPEG，
把路径交给 `tools.LAST_IMAGE`，跟截图一样由 llm 贴进 messages。
权限那格是 `camera`（默认每次单独问），由调用方先过闸门。
"""
from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path


def _decode(img, ext: str) -> bytes:
    import cv2
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise RuntimeError("这一帧编不成图片")
    return buf.tobytes()


def shoot(cfg: dict, data_dir: Path, index: int | None = None) -> dict:
    """拍一张。返回 {path, w, h, index, mean}；打不开/没画面就抛 RuntimeError。"""
    import cv2

    base = Path(data_dir) / "camera"
    base.mkdir(parents=True, exist_ok=True)
    want = int(index if index is not None else (cfg.get("camera_index", 0) or 0))
    order = [want] + [i for i in (0, 1, 2, 3) if i != want]
    last = "没有可用的摄像头"
    for i in order:
        cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
        if not cap.isOpened():
            cap.release()
            last = f"{i} 号打不开"
            continue
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok or frame is None:
            last = f"{i} 号没画面"
            continue
        h, w = frame.shape[:2]
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = base / f"camera-{stamp}-{i}.jpg"
        blob = _decode(frame, ".jpg")
        path.write_bytes(blob)
        # 等一下再返回：有的摄像头第一帧是黑的，调用方要的是「这一帧」不是上一帧
        time.sleep(0.05)
        return {"path": str(path), "w": int(w), "h": int(h), "index": i,
                "mean": float(frame.mean()), "bytes": len(blob)}
    raise RuntimeError(last)
