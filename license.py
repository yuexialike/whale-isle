"""开源版的「门」：不校验。

原版用一对 Ed25519 钥匙签激活码：私钥只在作者手里，签出来的码只给某个人、某台机器。
公开的这份把门拆了：check() 永远放行，签名、机器指纹、读码这几样都不在里面了。
拿到源码的人不用任何码，直接就能跑。
"""
from __future__ import annotations

import hashlib
import os
import uuid


def machine_id() -> str:
    raw = str(uuid.getnode()) + "-" + os.environ.get("COMPUTERNAME", "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()


def check(code=None, machine=None):
    return True, "开源版：不校验"


def _read_code() -> str:
    return ""


def save_code(code):
    return None

