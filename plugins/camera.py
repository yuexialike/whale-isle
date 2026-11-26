"""摄像头插件：给脑子一个「看一眼镜头前」的工具。

月下 2026-11-21 13:05 说「缺啥补啥」，眼睛三条里这条本来没有。
权限走 `permissions` 的 `camera` 那一格：默认每次单独问，不问就不拍。
"""
from __future__ import annotations

NAME = "摄像头"
ABOUT = "拍一张照看看镜头前有什么。要月下亲口说，摄像头权限每次单独问。"
MANIFEST = {"id": "camera", "name": "摄像头", "version": "0.1", "api": 1}

_CTX: dict = {}


def setup(ctx: dict) -> None:
    _CTX.update(ctx or {})


def _shoot(args: dict) -> str:
    import turn

    t = turn.now()
    if t is None or t.source not in turn.HUMAN:
        return "（不拍：只有你亲口说的才作数，网页/插件/心跳来的不算。）"

    try:
        import i18n
        import memory
        import permissions
        cfg = _CTX.get("config") or memory.load_config()
        if not permissions.require(cfg, "camera", i18n.t("page.perm.what.camera")):
            return i18n.t("page.perm.camera_denied")
    except PermissionError as e:
        return __import__("i18n").t("page.perm.no_photo", err=e)
    except Exception as e:                      # noqa: BLE001
        return __import__("i18n").t("page.perm.no_photo", err=f"{type(e).__name__} {e}")

    try:
        import camera
        shot = camera.shoot(cfg, memory.data_dir(cfg))
    except Exception as e:                      # noqa: BLE001
        return f"（摄像头没拍成：{type(e).__name__} {e}）"

    try:
        import tools as toolmod
        toolmod.LAST_IMAGE = shot["path"]       # 跟截图一样，交给 llm 贴进 messages
    except Exception:                           # noqa: BLE001
        pass
    return (f"拍到了（{shot['w']}×{shot['h']}，{shot['index']} 号镜头）：{shot['path']}。"
            f"要我看看画面里有什么就说一声。")


TOOLS = [(
    {"type": "function",
     "function": {
         "name": "see_camera",
         "description": "用摄像头拍一张照，看看镜头前有什么。要月下亲口说；摄像头权限每次单独问。",
         "parameters": {"type": "object", "properties": {}, "required": []},
     }},
    _shoot,
)]
