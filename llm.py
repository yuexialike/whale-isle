"""脑子：接 DeepSeek 的 chat/completions（OpenAI 兼容）。

key 从哪儿来，按顺序找：
  1. config.json 里的 api_key（自己填的）
  2. config.json 里 api_key_file 指向的文件（一行 key）
  3. 环境变量（api_key_env，默认 DEEPSEEK_API_KEY）
没有 key 时不报错，返回一句「我没接上脑子」，别让整个窗口崩掉。

三个入口：
  chat(messages)                 —— 一句话进、一句话出，不带工具
  reply(user_text, history)      —— 带上人格，一句话进、一句话出
  talk(user_text, history)       —— **带工具**：能读能写记忆，最多转 4 圈
"""
from __future__ import annotations

import json as _json
import os
import urllib.error
import urllib.request
from pathlib import Path


def _cfg():
    import memory
    return memory.load_config()


def api_key(cfg: dict | None = None) -> str:
    cfg = cfg or _cfg()
    key = (cfg.get("api_key") or "").strip()
    if key:
        return key
    f = cfg.get("api_key_file")
    if f:
        try:
            return Path(f).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    env = cfg.get("api_key_env", "DEEPSEEK_API_KEY")
    return os.environ.get(env, "").strip()


def _post(messages: list[dict], cfg: dict, timeout: float = 40.0, tools: list | None = None) -> dict:
    """真正的 HTTP。回来的是 message 那个 dict（可能带 tool_calls）。出错抛 RuntimeError。"""
    key = api_key(cfg)
    if not key:
        raise RuntimeError("没接上脑子：还缺 key")

    base = (cfg.get("api_base") or "https://api.deepseek.com/v1").rstrip("/")
    payload = {
        "model": cfg.get("api_model", "deepseek-chat"),
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.9)),
        "max_tokens": int(cfg.get("max_tokens", 4000)),
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    req = urllib.request.Request(
        base + "/chat/completions",
        data=_json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = _json.loads(resp.read().decode("utf-8"))
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        msg["_finish"] = choice.get("finish_reason")     # 21:05：len 截断要让上面看得见
        return msg


def chat(messages: list[dict], cfg: dict | None = None, timeout: float = 40.0) -> str:
    try:
        import permissions as _perm
        _perm.audit(cfg, "network", "模型请求")
    except Exception:  # noqa: BLE001
        pass
    """给一串 [{role, content}]，回一句话。出错就回一句人话，不抛。"""
    cfg = cfg or _cfg()
    try:
        return (_post(messages, cfg, timeout).get("content") or "").strip()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return f"（脑子出错了：HTTP {e.code} {body}）"
    except Exception as e:
        return f"（脑子出错了：{type(e).__name__} {e}）"


def system_prompt(cfg: dict | None = None, query: str = "") -> str:
    """开机装进脑子的那些话：CONSTITUTION + PARTNER + STATE + 怎么说话 + 用电脑的规矩。

    query 传当前这句，记忆中枢才知道该把哪十来条浮上来（11-02 接的）。
    """
    import persona
    return persona.system_prompt(cfg, query)


def _with_history(user_text: str, history: list[dict] | None, cfg: dict,
                  images: list[dict] | None = None) -> list[dict]:
    # 拿「他刚说的这句」当线索去召回记忆：这就是「想起来」，不是把 STATE 整份塞进来。
    msgs = [{"role": "system", "content": system_prompt(cfg, user_text)}]
    for turn in (history or [])[-12:]:
        msgs.append(turn)
    # 插件推来的话（2026-11-01 加的，见 hooks.py）：取一次就清空，塞在这一轮前面。
    # 特意单独一条、写清「不是月下打的字」——不然我会把它当他刚跟我说的话。
    try:
        import hooks as _hooks
        pushed = _hooks.HOOKS.take()
    except Exception:                     # noqa: BLE001
        pushed = ""
    if pushed:
        msgs.append({"role": "user", "content":
                     "（下面这段是插件推来的，不是你打的字；处理完这一轮它就没了。）\n" + pushed})
    msgs.append({"role": "user", "content": user_text})
    # 页面/QQ 刚发来的图：单独一段 user（内容是 text + image_url），跟在人话后面。
    for piece in images or []:
        if isinstance(piece, dict) and piece.get("role") == "user":
            msgs.append(piece)
    return msgs


# 截图能有多大：接口那边一次塞太多会慢，超了就只给文字描述，不硬贴。
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def image_message(path: str, note: str = "（这是我刚截的那张图。）") -> dict | None:
    """把一张本地图变成 messages 里的一段。太大或读不到就回 None。

    22:32 探过了：`deepseek-chat` 吃 `image_url`，四张纯色图全答对；
    不给图它只会瞎猜「白色」。所以这里是真看得见，不是摆设。
    """
    import base64

    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None
    ext = Path(path).suffix.lower().lstrip(".") or "png"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "png")
    url = f"data:image/{mime};base64,{base64.b64encode(data).decode()}"
    return {"role": "user", "content": [
        {"type": "text", "text": note},
        {"type": "image_url", "image_url": {"url": url}},
    ]}


def reply(user_text: str, history: list[dict] | None = None, cfg: dict | None = None) -> str:
    """一句话进、一句话出，不带工具。"""
    cfg = cfg or _cfg()
    import turn as _turn

    with _turn.open("system", "llm.reply"):
        return chat(_with_history(user_text, history, cfg), cfg)


def talk(user_text: str, history: list[dict] | None = None, cfg: dict | None = None,
         *, source: str, entry: str = "llm.talk",
         max_steps: int = 4, on_tool=None, on_start=None,
         images: list[dict] | None = None) -> str:
    """带工具的那种。`source` 必填：这一轮是谁说的（见 `turn.py`）。

    一轮就在这一句里开——不在入口各写一遍，漏不掉：不传 source 当场 TypeError。
    没有轮的时候调 `tools.run`，闸门一律拒（默认拒绝，不是默认放行）。
    `images` 是这一轮要贴给模型的图（llm.image_message 的返回值），没有就 None。
    """
    import turn as _turn

    with _turn.open(source, entry):
        return _talk(user_text, history, cfg, max_steps=max_steps,
                     on_tool=on_tool, on_start=on_start, images=images)


def _talk(user_text: str, history: list[dict] | None = None, cfg: dict | None = None,
          max_steps: int = 4, on_tool=None, on_start=None,
          images: list[dict] | None = None) -> str:
    """带工具的那种。模型想调工具就调，调完接着想，最多 max_steps 圈。

    on_start(name, args)         工具还没跑，先冒小字：「正在读 STATE.md」
    on_tool(name, args, result)  跑完了，记账用
    """
    import tools as toolmod

    cfg = cfg or _cfg()
    msgs = _with_history(user_text, history, cfg, images=images)
    max_steps = int(cfg.get("max_steps", max_steps) or max_steps)
    for _ in range(max(1, max_steps)):
        try:
            msg = _post(msgs, cfg, tools=toolmod.TOOLS)
        except urllib.error.HTTPError as e:
            # 20:32 补的：以前只回状态码，400 出来等于没线索。
            # 现在把接口原话记进 llm.log（回话里还是只说一句人话，别把一整段 JSON 甩给人看）。
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:400]
            except Exception:                    # noqa: BLE001
                pass
            try:
                import memory as _memory

                shape = []
                for m in msgs:
                    r = m.get("role")
                    mark = r
                    if m.get("tool_calls"):
                        mark += f"+tc{len(m['tool_calls'])}"
                    if m.get("tool_call_id"):
                        mark += "+id"
                    shape.append(mark)
                _memory.note_file("llm.log", f"HTTP {e.code} msgs={len(msgs)} tools={len(toolmod.TOOLS)} "
                                             f"shape={'/'.join(shape)} {body}", cfg)
            except Exception:                    # noqa: BLE001
                pass
            return f"（脑子出错了：HTTP {e.code}）"
        except Exception as e:
            return f"（脑子出错了：{type(e).__name__} {e}）"

        calls = msg.get("tool_calls") or []
        if msg.get("_finish") == "length":
            try:
                import memory as _memory

                _memory.note_file("llm.log", "输出被 max_tokens 截断", cfg)
            except Exception:            # noqa: BLE001
                pass
        if not calls:
            return (msg.get("content") or "").strip()

        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        pending_images: list[dict] = []
        for call in calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            try:
                args = _json.loads(fn.get("arguments") or "{}")
                broken = not isinstance(args, dict)
            except Exception:
                args, broken = {}, True
            if broken:
                # 21:05 修：以前这里 args={} 就照跑，工具收到空参数（path="" → 工作区根目录 →
                # 「Permission denied」），模型还以为是没权限，白绕十分钟。现在把话说给模型听。
                out = ("（这次工具参数不是完整的 JSON——多半是被 max_tokens 截断了。"
                       "要写长文件就分几次：先 mode=\"overwrite\" 写开头，再用 mode=\"append\" 接着补，"
                       "每次别超过一两千字。）")
                calls_ok = False
            else:
                calls_ok = True
            if on_start:
                try:
                    on_start(name, args)
                except Exception:
                    pass
            if calls_ok:
                out = toolmod.run(name, args)
            if on_tool:
                try:
                    on_tool(name, args, out)
                except Exception:
                    pass
            msgs.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": out})

            # 刚截的图，跟着这一圈贴进去——不然模型只有一串尺寸和坐标，点哪儿全靠猜。
            # 20:36 修的：以前是**就地**塞一条 user，正好插在 assistant(tool_calls) 和 tool 之间，
            # 接口回 400「tool_calls 后面必须跟 tool 消息」。攒着，等所有 tool 都齐了再放。
            shot = getattr(toolmod, "take_image", None)
            if shot is not None:
                try:
                    path = shot()
                except Exception:
                    path = None
                if path:
                    msg_img = image_message(path)
                    if msg_img:
                        pending_images.append(msg_img)
        msgs.extend(pending_images)

    # 圈数用完了还没给出正文——以前就到这儿吐一句「（转了几圈还没说完，我先停这儿）」，
    # 月下看到的是一句动作、一个字没听见（11:12 那轮就是这样）。
    # 现在再问最后一次，这回**不给工具**：只能说人话。
    try:
        msg = _post(
            msgs + [{
                "role": "user",
                "content": "（工具够了，这一轮不用再调。现在只把要跟月下说的那句话说完——"
                           "一两句，说清你刚做了什么、或你打算什么。）",
            }],
            cfg,
            tools=None,
            timeout=25.0,
        )
        text = (msg.get("content") or "").strip()
        if text:
            return text
    except Exception:
        pass

    return "（转了几圈还没说完，我先停这儿）"
