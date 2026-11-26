"""QQ 插件：把 Coop 上那套本事，先用最小的一份装进鲸屿。

月下 2026-11-01 21:52：「其实可以直接把 QQ 连接的那个插件放到我们这里头。」

装的是「能连、能收、能回、能关」这四件，别的（表情库/好感度/空间/群管）以后一块一块搬。
形状照 Coop 那个 `cortico-world-qq-promax` 来，但**不复用它的运行时**——那份是 TypeScript + Node，
这里是 Python，两套塞一个包里打包会炸（见 `计划-QQ插件搬进鲸屿.md`）。

连接方式用 NapCat 的**反向 WS**（Coop 的默认）：我在 127.0.0.1:8080 开一个 WebSocket 服务端，
NapCat 连进来。所以两边不能同时开——同一个喇叭，谁占用谁说话。

只用标准库，一个 WebSocket 服务端自己写（见下面 `_Hub`）：这样打包不用多带一个包。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import socket
import struct
import threading
import time
import urllib.request
import uuid
from collections import deque

NAME = "QQ"
ABOUT = "连 NapCat（反向 WS），把群里/私聊的话递给我，我能用 qq_send 回。"
ICON = "鱼"

# 设置页那一行点「设置」时按这个单子长输入框；存在 config 的 "qq" 那一格。
SETTINGS_SECTION = "qq"
SETTINGS = [
    {"key": "wsPort", "label": "反向 WS 端口", "kind": "int",
     "hint": "NapCat 往这儿连。Coop 那边也用 8080，同一时间只能一个占着"},
    {"key": "wsPath", "label": "路径", "kind": "text", "hint": "默认 /onebot/v11/ws"},
    {"key": "token", "label": "口令", "kind": "text", "hint": "留空 = 谁都让连（只在本机）"},
    {"key": "groups", "label": "听的群", "kind": "lines", "hint": "一行一个群号"},
    {"key": "privates", "label": "听的私聊", "kind": "lines", "hint": "一行一个 QQ 号"},
    {"key": "replyGroups", "label": "群里回话", "kind": "bool"},
    {"key": "replyPrivates", "label": "私聊回话", "kind": "bool"},
    {"key": "proactiveEnabled", "label": "主动说话", "kind": "bool",
     "hint": "没人找她的时候，她自己想说话了就冒一句。默认关"},
    {"key": "proactiveMode", "label": "对谁主动", "kind": "text",
     "hint": "private / group / both，默认 both"},
    {"key": "proactiveDaily", "label": "每天最多几条", "kind": "int", "hint": "0 = 不限，默认 6"},
    {"key": "sleepStart", "label": "她几点睡", "kind": "text",
     "hint": "HH:MM。睡着不主动冒泡，回话照旧。默认 23:00"},
    {"key": "sleepEnd", "label": "她几点起", "kind": "text", "hint": "HH:MM，默认 07:30"},
]

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# 现在这份最小版自己的状态（模块级：工具函数和收消息那条线程共用）
_HUB: "_Hub | None" = None
_STOP = threading.Event()      # 3-2：卸插件时置位，让两条后台循环收工
_LOG = None           # setup() 里接上 memory.note_file("qq.log", …)，收发都往这儿写一行
_COUNT = 0            # 这条命收到多少句（设置页那行状态要报数）
_SEEN = deque(maxlen=300)   # 最近收到的句子，给 qq_history 查（不落盘，进程关了就没）
_PENDING_JOIN: dict = {}    # 收到的加群请求：flag -> {...}，给 qq_admin_join_* 用
_IMAGES = deque(maxlen=10)  # 最近收到的图（url + 时间），qq_view_image 用


def status():
    """设置页来问的时候报一句实话：连没连、连着谁、收到几条。"""
    hub = _HUB
    if hub is None:
        return False, "没起来（插件没装或装的时候出错了）"
    if hub.connected:
        return True, (f"已接入 {hub.host}:{hub.port} · 我是 {hub.self_id or '还不知道'} · "
                      f"收到 {_COUNT} 条 · 最近 {hub.last_at or '还没收到'}")
    return False, f"没连上（在 {hub.host}:{hub.port} 等 NapCat）"


def _note(text: str) -> None:
    """写一行 qq.log。收发的正文都落盘：出问题时不靠猜。"""
    f = _LOG
    if f is None:
        return
    try:
        f(text)
    except Exception:                                # noqa: BLE001
        pass


# ------------------------------------------------------------------ 小工具
def _as_lines(value) -> list[str]:
    """配置里的名单可能是 `[{"id":1,"enabled":true}]`、`[1, 2]`、`"1 2 3"`——统一成字符串列表。"""
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        parts = value.replace("，", " ").replace(",", " ").split()
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, (int, float)):
        return [str(int(value))]
    for item in value:
        if isinstance(item, dict):
            if item.get("enabled") is False:
                continue
            if item.get("id") is not None:
                out.append(str(item["id"]))
        elif item is not None:
            out.append(str(item).strip())
    return [x for x in out if x]


def _as_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _to_text(message) -> str:
    """把 OneBot 的 message 变成人话。图片/表情这种先只留个记号，别让模型瞎猜。"""
    if message is None:
        return ""
    if isinstance(message, str):
        return message.strip()
    parts: list[str] = []
    for seg in message:
        if isinstance(seg, str):
            parts.append(seg)
            continue
        kind = seg.get("type")
        data = seg.get("data") or {}
        if kind == "text":
            parts.append(str(data.get("text", "")))
        elif kind == "at":
            parts.append("@" + str(data.get("qq", "")))
        elif kind == "face":
            parts.append("[表情]")
        elif kind == "image":
            parts.append("[图片]")
        elif kind == "record":
            parts.append("[语音]")
        elif kind == "reply":
            parts.append("[回的某条]")
        elif kind == "forward":
            parts.append("[合并转发]")
    return "".join(parts).strip()


def _at_me(message, self_id: str) -> bool:
    if not message or isinstance(message, str):
        return False
    for seg in message:
        if isinstance(seg, dict) and seg.get("type") == "at":
            if str((seg.get("data") or {}).get("qq")) == self_id:
                return True
    return False


# ------------------------------------------------------------------ WebSocket
def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("对面断了")
        buf += chunk
    return buf


def _read_frame(sock: socket.socket):
    b1, b2 = _recv_exact(sock, 2)
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    mask = _recv_exact(sock, 4) if masked else b""
    data = _recv_exact(sock, length) if length else b""
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


def _send_frame(sock: socket.socket, opcode: int, data: bytes) -> None:
    header = bytes([0x80 | opcode])
    n = len(data)
    if n < 126:
        header += bytes([n])
    elif n < 65536:
        header += bytes([126]) + struct.pack(">H", n)
    else:
        header += bytes([127]) + struct.pack(">Q", n)
    sock.sendall(header + data)


class _Hub:
    """一个反向 WS 服务端：等 NapCat 连进来，收发 OneBot 帧。"""

    def __init__(self, host: str, port: int, path: str, token: str,
                 on_event, log) -> None:
        self.host = host or "127.0.0.1"
        self.port = int(port or 8080)
        self.path = path or ""
        self.token = (token or "").strip()
        self.on_event = on_event
        self.log = log
        self.self_id = ""
        self.connected = False
        self.last_at = ""              # 最近一次收到消息的时刻
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[threading.Event, dict]] = {}
        self._stop = False
        self._srv: socket.socket | None = None

    # ---------------------------------------------------------- 起服务
    def start(self) -> str:
        threading.Thread(target=self._serve, daemon=True).start()
        return f"在 {self.host}:{self.port}{self.path} 等 NapCat"

    def stop(self) -> None:
        self._stop = True
        for s in (self._srv, self._sock):
            try:
                if s is not None:
                    s.close()
            except Exception:                       # noqa: BLE001
                pass

    def _serve(self) -> None:
        while not self._stop:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                srv.bind((self.host, self.port))
                srv.listen(4)
            except OSError as e:
                # 端口被人占着多半是 Coop 那边还在用同一个喇叭（一个号只能一边在线）。
                # 不吵、不退出：隔一会儿再试一次，他什么时候把那边关了这边就接上。
                self.log(f"开不了 {self.host}:{self.port} —— {e}（多半是 Coop 那边还占着，等 20 秒再试）")
                try:
                    srv.close()
                except Exception:                   # noqa: BLE001
                    pass
                for _ in range(20):
                    if self._stop:
                        return
                    time.sleep(1)
                continue
            self._srv = srv
            self.log(f"在 {self.host}:{self.port}{self.path} 等 NapCat")
            while not self._stop:
                try:
                    conn, addr = srv.accept()
                except OSError:
                    break
                threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()
            return

    def _handle(self, conn: socket.socket, addr) -> None:
        try:
            conn.settimeout(30)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                head += chunk
                if len(head) > 65536:
                    return
            first = head.split(b"\r\n", 1)[0].decode("latin-1")
            headers: dict[str, str] = {}
            for line in head.decode("latin-1").split("\r\n")[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            if self.path and self.path not in first:
                self.log(f"路径不对，不回它：{first}")
                conn.close()
                return
            if not self._token_ok(first, headers):
                self.log("token 不对，没让它连")
                try:
                    conn.sendall(b"HTTP/1.1 401 Unauthorized\r\n\r\n")
                except OSError:
                    pass
                conn.close()
                return
            key = headers.get("sec-websocket-key", "")
            if not key:
                conn.close()
                return
            accept = base64.b64encode(
                hashlib.sha1((key + _GUID).encode()).digest()).decode()
            conn.sendall((
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
            ).encode())
            conn.settimeout(None)
            with self._lock:
                old, self._sock = self._sock, conn
                self.connected = True
            if old is not None:
                try:
                    old.close()
                except Exception:                   # noqa: BLE001
                    pass
            self.log(f"NapCat 连上了（{addr[0]}:{addr[1]}）")
            self._loop(conn)
        except Exception as e:                      # noqa: BLE001
            self.log(f"这条连接断了：{type(e).__name__} {e}")
        finally:
            with self._lock:
                if self._sock is conn:
                    self._sock = None
                    self.connected = False
                    self.log("NapCat 走了（等它重连）")

    def _token_ok(self, request_line: str, headers: dict) -> bool:
        if not self.token:
            return True
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer ") and auth[7:].strip() == self.token:
            return True
        if headers.get("access_token", "") == self.token:
            return True
        query = request_line.split("?", 1)[1] if "?" in request_line else ""
        for pair in query.split("&"):
            if pair.startswith(("access_token=", "token=")):
                if pair.split("=", 1)[1] == self.token:
                    return True
        return False

    def _loop(self, conn: socket.socket) -> None:
        while not self._stop:
            opcode, data = _read_frame(conn)
            if opcode == 8:                          # close
                return
            if opcode == 9:                          # ping
                _send_frame(conn, 10, data)
                continue
            if opcode not in (1, 2):
                continue
            try:
                payload = json.loads(data.decode("utf-8", "replace"))
            except Exception:                        # noqa: BLE001
                continue
            self._dispatch(payload)

    def _dispatch(self, payload: dict) -> None:
        echo = payload.get("echo")
        if echo is not None:
            with self._lock:
                slot = self._pending.pop(str(echo), None)
            if slot is not None:
                slot[1].update(payload)
                slot[0].set()
            return
        try:
            self.on_event(payload)
        except Exception as e:                      # noqa: BLE001
            self.log(f"处理事件坏了：{type(e).__name__} {e}")

    # ---------------------------------------------------------- 发
    def call(self, action: str, params: dict | None = None, timeout: float = 10.0) -> dict:
        conn = self._sock
        if conn is None:
            return {"status": "failed", "wording": "没连上 NapCat"}
        echo = "j" + uuid.uuid4().hex[:12]
        event = threading.Event()
        box: dict = {}
        with self._lock:
            self._pending[echo] = (event, box)
        try:
            body = json.dumps({"action": action, "params": params or {}, "echo": echo},
                              ensure_ascii=False).encode("utf-8")
            _send_frame(conn, 1, body)
        except Exception as e:                      # noqa: BLE001
            with self._lock:
                self._pending.pop(echo, None)
            return {"status": "failed", "wording": f"发不出去：{type(e).__name__} {e}"}
        event.wait(timeout)
        with self._lock:
            self._pending.pop(echo, None)
        return box or {"status": "failed", "wording": "等回包等不到"}


# ------------------------------------------------------------------ 配置
def _settings(cfg: dict) -> dict:
    """从家里的大配置里挑出 QQ 这一块。没有就用能跑起来的默认（对着 Coop 那份抄的）。"""
    qq = {}
    for key in ("qq", "qqbot", "qqBot"):
        part = cfg.get(key)
        if isinstance(part, dict):
            qq = part
            break
    worlds = cfg.get("worlds")
    if not qq and isinstance(worlds, dict) and isinstance(worlds.get("qqbot"), dict):
        qq = worlds["qqbot"]

    def pick(*names, default=""):
        for n in names:
            if n in qq and qq[n] not in (None, ""):
                return qq[n]
        return default

    return {
        "host": str(pick("wsHost", "host", default="127.0.0.1")),
        "port": int(pick("wsPort", "port", default=8080)),
        "path": str(pick("wsPath", "path", default="/onebot/v11/ws")),
        "token": str(pick("token", default="")),
        "groups": _as_lines(pick("groups", default="")),
        "privates": _as_lines(pick("privates", "peers", default="")),
        "owner": str(pick("owner", "master", "qqOwner", default="")),
        "reply_groups": bool(pick("replyGroups", default=True)),
        "reply_privates": bool(pick("replyPrivates", default=True)),
        "allow_send": bool(pick("allowSend", default=True)),
        # 主动说话这一套的开关；细参数在 _PRO_DEFAULTS 里
        "proactive": bool(pick("proactiveEnabled", "proactive", default=False)),
        "proactive_mode": str(pick("proactiveMode", default="both")).strip().lower(),
        "proactive_daily": _as_int(pick("proactiveDaily", default=6), 6),
        "sleep_start": str(pick("sleepStart", default="23:00")),
        "sleep_end": str(pick("sleepEnd", default="07:30")),
        # 嗓子走本机那条 OpenAI 形状的线（跟 tts.py 用同一个口），发 QQ 语音时要用
        "tts_url": str(cfg.get("tts_url") or "http://127.0.0.1:8899/v1/audio/speech"),
        "tts_voice": str(cfg.get("tts_voice") or "fish"),
    }


# ------------------------------------------------------------------ 收
def _on_event(payload: dict) -> None:
    hub = _HUB
    if hub is None:
        return
    post = payload.get("post_type")
    self_id = str(payload.get("self_id") or hub.self_id or "")
    if self_id:
        hub.self_id = self_id
    if post == "meta_event":
        return
    if post == "request":
        # 加群申请 / 邀请：先存着，等我要审的时候一起看。
        kind = str(payload.get("request_type") or "")
        flag = str(payload.get("flag") or "")
        if kind == "group" and flag:
            _PENDING_JOIN[flag] = {
                "flag": flag,
                "subType": "invite" if payload.get("sub_type") == "invite" else "add",
                "groupId": payload.get("group_id"),
                "userId": payload.get("user_id"),
                "comment": str(payload.get("comment") or ""),
                "at": time.time(),
            }
            _note(f"加群请求 群{payload.get('group_id')} QQ{payload.get('user_id')}")
        return
    if post != "message":
        return

    cfg_info = _CONF or {}
    sender = payload.get("sender") or {}
    user_id = str(payload.get("user_id") or "")
    if not user_id or user_id == self_id:
        return
    group_id = payload.get("group_id")
    where = "private"
    if payload.get("message_type") == "group" or group_id:
        where = "group"
    text = _to_text(payload.get("message"))
    imgs = list(_img_urls(payload.get("message")))
    for _u in imgs:
        _IMAGES.append({"url": _u, "at": time.time(),
                        "conv": f"{where}:{group_id if where == 'group' else user_id}"})
    if not text:
        if not imgs:
            return
        text = "[图片]"          # 只发图也算一句话，别在记日志前悄悄丢掉

    if where == "group":
        if cfg_info.get("groups") and str(group_id) not in cfg_info["groups"]:
            return
        if not cfg_info.get("reply_groups", True):
            return
        if not _at_me(payload.get("message"), self_id) and NAME not in text \
                and "鱼鱼" not in text and "小鱼" not in text:
            return                                  # 群里没叫我就先不吵
    else:
        if cfg_info.get("privates") and user_id not in cfg_info["privates"]:
            return
        if not cfg_info.get("reply_privates", True):
            return

    nick = str(sender.get("card") or sender.get("nickname") or user_id)
    stamp = time.strftime("%H:%M:%S")
    hub.last_at = stamp
    global _COUNT
    _COUNT += 1
    if where == "group":
        head = f"QQ群 {group_id} [{stamp}] {nick}({user_id})："
    else:
        head = f"QQ私聊 [{stamp}] {nick}({user_id})："
    _SEEN.append({"at": stamp,
                  "conv": f"{where}:{group_id if where == 'group' else user_id}",
                  "nick": nick, "uid": user_id, "text": text,
                  "mid": payload.get("message_id")})
    _note(f"收 {head}{text[:80]}")
    _pro_notify_reply(f"{where}:{group_id if where == 'group' else user_id}")
    hook = _CTX.get("hooks") if isinstance(_CTX, dict) else None
    if hook is None:
        _note("没有 hooks，这句递不上去")
        return
    hook.push(head + text, source="QQ")
    # 11-21 月下：「只收不回，别往 QQ 发任何东西，收到就记下来，等他说可以再开口」。
    # allowSend 关掉时连叫醒也不做——叫醒了只会生成一句发不出去的话，还在桌面上起泡。
    # 发送开回来，这里自动恢复叫醒（默认行为不变）。
    if (cfg_info or {}).get("allow_send", True):
        hook.wake("QQ 来消息了")


# ------------------------------------------------------------------ 工具
def _refresh_conf() -> None:
    """5-2：每次发送前重读 QQ 这一块（设置页保存会当场改 _CTX 里的 cfg）。"""
    global _CONF
    cfg = _CTX.get("config") if isinstance(_CTX, dict) else None
    if not isinstance(cfg, dict):
        try:
            import memory
            cfg = memory.load_config()
        except Exception:                    # noqa: BLE001
            return
    try:
        _CONF = _settings(cfg)
    except Exception:                        # noqa: BLE001
        pass


def _qq_send(args: dict) -> str:
    # 4-1：对外发消息先过权限（outbox）；4-2：T1/T3 只建草稿，人确认才发。
    _refresh_conf()
    try:
        import permissions as _perm
        _cfg = _CTX.get("config") if isinstance(_CTX, dict) else None
        _what = __import__("i18n").t("page.perm.what.outbox")
        _perm.require(_cfg, "outbox", _what)
    except PermissionError as e:
        return __import__("i18n").t("page.perm.blocked", err=e)

    info = _CONF or {}
    to = str(args.get("to") or "").strip()
    text = str(args.get("text") or "").strip()
    images = args.get("images") or []
    if isinstance(images, str):
        images = [images]
    images = [str(u).strip() for u in images if str(u).strip()]
    if not to or (not text and not images):
        return "得说清楚发给谁、说什么（只发图也要给 to）。"
    kind, _, ident = to.partition(":")
    if kind not in ("group", "private") or not ident:
        return "to 写成 group:<群号> 或 private:<QQ号>。"

    tier = _tier_for(info, kind, ident)
    if tier == "T2":
        return (f"{to} 不在名单里（也不是 owner），按规矩不发给陌生人。"
                "要发先把他加进 qq 名单，或你自己手动发。")
    if tier in ("T1", "T3"):
        try:
            import outbox as _outbox
            d = _outbox.create(to=to, kind=kind, ident=ident, text=text,
                               images=images, tier=tier)
        except Exception as e:                    # noqa: BLE001
            return f"草稿没建起来：{type(e).__name__} {e}"
        what = text[:40] + ("…" if len(text) > 40 else "")
        return (f"草稿 {d['id']} 备好了（发给 {to}，{what or '只发图'}）。"
                f"确认请回：确认 {d['id']}（10 分钟内有效）")
    # 已经在上面的入口过过一次权限；这里别再过第二次（ask_each 会问两遍、日志写两行）。
    return _send_now(kind, ident, text, images, checked=True)


def _tier_for(info: dict, kind: str, ident: str) -> str:
    """T0 本人 / T1 名单内 / T2 陌生人 / T3 群发（目前没有入口，先留档）。"""
    owner = str(info.get("owner") or "").strip()
    groups = [str(x) for x in (info.get("groups") or [])]
    privates = [str(x) for x in (info.get("privates") or [])]
    if kind == "private":
        if owner and ident == owner:
            return "T0"
        return "T1" if ident in privates else "T2"
    if kind == "group":
        return "T1" if ident in groups else "T2"
    return "T2"


def _send_now(kind: str, ident: str, text: str, images: list[str], checked: bool = False) -> str:
    """真正发送。T0 直接走这里；T1/T3 由人确认后由 outbox 回调到这里。

    `checked=True` 表示调用方（`_qq_send` 的入口）已经查过 outbox 权限了，这里别再查一次——
    否则一次发送会问两遍、perm.log 写两行。
    """
    if not checked:
        _refresh_conf()
        try:
            import permissions as _perm
            _cfg = _CTX.get("config") if isinstance(_CTX, dict) else None
            _what = __import__("i18n").t("page.perm.what.outbox")
            _perm.require(_cfg, "outbox", _what)
        except PermissionError as e:
            return __import__("i18n").t("page.perm.blocked", err=e)
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，发不出去。"
    info = _CONF or {}
    if not info.get("allow_send", True):
        return "这份配置里没开「能发」，只收不发。"
    segs = _build_segments(text, images)
    params = {"message_type": kind, "message": segs if segs else text}
    if kind == "group":
        params["group_id"] = int(ident)
    else:
        params["user_id"] = int(ident)
    res = hub.call("send_msg", params)
    ok = str(res.get("status", "")) == "ok" or res.get("retcode") == 0
    to = f"{kind}:{ident}"
    _note(f"发 {to}: {text[:80]} -> {'成功' if ok else res}")
    if ok:
        _pro_notify_sent(to)
        mid = (res.get("data") or {}).get("message_id")
        tail = f"（消息号 {mid}，撤回就用 qq_admin_recall）" if mid else ""
        return f"发出去了（{to}）：{text[:60]}{tail}"
    return f"没发出去：{res.get('wording') or res}"


try:
    import outbox as _outbox_mod
    _outbox_mod.set_sender(lambda d: _send_now(d["kind"], d["ident"], d["text"], d["images"]))
except Exception:                                # noqa: BLE001
    _outbox_mod = None


def _qq_status(_args: dict) -> str:
    hub = _HUB
    if hub is None:
        return "QQ 插件没起来。"
    info = _CONF or {}
    bits = [
        f"{'连着' if hub.connected else '没连上'}（{hub.host}:{hub.port}）",
        f"我是 {hub.self_id or '还不知道'}",
        f"群 {', '.join(info.get('groups') or []) or '无'}",
        f"私聊 {', '.join(info.get('privates') or []) or '无'}",
        f"回群 {'开' if info.get('reply_groups') else '关'}",
        f"回私聊 {'开' if info.get('reply_privates') else '关'}",
    ]
    if hub.last_at:
        bits.append(f"最近收到消息 {hub.last_at}")
    return "；".join(bits)


def _qq_poke(args: dict) -> str:
    """戳一戳。私聊戳对方，群里戳点名的那个人。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，戳不了。"
    to = str(args.get("to") or "").strip()
    who = str(args.get("user") or "").strip()
    kind, _, ident = to.partition(":")
    if kind not in ("group", "private") or not ident:
        return "to 写成 group:<群号> 或 private:<QQ号>。"
    try:
        if kind == "group":
            if not who:
                return "群里戳人得说戳谁（QQ 号）。"
            res = hub.call("group_poke", {"group_id": int(ident), "user_id": int(who)})
            where = f"群 {ident} 里的 {who}"
        else:
            res = hub.call("friend_poke", {"user_id": int(ident)})
            where = ident
    except (TypeError, ValueError):
        return "群号、QQ 号得是数字。"
    except Exception as e:                           # noqa: BLE001
        return f"戳的时候出错了（{type(e).__name__}）"
    ok = str(res.get("status", "")) == "ok" or res.get("retcode") == 0
    _note(f"戳 {where} -> {'成功' if ok else res}")
    return f"戳了 {where}" if ok else f"没戳成：{res.get('wording') or res}"


def _qq_history(args: dict) -> str:
    """查这条命收到的消息（内存里最近 300 条，不落盘）。"""
    if not _SEEN:
        return "这条命还没收到过消息。"
    conv = str(args.get("conv") or "").strip()
    kw = str(args.get("keyword") or "").strip()
    try:
        limit = int(args.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    rows = [m for m in _SEEN
            if (not conv or m["conv"] == conv)
            and (not kw or kw in m["text"])]
    if not rows:
        return "没找到。"
    rows = rows[-max(1, min(limit, 100)):]
    return "\n".join(f'{m["at"]} {m["conv"]} {m["nick"]}: {m["text"][:120]}' for m in rows)


def _ok(res: dict) -> bool:
    return str(res.get("status", "")) == "ok" or res.get("retcode") == 0


def _why(res: dict) -> str:
    return str(res.get("wording") or res.get("message") or res)


def _qq_admin_recall(args: dict) -> str:
    """撤回一条群消息（只调 delete_msg，不碰本地状态）。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，撤不了。"
    mid = str(args.get("messageId") or "").strip().lstrip("#")
    if not mid:
        return "得给 messageId（群消息前面那个 #号 后面的数字）。"
    try:
        res = hub.call("delete_msg", {"message_id": int(mid)})
    except (TypeError, ValueError):
        return "messageId 得是数字。"
    _note(f"撤回 {mid} -> {'成功' if _ok(res) else res}")
    return "撤回了。" if _ok(res) else f"没撤成：{_why(res)}"


def _qq_admin_notice(args: dict) -> str:
    """发群公告。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，发不了公告。"
    content = str(args.get("content") or "").strip()
    ident = str(args.get("group") or "").strip().lstrip("group:")
    if not content:
        return "公告总得有字。"
    if not ident:
        return "得说发到哪个群（群号）。"
    try:
        gid = int(ident)
    except (TypeError, ValueError):
        return "群号得是数字。"
    if _CONF.get("groups") and ident not in _CONF["groups"]:
        return f"群 {ident} 不在监听名单里，不发。"
    res = hub.call("_send_group_notice", {"group_id": gid, "content": content})
    if not _ok(res):
        # 有的 NapCat 版本叫 send_group_notice，回头再试一次。
        res = hub.call("send_group_notice", {"group_id": gid, "content": content})
    _note(f"公告 {ident} -> {'成功' if _ok(res) else res}")
    return f"公告发出去了（群 {ident}）。" if _ok(res) else f"没发成：{_why(res)}"


def _qq_admin_at_all(args: dict) -> str:
    """@全体，后面跟一句正文。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，喊不了人。"
    text = str(args.get("text") or "").strip()
    ident = str(args.get("group") or "").strip().lstrip("group:")
    if not ident:
        return "得说喊哪个群（群号）。"
    try:
        gid = int(ident)
    except (TypeError, ValueError):
        return "群号得是数字。"
    if _CONF.get("groups") and ident not in _CONF["groups"]:
        return f"群 {ident} 不在监听名单里，不喊。"
    segs = [{"type": "at", "data": {"qq": "all"}}]
    if text:
        segs.append({"type": "text", "data": {"text": " " + text}})
    res = hub.call("send_group_msg", {"group_id": gid, "message": segs})
    _note(f"@全体 {ident}: {text[:40]} -> {'成功' if _ok(res) else res}")
    return f"喊了（群 {ident}）。" if _ok(res) else f"没喊成：{_why(res)}"


def _qq_qzone_post(args: dict) -> str:
    """发一条 QQ 空间动态。走 NapCat 的 send_qzone_msg；没回 tid 就不算发出去。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，发不了动态。"
    text = str(args.get("text") or "").strip()
    if not text:
        return "动态总得有字。"
    images = args.get("images") or []
    if isinstance(images, str):
        images = [images]
    images = [str(u).strip() for u in images if str(u).strip()]
    if len(images) > 9:
        return "一条动态最多 9 张图。"
    for u in images:
        if not u.startswith(("http://", "https://", "base64://")):
            return f"附图只收网络地址或 base64，不收本机路径：{u[:40]}"
    params: dict = {"content": text,
                    "ugc_right": int(args.get("permission") or 1)}
    if images:
        params["images"] = images
    res = hub.call("send_qzone_msg", params, timeout=25.0)
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    tid = res.get("tid") or data.get("tid")
    _note(f"发动态 -> {'tid=' + str(tid) if tid else res}")
    if tid:
        return f"发出去了，tid={tid}。"
    return f"没确认发出去（协议端没回 tid）：{_why(res)}——先读一遍列表核对，别重复发。"


def _qq_qzone_read(args: dict) -> str:
    """读自己空间最近的动态。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，读不了动态。"
    try:
        num = int(args.get("num") or 5)
    except (TypeError, ValueError):
        num = 5
    res = hub.call("get_qzone_msg_list", {"num": max(1, min(num, 20))})
    data = res.get("data")
    feeds = None
    if isinstance(data, list):
        feeds = data
    elif isinstance(data, dict):
        feeds = data.get("msglist") or data.get("feeds")
    if not isinstance(feeds, list):
        return f"协议端返回的列表读不懂，不能据此判断空间是不是空的：{_why(res)}"
    if not feeds:
        return "列表是空的。"
    lines = []
    for f in feeds[:num]:
        if not isinstance(f, dict):
            continue
        content = str(f.get("content") or f.get("text") or "").replace("\n", " ")[:60]
        lines.append(f'{f.get("tid") or f.get("feed_id") or "?"} · {content}')
    return "\n".join(lines) if lines else "列表里没有能读的条目。"


def _qq_qzone_delete(args: dict) -> str:
    """删一条自己发的动态。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，删不了。"
    tid = str(args.get("tid") or "").strip()
    if not tid:
        return "得给 tid（读列表时前面那串）。"
    res = hub.call("delete_qzone_msg", {"tid": tid}, timeout=20.0)
    _note(f"删动态 {tid} -> {'成功' if _ok(res) else res}")
    return f"删了（tid={tid}）。" if _ok(res) else f"没删成：{_why(res)}"


def _tts_wav(text: str) -> bytes:
    """拿本机那条线合成一句 wav（跟 tts.py 同一个口）。失败就返回空。"""
    import urllib.request
    url = _CONF.get("tts_url") or "http://127.0.0.1:8899/v1/audio/speech"
    payload = json.dumps({"model": "tts-1", "input": text,
                          "voice": _CONF.get("tts_voice") or "fish",
                          "response_format": "wav"}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except Exception as e:                           # noqa: BLE001
        _note(f"合成语音失败：{type(e).__name__} {e}")
        return b""
    if data[:4] == b"RIFF" or "wav" in ctype.lower():
        return data
    _note(f"合成回来的不是 wav（{ctype}，{len(data)} 字节）")
    return b""


def _qq_voice(args: dict) -> str:
    """发一条 QQ 语音：先用本机嗓子合成 wav，再以 base64 塞进 record 段（NapCat 不认本机路径）。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，发不了语音。"
    to = str(args.get("to") or "").strip()
    text = str(args.get("text") or "").strip()
    if not to or not text:
        return "得说清楚发给谁、说什么。"
    if not _CONF.get("allow_send", True):
        return "这份配置里没开「能发」，只收不发。"
    kind, _, ident = to.partition(":")
    if kind not in ("group", "private") or not ident:
        return "to 写成 group:<群号> 或 private:<QQ号>。"
    if kind == "group" and _CONF.get("groups") and ident not in _CONF["groups"]:
        return f"群 {ident} 不在监听名单里，不发。"
    if kind == "private" and _CONF.get("privates") and ident not in _CONF["privates"]:
        return f"私聊 {ident} 不在名单里，不发。"
    wav = _tts_wav(text)
    if not wav:
        return "没合成出 wav（嗓子那条线没应），这条语音没发。"
    seg = {"type": "record",
           "data": {"file": "base64://" + base64.b64encode(wav).decode()}}
    params = {"message_type": kind, "message": [seg]}
    if kind == "group":
        params["group_id"] = int(ident)
    else:
        params["user_id"] = int(ident)
    res = hub.call("send_msg", params, timeout=30.0)
    _note(f"发语音 {to}: {text[:40]}（{len(wav)} 字节）-> {'成功' if _ok(res) else res}")
    if _ok(res):
        return f"语音发出去了（{to}）：{text[:60]}"
    return f"没发出去：{_why(res)}"


# ------------------------------------------------------------ 记事本 / 提醒
# 两样都只落在本机 data 目录里：qq-notebook.jsonl（一行一条）和 qq-reminders.json。
# 记事本是给我自己写小纸条用的；提醒到点会自己发到当初记下的那个会话。

def _data_path(name: str) -> str:
    base = _DATA_DIR or "data"
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    return os.path.join(base, name)


def _nb_load() -> list:
    rows = []
    try:
        with open(_data_path("qq-notebook.jsonl"), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and item.get("text"):
                    rows.append(item)
    except OSError:
        return []
    return rows


def _qq_note_save(args: dict) -> str:
    """往我的 QQ 记事本里添一条。返回编号，忘的时候用编号删。"""
    text = str(args.get("text") or "").strip()
    if not text:
        return "要记什么？给我一句话。"
    rows = _nb_load()
    nid = str(len(rows) + 1)
    row = {"id": nid, "text": text, "ts": int(time.time())}
    try:
        with open(_data_path("qq-notebook.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:
        return f"写不进记事本：{type(e).__name__} {e}"
    _note(f"记事本 +{nid}: {text[:40]}")
    return f"记下了（第 {nid} 条）：{text[:60]}"


def _qq_note_list(args: dict) -> str:
    """看记事本。默认只给最近十条，省得一次糊一大片。"""
    rows = _nb_load()
    if not rows:
        return "记事本还是空的。"
    try:
        limit = int(args.get("limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    rows = rows[-max(1, limit):]
    out = []
    for r in rows:
        when = time.strftime("%m-%d %H:%M", time.localtime(int(r.get("ts") or 0)))
        out.append(f'{r.get("id")}. [{when}] {r.get("text")}')
    return "\n".join(out)


def _qq_note_forget(args: dict) -> str:
    """删记事本里的一条。"""
    nid = str(args.get("id") or "").strip()
    if not nid:
        return "得给编号（qq_note_list 里前面那个数）。"
    rows = _nb_load()
    keep = [r for r in rows if str(r.get("id")) != nid]
    if len(keep) == len(rows):
        return f"没有第 {nid} 条。"
    try:
        with open(_data_path("qq-notebook.jsonl"), "w", encoding="utf-8") as fh:
            for r in keep:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError as e:
        return f"改不动记事本：{type(e).__name__} {e}"
    _note(f"记事本 -{nid}")
    return f"删了第 {nid} 条。"


_REL_RE = re.compile(r"^(?:in\s+)?(\d+)\s*(分钟|分|小时|时|天|minutes?|mins?|m|hours?|hrs?|h|days?|d)\s*(?:后|以后|之后)?$",
                     re.I)


def _parse_when(s: str, now: float | None = None) -> float | None:
    """把「10:30 / 明天 9:00 / 30分钟后 / 2小时 / 2026-11-03 20:00」变成时间戳。"""
    s = (s or "").strip()
    if not s:
        return None
    now = time.time() if now is None else now
    m = _REL_RE.match(s)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("分") or unit.startswith("m"):
            return now + n * 60
        if unit.startswith("小时") or unit.startswith("时") or unit.startswith("h"):
            return now + n * 3600
        return now + n * 86400
    low = s.lower()
    tm = time.localtime(now)
    day_offset = 0
    if low.startswith("明天") or low.startswith("tomorrow"):
        day_offset = 1
        s = s[2:] if low.startswith("明天") else s.split(None, 1)[-1]
        low = s.lower()
    if low.startswith("今天") or low.startswith("today"):
        s = s[2:] if low.startswith("今天") else s.split(None, 1)[-1]
        low = s.lower()
    clock = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s.strip())
    if clock:
        hh, mm, ss = int(clock.group(1)), int(clock.group(2)), int(clock.group(3) or 0)
        if hh > 23 or mm > 59 or ss > 59:
            return None
        base = time.mktime((tm.tm_year, tm.tm_mon, tm.tm_mday, 0, 0, 0, 0, 0, -1))
        ts = base + day_offset * 86400 + hh * 3600 + mm * 60 + ss
        if day_offset == 0 and ts <= now:        # 今天这个点已经过了 → 顺到明天
            ts += 86400
        return ts
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(s, fmt))
        except ValueError:
            continue
    return None


def _when_text(ts: float) -> str:
    now = time.localtime()
    d = time.localtime(ts)
    same = (d.tm_year, d.tm_yday) == (now.tm_year, now.tm_yday)
    tomorrow = time.localtime(time.time() + 86400)
    if same:
        head = "今天"
    elif (d.tm_year, d.tm_yday) == (tomorrow.tm_year, tomorrow.tm_yday):
        head = "明天"
    else:
        head = f"{d.tm_mon}月{d.tm_mday}日"
    return f"{head} {d.tm_hour:02d}:{d.tm_min:02d}"


def _rm_load() -> list:
    try:
        with open(_data_path("qq-reminders.json"), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [r for r in data if isinstance(r, dict) and r.get("id")]
    except (OSError, json.JSONDecodeError):
        return []


def _rm_save(rows: list) -> None:
    try:
        with open(_data_path("qq-reminders.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
    except OSError as e:
        _note(f"提醒存不下来：{type(e).__name__} {e}")


def _qq_remind_add(args: dict) -> str:
    """记一条提醒；到点我会自己把这句话发到当初那个会话。"""
    text = str(args.get("text") or "").strip()
    when_raw = str(args.get("when") or "").strip()
    to = str(args.get("to") or "").strip()
    if not text or not when_raw:
        return "得说清「什么时候」和「提醒什么」。"
    ts = _parse_when(when_raw)
    if ts is None:
        return "这个时间我读不懂，试试「10:30」「明天 9:00」「30分钟后」。"
    rows = _rm_load()
    rid = "r" + time.strftime("%m%d%H%M%S")
    rows.append({"id": rid, "text": text, "when": ts, "to": to,
                 "created": time.time(), "done": False})
    _rm_save(rows)
    _note(f"提醒 +{rid} {_when_text(ts)}：{text[:40]}")
    return f"记下了：{_when_text(ts)} 提醒——{text[:60]}"


def _qq_remind_list(args: dict) -> str:
    rows = [r for r in _rm_load() if not r.get("done")]
    if not rows:
        return "没有还没到点的提醒。"
    rows.sort(key=lambda r: float(r.get("when") or 0))
    out = []
    for r in rows:
        who = r.get("to") or "（记的时候的会话）"
        out.append(f'{r.get("id")} · {_when_text(float(r.get("when") or 0))} · {r.get("text")} · {who}')
    return "\n".join(out)


def _qq_remind_remove(args: dict) -> str:
    rid = str(args.get("id") or "").strip()
    if not rid:
        return "得给编号（qq_remind_list 里前面那串）。"
    rows = _rm_load()
    keep = [r for r in rows if str(r.get("id")) != rid]
    if len(keep) == len(rows):
        return f"没有 {rid} 这条。"
    _rm_save(keep)
    _note(f"提醒 -{rid}")
    return f"删了 {rid}。"


def _reminder_loop() -> None:
    """每 20 秒看一眼有没有到点的；到了就发出去，然后标成做过。"""
    while not _STOP.is_set():
        if _STOP.wait(20):
            break
        hub = _HUB
        if hub is None or not hub.connected:
            continue
        rows = _rm_load()
        changed = False
        for r in rows:
            if r.get("done"):
                continue
            try:
                due = float(r.get("when") or 0) <= time.time()
            except (TypeError, ValueError):
                due = False
            if not due:
                continue
            to = str(r.get("to") or "").strip()
            if to:
                try:
                    kind, _, ident = to.partition(":")
                    params = {"message_type": kind, "message": f"到点了：{r.get('text')}"}
                    if kind == "group":
                        params["group_id"] = int(ident)
                    else:
                        params["user_id"] = int(ident)
                    res = hub.call("send_msg", params, timeout=20.0)
                    _note(f"提醒 {r.get('id')} 发出 -> {'成功' if _ok(res) else res}")
                except Exception as e:               # noqa: BLE001
                    _note(f"提醒发不出去：{type(e).__name__} {e}")
            r["done"] = True
            changed = True
        if changed:
            _rm_save(rows)


# ----------------------------------------------------------------- 表情库
# 只存图 + 一点标注；自动识别情绪要模型看图，新家这份还没接，所以留给人（或我）手动标。
# 图放 data/qq-stickers/，标注放 data/qq-stickers/index.json（键=文件名）。

_STICKER_RE = re.compile(r"\[表情包:([^\]]+)\]")


def _stick_dir() -> str:
    path = _data_path("qq-stickers")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def _stick_index() -> dict:
    try:
        with open(os.path.join(_stick_dir(), "index.json"), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _stick_save(mapping: dict) -> None:
    try:
        with open(os.path.join(_stick_dir(), "index.json"), "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        _note(f"表情库标注存不下：{type(e).__name__} {e}")


def _stick_list() -> list:
    """库里的文件名（不带目录）。"""
    try:
        names = os.listdir(_stick_dir())
    except OSError:
        return []
    return sorted(n for n in names
                  if not n.startswith(".") and n.lower() != "index.json")


def _stick_download(url: str) -> str:
    """下一张图进库，返回文件名；失败返回空字符串。"""
    url = str(url or "").strip()
    if not url:
        return ""
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:   # noqa: S310
            blob = resp.read()
    except Exception as e:                                      # noqa: BLE001
        _note(f"表情下载失败 {url[:60]}：{type(e).__name__}")
        return ""
    if len(blob) < 64 or len(blob) > 8 * 1024 * 1024:
        return ""
    head = blob[:4]
    ext = ".jpg"
    if head[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    elif head[:8] == b"\x89PNG\r\n\x1a\n":
        ext = ".png"
    elif head[:6] in (b"GIF87a", b"GIF89a"):
        ext = ".gif"
    elif head[:4] == b"RIFF":
        ext = ".webp"
    name = "sticker-" + hashlib.sha1(blob).hexdigest()[:12] + ext
    path = os.path.join(_stick_dir(), name)
    if os.path.exists(path):
        return name
    try:
        with open(path, "wb") as fh:
            fh.write(blob)
    except OSError:
        return ""
    return name


def _qq_sticker_sync(_args: dict) -> str:
    """把 QQ 收藏表情同步进本地库（只读对面，不发消息）。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，同步不了。"
    res = hub.call("fetch_custom_face", {"count": 200}, timeout=20.0)
    data = res.get("data")
    urls: list = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                urls.append(str(item.get("url") or item.get("file") or ""))
    if not urls:
        return f"没拿到收藏表情：{_why(res)}"
    index = _stick_index()
    added = 0
    for u in urls:
        name = _stick_download(u)
        if name and name not in index:
            index[name] = {"emotion": "", "usage": "", "tag": "", "label": "",
                           "addedAt": int(time.time())}
            added += 1
    _stick_save(index)
    _note(f"表情同步：{len(urls)} 张，新进 {added} 张")
    return f"同步了 {len(urls)} 张，新进 {added} 张，库里现在 {len(_stick_list())} 张。"


def _qq_sticker_stats(args: dict) -> str:
    """看库里有哪些表情（可按标注筛）。"""
    rows = _stick_list()
    if not rows:
        return "表情库还空着，先跑一次 qq_sticker_sync。"
    index = _stick_index()
    query = str(args.get("query") or "").strip()
    try:
        limit = int(args.get("limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    picked = []
    for name in rows:
        meta = index.get(name) or {}
        blob = " ".join(str(meta.get(k) or "") for k in ("emotion", "usage", "tag", "label"))
        if query and query not in blob and query not in name:
            continue
        picked.append((name, meta))
    if not picked:
        return f"库里没有跟「{query}」搭得上的。"
    out = []
    for name, meta in picked[-max(1, limit):]:
        bits = [f"[表情包:{name}]", meta.get("label") or "", meta.get("tag") or "",
                meta.get("emotion") or ""]
        out.append(" ".join(b for b in bits if b))
    return "\n".join(out)


def _qq_sticker_tag(args: dict) -> str:
    """给库里某张图改标注。"""
    fname = _STICKER_RE.sub(r"\1", str(args.get("file") or "").strip())
    if not fname:
        return "得给文件名（qq_sticker_stats 里那个）。"
    if fname not in _stick_list():
        return f"库里没有 {fname}。"
    index = _stick_index()
    meta = dict(index.get(fname) or {})
    changed = []
    for key in ("emotion", "usage", "tag", "label"):
        val = args.get(key)
        if isinstance(val, str):
            meta[key] = val.strip()
            changed.append(key)
    if not changed:
        return "要改哪一项？emotion / usage / tag / label。"
    index[fname] = meta
    _stick_save(index)
    return f"改好了 {fname}：{', '.join(changed)}。"


def _sticker_path(fname: str) -> str:
    """库里的文件名 -> 绝对路径；不在库里就空。"""
    fname = os.path.basename(_STICKER_RE.sub(r"\1", str(fname or "").strip()))
    if not fname or "/" in fname or "\\" in fname:
        return ""
    path = os.path.join(_stick_dir(), fname)
    return path if os.path.isfile(path) else ""


def _image_segment(src: str) -> dict | None:
    """一张图 -> OneBot 的 image 段。认：http(s) 链接、库里文件名、base64://。"""
    src = str(src or "").strip()
    if not src:
        return None
    if src.startswith(("http://", "https://", "base64://")):
        return {"type": "image", "data": {"file": src}}
    path = _sticker_path(src)
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return None
    return {"type": "image", "data": {"file": "base64://" + base64.b64encode(blob).decode("ascii")}}


def _build_segments(text: str, images: list) -> list:
    """一段带 [表情包:xxx] 的正文 + 若干图 -> OneBot 的 message 段。"""
    segs: list = []
    pos = 0
    for m in _STICKER_RE.finditer(text):
        before = text[pos:m.start()]
        if before.strip():
            segs.append({"type": "text", "data": {"text": before}})
        seg = _image_segment(m.group(1))
        if seg:
            segs.append(seg)
        else:
            segs.append({"type": "text", "data": {"text": m.group(0)}})
        pos = m.end()
    tail = text[pos:]
    if tail.strip():
        segs.append({"type": "text", "data": {"text": tail}})
    for item in images or []:
        seg = _image_segment(item)
        if seg:
            segs.append(seg)
    return segs


def _img_urls(message) -> list:
    """把一条消息里的图片地址挑出来。"""
    out = []
    if not isinstance(message, list):
        return out
    for seg in message:
        if isinstance(seg, dict) and seg.get("type") == "image":
            data = seg.get("data") or {}
            url = str(data.get("url") or data.get("file") or "").strip()
            if url:
                out.append(url)
    return out


def _image_ext(blob: bytes) -> str:
    """按文件头猜扩展名：以前写死 .jpg，PNG 图会被当成 JPEG 贴给模型。"""
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if blob[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def _qq_view_image(args: dict) -> str:
    """下载一张 QQ 图，交给脑子看一眼，回一句描述。"""
    src = str(args.get("url") or "").strip()
    if not src:
        try:
            idx = int(args.get("index"))
        except (TypeError, ValueError):
            idx = -1
        if not _IMAGES:
            return "还没见过图，没得看。"
        try:
            src = _IMAGES[idx]["url"]
        except IndexError:
            return f"最近只有 {len(_IMAGES)} 张图，没有第 {idx} 张。"
    tmp_dir = _data_path("qq-tmp")
    try:
        os.makedirs(tmp_dir, exist_ok=True)
    except OSError:
        pass
    base = "view-" + hashlib.sha1(src.encode("utf-8")).hexdigest()[:12]
    path = ""
    try:
        for name in os.listdir(tmp_dir):
            if name.startswith(base + "."):
                path = os.path.join(tmp_dir, name)
                break
    except OSError:
        pass
    if not path:
        try:
            with urllib.request.urlopen(src, timeout=20) as resp:   # noqa: S310
                blob = resp.read()
        except Exception as e:                                       # noqa: BLE001
            return f"图下不下来：{type(e).__name__} {e}"
        if not blob:
            return "图是空的，没东西看。"
        path = os.path.join(tmp_dir, base + _image_ext(blob))
        try:
            with open(path, "wb") as fh:
                fh.write(blob)
        except OSError as e:
            return f"存不下临时图：{type(e).__name__} {e}"
    try:
        import llm as _llm
    except Exception as e:                                           # noqa: BLE001
        return f"接不上脑子，看不了图：{type(e).__name__} {e}"
    piece = _llm.image_message(path, "（这是别人在 QQ 上发来的一张图。）看图，用一两句说清画面里有什么、在干什么，别客套。")
    if piece is None:
        return "图太大或读不动，看不了。"
    out = _llm.chat([piece])
    _note(f"看图 {src[:60]} -> {out[:60]}")
    return out or "看了，但没话可说。"


def _qq_sticker_to_favorites(args: dict) -> str:
    """把库里的表情推到 QQ 收藏（走 add_custom_face）。推过的记账，不重复推。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，推不了。"
    if not _CONF.get("sticker_to_favorites", False):
        return "这份配置没开「同步到 QQ 收藏表情」，不推。"
    try:
        limit = int(args.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))
    index = _stick_index()
    todo = []
    for name in _stick_list():
        meta = index.get(name) or {}
        if meta.get("favId"):
            continue
        todo.append(name)
        if len(todo) >= limit:
            break
    if not todo:
        return "没有还没推过的。"
    pushed = 0
    for name in todo:
        path = os.path.join(_stick_dir(), name)
        try:
            with open(path, "rb") as fh:
                blob = fh.read()
        except OSError:
            continue
        if not blob:
            continue
        res = hub.call("add_custom_face",
                       {"file": "base64://" + base64.b64encode(blob).decode("ascii")},
                       timeout=25.0)
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        eid = (data or {}).get("emoji_id") or (data or {}).get("id")
        if _ok(res) and eid:
            meta = dict(index.get(name) or {})
            meta["favId"] = eid
            index[name] = meta
            pushed += 1
        else:
            _note(f"推收藏失败 {name}：{_why(res)}")
    _stick_save(index)
    return f"推了 {pushed} 张到 QQ 收藏（这次试了 {len(todo)} 张）。"


def _qq_forward_by_id(args: dict) -> str:
    """把几条消息合成一张转发卡片。逐条 get_msg 取回原文，再 send_forward_msg。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，转不了。"
    to = str(args.get("to") or "").strip()
    kind, _, ident = to.partition(":")
    if kind not in ("group", "private") or not ident:
        return "to 写成 group:<群号> 或 private:<QQ号>。"
    raw = args.get("message_ids") or []
    if isinstance(raw, (str, int)):
        raw = [raw]
    ids = []
    for item in raw:
        try:
            ids.append(int(str(item).strip().lstrip("#")))
        except (TypeError, ValueError):
            continue
    if not ids:
        return "得给要转的消息编号（一条或多条）。"
    nodes = []
    for mid in ids:
        res = hub.call("get_msg", {"message_id": mid}, timeout=15.0)
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        if not data:
            _note(f"转发出错：取不到 {mid}（{_why(res)}）")
            continue
        sender = data.get("sender") or {}
        nick = str(sender.get("card") or sender.get("nickname") or sender.get("user_id") or "某人")
        uin = str(sender.get("user_id") or "0")
        content = data.get("message") or data.get("raw_message") or ""
        nodes.append({"type": "node", "data": {"name": nick, "uin": uin, "content": content}})
    if not nodes:
        return "一条都没取回来，没转。"
    params: dict = {"message_type": kind, "messages": nodes}
    if kind == "group":
        params["group_id"] = int(ident)
    else:
        params["user_id"] = int(ident)
    res = hub.call("send_forward_msg", params, timeout=30.0)
    _note(f"合并转发 {len(nodes)} 条 -> {to}：{'成功' if _ok(res) else res}")
    if _ok(res):
        return f"转过去了，{len(nodes)} 条。"
    return f"没转成：{_why(res)}（有的协议端不支持 send_forward_msg / get_msg）"


# --------------------------------------------------------------- 好感度 / 别名
# 好感度：每人一份，-100~100，0=普通。落 data/qq-affinity.json。
# 别名：外号 -> QQ 号，落 data/qq-alias.json。两样都在本机，不走 NapCat。

_AFF_MIN, _AFF_MAX = -100, 100


def _aff_load() -> dict:
    try:
        with open(_data_path("qq-affinity.json"), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    ent = raw.get("entries") if isinstance(raw, dict) else None
    return ent if isinstance(ent, dict) else {}


def _aff_save(entries: dict) -> None:
    try:
        with open(_data_path("qq-affinity.json"), "w", encoding="utf-8") as fh:
            json.dump({"entries": entries}, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        _note(f"好感度存不下：{type(e).__name__} {e}")


def _aff_clamp(n) -> int:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return 0
    if n != n:
        return 0
    return int(max(_AFF_MIN, min(_AFF_MAX, round(n))))


def _aff_label(score: int) -> str:
    if score >= 80:
        return "挚友（非常亲近，可以很放松很亲昵）"
    if score >= 50:
        return "很要好（明显有好感，态度可以热络）"
    if score >= 20:
        return "有好感（偏亲近，比普通朋友多一点）"
    if score > -10:
        return "普通（中性，正常有礼貌地相处即可）"
    if score > -40:
        return "有点不爽（略带冷淡/客气，保持分寸）"
    if score > -70:
        return "反感（明显不待见，客气但疏远）"
    return "厌恶（很负面，尽量公事公办、保持距离）"


def _alias_load() -> dict:
    try:
        with open(_data_path("qq-alias.json"), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _alias_save(mapping: dict) -> None:
    try:
        with open(_data_path("qq-alias.json"), "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        _note(f"别名存不下：{type(e).__name__} {e}")


def _who_key(who: str) -> str:
    """把「外号 / QQ 号」统一成 QQ 号；认不出来就原样返回。"""
    s = str(who or "").strip()
    if not s:
        return ""
    if s.isdigit():
        return s
    return str(_alias_load().get(s) or s)


def _qq_affinity_adjust(args: dict) -> str:
    """调某人的好感度（可正可负），顺手记一句原因。"""
    who = _who_key(args.get("who"))
    if not who or not who.isdigit():
        return "得给 QQ 号（或记过的外号）。"
    try:
        delta = float(args.get("delta"))
    except (TypeError, ValueError):
        return "delta 得是数字，比如 5 或 -10。"
    entries = _aff_load()
    cur = dict(entries.get(who) or {})
    cur.setdefault("score", 0)
    cur["score"] = _aff_clamp(float(cur.get("score") or 0) + delta)
    reason = str(args.get("reason") or "").strip()
    if reason:
        cur["lastReason"] = reason
    cur["updatedAt"] = int(time.time())
    entries[who] = cur
    _aff_save(entries)
    _note(f"好感度 {who} {delta:+g} -> {cur['score']}")
    tail = f"，记着：{cur['lastReason']}" if cur.get("lastReason") else ""
    return f"{who} 的好感度 {cur['score']}/100 —— {_aff_label(cur['score'])}{tail}"


def _qq_affinity_read(args: dict) -> str:
    """看一个人的好感度，或按高低排个序。"""
    entries = _aff_load()
    if not entries:
        return "还没记过谁的好感度，都是 0（普通）。"
    view = str(args.get("view") or "person").strip()
    if view == "ranking":
        rows = sorted(entries.items(), key=lambda kv: float(kv[1].get("score") or 0), reverse=True)
        out = [f'{qq} {v.get("name") or ""} {int(v.get("score") or 0)}'.rstrip() for qq, v in rows]
        return "好感度排行：\n" + "\n".join(out)
    who = _who_key(args.get("who"))
    if not who:
        return "看谁？给 QQ 号或外号。"
    v = entries.get(who)
    score = int((v or {}).get("score") or 0)
    if not v:
        return f"{who}：0/100 —— 普通，还没打过交道。"
    bits = [f"{who}：{score}/100 —— {_aff_label(score)}"]
    if v.get("lastReason"):
        bits.append(f"上次因为：{v['lastReason']}")
    return "；".join(bits)


def _qq_alias_list(_args: dict) -> str:
    """看记过的外号。"""
    mapping = _alias_load()
    if not mapping:
        return "还没记过外号。"
    return "外号：\n" + "\n".join(f"{k} -> {v}" for k, v in sorted(mapping.items()))


def _qq_alias_update(args: dict) -> str:
    """记一个外号，或者删掉一个。"""
    action = str(args.get("action") or "set").strip().lower()
    alias = str(args.get("alias") or "").strip()
    if not alias:
        return "得给外号。"
    mapping = _alias_load()
    if action == "forget":
        if alias not in mapping:
            return f"没记过「{alias}」。"
        mapping.pop(alias, None)
        _alias_save(mapping)
        return f"忘了「{alias}」。"
    qq = str(args.get("qq") or "").strip()
    if not qq.isdigit():
        return "qq 得是纯数字的 QQ 号。"
    mapping[alias] = qq
    _alias_save(mapping)
    return f"记下了：「{alias}」就是 {qq}。"


# ----------------------------------------------------------------- 群管理
def _qq_admin_join_list(_args: dict) -> str:
    """看还有谁在等着加群。内存里没有就去问 NapCat 要一次。"""
    hub = _HUB
    rows = list(_PENDING_JOIN.values())
    if not rows and hub is not None and hub.connected:
        try:
            res = hub.call("get_group_system_msg", {})
        except Exception as e:                       # noqa: BLE001
            res = {"status": "failed", "wording": f"{type(e).__name__} {e}"}
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        for key in ("join_requests", "JoinRequests", "invited_requests"):
            for item in (data.get(key) or []):
                if not isinstance(item, dict):
                    continue
                flag = str(item.get("flag") or item.get("request_id") or "")
                if not flag:
                    continue
                _PENDING_JOIN[flag] = {
                    "flag": flag,
                    "subType": "invite" if key == "invited_requests" else "add",
                    "groupId": item.get("group_id"),
                    "userId": item.get("invitor_uin") or item.get("user_id"),
                    "comment": str(item.get("message") or item.get("comment") or ""),
                    "at": time.time(),
                }
        rows = list(_PENDING_JOIN.values())
    if not rows:
        return "眼下没人等着加群。"
    out = []
    for r in rows:
        who = r.get("userId")
        kind = "邀请" if r.get("subType") == "invite" else "申请"
        note = r.get("comment") or "（没留言）"
        out.append(f'{r["flag"]} 群{r.get("groupId")} QQ{who}（{kind}）留言：{note}')
    return "待审的加群请求：\n" + "\n".join(out)


def _qq_admin_join_decide(args: dict) -> str:
    """批一条加群请求：approve / reject。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，审不了。"
    flag = str(args.get("flag") or "").strip().lstrip("#")
    if not flag:
        return "得给 flag（qq_admin_join_list 里那一串）。"
    decision = str(args.get("decision") or "").strip().lower()
    if decision not in ("approve", "reject"):
        return "decision 只能填 approve 或 reject。"
    row = _PENDING_JOIN.get(flag) or {}
    params = {"flag": flag,
              "sub_type": row.get("subType") or "add",
              "approve": decision == "approve"}
    reason = str(args.get("reason") or "").strip()
    if reason and decision == "reject":
        params["reason"] = reason
    res = hub.call("set_group_add_request", params)
    ok = _ok(res)
    if ok:
        _PENDING_JOIN.pop(flag, None)
    _note(f"加群审核 {flag} {decision} -> {'成功' if ok else res}")
    if not ok:
        return f"没审成：{_why(res)}"
    return "放进来了。" if decision == "approve" else "拒了。"


def _qq_admin_title(args: dict) -> str:
    """给群里某人设个头衔（空字符串就是清掉）。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，改不了头衔。"
    ident = str(args.get("group") or "").strip().lstrip("group:")
    if not ident.isdigit():
        return "得说哪个群（群号）。请把群号填进 group。"
    who = _who_key(args.get("who"))
    if not who.isdigit():
        return "得说是谁（QQ 号或外号）。"
    title = str(args.get("title") or "")
    gid = int(ident)
    if _CONF.get("groups") and ident not in _CONF["groups"]:
        return f"群 {ident} 不在监听名单里，不动它。"
    res = hub.call("set_group_special_title",
                   {"group_id": gid, "user_id": int(who), "special_title": title}, timeout=15.0)
    _note(f"头衔 {ident}/{who} 「{title}」-> {'成功' if _ok(res) else res}")
    if not _ok(res):
        return f"没改成：{_why(res)}"
    return f"头衔设成「{title}」了。" if title else "头衔清掉了。"


def _qq_qzone_reply(args: dict) -> str:
    """回一条 QQ 空间动态下的评论。"""
    hub = _HUB
    if hub is None or not hub.connected:
        return "没连上 NapCat，回不了评论。"
    tid = str(args.get("tid") or "").strip()
    cid = str(args.get("comment_id") or "").strip()
    content = str(args.get("content") or "").strip()
    if not tid or not cid:
        return "得给 tid 和 comment_id。"
    if not content:
        return "回什么？给一句话。"
    params = {"tid": tid, "comment_id": cid, "content": content}
    action = str(_CONF.get("qzone_reply_action") or "reply_qzone_comment")
    res = hub.call(action, params, timeout=20.0)
    if not _ok(res) and action != "send_qzone_comment":
        res = hub.call("send_qzone_comment", params, timeout=20.0)
    _note(f"回评论 {tid}/{cid}: {content[:30]} -> {'成功' if _ok(res) else res}")
    return "回好了。" if _ok(res) else f"没回成：{_why(res)}"


# ------------------------------------------------------------ 主动说话（调度器）
# 照 Coop 那份 `_qqplug/src/proactive.ts` 搬的一小份：暖场 / 稳定 / 静默三段。
# 后台每 tick 秒掷一次骰子，决定要不要往某个监听会话主动冒一句话。
# 状态落 data/qq-proactive.json（今天发过几条、哪个会话静默到什么时候），重启还认得。
# MC 那套（发现玩法/求助）没搬——QQ 这边没游戏状态，只留闲聊冒泡。

_PRO_LOCK = threading.Lock()
_PRO: dict = {}              # address -> {firstSeen, lastSent, lastActivity, activityVersion, unreplied, silentUntil, state}
_PRO_RECENT: list = []       # 最近发过的正文，防同一句话、同一个话题反复
_PRO_DAILY: dict = {"count": 0, "day": "", "first": False}
_PRO_GEN: set = set()        # 正在生成中的会话，别叠着来

_PRO_DEFAULTS = {
    "tick_sec": 60,
    "warmup_min": 30,
    "warmup_chance": 1 / 3,
    "stable_chance": 1 / 30,
    "private_cooldown": 1800,
    "group_cooldown": 3600,
    "unreplied_threshold": 3,
    "silent_hours": 6,
    "dedup_window": 20,
    "topic_similarity": 0.6,
}


def _pro_path() -> str:
    return _data_path("qq-proactive.json")


def _pro_today() -> str:
    t = time.localtime()
    return f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}"


def _pro_load() -> None:
    global _PRO_RECENT
    try:
        with open(_pro_path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return
    states = raw.get("states")
    if isinstance(states, dict):
        for addr, item in states.items():
            if isinstance(item, dict):
                _PRO[str(addr)] = item
    recent = raw.get("recent")
    if isinstance(recent, list):
        _PRO_RECENT = [str(x) for x in recent][-50:]
    daily = raw.get("daily")
    if isinstance(daily, dict):
        _PRO_DAILY["count"] = _as_int(daily.get("count"), 0)
        _PRO_DAILY["day"] = str(daily.get("day") or "")
        _PRO_DAILY["first"] = bool(daily.get("first"))


def _pro_save() -> None:
    try:
        with open(_pro_path(), "w", encoding="utf-8") as fh:
            json.dump({"states": _PRO, "recent": _PRO_RECENT[-50:], "daily": _PRO_DAILY},
                      fh, ensure_ascii=False)
    except OSError:
        pass


def _pro_cfg() -> dict:
    c = dict(_PRO_DEFAULTS)
    c["enabled"] = bool(_CONF.get("proactive", False))
    mode = str(_CONF.get("proactive_mode") or "both").strip().lower()
    c["mode"] = mode if mode in ("private", "group", "both") else "both"
    c["daily_quota"] = _as_int(_CONF.get("proactive_daily"), 6)
    c["sleep_start"] = str(_CONF.get("sleep_start") or "23:00")
    c["sleep_end"] = str(_CONF.get("sleep_end") or "07:30")
    return c


def _pro_hhmm(text: str) -> int:
    """'23:00' -> 1380；看不懂就 -1。"""
    try:
        h, _, m = str(text).partition(":")
        return int(h) * 60 + int(m or 0)
    except (TypeError, ValueError):
        return -1


def _pro_sleeping(cfg: dict) -> bool:
    """她在自己的睡觉时段里就不主动冒泡（回话不受影响）。"""
    s0, s1 = _pro_hhmm(cfg["sleep_start"]), _pro_hhmm(cfg["sleep_end"])
    if s0 < 0 or s1 < 0 or s0 == s1:
        return False
    t = time.localtime()
    cur = t.tm_hour * 60 + t.tm_min
    return s0 <= cur < s1 if s0 < s1 else (cur >= s0 or cur < s1)


def _pro_targets(cfg: dict) -> list:
    """能主动说话的会话：按「对谁主动」从监听名单里挑。"""
    out = []
    if cfg["mode"] in ("both", "private"):
        for uid in _CONF.get("privates") or []:
            out.append({"address": f"private:{uid}", "kind": "private", "label": f"私聊 {uid}"})
    if cfg["mode"] in ("both", "group"):
        for gid in _CONF.get("groups") or []:
            out.append({"address": f"group:{gid}", "kind": "group", "label": f"群 {gid}"})
    return out


def _pro_ensure(addr: str) -> dict:
    now = time.time()
    s = _PRO.get(addr)
    if not isinstance(s, dict):
        s = {"firstSeen": now, "lastSent": 0, "lastActivity": 0, "activityVersion": 0,
             "unreplied": 0, "silentUntil": 0, "state": "warmup"}
        _PRO[addr] = s
        return s
    for key, default in (("firstSeen", now), ("lastSent", 0), ("lastActivity", 0),
                         ("activityVersion", 0), ("unreplied", 0),
                         ("silentUntil", 0), ("state", "warmup")):
        s.setdefault(key, default)
    if now - float(s.get("firstSeen") or 0) > 6 * 3600:
        s["firstSeen"] = now                      # 隔了六小时以上，重新暖场
    return s


def _pro_eval(s: dict, cfg: dict) -> str:
    """算这个会话现在处在哪一段：暖场 / 稳定 / 静默。"""
    now = time.time()
    until = float(s.get("silentUntil") or 0)
    if until and now < until:
        s["state"] = "silent"
        return "silent"
    if until and now >= until:
        s["silentUntil"] = 0
        s["unreplied"] = 0
    if int(s.get("unreplied") or 0) >= int(cfg["unreplied_threshold"]):
        s["state"] = "silent"
        s["silentUntil"] = now + float(cfg["silent_hours"]) * 3600
        _note(f"主动：{s.get('unreplied')} 条没人接，静默 {cfg['silent_hours']} 小时")
        return "silent"
    warm = float(cfg["warmup_min"]) * 60
    s["state"] = "warmup" if now - float(s.get("firstSeen") or now) < warm else "stable"
    return s["state"]


def _pro_notify_reply(addr: str) -> None:
    """有人回话了：这个会话的未回计数清零、静默解除。"""
    with _PRO_LOCK:
        s = _pro_ensure(addr)
        s["lastActivity"] = time.time()
        s["activityVersion"] = int(s.get("activityVersion") or 0) + 1
        s["unreplied"] = 0
        s["silentUntil"] = 0
        if s.get("state") == "silent":
            s["state"] = "stable"
        _pro_save()


def _pro_notify_sent(addr: str) -> None:
    """发出去一句话（不管谁让发的）：记一笔活跃时间。"""
    with _PRO_LOCK:
        s = _pro_ensure(addr)
        s["lastSent"] = time.time()
        s["activityVersion"] = int(s.get("activityVersion") or 0) + 1
        _pro_save()


def _pro_context(addr: str, limit: int = 12) -> str:
    rows = [m for m in list(_SEEN) if m.get("conv") == addr][-limit:]
    if not rows:
        return "（这个会话还没收过话。）"
    return "\n".join(f'{m.get("at")} {m.get("nick")}: {m.get("text")}' for m in rows)


def _pro_prompt(t: dict, forced: bool) -> str:
    now = time.strftime("%H:%M")
    hint = "（这次是手动让我试一次开口，仍然可以保持安静。）\n" if forced else ""
    return (
        f"现在是 {now}。你可以主动向 {t['address']}（{t['label']}）说一句话，也可以选择不说。\n"
        f"{hint}这个会话最近收到的：\n{_pro_context(t['address'])}\n\n"
        "先看最后是谁说话、对方有没有接话、旧话题结束没有。已有的话没被回应、又没有新内容，就不发。"
        "不追问进展、不重新点评已经结束的事；不要换个说法发早安、吃饭睡觉提醒或者「不打扰」这种。\n"
        "真想说就围着一个还有意思的细节，说自己的感觉、看法或好奇，留给他接话，长短随内容。"
        "只依据上面这些记录，不编自己的经历和约定。\n"
        '只回 JSON：{"text":"正文"}；不发就回 {"text":""}，别把「空」写进正文。'
    )


def _pro_parse(raw: str) -> str:
    """从模型那段话里抠出正文。抠不出来就当它不想说话。"""
    if not raw:
        return ""
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "text" in obj:
                return str(obj.get("text") or "").strip()
        except json.JSONDecodeError:
            pass
    if raw.startswith("（脑子出错了"):
        _note(f"主动：{raw[:120]}")
        return ""
    return raw.strip()


def _pro_bigrams(text: str) -> set:
    t = re.sub(r"\s+", "", text).lower()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _pro_similarity(a: str, b: str) -> float:
    ba, bb = _pro_bigrams(a), _pro_bigrams(b)
    if not ba or not bb:
        return 0.0
    inter = len(ba & bb)
    return inter / (len(ba) + len(bb) - inter)


def _pro_send(addr: str, text: str) -> bool:
    hub = _HUB
    if hub is None or not hub.connected:
        return False
    if not (_CONF or {}).get("allow_send", True):
        return False
    kind, _, ident = addr.partition(":")
    try:
        params: dict = {"message_type": kind, "message": text}
        if kind == "group":
            params["group_id"] = int(ident)
        else:
            params["user_id"] = int(ident)
        res = hub.call("send_msg", params, timeout=20.0)
    except Exception as e:                       # noqa: BLE001
        _note(f"主动发不出去：{type(e).__name__} {e}")
        return False
    ok = _ok(res)
    _note(f"主动 -> {addr}: {text[:60]} {'成功' if ok else res}")
    return ok


def _pro_emit(t: dict, forced: bool, cfg: dict) -> str:
    """想一句、查一遍重复、发出去。回一句人话说明结果。"""
    addr = t["address"]
    with _PRO_LOCK:
        if addr in _PRO_GEN:
            return "正在想，别催。"
        _PRO_GEN.add(addr)
        version = int(_pro_ensure(addr).get("activityVersion") or 0)
    try:
        user = _pro_prompt(t, forced)
        try:
            import llm
            cfg_all = _CTX.get("config") or {}
            raw = llm.chat([{"role": "system", "content": llm.system_prompt(cfg_all, user)},
                            {"role": "user", "content": user}], cfg_all, timeout=90.0)
        except Exception as e:                   # noqa: BLE001
            _note(f"主动：生成失败 {type(e).__name__} {e}")
            return "脑子没接上，这次算了。"
        text = _pro_parse(raw)
        if not text:
            return "她想了想，决定不说。"
        if not forced:
            if text in _PRO_RECENT:
                return "跟最近说过的一样，跳过。"
            limit = float(cfg["topic_similarity"])
            if limit > 0:
                top = max((_pro_similarity(text, r) for r in _PRO_RECENT), default=0.0)
                if top > limit:
                    _PRO_RECENT.append(text)
                    return "跟最近聊的太像，跳过。"
        with _PRO_LOCK:
            if int(_pro_ensure(addr).get("activityVersion") or 0) != version:
                return "刚有人说话，这条不发了。"
        if not _pro_send(addr, text):
            return "没发出去。"
        with _PRO_LOCK:
            s = _pro_ensure(addr)
            s["lastSent"] = time.time()
            s["unreplied"] = int(s.get("unreplied") or 0) + 1
            _PRO_RECENT.append(text)
            cap = max(1, int(cfg["dedup_window"]))
            del _PRO_RECENT[:-cap]
            _PRO_DAILY["count"] = int(_PRO_DAILY.get("count") or 0) + 1
            _PRO_DAILY["first"] = True
            _pro_save()
        return f"说了：{text[:60]}"
    finally:
        with _PRO_LOCK:
            _PRO_GEN.discard(addr)


def _pro_tick() -> None:
    """一分钟一次：谁的骰子掷中了，就朝谁冒一句。"""
    cfg = _pro_cfg()
    if not cfg["enabled"]:
        return
    hub = _HUB
    if hub is None or not hub.connected:
        return
    if _pro_sleeping(cfg):
        return
    today = _pro_today()
    if _PRO_DAILY.get("day") != today:
        with _PRO_LOCK:
            _PRO_DAILY["day"] = today
            _PRO_DAILY["count"] = 0
            _pro_save()
    targets = _pro_targets(cfg)
    if not targets:
        return
    quota = int(cfg["daily_quota"] or 0)
    if quota > 0 and int(_PRO_DAILY.get("count") or 0) >= quota:
        return
    for t in targets:
        with _PRO_LOCK:
            s = _pro_ensure(t["address"])
            st = _pro_eval(s, cfg)
            _pro_save()
            idle = time.time() - max(float(s.get("lastSent") or 0),
                                     float(s.get("lastActivity") or 0))
        if st == "silent":
            continue
        cooldown = float(cfg["private_cooldown"] if t["kind"] == "private"
                         else cfg["group_cooldown"])
        if idle < cooldown:
            continue
        if st == "warmup":
            p = 1.0 if not _PRO_DAILY.get("first") else float(cfg["warmup_chance"])
        else:
            p = float(cfg["stable_chance"])
        if random.random() < p:
            _pro_emit(t, False, cfg)
        if quota > 0 and int(_PRO_DAILY.get("count") or 0) >= quota:
            break


def _pro_loop() -> None:
    """后台那条线：先读回上次的账，然后一分钟一 tick。"""
    _pro_load()
    while not _STOP.is_set():
        try:
            if _STOP.wait(max(15, int(_PRO_DEFAULTS["tick_sec"]))):
                break
            _pro_tick()
        except Exception as e:                   # noqa: BLE001
            _note(f"主动调度出事：{type(e).__name__} {e}")


def _qq_proactive_status(_args: dict) -> str:
    cfg = _pro_cfg()
    count = int(_PRO_DAILY.get("count") or 0)
    quota = int(cfg["daily_quota"] or 0)
    out = ["主动说话：" + ("开" if cfg["enabled"] else "关")
           + f"（对 {cfg['mode']}，今天 {count}/{quota or '不限'} 条）"]
    if _pro_sleeping(cfg):
        out.append(f"现在是她的睡觉时段（{cfg['sleep_start']}–{cfg['sleep_end']}），不主动冒泡。")
    targets = _pro_targets(cfg)
    if not targets:
        out.append("能主动说话的会话：一个都没有（看群/私聊名单）。")
    for t in targets:
        s = _PRO.get(t["address"]) or {}
        st = {"warmup": "暖场", "stable": "稳定", "silent": "静默"}.get(str(s.get("state")), "没开始")
        until = float(s.get("silentUntil") or 0)
        tail = f"，静默到 {time.strftime('%H:%M', time.localtime(until))}" if until > time.time() else ""
        out.append(f"  · {t['address']} {t['label']}：{st}，没接 {int(s.get('unreplied') or 0)} 条{tail}")
    if _PRO_RECENT:
        out.append("最近说过：")
        out.extend("  · " + r[:60] for r in _PRO_RECENT[-5:])
    else:
        out.append("最近还没主动说过话。")
    return "\n".join(out)


def _qq_proactive_trigger(args: dict) -> str:
    cfg = _pro_cfg()
    if not cfg["enabled"]:
        return "主动说话没开：设置页「主动说话」是关的。"
    if _pro_sleeping(cfg):
        return f"现在是她的睡觉时段（{cfg['sleep_start']}–{cfg['sleep_end']}），不主动冒泡。"
    targets = _pro_targets(cfg)
    address = str(args.get("address") or "").strip()
    pick = None
    if address:
        pick = next((t for t in targets if t["address"] == address), None)
        if pick is None:
            return f"{address} 不在能主动说话的名单里。"
    elif targets:
        pick = random.choice(targets)
    if pick is None:
        return "没有可主动说话的会话（检查群/私聊名单和「对谁主动」）。"
    return _pro_emit(pick, True, cfg)


TOOLS = [
    (
        {
            "type": "function",
            "function": {
                "name": "qq_send",
                "description": "往 QQ 群里或私聊发一句话（走 NapCat）。只在监听名单内发得出去。正文里写 [表情包:文件名] 会换成库里的图；也可以另给 images。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string",
                               "description": "发到哪儿：group:<群号> 或 private:<QQ号>"},
                        "text": {"type": "string", "description": "要说的话，可含 [表情包:文件名]"},
                        "images": {"type": "array", "items": {"type": "string"},
                                   "description": "要附的图：http(s) 链接、base64://，或表情库里的文件名"},
                    },
                    "required": ["to"],
                },
            },
        },
        _qq_send,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_status",
                "description": "看看 QQ 现在连没连上、监听哪些群和私聊。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _qq_status,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_poke",
                "description": "戳一戳。私聊戳对方；群里要在 user 里写戳谁的 QQ 号。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string",
                               "description": "group:<群号> 或 private:<QQ号>"},
                        "user": {"type": "string",
                                 "description": "群里戳谁（QQ 号）；私聊不用填"},
                    },
                    "required": ["to"],
                },
            },
        },
        _qq_poke,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_history",
                "description": "查这条命收到过的 QQ 消息（最近 300 条，存在内存里）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conv": {"type": "string",
                                 "description": "只看某个会话：group:<群号> 或 private:<QQ号>，不填就全都看"},
                        "keyword": {"type": "string", "description": "只看含这个词的"},
                        "limit": {"type": "integer", "description": "最多几条，默认 20"},
                    },
                },
            },
        },
        _qq_history,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_admin_recall",
                "description": "撤回一条群消息（撤回自己的，或者管理员撤别人的）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "messageId": {"type": "string",
                                      "description": "消息 id：群消息前面「#123456」里 # 后面那串数字"},
                    },
                    "required": ["messageId"],
                },
            },
        },
        _qq_admin_recall,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_admin_notice",
                "description": "发一条群公告。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "公告正文"},
                        "group": {"type": "string", "description": "群号；不填就发当前这个群"},
                    },
                    "required": ["content"],
                },
            },
        },
        _qq_admin_notice,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_admin_at_all",
                "description": "在群里 @全体成员，可以带一句话。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "跟在 @全体 后面的正文"},
                        "group": {"type": "string", "description": "群号；不填就用当前群"},
                    },
                    "required": ["text"],
                },
            },
        },
        _qq_admin_at_all,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_qzone_post",
                "description": "发一条 QQ 空间动态。附图只收网络地址或 base64://，一条最多九张。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "动态正文"},
                        "images": {"type": "array", "items": {"type": "string"},
                                   "description": "图片地址：http(s):// 或 base64://，也可以不填"},
                        "permission": {"type": "integer",
                                       "description": "可见范围，默认 1（公开）"},
                    },
                    "required": ["text"],
                },
            },
        },
        _qq_qzone_post,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_qzone_read",
                "description": "读自己 QQ 空间最近的动态（协议端支持 get_qzone_msg_list 才有）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "num": {"type": "integer", "description": "读几条，默认 5"},
                    },
                },
            },
        },
        _qq_qzone_read,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_qzone_delete",
                "description": "删一条自己发的 QQ 空间动态。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tid": {"type": "string", "description": "动态的 tid"},
                    },
                    "required": ["tid"],
                },
            },
        },
        _qq_qzone_delete,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_voice",
                "description": "发一条 QQ 语音：用本机嗓子把这句话合成 wav，再作为语音发出去。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string",
                               "description": "group:<群号> 或 private:<QQ号>"},
                        "text": {"type": "string", "description": "要念的话，别太长"},
                    },
                    "required": ["to", "text"],
                },
            },
        },
        _qq_voice,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_note_save",
                "description": "往我自己的 QQ 记事本里写一条小纸条，返回编号。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要记的一句话"},
                    },
                    "required": ["text"],
                },
            },
        },
        _qq_note_save,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_note_list",
                "description": "看记事本里记了什么（默认最近十条）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "看几条，默认 10"},
                    },
                },
            },
        },
        _qq_note_list,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_note_forget",
                "description": "删掉记事本里的一条。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "条目编号"},
                    },
                    "required": ["id"],
                },
            },
        },
        _qq_note_forget,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_remind_add",
                "description": "记一条定时提醒，到点我自己把这句话发到那个会话。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "提醒什么"},
                        "when": {"type": "string",
                                 "description": "什么时候：10:30 / 明天 9:00 / 30分钟后 / 2小时"},
                        "to": {"type": "string",
                               "description": "发到哪：group:<群号> 或 private:<QQ号>，不填就只在本地记"},
                    },
                    "required": ["text", "when"],
                },
            },
        },
        _qq_remind_add,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_remind_list",
                "description": "看还没到点的提醒。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _qq_remind_list,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_remind_remove",
                "description": "删一条提醒。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "提醒编号"},
                    },
                    "required": ["id"],
                },
            },
        },
        _qq_remind_remove,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_affinity_adjust",
                "description": "调我对某个人的好感度（关系分）。可正可负，范围 -100~100，0=普通；做让人舒服的事加，越界就减。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "who": {"type": "string", "description": "QQ 号（或记过的外号）"},
                        "delta": {"type": "number", "description": "加减多少，比如 5 或 -10"},
                        "reason": {"type": "string", "description": "可选，记一句为什么"},
                    },
                    "required": ["who", "delta"],
                },
            },
        },
        _qq_affinity_adjust,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_affinity_read",
                "description": "看某人的好感度（view=person），或者按高低排一遍（view=ranking）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "view": {"type": "string", "description": "person（默认）或 ranking"},
                        "who": {"type": "string", "description": "QQ 号或外号，view=person 时给"},
                    },
                },
            },
        },
        _qq_affinity_read,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_alias_list",
                "description": "看记过哪些外号、各对应哪个 QQ 号。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _qq_alias_list,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_alias_update",
                "description": "记一个外号（action=set）或删掉一个（action=forget）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "set 或 forget"},
                        "alias": {"type": "string", "description": "外号"},
                        "qq": {"type": "string", "description": "对应的 QQ 号（action=set 时给）"},
                    },
                    "required": ["action", "alias"],
                },
            },
        },
        _qq_alias_update,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_admin_join_list",
                "description": "看还有谁在等着加群：给出 flag、群号、申请人、留言。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _qq_admin_join_list,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_admin_join_decide",
                "description": "审一条加群请求：decision=approve 通过，reject 拒绝（可带理由）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "flag": {"type": "string", "description": "qq_admin_join_list 给出的 flag"},
                        "decision": {"type": "string", "description": "approve 或 reject"},
                        "reason": {"type": "string", "description": "拒绝理由（可选）"},
                    },
                    "required": ["flag", "decision"],
                },
            },
        },
        _qq_admin_join_decide,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_admin_title",
                "description": "给群里某人设专属头衔；title 给空字符串就是清掉。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "group": {"type": "string", "description": "群号"},
                        "who": {"type": "string", "description": "谁的 QQ 号或外号"},
                        "title": {"type": "string", "description": "头衔内容，空字符串=清除"},
                    },
                    "required": ["group", "who"],
                },
            },
        },
        _qq_admin_title,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_qzone_reply",
                "description": "回一条 QQ 空间动态下面的评论。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tid": {"type": "string", "description": "动态 tid"},
                        "comment_id": {"type": "string", "description": "评论 id"},
                        "content": {"type": "string", "description": "回什么"},
                    },
                    "required": ["tid", "comment_id", "content"],
                },
            },
        },
        _qq_qzone_reply,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_sticker_sync",
                "description": "把 QQ 收藏表情同步进本地表情库（只读，不发消息）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _qq_sticker_sync,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_sticker_stats",
                "description": "看表情库里有什么，给的是能直接写进 qq_send 的 [表情包:文件名]。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "按标注/文件名筛，可不填"},
                        "limit": {"type": "integer", "description": "给几条，默认 10"},
                    },
                },
            },
        },
        _qq_sticker_stats,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_sticker_tag",
                "description": "给库里某张表情补标注（emotion / usage / tag / label）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "description": "文件名，如 sticker-ab12cd34ef56.jpg"},
                        "emotion": {"type": "string", "description": "情绪，如 开心/无语"},
                        "usage": {"type": "string", "description": "什么场合用"},
                        "tag": {"type": "string", "description": "2-4 字短标签"},
                        "label": {"type": "string", "description": "显示短名"},
                    },
                    "required": ["file"],
                },
            },
        },
        _qq_sticker_tag,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_view_image",
                "description": "看一张 QQ 上的图：不传 url 就看最近收到的那张，回来是一句画面描述。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "图片地址，可不填"},
                        "index": {"type": "integer",
                                  "description": "取最近第几张（0 最早，-1 最新），默认 -1"},
                    },
                },
            },
        },
        _qq_view_image,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_sticker_to_favorites",
                "description": "把本地表情库还没推过的图推到 QQ 收藏表情（add_custom_face）；需配置里开着同步。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "这次最多推几张，默认 50"},
                    },
                },
            },
        },
        _qq_sticker_to_favorites,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_forward_by_id",
                "description": "把几条消息编号合成一张转发卡片发出去（先 get_msg 取原文，再 send_forward_msg）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "group:<群号> 或 private:<QQ号>"},
                        "message_ids": {"type": "array", "items": {"type": "integer"},
                                        "description": "要转的消息编号"},
                    },
                    "required": ["to", "message_ids"],
                },
            },
        },
        _qq_forward_by_id,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_proactive_status",
                "description": "看主动说话调度器现在什么状态：开关、今天发了几条、每个会话在暖场/稳定/静默、最近说过什么。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _qq_proactive_status,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "qq_proactive_trigger",
                "description": "手动触发一次主动说话（挑一个监听会话，或者指定 address 如 private:123）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {"type": "string",
                                    "description": "可选：group:<群号> 或 private:<QQ号>；不填就随便挑一个"},
                    },
                },
            },
        },
        _qq_proactive_trigger,
    ),
]


# ------------------------------------------------------------------ 装
_CTX: dict = {}
_CONF: dict = {}
_DATA_DIR: str = ""


def setup(ctx: dict) -> None:
    """开机时 plug.py 调进来。开一个 WS 服务端等 NapCat，谁也不惊动。"""
    global _HUB, _CTX, _CONF, _LOG, _DATA_DIR
    _STOP.clear()
    _CTX = ctx or {}
    cfg = (_CTX.get("config") or {}) if isinstance(_CTX, dict) else {}
    _CONF = _settings(cfg)
    _DATA_DIR = str(cfg.get("data_dir") or "data")

    def log(text: str) -> None:
        try:
            import memory
            memory.note_file("qq.log", text, cfg)
        except Exception:                            # noqa: BLE001
            print(f"[qq] {text}")

    _LOG = log

    _HUB = _Hub(_CONF["host"], _CONF["port"], _CONF["path"], _CONF["token"],
                on_event=_on_event, log=log)
    log(_HUB.start())
    threading.Thread(target=_reminder_loop, daemon=True).start()
    threading.Thread(target=_pro_loop, daemon=True).start()


def stop() -> None:
    """3-2：卸 qq 时调——先让提醒/主动两条循环退出，再关 WS 服务端。

    为什么存在：设置页「卸载」以前只把 qq.py 挪进 removed\\，8080 的监听和
    _reminder_loop / _pro_loop 两条 daemon 线程照跑；不写这个 stop，卸载就是假的。
    """
    _STOP.set()
    hub = _HUB
    if hub is not None:
        hub.stop()
