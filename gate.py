"""闸门：所有「看屏幕 / 动键鼠 / 开终端」都得从这一个门口过。

来源（source）不再是谁随手设的一个变量，而是**这一轮自己带着的**（`turn.py`）：
开轮的时候定死，只读，跟着线程走。只有

    typed   月下在对话页/输入框打的字
    voice   月下按住 F9 说的话

算「人说的」。网页、插件、心跳、闹钟、系统自己、自检，一律不算——
它们传来的话不能当「用电脑」的理由。
例外只有一个：qq 来源，且发送者号码在白名单里（默认只有他一个 1000000000）。
群里谁都能说话，白名单挡得住号码，挡不住「冒充语境」，所以群消息一律不带 qq 来源。

（Coop 那边也有代码级的门：`cua/cua.ts` 的 `permit()` / `permitTerminal()`，
管的是「这一轮能不能用电脑」（四档 + grantMinutes + 终端单独问）。
我们这道门管的是另一件事：**这句话是谁说的**。两层不冲突，各有各的漏。）

我的规矩：

  看（截图、列窗口、缩放）  看屏幕不疼。来源是人说的话，就放行。
  动（点击、拖、滚、打字、按键、聚焦）  每件事问一次，一次只顶一件事，
                                   问的时候说清「要改什么、改了会怎样」。
  终端 / Win+R            默认问；权限页写着「一直允许 / 借一会儿」才不问。

权限（`permissions.py`）是另一层：来源对、可那一格没开，同样不做。

自检怎么办：直接造一个 `Turn` 丢给 `Gate(given_turn=...)`——**不经过开轮入口**。
「假装人说话」这条路只许活在 `main.py` 自检那一段里，别处谁都不许抄。
"""
from __future__ import annotations

from typing import Callable

import turn

# 旧名字：等于 turn.HUMAN。留着是因为外面可能还有 import（确认没人用就删）。
SOURCES = turn.HUMAN


class Refused(Exception):
    """没答应，或者来路不对。工具不执行，把 reason 原样说给人听。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Gate:
    """一个门口。

    ask:          问人一件事，返回 True/False。问的话要说清做什么、后果是什么。
    log:          记一笔（往 gate.log 写）。可以不给。
    cfg:          活的 config：权限页一改，下一次动手就按新的算。
    given_turn:   **只给自检用**。给一个 Turn 就当这一轮是它，不读 turn.now()。
    """

    def __init__(self, ask: Callable[[str], bool], log: Callable[[str], None] | None = None,
                 cfg: dict | None = None, given_turn: "turn.Turn | None" = None):
        self._ask = ask
        self._log = log or (lambda line: None)
        self._cfg = cfg
        self._given_turn = given_turn

    # ---- 拒 ----

    def _refuse(self, reason: str) -> None:
        """记一笔（这一轮拒了一次），写日志，然后抛。"""
        turn.count_refusal()
        self._log("deny: " + reason)
        raise Refused(reason)

    # ---- 来路 ----

    @staticmethod
    def _caller() -> str:
        """拒的时候写清谁在调：跳过 gate/turn/tools 自己的帧，取第一帧外面的。"""
        import traceback
        from pathlib import Path
        stack = traceback.extract_stack()
        for fr in reversed(stack[:-1]):
            name = Path(fr.filename).name
            if name in ("gate.py", "turn.py", "tools.py"):
                continue
            return f"{name}:{fr.lineno}:{fr.name}"
        return "?"

    def _where(self, t) -> str:
        """日志里那三样：caller / source / entry。"""
        return (f"（caller={self._caller()} source={t.source} "
                f"entry={t.entry or '-'}）")

    def _qq_whitelist(self) -> tuple:
        """QQ 上谁能当「月下」：只认号码，配置键 qq_sources。

        默认只有他一个（1000000000）。配置里写成别的（比如空的 []）就按配置来——
        空列表 = 谁都不算，那 QQ 来的话一律拒。
        """
        cfg = self._cfg
        if cfg is None:
            try:
                import memory
                cfg = memory.load_config()
            except Exception:                        # noqa: BLE001
                cfg = {}
        allow = (cfg or {}).get("qq_sources", ("1000000000",))
        if isinstance(allow, str):
            allow = [x for x in allow.replace("，", ",").split(",") if x.strip()]
        try:
            return tuple(str(x).strip() for x in allow if str(x).strip())
        except TypeError:
            return ("1000000000",)

    def _soft_no_probe(self) -> bool:
        """软档开关：钩子没起来时只记不拦。默认开，cfg 里一行可关。"""
        cfg = self._cfg
        if cfg is None:
            try:
                import memory
                cfg = memory.load_config()
            except Exception:                        # noqa: BLE001
                cfg = {}
        return bool((cfg or {}).get("typed_soft_when_no_probe", True))

    def _why(self, what: str) -> None:
        """来路不对就当场拒；对就什么都不做（返回 None）。

        来源是只读的：这里没有任何「设一下」的路——要换来源只能换一轮。
        """
        t = self._given_turn or turn.now()
        if t is None:
            self._refuse(f"这一轮没有来源——不是月下在桌宠这边说的话，我不能{what}。")
        if t.source == "qq":
            sender = str((t.meta or {}).get("sender") or "")
            allow = self._qq_whitelist()
            if sender and sender in allow:
                return
            self._refuse(f"这句是 QQ 上 {sender or '不明号码'} 说的，不在白名单里，"
                         f"我不把它当成月下说的。白名单只认号码。")
        if t.source in turn.HUMAN:
            if t.source == "typed":
                if self._given_turn is not None:
                    return      # 自检专用：given_turn 不走 provenance，别把自检误伤
                how = str((t.meta or {}).get("input") or "unknown")
                where = self._where(t)
                if how == "physical":
                    return
                if how == "injected":
                    self._refuse("这一轮的字是程序塞进来的（不是键盘打出来的），我不把它当成你说的。"
                                 "要我用电脑，你自己敲一句，或者按住 F9 说一句。" + where)
                if how == "provenance_unavailable":
                    reason = ("键盘来源探针没起来（provenance_unavailable），分不清这轮的字是人打的"
                              "还是程序塞的，不敢动。")
                    if self._soft_no_probe():
                        # 过渡软档：钩子起不来时别把月下所有打字都拒了；只记不拦，日志留 soft 标记。
                        self._log("deny: " + reason + "soft=1 mode=soft（只记不拦）" + where)
                        return
                    self._refuse(reason + where)
                self._refuse(f"这一轮拿不出键盘证据（input={how}）——一个人真在打字就一定有过键盘"
                             f"事件；拿不出证据的，就别自称是人打的。" + where)
            return
        self._refuse(f"{turn.label(t.source)}传来的话不能让我{what}。"
                     "要用电脑得是月下在桌宠这边自己说的——让他说一句，我再做。")

    # ---- 权限那一张表 ----

    def _perm_ok(self, pid: str) -> None:
        """11-04 17:52 补的：权限页以前是个空壳——没人读它。

        从今往后，看屏幕 / 动手 / 终端这三件都先问一遍那张表：
        没开就不做，回一句话告诉人去哪一格点一下。
        （`ask_each` 那两档（删文件、对外发送）本来就要一次一次点头，这里放过去。）
        """
        import permissions as p

        st = p.state(self._cfg, pid)
        if st in (p.ALWAYS, p.TIMED, p.ASK):
            return
        name = p.BY_ID.get(pid, (pid, "", ""))[0]
        self._refuse(f"「{name}」这一格没开。去设置 → 权限，点「一直允许」或者「借一会儿」。")

    # ---- 看 ----

    def see(self, what: str) -> None:
        """看屏幕、列窗口、放大。来源对、权限开着，就放行。"""
        self._why(what)
        self._perm_ok("screen")
        self._log(f"see ok: {what}")

    # ---- 动 ----

    def act(self, what: str, effect: str = "") -> None:
        """动手。每件事问一次，问一次只顶这一件。

        what:   做什么（「在 (400, 60) 点一下」）
        effect: 改了会怎样（「会把当前窗口的那一行选中」），问人的时候一起说。
        """
        self._why(what)
        self._perm_ok("input")

        import permissions as p

        if p.state(self._cfg, "input") in (p.ALWAYS, p.TIMED):
            # 权限页写着「一直允许 / 借了一会儿」，就别再一件一件地问了。
            self._log(f"act pass: {what}")
            return

        q = f"我要{what}"
        if effect:
            q += f"，{effect}"
        q += "。做吗？"

        if not self._ask(q):
            self._refuse("这件事没答应，我没做。")
        self._log(f"act ok: {what}")

    # ---- 终端 ----

    def terminal(self, what: str) -> None:
        """终端里打字、按键、Win+R。

        21:15 改（月下：「走一步要一步，太频繁了」）：以前不管权限页怎么设，
        每一句都问一遍——写个插件半小时点二十次「做」。
        现在按权限表来：always / timed 不问（timed 是「借它一会儿」，到点自己收回）；
        ask / off 还是问，问一次顶一条。
        """
        self._why(what)
        self._perm_ok("shell")

        import permissions as p

        st = p.state(self._cfg, "shell")
        if st in (p.ALWAYS, p.TIMED):
            self._log(f"terminal pass({st}): {what}")
            return

        q = f"我要在命令行里{what}。这一步会和别的动手分开问，做吗？"
        if not self._ask(q):
            self._refuse("终端那一步没答应，我没做。")
        self._log(f"terminal ok: {what}")
