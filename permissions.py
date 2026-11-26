"""权限区块：哪些能给、哪些每次都要问、哪些永远不给。

月下 19:16：「在咱们软件上写一个区块，叫权限区块，要把哪些权限能给你、哪些权限不能给你
说清楚。然后给他一个开关，给他一个选项。比如说就像你现在这个授权一次 30 分钟或者自定义
时长的这种。因为不是每一个人都愿意把权限给你的。」

所以这里分三种档：

  grantable —— 能开，开法三选：一直允许 / 只给一段时间 / 先不用
  ask_each  —— 能开，但**每次都要单独点头**，不能一口气放到底
  never     —— 不开放，选项是灰的，点了也不会亮

存进 `config.json`：

    "permissions": {"screen": {"mode": "timed", "until": 1761900000.0}}

`until` 是 unix 时间秒；过了点就自动当 `off`，不用谁来收。
"""
from __future__ import annotations

import time

import memory

ALWAYS = "always"
TIMED = "timed"
OFF = "off"
ASK = "ask"          # ask_each 那一档的常态
GRANTED = "grantable"   # 粗档「允许」：不再每次问；细护栏（收件人分级）在 4-2

GRANTABLE = "grantable"
ASK_EACH = "ask_each"
NEVER = "never"

ROSTER: list[tuple[str, str, str, str]] = [
    # id, 名字, 说明, 档位
    ("screen", "看屏幕", "截图、读窗口上的字。不给也能用，只是看不见你要它点什么。", GRANTABLE),
    ("input", "动鼠标键盘", "替你点鼠标、打字、按键。", GRANTABLE),
    ("shell", "跑命令行", "开命令提示符、跑脚本。给到这一条，改动会落在这台真电脑上，"
                        "建议先只借它一会儿。", GRANTABLE),
    ("network", "联网", "连模型、连语音和听写服务。关掉它还能说话，只是不上网。", GRANTABLE),
    ("install", "自己装东西", "缺的模型和服务，它自己去下、自己去连。", GRANTABLE),
    ("mic", "听你说话", "麦克风常开，喊一声就应。", GRANTABLE),
    ("speak", "出声", "用扬声器把话念出来。", GRANTABLE),
    ("files", "读写工作区", "文件读写都只在工作区这一个文件夹里。", GRANTABLE),
    ("delete", "删文件", "删掉就找不回来了，所以默认每次都先单独问你一句。", ASK_EACH),
    ("outbox", "对外发消息", "往 QQ、邮件这类地方发东西。发出去收不回来，"
                          "所以默认每次都先问你一句。", ASK_EACH),
    ("camera", "摄像头", "看你在不在。可授权，但每次都要单独问。", ASK_EACH),
    ("secrets", "密码 / 验证码 / 付款", "这几件事它只会提醒你自己去办，不代劳。", NEVER),
]

BY_ID = {pid: (name, why, kind) for pid, name, why, kind in ROSTER}


def _t(key: str, **kw) -> str:
    """权限话术走词表：界面和 PermissionError 用同一套词。"""
    import i18n
    return i18n.t(key, **kw)


def display_name(pid: str) -> str:
    """这一格当前语言的名字（ROSTER 里的中文只当兜底）。"""
    if pid in BY_ID:
        return _t(f"page.perm.{pid}.name")
    return BY_ID.get(pid, (pid, "", NEVER))[0]

# 30 分钟那种「先借给它一会儿」的默认时长
DEFAULT_MINUTES = 30

# 问人用的回调：main 开机把「弹卡问一句」接进来；没接时 ask_each 只能拒。
_ASKER = None


def set_asker(fn) -> None:
    """main 开机调：给一个「问人一句，回 True/False」的函数。"""
    global _ASKER
    _ASKER = fn


def load(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else memory.load_config()
    perms = cfg.get("permissions")
    if not isinstance(perms, dict):
        perms = {}
        cfg["permissions"] = perms
    return perms


def _entry(perms: dict, pid: str) -> dict:
    item = perms.get(pid)
    if not isinstance(item, dict):
        item = {}
        perms[pid] = item
    return item


def state(cfg: dict | None, pid: str) -> str:
    """此刻这一条到底是什么状态：always / timed / ask / off。"""
    _name, _why, kind = BY_ID.get(pid, ("", "", NEVER))
    if kind == NEVER:
        return OFF
    perms = load(cfg)
    item = perms.get(pid) or {}
    mode = str(item.get("mode", "")) or (ASK if kind == ASK_EACH else OFF)
    if mode == GRANTED:
        # 显式写了 grantable = 粗档允许：ask_each 的行也不再每次弹卡。
        # 为什么留这个值：4-2 还没做「按收件人分级」之前，先别让每句话都弹卡。
        return ALWAYS
    if mode == TIMED:
        until = float(item.get("until", 0) or 0)
        if until and time.time() < until:
            return TIMED
        return OFF
    if kind == ASK_EACH and mode == ALWAYS:
        return ASK
    return mode if mode in (ALWAYS, OFF, ASK) else OFF


def allowed(cfg: dict | None, pid: str) -> bool:
    """能不能直接动手。timed 还没到期算能；ask_each 永远得再问一次。"""
    return state(cfg, pid) in (ALWAYS, TIMED)


def needs_ask(cfg: dict | None, pid: str) -> bool:
    """这一次要不要单独问一句。"""
    st = state(cfg, pid)
    _name, _why, kind = BY_ID.get(pid, ("", "", NEVER))
    if kind == NEVER:
        return True          # 问了也不给，但界面上要提示「这个得你自己来」
    if kind == ASK_EACH:
        return True
    return st == OFF


def audit(cfg: dict | None, pid: str, what: str) -> str:
    """只记不拦：files 这类先观察，别一上来就硬拒。"""
    try:
        st = state(cfg, pid)
    except Exception:                        # noqa: BLE001
        st = OFF
    try:
        memory.note_file("perm.log", f"audit {pid}: {what}（st={st}，只记不拦）", cfg)
    except Exception:                        # noqa: BLE001
        pass
    return st


def require(cfg: dict | None, pid: str, what: str, ask=None) -> bool:
    """动作入口的统一检查：没开就抛 PermissionError（话术里带行名）。

    - always / timed：放行。
    - ask_each + ask 回调：问一次，答应才放行。
    - off / never / 缺行：拒，并往 perm.log 记一行带行名的记录。
    - 权限表读不出来（异常）：按最严处理，拒。
    """
    name, _why, kind = BY_ID.get(pid, (pid, "", NEVER))
    name = display_name(pid)
    try:
        st = state(cfg, pid)
    except Exception:                            # noqa: BLE001
        st = OFF
    if st in (ALWAYS, TIMED) and kind != NEVER:
        # 放行也留一行：事后要查得到「谁被允许过」，不能只有 deny/audit 有记录。
        try:
            memory.note_file("perm.log", f"allow {pid}（{name}）: {what}；st={st}", cfg)
        except Exception:                            # noqa: BLE001
            pass
        return True
    ask = ask or _ASKER
    if kind == ASK_EACH and st == ASK and callable(ask):
        try:
            if ask(_t("page.perm.ask.question", name=name, what=what)):
                try:
                    memory.note_file("perm.log",
                                     f"allow {pid}（{name}）: {what}；st={st}（ask=yes）", cfg)
                except Exception:                    # noqa: BLE001
                    pass
                return True
        except Exception:                        # noqa: BLE001
            pass
    missing = False
    try:
        missing = pid not in load(cfg)
    except Exception:                            # noqa: BLE001
        missing = True
    try:
        memory.note_file("perm.log", f"deny {pid}（{name}）: {what}；missing={missing} st={st}", cfg)
    except Exception:                            # noqa: BLE001
        pass
    raise PermissionError(_t("page.perm.deny", name=name,
                             always=_t("page.perm.mode.always"),
                             timed=_t("page.perm.mode.timed")))


def grant(cfg: dict | None, pid: str, minutes: int | None = None) -> dict:
    """开一条：minutes 为空 = 一直允许；给了 = 从现在起借这么久。"""
    name, _why, kind = BY_ID.get(pid, ("", "", NEVER))
    if kind == NEVER:
        raise PermissionError(_t("page.perm.grant_never", name=display_name(pid)))
    perms = load(cfg)
    item = _entry(perms, pid)
    if kind == ASK_EACH:
        item.clear()
        item["mode"] = ASK
        return item
    if minutes and int(minutes) > 0:
        item["mode"] = TIMED
        item["until"] = time.time() + int(minutes) * 60
    else:
        item["mode"] = ALWAYS
        item.pop("until", None)
    return item


def revoke(cfg: dict | None, pid: str) -> dict:
    perms = load(cfg)
    item = _entry(perms, pid)
    item["mode"] = OFF
    item.pop("until", None)
    return item


def left_minutes(cfg: dict | None, pid: str) -> int:
    """timed 还剩几分钟；不是 timed 就 0。"""
    perms = load(cfg)
    item = perms.get(pid) or {}
    if item.get("mode") != TIMED:
        return 0
    return max(0, int((float(item.get("until", 0) or 0) - time.time()) // 60 + 0.999))


def summary(cfg: dict | None = None) -> str:
    """一句话总结，给气泡/对话页用。"""
    parts = []
    for pid, name, _why, kind in ROSTER:
        if kind == NEVER:
            continue
        st = state(cfg, pid)
        if st == ALWAYS:
            parts.append(_t("page.perm.summary.always", name=display_name(pid)))
        elif st == TIMED:
            parts.append(_t("page.perm.summary.timed", name=display_name(pid),
                            minutes=left_minutes(cfg, pid)))
    return _t("page.perm.summary.sep").join(parts) if parts else _t("page.perm.summary.none")


if __name__ == "__main__":
    import json

    cfg = memory.load_config()
    for pid, name, why, kind in ROSTER:
        print(f"{name:<12}{kind:<10}{state(cfg, pid)}")
    print()
    print(json.dumps(cfg.get("permissions", {}), ensure_ascii=False, indent=2))
