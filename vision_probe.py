"""探一下：DeepSeek 的接口吃不吃图。

只用标准库。key 从 config.json 里读（不写进命令，省得在屏幕上露出来）。

只测「能回话」不够——接口也可能把图默默丢掉，让模型瞎猜。
所以拿几种颜色挨个问，把发的颜色和它答的颜色并排写下来：对得上才算真看见。

结果写 data/vision_probe.txt（UTF-8），cmd 窗口里不会乱码。
"""
import base64
import json
import struct
import urllib.error
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "vision_probe.txt"

CASES = [
    ("红色", (220, 30, 30)),
    ("蓝色", (20, 40, 220)),
    ("黄色", (240, 220, 20)),
    ("黑色", (10, 10, 10)),
]


def tiny_png(rgb, size: int = 48) -> bytes:
    """手搓一张纯色 PNG，不依赖 Pillow。"""
    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def ask(cfg: dict, rgb, with_image: bool) -> str:
    base = (cfg.get("api_base") or "https://api.deepseek.com/v1").rstrip("/")
    model = cfg.get("api_model", "deepseek-chat")
    prompt = "这张图是什么颜色？只回一个词。"
    if with_image:
        b64 = base64.b64encode(tiny_png(rgb)).decode()
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
    else:
        content = prompt
    payload = {"model": model, "messages": [{"role": "user", "content": content}],
               "max_tokens": 20, "temperature": 0}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg.get('api_key', '').strip()}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode("utf-8"))
        return (data["choices"][0]["message"].get("content") or "").strip()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        return f"出错 {type(e).__name__} {e}"


def main() -> None:
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    lines = [f"模型 {cfg.get('api_model')} · 接口 {cfg.get('api_base')}"]
    for name, rgb in CASES:
        seen = ask(cfg, rgb, True)
        blind = ask(cfg, rgb, False)
        mark = "对" if name in seen else "没对上"
        lines.append(f"发的{name}{rgb} → 带图答「{seen}」[{mark}] · 不带图答「{blind}」")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("写好了:", OUT)


if __name__ == "__main__":
    main()
