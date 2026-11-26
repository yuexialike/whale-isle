"""新家·第三版：拆开了。

以前什么都塞在这个文件里。现在只管一件事：**把零件拼起来，然后跑**。

  shell.py    壳    崩溃证据 / 送走旧的自己 / pid / 心跳
  persona.py  人格  读 CONSTITUTION / PARTNER / STATE，拼成脑子里的那段话
  gate.py     闸门  看屏幕 / 动手 / 终端，全从一个门
  ask.py      问句  「做吗」的小卡片（主线程弹，工作线程等）口过
  body.py     身体  立绘、气泡、戳、走路
  hands.py    手    鼠标 / 键盘（ctypes SendInput，不经过输入法）
  screen.py   眼睛  抓屏 + 报坐标
  chat.py     耳朵  双击弹输入框
  page.py     对话页
  tts.py      嗓子
  llm.py      脑子
  memory.py   记忆  纯文本

跑：
  D:\\fish\\svc\\venv\\Scripts\\pythonw.exe D:\\fish\\home\\main.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# pythonw（还有打包后的窗口程序）没有控制台：sys.stdout 和 sys.stderr 都是 None。
# 那种情况下任何一句 print() 都会抛 AttributeError，进程一声不响地死掉——
# 11-04 18:00 查「run.bat 用 pythonw 起不来」就是这个：进程起得来，死在第一句 print。
# 所以第一件事先把这两根管子接到文件上，再谈别的。
if sys.stdout is None or sys.stderr is None:
    try:
        _sink_dir = Path(__file__).resolve().parent / "data"
        _sink_dir.mkdir(parents=True, exist_ok=True)
        _sink = open(_sink_dir / "stdout.log", "a", encoding="utf-8", buffering=1)
    except Exception:
        import io

        _sink = io.StringIO()
    if sys.stdout is None:
        sys.stdout = _sink
    if sys.stderr is None:
        sys.stderr = _sink

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import memory
import shell
from body import Body
from chat import InputBox
from gate import Gate
from page import ChatPage


_ACTION_RE = __import__("re").compile(r"（[^）]*）|\([^)]*\)|【[^】]*】|<[^>]*>")


def _strip_actions(text: str) -> str:
    """把（动作）【表情】<标记> 从话里拿掉，剩下的是真要说出口的字。"""
    return _ACTION_RE.sub(" ", text or "").strip()


def _only_actions(text: str) -> bool:
    """整句都是动作才算「不说话」。

    以前只要开头是「（」就当整句闭嘴——11:06 心跳那句
    「（冒出个气泡，又缩回去）老爹好像忙了一整夜……」就被当成哑剧，
    后半句明明是要说的话，结果没出声。
    """
    return not _strip_actions(text)


class _Waker(QObject):
    """心跳在想事情的时候在工作线程里，回来得送回主线程才敢说话。"""

    woke = Signal(str)


def _idle_minutes(log_path) -> float | None:
    """月下最后一次说话是多少分钟前。看不懂就当说不清。"""
    import datetime as _dt

    try:
        lines = memory.read_text(log_path).splitlines()
    except Exception:
        return None
    for line in reversed(lines[-80:]):
        if not (line.startswith("[") and "月下" in line):
            continue
        try:
            stamp = line[1:line.index("]")]
            when = _dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        return (_dt.datetime.now() - when).total_seconds() / 60.0
    return None


def make_gate(data, ask, cfg: dict | None = None, given_turn=None) -> Gate:
    """门装好了，`tools.bind()` 一挂，看屏幕就从这儿过。

    ask 从外面递进来：问句得在主线程弹（`ask.Asker` 管这件事，工作线程只管等）。
    闸门自己不认识界面，只管「答没答应」。
    cfg 是**活的**那份（同一个 dict）：权限页改了，下一次动手就按新的算。
    given_turn 只给自检用（直造一个 Turn 丢进去，不经过 turn.open）。
    """

    def log(line: str) -> None:
        memory.note_file("gate.log", line)

    return Gate(ask=ask, log=log, cfg=cfg, given_turn=given_turn)


def main() -> int:
    # L4 测试口：设了 JINGYU_FAKE_REPLY 就让她照这句回，不调真模型（只在开发机手动验时用）。
    # 不设这个环境变量，这段完全不影响正常跑。
    _fake = os.environ.get("JINGYU_FAKE_REPLY")
    if _fake:
        import llm
        llm.talk = lambda *a, **k: _fake

    # 4-5：单实例锁放在最前面，拿到才继续；拿不到干净退出，不写半截状态。
    # 被 guardian 托管时由 guardian 持锁，子进程不再抢（环境变量标记）。
    if os.environ.get("WHALE_ISLE_SUPERVISED") != "1":
        import single_instance
        if not single_instance.acquire():
            memory.note_file("startup.log", "已有一个在跑（互斥量），这个自己退")
            return 0

    # 第一次开机：没有 config / workspace 就先铺床（已有一律不覆盖）
    import firstrun
    for line in firstrun.ensure():
        try:
            memory.note_file("startup.log", f"首次 {line}")
        except Exception:
            pass

    cfg = memory.load_config()
    # 界面语言：设置页里切过就按 config.language 起；没有就中文。
    try:
        import i18n as _i18n
        _i18n.set_lang(cfg.get("language") or "zh")
    except Exception:                                  # noqa: BLE001
        pass
    try:
        # 5-4：每天一份记忆快照（同一天不重复）；失败不影响开机。
        import history as _history
        _history.snapshot_if_due(cfg)
    except Exception as e:                            # noqa: BLE001
        memory.note_file("startup.log", f"记忆快照没做成：{type(e).__name__} {e}")
    data = memory.data_dir(cfg)

    # ---- 打包后自检门：`YuYu.exe --license-selftest` 只写一张表就走，不开窗 ----
    # 冻结成 exe 之后最容易坏的就是「公钥到底有没有进包」——这里一句话说清。
    if "--license-selftest" in sys.argv:
        import license as lic
        lines = [f"冻结: {'是' if getattr(sys, 'frozen', False) else '否'}",
                 f"程序在哪: {lic._app_dir()}"]
        pub = lic._pub_hex()
        lines.append(f"公钥: {'有 ' + pub[:16] + '…' if pub else '没有（验不了任何码）'}")
        lines.append(f"这台指纹: {lic.machine_id()}")
        ok, why = lic.check()
        lines.append(f"桌上这张码: {'过' if ok else '不过'}（{why}）")
        try:
            lic.make_code("自检", lic.machine_id(), "2099-12-31")
            lines.append("能自己签: 能 —— 私钥也在包里，发出去的那份不该这样")
        except Exception as exc:                                  # noqa: BLE001
            lines.append(f"能自己签: 不能（对）—— {exc}")
        text = "\n".join(lines) + "\n"
        (data / "license-selftest.txt").write_text(text, encoding="utf-8")
        return 0

    import screen as _screen
    # 11-26 22:0x：**这一句从「QApplication 之前」挪到了之后。**
    # 以前抢在 Qt 前面调 SetProcessDpiAwareness(2)（每屏一份，v1 那套），Qt 6 随后想升到
    # per-monitor v2 就被 Windows 拒了，于是每次开机都打一行「SetProcessDpiAwarenessContext() failed: 拒绝访问」。
    # DPI 感知由 Qt 自己设就够（它默认就是 v2），我们只在它没设成的平台上补一下——见下面 app 之后那一句。
    # 11-01 19:0x：分层小人（QWebEngineView）要这个属性，而且必须在 QApplication 之前设
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    # 11-01 20:20 任务栏里要它自己单独一格、用自己的图标。
    # 不设 AppUserModelID 的话，Windows 把 pythonw.exe 起的所有窗口归到「Python」那一格，
    # 图标也是 Python 的——月下 20:13 说的「进程里看不到它独立是一个软件」就是这个。
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Coopanion.Yuyu.1")
        except Exception:
            pass
    app = QApplication(sys.argv)
    # 保险：Qt 已经把进程设成 per-monitor v2 了，这句什么都不做（dpi_aware 先问再设）；
    # 万一某个平台 Qt 没设成，这里补上去，坐标才不会缩 0.75 倍。
    _screen.dpi_aware()
    # 11-01 13:56 修：身体是 Qt.Tool、不算「主窗口」，开场那块才是。开场一 close，
    # Qt 就以为「最后一个窗口关了」→ 整个程序退出去（exit 0，没有报错，鱼凭空没了）。
    # 所以这里明说：别因为没主窗口就退，退出只由 main() 决定。
    app.setQuitOnLastWindowClosed(False)

    # 2-2：分清「真键盘敲的」和「程序 SendInput 塞进来的」。
    # 没装上也不影响跑：turn 会记 provenance_unavailable，闸门拒（这一轮不给电脑权限），
    # 聊天本身照常。日志里「provenance_unavailable」和「unknown」是分开的。
    try:
        import input_provenance as _prov
        _ok = _prov.start()
        memory.note_file("prov.log", f"开机 start()={_ok} available={_prov.available()} "
                                     f"状态={_prov.status()}")
        memory.note_file("startup.log", f"键盘来源: {_prov.status()}")
    except Exception as e:                            # noqa: BLE001
        import traceback
        memory.note_file("prov.log", "开机 start() 抛异常：\n" + traceback.format_exc())
        memory.note_file("startup.log", f"键盘来源钩不上：{type(e).__name__} {e}")

    # ---- 图标：桌面快捷方式上那张 isla（20:16 月下说换成「现在用的这个」）----
    # 用哪张只在 appicon.py 里定一次：先 isla.ico，找不到退回 yuyu.ico（老包里只有它）。
    import appicon
    _ico = appicon.path()
    if _ico is not None:
        app.setWindowIcon(QIcon(str(_ico)))
    else:
        memory.note_file("startup.log", f"没有图标文件：{appicon.here()}")

    shell.arm_crash_log(data)
    shell.retire_old(data)
    shell.retire_lookalikes(Path(__file__).resolve())
    shell.claim_pid(data)

    # ---- 门：没过认证就只开一张小窗，别的什么都不做 ----
    # 月下这台先关着（config.license_required = false），发给别人时才打开。
    if bool(cfg.get("license_required", False)):
        import license as lic
        ok, why = lic.check()
        if not ok:
            memory.note_file("license.log", f"没过门（{why}），弹窗要码")
            from license_ui import ask_code
            if not ask_code(why):
                memory.note_file("license.log", "没给码，退出")
                return 0
            memory.note_file("license.log", f"给码了：{lic.check()[1]}")
        else:
            memory.note_file("license.log", f"过了门：{why}")

    # 人格拼一次，写进 startup.log 备查（看它读到的是不是我写的那几份）
    import persona
    prompt = persona.system_prompt(cfg)
    memory.note_file("startup.log", f"人格拼好了: {len(prompt)} 字")

    # 3-4：形象包从 skin/figures/<id> 取；config 没写就用临时包 whale。
    import figure_pack
    figure_pack.set_current(cfg.get("figure_pack") or "whale")

    body = Body(cfg.get("name", "鱼鱼"), float(cfg.get("x_fraction", 0.5)),
                str(cfg.get("figure_image", "")), str(cfg.get("roam", "free")),
                layered=str(cfg.get("layered_figure", "")),
                layered_theme=str(cfg.get("layered_theme", "dark")),
                float_height=int(cfg.get("float_height", 0) or 0),
                bubble_font=float(cfg.get("bubble_font", 1.0) or 1.0),
                bubble_width=float(cfg.get("bubble_width", 1.0) or 1.0),
                bubble_seconds=float(cfg.get("bubble_seconds", 5.0) or 5.0),
                hide_fullscreen=bool(cfg.get("hide_fullscreen", False)),
                scale=float(cfg.get("scale", 1.0) or 1.0))

    # ---- 开场：先把片子放完，身体再出面（11-01 接进来的）----
    # 「播不播」只有 boot.decide_play 一处判断（cfg["boot_animation"] = start / daily / off）；
    # 这里只管顺序和兜底——开场出任何问题都不许挡住主界面。
    boot_screen = None
    try:
        import boot as _boot
        if _boot.decide_play(cfg, data):
            _boot.mark_played(data)
            boot_screen = _boot.show_boot()
    except Exception:
        import traceback
        memory.note_file("startup.log", "开场没放成：\n" + traceback.format_exc())
        boot_screen = None

    def _figure_on() -> bool:
        """形象要不要站到屏幕上。默认站；关掉就只剩任务栏那一格和设置页。"""
        v = cfg.get("figure_visible", True)
        if isinstance(v, str):
            return v.strip().lower() not in ("0", "false", "no", "off", "关", "不", "隐藏", "藏")
        return bool(v)

    def _reveal_body() -> None:
        if not _figure_on():
            body.show_figure(False)
            memory.note_file("startup.log", "形象关着（figure_visible=false），这次不站出来")
            return
        body.show_figure(True)

    if boot_screen is not None:
        boot_screen.finished.connect(_reveal_body)
        # 兜底：万一动画卡住、finished 没发出来，也别让界面永远不出来
        QTimer.singleShot(int(getattr(boot_screen, "_total", 20000)) + 5000, _reveal_body)
    else:
        _reveal_body()

    # ---- 第一次开机的引导页（20:15 清单第 7 项）----
    # 只在「从来没看过」的时候弹（配置里 `welcomed` 还是 false）；看完写 true，以后不再弹。
    # 摆在开场之后：片子放完、身体出来了，人才看到这页纸，不跟开场抢屏幕。
    _welcomed = {"shown": False}

    def _show_welcome() -> None:
        if _welcomed["shown"]:
            return
        _welcomed["shown"] = True
        try:
            import welcome as _welcome
            _welcome.show_welcome(cfg)
        except Exception:
            import traceback
            memory.note_file("startup.log", "引导页没弹成：\n" + traceback.format_exc())

    if boot_screen is not None:
        boot_screen.finished.connect(_show_welcome)
        QTimer.singleShot(int(getattr(boot_screen, "_total", 20000)) + 300, _show_welcome)
    else:
        QTimer.singleShot(1200, _show_welcome)

    def _apply_figure() -> None:
        """开关一按就见效，不用等重启。"""
        body.show_figure(_figure_on())
        memory.note_file("startup.log", f"形象开关 → {'站到屏幕上' if _figure_on() else '收起来'}")


    from ask import Asker
    asker = Asker(near_getter=lambda: body)

    gate = make_gate(data, asker.ask, cfg)
    try:
        # 4-1：权限表的 ask_each（对外发消息、删文件）要能弹卡问人，走同一个 asker。
        import permissions as _perm
        _perm.set_asker(asker.ask)
    except Exception:                                 # noqa: BLE001
        pass
    import tools
    tools.bind(gate)
    memory.note_file("startup.log", f"闸门就绪: {len(gate.__dict__)} 项; 工具 {len(tools.TOOLS)} 个")

    # ---- 嗓子：说一句、冒一个气泡 ----
    from tts import Voice
    voice = Voice(cfg)

    def apply_live(c: dict) -> None:
        """设置页每存一次就走这儿：能当场换的当场换上，不让人重启。

        换不动的（大小、立绘、名字进窗口标题这些）留给下次开机——但嘴上要说清是哪样。
        """
        # 11-04 17:43 他勾掉「站在屏幕上」我却还站着：
        # 设置页手里的是一份**副本**（`dict(cfg)`），存盘存的是副本，
        # 我这边读的还是老的那份，永远看不见 False。所以先把副本里的值搬回来。
        if isinstance(c, dict):
            try:
                cfg.update(c)
            except Exception:
                pass
        try:
            body.apply_look(c)
        except Exception as e:                        # noqa: BLE001
            memory.note_file("startup.log", f"装扮没当场换上：{type(e).__name__} {e}")
        try:
            voice.enabled = bool(c.get("speak_aloud", True))
            voice.url = str(c.get("tts_url") or voice.url)
        except Exception:
            pass
        try:
            minutes = float(c.get("heartbeat_minutes", 30) or 30)
            hb = getattr(app, "_heartbeat", None)
            if hb is not None:
                hb.setInterval(int(max(1.0, minutes) * 60_000))
        except Exception:
            pass
        _apply_figure()

    mouth = {"ears": None}          # 耳朵还没装好时先留个空位

    def say(text: str, seconds: float = 5.0) -> None:
        if _figure_on() or body.isVisible():     # 形象关着就只进对话页，不硬把窗口叫出来
            body.say(text, seconds)
        speaking = not _only_actions(text)
        if speaking:
            spoken = _strip_actions(text) or text
            voice.say(spoken)
            # 自己一出声就先捂一会儿耳朵，不然会听见自己，再回自己一句
            ear = mouth["ears"]
            if ear is not None:
                ear.deaf_for(min(30.0, len(spoken) / 4.5 + 1.5))
        # 一条也记进 chat.log，对话页才看得见（以前只有打过字的才记）
        # 18:41 修：多行的回答按行存会把一条拆成好几行，对话页只认得开头那一行，
        # 重开页面就只剩半句。所以整段压成一行再写。
        try:
            cap = "说过 · 出声" if speaking else "说过"
            one = " ".join(str(text).split())
            memory.note_file("chat.log", f"我: {one}")
            memory.note_file("chat.log", f"· {cap}")
        except Exception:
            pass

    # ---- 插件：只装 config.plugins 里点了名的（其余文件躺着也不跑）----
    # 月下 12:03：插件不预装，要装得从他那儿拿。所以单子在 config 里，代码不认识插件。
    def make_plug_ctx() -> dict:
        """插件拿到的 ctx；开机和设置页共用这一份，别两处各拼一个。

        3-2 改：以前 ctx 只在 main() 里拼一次、装完就丢，设置页装卸插件时没有
        say/body/hooks 可用；现在存进 plug.set_ctx，设置页用 plug.ctx() 取同一份。
        """
        import hooks as _hooks
        return {
            "say": say,
            "tools": tools,
            "config": cfg,
            "data_dir": data,
            "workspace": memory.workspace(cfg),
            "body": body,                 # 动作插件要一条能指挥身体的路
            "hooks": _hooks.HOOKS,        # 推上下文 / 叫醒脑子 / 冒泡（见 hooks.py）
        }

    try:
        import plug
        plug.set_ctx(make_plug_ctx())
        for line in plug.load(cfg, plug.ctx()):
            memory.note_file("startup.log", f"插件 {line}")
    except Exception as e:                            # noqa: BLE001
        memory.note_file("startup.log", f"插件装不上：{type(e).__name__} {e}")

    # ---- 开场白 ----
    # 11-03 15:10 月下问「为什么每次重启都说这句我回来了，什么什么什么什么什么」：
    # 以前开机固定念「我回来了。」+ STATE.md 那节的第一行。那节很久没更新，
    # 于是每次重启念的都是同一句旧的，还一条条堆进对话页。
    # 现在：这句话只在**变了**的时候念一遍，重复的就只说「我回来了。」。
    headline = memory.state_headline(cfg)
    ws = memory.workspace(cfg)
    short = ""
    if headline:
        short = headline.strip()
        if len(short) > 24:
            short = short[:24] + "…"
    _last_path = data / "open-line.txt"
    try:
        _last = _last_path.read_text(encoding="utf-8").strip()
    except OSError:
        _last = ""
    # 15:14 月下要「开机动画能关」——顺手也给这句打招呼一个开关（习惯页「开机时」）。
    _greet = cfg.get("greet_on_start", True)
    if isinstance(_greet, str):
        _greet = _greet.strip().lower() not in ("0", "false", "no", "off", "关", "不", "不播")
    if not _greet:
        pass                              # 关掉就安安静静起来，不冒泡也不出声
    elif short and short != _last:
        say(f"我回来了。{short}", 6.0)
        try:
            _last_path.write_text(short + "\n", encoding="utf-8")
        except OSError:
            pass
    else:
        say("我回来了。", 4.0)
    memory.note_file("startup.log", f"开机，读 {ws}")

    # ---- 耳朵：双击身体弹输入框，右键开对话页 ----

    box = InputBox(cfg, say, status=body.status, said=body.add_said_line)
    page = ChatPage(cfg, say, status=body.status, embedded=True, said=body.add_said_line)
    page.history = box.history            # 两个入口共用一个对话上下文
    page.body = body                      # 3-4：回答里的【…】/<…> 要能指挥身体

    # ---- 提问卡 + 静音：11-03 15:05 对着 COOP 的 pet_ask / hush 补上的 ----
    import threading as _th

    def _ask_user_tool(args: dict) -> str:
        """弹一张卡问一句，等他挑。等不到就说没答，不许替他做主。"""
        question = str(args.get("question") or "").strip()
        if not question:
            return "得给一个问句。"
        raw = args.get("options") or []
        if isinstance(raw, str):
            raw = [raw]
        options = [str(o).strip() for o in raw if str(o).strip()][:3]
        slot = {"ev": _th.Event(), "text": ""}

        def picked(text: str) -> None:
            slot["text"] = str(text)
            slot["ev"].set()

        page.ask_async(question, options, picked)
        memory.note_file("chat.log", f"我问: {question}（{' / '.join(options) or '只让他自己写'}）")
        try:
            timeout = float(args.get("timeout") or 180)
        except (TypeError, ValueError):
            timeout = 180.0
        if not slot["ev"].wait(timeout):
            return "他没答（卡片还开着，或者被关掉了）——这一轮别替他做主。"
        memory.note_file("chat.log", f"· 他答: {slot['text']}")
        return f"他答了：{slot['text']}"

    def _hush_tool(args: dict) -> str:
        """停下嗓子。给了 minutes 就静这么久，气泡不受影响。"""
        try:
            minutes = float(args.get("minutes") or 0)
        except (TypeError, ValueError):
            minutes = 0.0
        if minutes > 0:
            voice.mute(minutes * 60)
            memory.note_file("chat.log", f"· 静音 {minutes:g} 分钟")
            return f"静音了，{minutes:g} 分钟内不出声（气泡照旧）。"
        voice.stop()
        memory.note_file("chat.log", "· 停下声音")
        return "声音停了（后面再说照常念）。"

    tools.register(
        {
            "type": "function",
            "function": {
                "name": "ask_user",
                "description": "在对话页弹一张卡片问他一句，等他的回答。最多三个选项，他还能自己写。"
                               "等不到就返回「没答」，那种时候别替他做主。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "问什么，一句话"},
                        "options": {"type": "array", "items": {"type": "string"},
                                    "description": "1-3 个选项，短一点"},
                        "timeout": {"type": "number", "description": "等多少秒，默认 180"},
                    },
                    "required": ["question"],
                },
            },
        },
        _ask_user_tool, owner="core")

    tools.register(
        {
            "type": "function",
            "function": {
                "name": "hush",
                "description": "立刻停下嗓子（不再念）。给 minutes 就静音这么久。气泡不影响。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "minutes": {"type": "number",
                                    "description": "静音多少分钟；不给就是只停这一下"},
                    },
                },
            },
        },
        _hush_tool, owner="core")

    def open_chat() -> None:
        x, y = body.x() + 10, max(0, body.y() - 66)
        memory.note_file("event.log", f"open_chat 到 ({x},{y})")
        box.pop_up(x, y)

    body.on_double_click = open_chat

    # ---- 设置页：11-01 14:05 月下说「把对话加到设置里头」----
    # 所以对话不再是单独一扇窗，它是设置页的第一页；屏幕上的门只有这一扇。
    _settings_win = {"w": None}

    def open_settings(go_chat: bool = False):
        import settings_page
        w = _settings_win["w"]
        try:
            if w is not None:
                w.show()
                w.raise_()
                w.activateWindow()
                if go_chat:
                    w.go_chat()
                return w
        except RuntimeError:
            pass                             # 关掉时已经销毁了，重新开一张
        w = settings_page.show_settings(cfg, chat=page)
        _settings_win["w"] = w
        try:
            w.on_apply = apply_live           # 每存一次就当场换，不用重启
        except Exception:
            pass
        body.set_behind_panels(True)          # 面板开着，她让到下面去（11-02 13:17 的毛病）
        try:
            w.destroyed.connect(lambda *_: body.set_behind_panels(False))
        except Exception:
            pass
        if go_chat:
            w.go_chat()
        return w

    body.on_right_click = lambda: open_settings(True)     # 右键：设置 → 对话那页

    # ---- 任务栏那一格：11-02 20:07「任务栏里要有一格，点了能开来」----
    # 本体是 Qt.Tool，Windows 不给它任务栏按钮；立一个 1×1 的透明锚占那一格，
    # 点了就把设置页（对话那页）开出来。ancher 挂在 app 上，别让 GC 收走。
    try:
        import taskbar as _taskbar
        app._taskbar_anchor = _taskbar.TaskbarAnchor(
            lambda: open_settings(True),
            title=str(cfg.get("name", "鱼鱼")),
            icon=app.windowIcon())
        app._taskbar_anchor.show()
        memory.note_file("startup.log", "任务栏锚立好了")
    except Exception:
        import traceback
        memory.note_file("startup.log", "任务栏锚没立起来：\n" + traceback.format_exc())


    page.on_settings = open_settings

    # ---- 耳朵：按住 ear_key 说话（config 里 "ears": true 才开；默认关）----
    if bool(cfg.get("ears", False)):
        from hearing import Ears
        try:
            import permissions as _perm
            _perm.audit(cfg, "mic", "开耳朵")
        except Exception:  # noqa: BLE001
            pass
        ear = Ears(cfg)
        ear.pause_check = lambda: voice.busy      # 我嘴里有话说的时候不听
        mouth["ears"] = ear
        voice.set_ear(ear)                      # 出声时先闭麦（half-duplex）

        def _on_hold(down: bool) -> None:
            """按住时头上挂一句，让他知道耳朵真的在听（19:07 他说「看不到反馈」）。"""
            if down:
                body.status("在听…… （松开手就说完了）", 600)
            else:
                body.clear_status()

        def _on_heard(t: str) -> None:
            body.status(f"听到：{t}", 4)
            box.submit_text(t, "voice")

        ear.holding.connect(_on_hold)                                  # 回主线程才敢动界面
        ear.note.connect(lambda s: body.status(s, 4))
        ear.heard.connect(_on_heard)
        ear.start()
        memory.note_file("startup.log",
                         f"耳朵开着（{ear.mode}，键 {ear.key_name}）")
    else:
        memory.note_file("startup.log", "耳朵关着（config.ears = false）")

    # ---- 自检：key 有没有、脑子通不通（结果写进 startup.log，外面看得到）----
    def selftest() -> None:
        import llm
        # 工具层：不进模型，直接跑一遍，看能不能读到自己
        try:
            import tools
            listing = tools.run("list_memory", {})
            head = listing.splitlines()[0] if listing else "(空)"
            one = tools.run("read_memory", {"path": "STATE.md", "limit": 1})
            memory.note_file("startup.log", f"工具层: {len(tools.TOOLS)} 个; 首项={head}; 读STATE={one[:30]}")
        except Exception as e:
            memory.note_file("startup.log", f"工具层坏了: {type(e).__name__} {e}")

        # 闸门自测：开机这一轮没有来源，所以「看屏幕」必须被拒——拒了才算装对了
        try:
            import tools

            import turn as _turn
            memory.note_file("startup.log", f"闸门自测: {tools.run('see_screen', {})[:80]}")
            # 自检专用：直接造一个「人打的」Turn 丢给 Gate，**不经过开轮入口 turn.open**。
            # 「假装人说话」这条路只许活在这一段里，别处谁都不许抄。
            fake = _turn.Turn(id="selftest", source="typed", entry="selftest")
            tools.bind(make_gate(data, asker.ask, cfg, given_turn=fake))
            try:
                memory.note_file("startup.log", f"眼睛自测: {tools.run('see_screen', {})[:150]}")
            finally:
                tools.bind(gate)          # 换回真的门
                # 11-21 补：自检这张图只是给启动日志看的，不交给模型。
                # 不清掉的话，后面随便哪个插件轮调一次工具，都会把这张开机旧图
                # 当成「刚截的」贴进 messages（11:39 真机撞到：她对着开机时的
                # 设置页截图说「看到了」）。take_image 取一次就清。
                try:
                    tools.take_image()
                except Exception:                     # noqa: BLE001
                    pass
        except Exception as e:
            memory.note_file("startup.log", f"闸门自测坏了: {type(e).__name__} {e}")

        # 手自检：只验结构体/系统调用在不在，不动鼠标
        try:
            import hands
            memory.note_file("startup.log", hands.self_check())
        except Exception as e:
            memory.note_file("startup.log", f"手坏了: {type(e).__name__} {e}")

        has = bool(llm.api_key(cfg))
        memory.note_file("startup.log", f"key={'有' if has else '没有'}")
        if not has:
            return
        answer = llm.chat([{"role": "user", "content": "只回一个字：在"}], cfg)
        memory.note_file("startup.log", f"brain: {answer[:200]}")

    QTimer.singleShot(1500, selftest)

    # ---- 心跳：醒一次，自己决定说不说话 ----
    waker = _Waker()

    def _hhmm(s: str, default: str) -> int:
        """'23:00' → 1380。看不懂就用默认那个。"""
        try:
            h, _, m = (s or default).strip().partition(":")
            return (int(h) % 24) * 60 + int(m or 0) % 60
        except Exception:                             # noqa: BLE001
            h, _, m = default.partition(":")
            return int(h) * 60 + int(m or 0)

    def sleeping_now() -> bool:
        """熄灯之后到起床之前：心跳醒着也不开口（他 11-04 说的「23 点熄灯」）。"""
        routine = cfg.get("routine") or {}
        if not isinstance(routine, dict):
            return False
        start = _hhmm(routine.get("lights_out", "23:00"), "23:00")
        end = _hhmm(routine.get("wake", "07:30"), "07:30")
        import datetime as _dt
        now = _dt.datetime.now()
        cur = now.hour * 60 + now.minute
        if start == end:
            return False
        return (cur >= start or cur < end) if start > end else (start <= cur < end)

    def wake() -> None:
        """到点了。在后台问一遍：现在要不要开口？不想说就不说。"""
        import threading

        if sleeping_now():
            memory.note_file("heartbeat.log", "熄灯了，这一轮醒着但不说话")
            return

        def work() -> None:
            try:
                import datetime as _dt

                import llm
                idle = _idle_minutes(memory.data_dir() / "chat.log")
                mins = f"{idle:.0f}" if idle is not None else "说不清"
                now = _dt.datetime.now().strftime("%H:%M")
                hush = ""
                if idle is not None and idle < 8:
                    hush = "他才刚说过话，这会儿多半不用你开口。\n"
                text = (
                    f"（心跳）现在 {now}。月下最后一次说话是 {mins} 分钟前。\n"
                    f"{hush}"
                    "没人在叫你。你可以说一句，也可以什么都不说——不说不会挨怪。\n"
                    "想说就直接说，一两句像平时那样；不想说，只回四个字：不说话。"
                )
                answer = llm.talk(text, list(box.history)[-6:], cfg,
                                  source="heartbeat", entry="heartbeat")
                waker.woke.emit(answer or "")
            except Exception as e:
                memory.note_file("heartbeat.log", f"醒的时候坏了: {type(e).__name__} {e}")

        threading.Thread(target=work, daemon=True).start()

    def on_woke(answer: str) -> None:
        answer = (answer or "").strip()
        if not answer:
            memory.note_file("heartbeat.log", "醒了一下，没说出话")
            return
        if "不说话" in answer.replace(" ", "")[:12]:
            memory.note_file("heartbeat.log", "醒了一下，选择不说")
            return
        say(answer, max(6.0, min(20.0, len(answer) / 6.0)))

    waker.woke.connect(on_woke)

    # ---- 插件那三个口子接线（2026-11-01：QQ 插件要能自己叫醒我）----
    def plug_wake(reason: str = "") -> None:
        """插件说「有事」，立刻起一轮，不等心跳（心跳最久半小时）。

        跟心跳只有一处不同：由头是插件给的。电脑那边的规矩一条不少——
        插件不是人：这一轮开成 `source="plugin"`，闸门不认它。
        """
        import threading

        def work() -> None:
            try:
                import llm
                text = (
                    f"（{reason or '插件那边有事'}）\n"
                    "插件推来的那段在上一段里，你自己判断：该回就用它给的发送工具回，"
                    "不该回就只回四个字：不说话。"
                )
                answer = llm.talk(text, list(box.history)[-6:], cfg,
                                  source="plugin", entry="plugin")
                waker.woke.emit(answer or "")
            except Exception as e:
                memory.note_file("heartbeat.log", f"插件叫醒坏了: {type(e).__name__} {e}")

        threading.Thread(target=work, daemon=True).start()

    try:
        import hooks as _hooks
        _hooks.HOOKS.bind(
            wake=plug_wake,
            say=lambda text, sec=6.0: say(text, sec),
            log=lambda text: memory.note_file("plugin.log", text),
        )
        if _hooks.HOOKS.pending():            # 插件装得比这里早，它攒下的话别丢
            plug_wake("插件有话说")
    except Exception as e:                    # noqa: BLE001
        memory.note_file("plugin.log", f"钩子接不上：{type(e).__name__} {e}")


    # ---- 心跳：没人说话也能醒 ----
    hb = shell.start_heartbeat(float(cfg.get("heartbeat_minutes", 30)), on_beat=wake)
    app._heartbeat = hb      # 留个引用，别被回收
    app._waker = waker

    # ---- 闹钟：每 30 秒看一眼有没有到点的（自己的，不靠外面平台）----
    import alarms

    import threading as _alarm_th

    def _qq_voice_send(text: str, to: str) -> str:
        """借 QQ 插件那条嗓子发一条语音。插件没装就照实说，不假装发了。"""
        for mod in list(sys.modules.values()):
            fn = getattr(mod, "_qq_voice", None)
            if callable(fn):
                return fn({"to": to, "text": text})
        return "QQ 插件没装上，语音没发"

    def _speak_line(prompt: str, fallback: str) -> str:
        """到点该说一句：让脑子按平时的口气写，写不出来就用那句现成的。"""
        try:
            import datetime as _dt

            import llm
            now = _dt.datetime.now()
            text = (
                f"（{prompt}）现在 {now.strftime('%H:%M')}。\n"
                "照平时那样说一句，二十字以内，别解释、别写动作标记。"
            )
            line = (llm.talk(text, list(box.history)[-4:], cfg,
                             source="alarm", entry="alarm") or "").strip()
            line = _strip_actions(line).splitlines()[0][:60] if line else ""
            return line or fallback
        except Exception as e:                        # noqa: BLE001
            memory.note_file("alarm.log", f"到点那句没写出来：{type(e).__name__} {e}")
            return fallback

    def _voice_job(a: dict) -> None:
        """闹钟带 voice 的：说一句，再从 QQ 发一条语音过去。"""
        try:
            to = str(a.get("to") or cfg.get("daily_voice_to") or "private:YOUR_QQ")
            prompt = str(a.get("prompt") or a.get("note") or "到点了，跟老爹说一句")
            fallback = str(a.get("say") or a.get("note") or "到点啦")
            line = _speak_line(prompt, fallback)
            res = _qq_voice_send(line, to)
            memory.note_file("alarm.log", f"语音 #{a.get('id')}「{line}」→ {to}：{res}")
        except Exception as e:                        # noqa: BLE001
            memory.note_file("alarm.log", f"语音闹钟坏了：{type(e).__name__} {e}")

    def check_alarms() -> None:
        try:
            for a in alarms.due():
                note = (a.get("note") or "").strip()
                if a.get("_late"):
                    say(f"闹钟（本来是 {a.get('at')} 的）：{note}", 8.0)
                else:
                    say(f"闹钟：{note}", 8.0)
                memory.note_file("alarm.log", f"响 #{a.get('id')} {note}")
                if a.get("voice"):
                    # 合成＋发语音要几秒，别卡着界面
                    _alarm_th.Thread(target=_voice_job, args=(a,), daemon=True).start()
        except Exception as e:
            memory.note_file("alarm.log", f"查闹钟坏了：{type(e).__name__} {e}")

    alarm_timer = QTimer()
    alarm_timer.timeout.connect(check_alarms)
    alarm_timer.start(30_000)
    app._alarm_timer = alarm_timer
    QTimer.singleShot(4000, check_alarms)     # 开机先补一次：断电那会儿错过的

    # ---- 第一次进来：身体先站着，再一张一张问 ----
    # 月下 19:13：「先出形象，然后再弹窗一个一个问。」
    try:
        import welcome
        if welcome.should_show(cfg):
            QTimer.singleShot(1200, lambda: welcome.run_onboarding(cfg, anchor=body, say=say))
    except Exception as e:                                        # noqa: BLE001
        memory.note_file("startup.log", f"欢迎页没开起来：{type(e).__name__} {e}")

    # ---- 开门：双击之后先站出来的是设置页，不是对话页（11-01 14:05 月下说的）----
    QTimer.singleShot(700, lambda: open_settings())

    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        try:
            import memory
            out = memory.data_dir() / "error.log"
        except Exception:
            from pathlib import Path
            out = Path(__file__).resolve().parent / "data" / "error.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(traceback.format_exc(), encoding="utf-8")
        raise
