"""插件：从月下那儿拿了才装的东西。

12:03 月下说的第三档：「有一些插件不会直接往里头装，要让他们从我这拿插件去装。」

所以：
  · 核心那一套（壳 / 脑子 / 手 / 门）永远在，插件拔了它照样活；
  · `plugins/` 里的东西，程序**只认 config.json 的 `plugins` 里点了名的**；
  · 名字没在单子上的，文件躺在那儿也不会跑；
  · 单子里写 `"*"` 才是「全装」（我这台开发机图省事可以用，发出去不许这样写）。

一个插件就一个 `.py`，长这样：

    NAME  = "现在几点"            # 给人看的名字，可有可无
    TOOLS = [(schema, fn), ...]   # 和 tools.TOOLS 里那些 schema 一个形状；fn(args) -> str
    def setup(ctx):               # 可选：要先做点什么（拿 ctx 里的 say / tools / config）
        ...

`ctx` 里给的是：say(text) / tools(模块) / config / data_dir / workspace / body，
以及 **hooks**（2026-11-01 21:52 加的，见 `hooks.py`）——插件想「自己冒头」只能走它：

    ctx["hooks"].push("QQ 来消息了：……")   # 塞进下一轮；取一次就清空
    ctx["hooks"].wake("QQ 来消息了")        # 立刻起一轮，不等心跳
    ctx["hooks"].say("连不上 QQ 了")        # 不经过脑子，直接冒个泡

光有 `TOOLS` 的插件只能被叫；要主动说话，就得 `push` + `wake`。
（插件不是人：`wake` 起的那一轮开成 `source="plugin"`，闸门不认，不许动电脑。）
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_DIR = HERE / "plugins"

# 从链接装的时候最多收多大（字节）。见 install_from_url 里那段注释。
MAX_BYTES = 1024 * 1024


def dir_path() -> Path:
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    return PLUGIN_DIR


_LIVE: dict[str, object] = {}       # 已经跑起来的插件：id → 模块（设置页要问它「现在怎么样」）
_MOUNTED: dict[str, dict] = {}      # id → {tools: [名字], module: 模块, stopped: bool}
_CTX: dict = {}                     # 启动时 main 塞进来的那份 ctx；设置页装卸时共用


def set_ctx(ctx: dict | None) -> None:
    _CTX.clear()
    _CTX.update(ctx or {})


def ctx() -> dict:
    return dict(_CTX)

# 插件契约版本：MANIFEST 里 api 不等于它就拒装（照 Coop 的 extension api 思路，只留一个版本号）。
API = 1


def _load_file(path: Path):
    spec = importlib.util.spec_from_file_location(f"petplug_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"读不了 {path.name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 记下来：module_from_spec 不会自动进 sys.modules，不记就找不回这个模块，
    # 设置页那行状态灯也就没法问它「连上没有」。
    _LIVE[path.stem] = mod
    sys.modules.setdefault(f"petplug_{path.stem}", mod)
    return mod


def available() -> list[str]:
    """plugins/ 里有哪些文件（不管装没装）。"""
    p = dir_path()
    return sorted(f.stem for f in p.glob("*.py") if not f.name.startswith("_"))


def describe(name: str) -> dict:
    """只看不跑：从文件里抠出 NAME / ABOUT / 几个工具。

    扩展市场那张表要一排排摆出来，**不能为了看一眼就 exec 一遍**——
    别人给的插件里写什么都有可能。用 ast 只读字面量，读到多少算多少。
    """
    path = dir_path() / f"{name}.py"
    info = {"id": name, "name": name, "about": "", "tools": 0,
            "tool_names": [], "size": 0, "mtime": 0.0, "broken": "",
            "icon": "", "has_settings": False}
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        info["size"] = len(src.encode("utf-8"))
        info["mtime"] = path.stat().st_mtime
    except OSError as e:
        info["broken"] = f"读不了（{type(e).__name__}）"
        return info

    try:
        import ast

        tree = ast.parse(src)
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if not isinstance(t, ast.Name):
                    continue
                if t.id in ("NAME", "ABOUT", "DOC", "DESCRIPTION", "DESC", "ICON"):
                    try:
                        val = ast.literal_eval(node.value)
                    except Exception:                  # noqa: BLE001
                        continue
                    if isinstance(val, str):
                        if t.id == "NAME":
                            info["name"] = val.strip() or name
                        elif t.id == "ICON":
                            info["icon"] = val.strip()[:2]
                        elif not info["about"]:
                            info["about"] = val.strip()
                elif t.id == "TOOLS":
                    # 一个条目是 `(schema, 函数)` —— 第二格是函数名，literal_eval 读不动整条，
                    # 所以只把每条的**第一格**（schema 字典）抠出来念。
                    elts = node.value.elts if isinstance(node.value, ast.List) else []
                    if isinstance(node.value, ast.List):
                        info["tools"] = len(elts)
                    else:
                        try:
                            info["tools"] = len(ast.literal_eval(node.value))
                        except Exception:              # noqa: BLE001
                            info["tools"] = 0
                    names = []
                    for elt in elts:
                        if not (isinstance(elt, ast.Tuple) and elt.elts):
                            continue
                        try:
                            schema = ast.literal_eval(elt.elts[0])
                            nm = schema.get("function", {}).get("name")
                        except Exception:              # noqa: BLE001
                            continue
                        if isinstance(nm, str) and nm:
                            names.append(nm)
                    info["tool_names"] = names
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id in ("SETTINGS", "SETTINGS_SCHEMA"):
                        info["has_settings"] = True
            elif isinstance(node, ast.FunctionDef) and node.name in ("status", "STATUS"):
                info["has_status"] = True
    except SyntaxError as e:
        info["broken"] = f"语法不对（第 {e.lineno} 行）"
    except Exception as e:                          # noqa: BLE001
        info["broken"] = f"读不干净（{type(e).__name__}）"
    return info


def live(name: str):
    """已经在跑的那个模块对象——没装过的插件从来没被 exec 过，返回 None。"""
    mod = _LIVE.get(name)
    if mod is not None:
        return mod
    return sys.modules.get(f"petplug_{name}")


def status(name: str):
    """插件自己报一句现在的样子：(亮不亮, 一句话)。没写就 None。

    为什么让插件自己报：只有它知道「连着没有、接了几条」。设置页去猜准会猜错。
    """
    mod = live(name)
    fn = getattr(mod, "status", None) if mod is not None else None
    if not callable(fn):
        return None
    try:
        ok, text = fn()
        return bool(ok), str(text)
    except Exception as e:                          # noqa: BLE001
        return False, f"状态读不出来（{type(e).__name__}）"


def settings_schema(name: str) -> list[dict]:
    """插件声明的设置项：`[{key,label,kind,hint}]`，kind 是 text / int / bool / lines。"""
    mod = live(name)
    data = getattr(mod, "SETTINGS", None) if mod is not None else None
    return data if isinstance(data, list) else []


def settings_section(name: str) -> str:
    """这份设置存在 config 的哪一格；默认跟插件 id 同名，插件可以自己改。"""
    mod = live(name)
    sec = getattr(mod, "SETTINGS_SECTION", None) if mod is not None else None
    return str(sec) if isinstance(sec, str) and sec else name


def catalogue(cfg: dict) -> list[dict]:
    """整个插件目录，顺手标上装没装。"""
    chosen = cfg.get("plugins") or []
    if isinstance(chosen, str):
        chosen = [chosen]
    chosen = [str(c).strip() for c in chosen]
    on = "*" in chosen
    rows = []
    for name in available():
        info = describe(name)
        info["on"] = on or name in chosen
        info["wildcard"] = on
        rows.append(info)
    return rows


def install_file(src, overwrite: bool = False):
    """把外面拿来的 .py 收进 plugins/。返回 (收下的名字, 原来的路径)。"""
    from pathlib import Path as _P
    from shutil import copyfile

    src = _P(src)
    if src.suffix.lower() != ".py":
        raise ValueError("只收 .py")
    dest = dir_path() / src.name
    if dest.exists() and not overwrite:
        raise FileExistsError(dest.name)
    copyfile(src, dest)
    return dest.stem, src


def install_from_url(url: str, overwrite: bool = False):
    """从直链下回来收进 plugins/。没有服务器也能装——只要有个能直链的地方。

    GitHub raw、gitee raw、网盘直链、自己丢在某个静态空间里的文件都行。
    只收 .py；下回来先看能不能 ast 解析，语法都不对的不往家里放。
    """
    import urllib.parse
    import urllib.request
    from pathlib import Path as _P

    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("得是 http(s) 的直链")
    stem = _P(urllib.parse.urlparse(url).path).name
    if not stem.lower().endswith(".py"):
        raise ValueError("链接最后那段得是 xxx.py")
    req = urllib.request.Request(url, headers={"User-Agent": "jingyu/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        # 11-05 10:00 加的上限：一个插件几百行，1 MB 绰绰有余。
        # 以前是 read() 一把梭——链接给错、指到一个大文件，就是几百兆凭空落进硬盘。
        raw = resp.read(MAX_BYTES + 1)
    if not raw:
        raise ValueError("下回来是空的")
    if len(raw) > MAX_BYTES:
        raise ValueError(f"太大了（超过 {MAX_BYTES // 1024} KB），插件不该这么大")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError(f"不是 utf-8（{e}）") from e
    import ast

    try:
        ast.parse(text)
    except SyntaxError as e:
        raise ValueError(f"语法不对（第 {e.lineno} 行）") from e

    dest = dir_path() / stem
    if dest.exists() and not overwrite:
        raise FileExistsError(dest.name)
    dest.write_text(text, encoding="utf-8")
    return dest.stem, url


# ---------------------------------------------------------------- 生命周期（3-2）
# 装：校验 manifest → exec → 注册工具 → start(ctx)
# 卸：stop() → 注销工具 → 移出 _LIVE/sys.modules
# 坏：任何一步抛错都回滚（工具摘掉、尽量 stop），理由交回去，不向主进程抛。

def _read_manifest(path: Path) -> dict:
    """只读地抠模块级 MANIFEST（字面量），不 exec。"""
    try:
        import ast

        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:                            # noqa: BLE001
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "MANIFEST":
                try:
                    val = ast.literal_eval(node.value)
                except Exception:                # noqa: BLE001
                    return {}
                return val if isinstance(val, dict) else {}
    return {}


def is_mounted(name: str) -> bool:
    return name in _LIVE


def mounted() -> list[str]:
    return sorted(_LIVE)


def _stop_quiet(mod) -> bool:
    fn = getattr(mod, "stop", None)
    if not callable(fn):
        return False
    try:
        fn()
        return True
    except Exception:                            # noqa: BLE001
        return False


def mount(name: str, ctx: dict) -> tuple[bool, str]:
    """装一个插件：校验 manifest → exec → 注册工具 → start(ctx)。

    坏在任何一步都回滚（工具摘掉、尽量 stop），把理由交回去，不抛。
    """
    import tools as toolmod

    path = dir_path() / f"{name}.py"
    if not path.exists():
        return False, f"{name}: 没有这个文件"
    if name in _LIVE:
        return True, f"{name}: 已经在跑"

    man = _read_manifest(path)
    try:
        api = int(man.get("api", API))
    except (TypeError, ValueError):
        api = -1
    if api != API:
        return False, f"{name}: manifest api={api}，这版只认 {API}，不装"

    try:
        mod = _load_file(path)
    except Exception as e:                       # noqa: BLE001
        return False, f"{name}: 读的时候就坏了（{type(e).__name__} {e}）"

    registered: list[str] = []
    try:
        for item in getattr(mod, "TOOLS", []) or []:
            schema, fn = item
            toolmod.register(schema, fn, owner=name)
            registered.append(str(schema.get("function", {}).get("name") or ""))
        start = getattr(mod, "start", None) or getattr(mod, "setup", None)
        if callable(start):
            start(ctx)
    except Exception as e:                       # noqa: BLE001
        # 回滚：先把这次已经 register 的工具摘掉，再尽量 stop。
        # 不这么做的话，坏插件会把工具留在 TOOLS 里，模型还能调到一个没有 start 过的插件。
        for tool_name in registered:
            toolmod.unregister(tool_name)
        stopped = _stop_quiet(mod)
        _LIVE.pop(name, None)
        _MOUNTED.pop(name, None)
        sys.modules.pop(f"petplug_{name}", None)
        return False, (f"{name}: 装到一半坏了（{type(e).__name__} {e}），"
                       f"工具已摘、{'stop 调过' if stopped else '没 stop'}")

    _MOUNTED[name] = {"tools": registered, "module": mod, "stopped": False}
    label = getattr(mod, "NAME", name)
    msg = f"{name}（{label}）: {len(registered)} 个工具"
    _log(msg + f"；现在共 {len(toolmod.TOOLS)} 个")
    return True, msg


def unmount(name: str) -> tuple[bool, str]:
    """卸一个插件：stop() → 注销工具 → 移出 _LIVE/sys.modules。

    插件没写 stop() 就照实说「没 stop，线程可能还在」——不假装干净。
    """
    import tools as toolmod

    mod = _LIVE.get(name)
    if mod is None:
        return False, f"{name}: 没在跑"
    entry = _MOUNTED.get(name) or {}
    stopped = _stop_quiet(mod)
    for tool_name in entry.get("tools", []):
        toolmod.unregister(tool_name)
    _LIVE.pop(name, None)
    _MOUNTED.pop(name, None)
    sys.modules.pop(f"petplug_{name}", None)
    # 没写 stop() 的插件只能靠插件自己收线程，Python 杀不掉；
    # 这里照实说「线程可能还在」，不把「工具注销了」当成「干净」。
    msg = f"{name}: 卸了（{'stop 调过' if stopped else '没 stop，线程可能还在'}）"
    _log(msg + f"；现在共 {len(toolmod.TOOLS)} 个")
    return True, msg


def _chosen(cfg: dict) -> list[str]:
    raw = cfg.get("plugins") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(x).strip() for x in raw if str(x).strip()]


def _log(line: str) -> None:
    """插件生命周期记一行到 startup.log——真机验的时候只认这个。"""
    try:
        import memory

        memory.note_file("startup.log", f"插件 {line}", (ctx() or {}).get("config"))
    except Exception:                            # noqa: BLE001
        pass


def _save(cfg: dict) -> None:
    """只把「插件名单」写回去，替调用方挡住「半截配置覆盖整份」的坑。

    为什么存在：2026-11-20 3-2 测试拿假 cfg={"plugins":[inst]} 调 uninstall，
    旧版 `_save` 直接 `save_config(cfg)`，把真 config.json 整份冲成
    `{"plugins": []}`——workspace / api_key / qq 全没了，靠 save_config 自己留的
    config.backup.json 才救回来。所以现在一律：先读盘上那份，只换 `plugins` 键。
    """
    try:
        import memory

        disk = memory.load_config()
        if disk.get("_locked"):
            return                              # 封印不对时别把锁定态写回盘：写回会把临时锁定变成永久
        disk["plugins"] = _chosen(cfg)
        memory.save_config(disk)
    except Exception:                            # noqa: BLE001
        pass


def enable(cfg: dict, name: str, ctx: dict) -> tuple[bool, str]:
    ok, msg = mount(name, ctx)
    if ok:
        chosen = _chosen(cfg)
        if name not in chosen:
            chosen.append(name)
            cfg["plugins"] = chosen
            _save(cfg)
    return ok, msg


def disable(cfg: dict, name: str) -> tuple[bool, str]:
    ok, msg = unmount(name)
    cfg["plugins"] = [x for x in _chosen(cfg) if x != name]
    _save(cfg)
    return ok, msg


def uninstall(cfg: dict, name: str) -> tuple[bool, str]:
    """卸干净再把文件挪进 plugins\\removed\\（不删，后悔能捡回来）。"""
    unmount(name)
    path = dir_path() / f"{name}.py"
    dest = ""
    if path.exists():
        trash = dir_path() / "removed"
        trash.mkdir(parents=True, exist_ok=True)
        target = trash / f"{name}.py"
        n = 1
        while target.exists():
            target = trash / f"{name}-{n}.py"
            n += 1
        path.replace(target)
        dest = target.name
    cfg["plugins"] = [x for x in _chosen(cfg) if x != name]
    _save(cfg)
    return True, (f"{name}: 卸了，文件挪进 removed\\{dest}" if dest else f"{name}: 卸了（没有文件可挪）")


def load(cfg: dict, ctx: dict) -> list[str]:
    """按 config 的单子装插件。返回每个的结果，留给 startup.log 看。"""
    wanted = cfg.get("plugins")
    if not wanted:
        return ["（没装插件：config.plugins 是空的）"]
    if isinstance(wanted, str):
        wanted = [wanted]
    wanted = [str(w).strip() for w in wanted if str(w).strip()]
    if "*" in wanted:
        wanted = available()

    said: list[str] = []
    for name in wanted:
        ok, msg = mount(name, ctx)
        said.append(msg)
    return said or ["（没装插件）"]
