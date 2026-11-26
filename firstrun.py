"""第一次开机：把家给铺好。

为什么要有这一步：发给别人的软件，拷过去的时候只有一个 exe 和一堆文件——
config.json 没有、workspace 没有。要是程序直接 `load_config()` 拿个空 dict 就往下走，
它会站在屏幕底边、什么都不知道、还写一堆日志到临时目录里。所以第一次先铺床：

  1. 没有 config.json → 按默认写一份（名字、形象、工作区都在自己旁边）；
  2. 有 `template/` → 把 CONSTITUTION / PARTNER / STATE 三份起手的抄进 workspace；
  3. 建好 data\\。

已经有的东西**一律不覆盖**——第二次开机它只是路过。
"""
from __future__ import annotations

import json
from pathlib import Path

import memory

SEED = ("CONSTITUTION.md", "PARTNER.md", "STATE.md")

OWNER_SEAL = "owner.seal"


def _is_owner(home: Path) -> bool:
    """是不是咱俩这台机器：(家) 里有没有一张用私钥签过名的 `owner.seal`。

    2026-11-23 16:01 月下看出来的毛病——以前是「包根上放个 beta.marker 才锁上」，
    等于**默认是开着的**：谁把源码拉下去直接跑，没有 marker，起来就是全功能那一套。
    现在反过来：
      · 默认锁着（要激活码、权限全关、一次 4 步……）；
      · 只有本机有这张签过名的 `owner.seal`，验签过了，才解开。
    签名用 `license-key.txt` 那把私钥（只在月下手里），验签用 `license_pub.py` 里的公钥。
    这张文件**不进仓库、不进包**——别人拿到源码也解不开。
    """
    try:
        text = (home / OWNER_SEAL).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not text:
        return False
    try:
        import license as _license
        ok, _why = _license.check(text)
    except Exception:          # noqa: BLE001
        return False
    return ok


def _default_config(home: Path) -> dict:
    # 两套版本，唯一的分岔就在这一行（月下 11-01 14:47 定的：咱俩这份安全协议是解开的，
    # 发出去的那份是锁上的，而且是个阉割版）。
    #   有 owner.seal（验签过）  → 自己这一份：解开
    #   没有                     → 默认就是锁着的那份
    #   beta.marker              → 不管有没有 seal，一律锁（打包给别人的时候放）
    beta = (home / "beta.marker").exists() or not _is_owner(home)
    return {
        "name": "新朋友",
        "x_fraction": 0.5,
        "roam": "free",
        # 形象：build.bat 会把立绘拷成 exe 旁边的 figure-default.png（11-01 月下定的：
        # 给别人的版本先用现在这个 2D 形象）。找不到就退回 QPainter 画的团子，不会崩。
        "figure_image": str(home / "figure-default.png"),
        "speak_aloud": True,
        "heartbeat_minutes": 30,
        # 19:55 检查更新：清单放静态地址就行（关于页里能填）。空着 = 只提示「还没配」。
        "update_url": "",
        # 20:15 引导页：新装的包第一次开机要摆一页纸，看完写 true（见 welcome.py）
        "welcomed": False,
        "ears": False,
        "api_base": "https://api.deepseek.com/v1",
        # 2026-11-21 16:44 月下：「打包版模型因为是内测使用，就用现在这个模型」。
        # 现在这个 = deepseek-flash（能看图的那只）。改过这里要重打包才生效。
        "api_model": "deepseek-flash",
        "api_key": "",
        "api_key_env": "DEEPSEEK_API_KEY",
        "workspace": str(home / "workspace"),
        "data_dir": str(home / "data"),
        # 授权：发出去的那份**照旧要码**（一人一张，用 make-code.py 签）。
        # 解开的那份只在自己机器上。
        "license_required": beta,
        # 权限区块：一条都不预开。想让桌宠动电脑，得人自己在设置页里一条条给。
        # （permissions.py 里没写的项就是 off，所以这里空着就等于全锁。）
        "permissions": {},
        # 阉割的那几样：别人的版本别一上来就满配
        "max_steps": 4 if beta else 8,
        "plugins": [],
    }


def ensure() -> list[str]:
    """铺床。返回做了哪些事，没做事就是空表。"""
    said: list[str] = []
    home = memory.home()
    cfg_path = home / "config.json"

    if not cfg_path.exists():
        cfg = _default_config(home)
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        try:                   # 出生就盖封印，之后改一行都认得出
            import guard
            guard.write_seal(cfg, home)
        except Exception:      # noqa: BLE001
            pass
        said.append(f"第一次开机：写了 config.json（名字={cfg['name']}）")

    cfg = memory.load_config()
    ws = memory.workspace(cfg)
    ws.mkdir(parents=True, exist_ok=True)

    tpl = home / "template"
    for name in SEED:
        target = ws / name
        if target.exists():
            continue
        src = tpl / name
        if not src.exists():
            continue
        target.write_text(memory.decode_bytes(src.read_bytes()), encoding="utf-8")
        said.append(f"种下 {name}")

    memory.data_dir(cfg)
    return said
