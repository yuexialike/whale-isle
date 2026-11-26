"""开源版的「封印」：什么都不做。

原版会给 config.json 盖一道封印，防止别人顺手改配置（门、权限、插件那几格）。
公开的这份没有封印：配置怎么改都算数。
"""
from __future__ import annotations

from pathlib import Path


def seal_path(home):
    return Path(home) / "seal.json"


def dev_path(home):
    return Path(home) / "dev.ok"


def make_seal(cfg):
    return ""


def write_seal(cfg, home):
    return seal_path(home)


def check(cfg, home):
    return True, "开源版：不校验"


def dev_ok(home):
    return True


def mark_dev(home):
    return dev_path(home)


def locked(cfg):
    return cfg


def note(home, why):
    return None


def apply(cfg, home):
    return cfg

