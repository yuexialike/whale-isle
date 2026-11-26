"""打包协议：鲸屿 Whale Isle —— 正式版。

月下 11-01 14:38 说的「给要发给别人测试的那份做一个打包协议」，就是这个文件。
一个命令出完整的一份可发布文件夹，不用再手工拷来拷去：

    D:\\fish\\svc\\venv\\Scripts\\python.exe pack_beta.py

七步，一步都不许省：

  1. PyInstaller 按 
ewhouse.spec` 编译 → `dist\\WhaleIsle\\`
  2. 在 `D:\\鲸屿\\鲸屿-<版号>\\` 备一个干净目录
  3. 拷 exe 全套 + `template\\*.md`（空白起步三页）+ `whale-isle.ico` + `figure-default.png`
  4. 放 `beta.marker` —— firstrun 看见它就要激活码、权限一条不预开（见 firstrun.py）
  5. 删掉一切不该出门的东西，再**逐条核对**（FORBIDDEN + 正文扫描）
  6. 写 `README-正式版.txt`、`建快捷方式.bat`（GBK 写，cmd 才认中文）
  7. 压一个同名 zip 放同目录

为什么要写成一个文件：发出去的东西收不回来。慢一点、每一步都核对一遍，
比把「我的真 workspace 路径和 API key」一起发出去好一万倍。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = Path(sys.executable)
LOG = HERE / "data" / "pack-beta.log"

STAMP = time.strftime("%Y%m%d")
DATE_CN = time.strftime("%Y-%m-%d")
DIST = HERE / "dist" / "WhaleIsle"
# 月下 11-01 15:16：D 盘新建一个文件夹叫「鲸屿」，里头按名字 + 测试版 + 版号排。
# 19:55 版号改成读 version.py——打包和「检查更新」认同一份，别再各写一个。
from version import VERSION                             # noqa: E402
OUT_ROOT = Path(r"D:\鲸屿")
OUT = OUT_ROOT / f"鲸屿-{VERSION}"
ZIP = OUT_ROOT / f"鲸屿-{VERSION}.zip"

APP_NAME_EN = "WhaleIsle"
LINK_NAME = "鲸屿 Whale Isle"

# 包根上绝对不许出现的东西。名字出现在这一层就算出事，不看内容。
FORBIDDEN = {
    "config.json", "workspace", "data", "license.key", "license-key.txt",
    "make-code.py", "make-keys.py", "yuyu.ico", "yuyu.png",
    "isla.ico", "isla.png", "appicon.py", "comfy-start-log.txt",
}
# 正文里绝对不许出现的字。扫所有小文本文件（_internal 里的二进制跳过）。
FORBIDDEN_TEXT = ("sk-", "Coopanion", "28117", "D:\\fish\\home")

_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    _lines.append(str(msg))


def die(msg: str) -> None:
    log(f"!! {msg}")
    log("---- 停了，什么都没发出去 ----")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(_lines), encoding="utf-8")
    raise SystemExit(1)


# ---------------------------------------------------------------- 1. 编译
def compile_exe() -> None:
    log("== 1. PyInstaller ==")
    try:
        subprocess.run([str(PY), "-m", "PyInstaller", "--version"],
                       cwd=HERE, check=True, capture_output=True,
creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.CalledProcessError:
        die(f"这个 python 里没有 PyInstaller：{PY}\n   先装：{PY} -m pip install pyinstaller")
    r = subprocess.run(
        [str(PY), "-m", "PyInstaller", "--noconfirm", "--clean", "newhouse.spec"],
        cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if r.returncode != 0:
        log(r.stdout[-3000:] if r.stdout else "")
        log(r.stderr[-3000:] if r.stderr else "")
        die(f"编译失败，尾部输出在上面，也写进 {LOG}")
    if not DIST.is_dir():
        die(f"编译说成功，但没有 {DIST} —— spec 里的 name 和这里对不上？")
    log(f"   好了：{DIST}")


# ---------------------------------------------------------------- 2. 备目录
def prepare_out() -> None:
    log("== 2. 发行目录 ==")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        marker = OUT / ".pack_beta"
        if not marker.exists():
            die(f"{OUT} 已经在了，而且不是这个脚本建的 —— 我不敢删别人的东西，你自己看一眼再决定。")
        shutil.rmtree(OUT)
        log("   删掉了今天早些时候那份（带 .pack_beta 标记，是同一脚本的产物）")
    OUT.mkdir(parents=True)
    (OUT / ".pack_beta").write_text(
        f"这个目录由 newhouse/pack_beta.py 生成，{DATE_CN}。\n"
        "重新打包会整个删掉再建 —— 别往里放唯一的东西。\n",
        encoding="utf-8",
    )
    log(f"   {OUT}")


# ---------------------------------------------------------------- 3. 拷文件
def stage_files() -> None:
    log("== 3. 拷文件 ==")
    for item in DIST.iterdir():
        dst = OUT / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)
        log(f"   + {item.name}")

    # 3-4：临时形象包对外一律不带——PROVENANCE.json 里写了 ship:false 就整目录拿掉。
    # 以后月下自己画的包不带这个标记，会照常进包。
    packs = OUT / "skin" / "figures"
    if packs.is_dir():
        for p in sorted(packs.iterdir()):
            prov = p / "PROVENANCE.json"
            try:
                ship = json.loads(prov.read_text(encoding="utf-8")).get("ship", True)
            except Exception:                        # noqa: BLE001
                ship = True
            if ship is False:
                shutil.rmtree(p, ignore_errors=True)
                log(f"   - skin/figures/{p.name}（临时素材，ship:false，不带）")

    tpl = OUT / "template"
    tpl.mkdir(exist_ok=True)
    for md in sorted((HERE / "template").glob("*.md")):
        shutil.copy2(md, tpl / md.name)
        log(f"   + template/{md.name}")

    icon = HERE / "whale-isle.ico"
    if icon.exists():
        shutil.copy2(icon, OUT / icon.name)
        log(f"   + {icon.name}")
    else:
        die("whale-isle.ico 不见了 —— 快捷方式和窗口图标都要它。先生成：make_icon_fish.py")

    fig = HERE / "figure-me-child-v23.png"
    if fig.exists():
        shutil.copy2(fig, OUT / "figure-default.png")
        log("   + figure-default.png （2D 形象，firstrun 会指向它）")
    else:
        die("figure-me-child-v23.png 不见了 —— 别人的版本会退回 QPainter 画的团子。")

    (OUT / "plugins").mkdir(exist_ok=True)
    log("   + plugins/ （空目录，插件由作者自己放）")

    # 11-04 22:15 开发者平台第一层：把写插件要的东西一起发出去。
    # 只有规范和工具，没有一个我自己的插件，没有记忆。
    devkit = HERE / "devkit"
    if devkit.is_dir():
        # .pyc 里带着 co_filename = 这台机器的真实路径，跟着发出去就是漏地址。
        for pyc in devkit.rglob("__pycache__"):
            shutil.rmtree(pyc, ignore_errors=True)
        shutil.copytree(devkit, OUT / "devkit",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for f in sorted((OUT / "devkit").glob("*")):
            log(f"   + devkit/{f.name}")
    else:
        log("   ! devkit/ 不在，插件开发包没带上（不影响运行）")


# ---------------------------------------------------------------- 4. 测试版标记
def mark_beta() -> None:
    log("== 4. beta.marker ==")
    (OUT / "beta.marker").write_text(
        "锁版标记（发给别人测试的那份）。\n"
        "firstrun.py 看见它，就按 beta 那套建 config.json：\n"
        "  · license_required = True  —— 要激活码\n"
        "  · permissions = {}         —— 权限一条都不预开，人自己一条条给\n"
        "  · max_steps = 4            —— 比我们那份少一半\n"
        "自己机器上的那份没有这个文件，安全协议是解开的。\n"
        "正式放出去的版本也带着它（锁着是常态，解开才是例外）。\n",
        encoding="utf-8",
    )
    log("   + beta.marker （锁版：要码、权限全关、少开几档）")


# ---------------------------------------------------------------- 5. 核对
def verify() -> None:
    log("== 5. 核对 ==")
    bad = 0
    for name in FORBIDDEN:
        if (OUT / name).exists():
            log(f"   !! 不许出门的东西还在：{name}")
            bad += 1
    for p in sorted(OUT.rglob("*")):
        if "_internal" in p.parts or not p.is_file():
            continue
        if p.suffix.lower() not in {".txt", ".md", ".json", ".bat", ".marker", ""}:
            continue
        if p.stat().st_size > 2_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for needle in FORBIDDEN_TEXT:
            if needle in text:
                log(f"   !! {p.relative_to(OUT)} 里出现 {needle!r}")
                bad += 1
    if bad:
        die(f"核对没过，{bad} 处。这个目录不能发。")
    n = sum(1 for _ in OUT.rglob("*"))
    log(f"   干净：{n} 个文件，没有私有路径、没有 key、没有 config、没有 workspace")


# ---------------------------------------------------------------- 6. 说明书
README = """鲸屿 Whale Isle —— {ver} 正式版（{date}）
========================================

这是 v1.0.0 正式版。先说清楚：它是**别人家里的一只桌宠**，
不是我，也不联网到我这台机器。你电脑上它叫什么随你改。

怎么开
------
1. 双击 `建快捷方式.bat`（在桌面上建一个「鲸屿 Whale Isle」）。
   不想建快捷方式就直接双击 `WhaleIsle.exe`。
2. 第一次开机会自己铺床：在你放 exe 的那个文件夹旁边生成
   `config.json`、`workspace\\`、`data\\`，并且把三页空白模板
   （CONSTITUTION.md / PARTNER.md / STATE.md）种进 `workspace\\`。
   已经有的东西一律不覆盖，第二次开机它只是路过。
3. 它会站在屏幕底边。戳它、摸它、拎起来甩出去，它都有反应。

要填的东西
----------
**API key 必须你自己填**，不填它就张不开嘴（只会站着、有反应但不会说话）。

  · 打开设置页（右键它 / 托盘菜单里找「设置」），在 API 那一栏填：
      接口地址  https://api.deepseek.com/v1
      模型      deepseek-flash
      密钥      sk-...（你自己的）
  · 或者设一个环境变量 `DEEPSEEK_API_KEY`，程序会去读。
  · 想让它念出声：需要本机的语音服务（Sovits / TTS 在 127.0.0.1:8899），
    没有就把「朗读」关掉，不影响打字说话。

语音输入（可选，要另外下 228 MB）
--------------------------------
不说话只打字，也能用；想按热键跟它说话，就得先把本地识别模型（「语音包」）下下来。

  · 位置：设置页 → 声音 → 「下载语音包（228 MB）」，点一下就开始下，有进度条。
    下完重启程序生效。旁边有「删掉」，不想要了随时删。
  · 从哪儿下：先走 ModelScope（国内快），不行再试 Hugging Face，两边是同一份文件。
  · 每个文件都钉死了字节数和 SHA-256，对不上就当没下过，不会留半截模型。
  · 默认**不会自动下**——228 MB 不小，等你自己点。
  · 不下的话，「按住热键说话」那条路是哑的，打字那条一直能用。

它记得什么
----------
它把记得的东西写在自己的 `workspace\\` 里（就是那三页 md）。想让它像谁，
就改那三页 —— 那是它的自述、它的相处方式、它当下的记事。改完下次开机生效。
**这三页是空的模板，请你自己写。** 里面没有原作者的任何私人内容。

写插件（可选）
--------------
`devkit\\` 里是插件开发包：`README.md` 是全部规范，`template.py` 是能跑的模板，
`check.py` 是体检器（查语法、查危险调用、查非标准库、查工具名重复）。

    py -3 devkit\\check.py plugins\\你的插件.py

全绿之后把那个 `.py` 放进 `plugins\\`，在 `config.json` 的 `plugins` 里写上它的名字，
重启就生效。一个插件就是一个文件，不用编译、不用注册。

关于授权
--------
这份是**锁着的**：第一次开机要激活码，没有码就打不开。

  1. 找发给你的人要一张码（一人一张，里面写着给谁、到哪天）。
  2. 把它粘进设置页的「激活码」那一栏，或者存成 exe 旁边的 `license.key`
     （一行，别加空格）。
  3. 码是本地验的：不联网、不上报，谁在用不会传出去。

这一版和我们自己那台机器上的那份**不是同一个东西**，区别在这几处：

  授权        这边要码               我们那份不用
  权限        一条都不开             能开的都开着
  一次能走几步 少一半                 多一倍
  消息通道    QQ / 语音 / 终端        全有
  记忆        workspace 里是空白模板   是我自己的真记事

想让桌宠动你的电脑（看屏幕、点鼠标、跑命令），得你自己在**设置页 → 权限**
里一条条给，给的时候还能选「一直允许 / 只借 30 分钟」。
不给它也能说话、能站着陪你，只是看不见你屏幕、动不了手。

别做的事
--------
· 别把这一整包连同你自己的 `config.json`（里面有你的 key）再传给别人。
· 出了什么事、报什么错、哪里不对劲，截图丢回来就行，别自己改 exe。

出问题找谁
----------
找把它发给你的那个人。
"""

# 快捷方式的 bat：ASCII 之外只有那个链接名是中文，所以整份用 GBK 写。
# （build.bat 顶上那句话说的就是这个：中文按 UTF-8 写进 .bat，cmd 会解析成乱码。）
SHORTCUT_BAT = r"""@echo off
rem Make a desktop shortcut for Whale Isle. Generated by pack_beta.py - do not hand-edit.
set "HERE=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $h=$env:HERE; $p=Join-Path $d '鲸屿 Whale Isle.lnk'; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($p); $s.TargetPath=(Join-Path $h 'WhaleIsle.exe'); $s.WorkingDirectory=$h; $s.IconLocation=((Join-Path $h 'whale-isle.ico')+',0'); $s.Description='鲸屿 Whale Isle'; $s.Save(); Write-Host ('OK: ' + $p)"
echo.
pause
"""


def write_docs() -> None:
    log("== 6. 说明书 ==")
    (OUT / "README-正式版.txt").write_text(
        README.format(date=DATE_CN, ver=VERSION), encoding="utf-8-sig"
    )
    log("   + README-正式版.txt （utf-8-sig，记事本不乱码）")
    (OUT / "建快捷方式.bat").write_bytes(SHORTCUT_BAT.replace("\n", "\r\n").encode("gbk"))
    log(f"   + 建快捷方式.bat （GBK，链接名「{LINK_NAME}」）")


# ---------------------------------------------------------------- 7. 压缩
def zip_it() -> None:
    log("== 7. 压 zip ==")
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                z.write(p, Path(OUT.name) / p.relative_to(OUT))
    mb = ZIP.stat().st_size / 1024 / 1024
    log(f"   {ZIP} （{mb:.1f} MB）")


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log(f"==== 鲸屿 打包协议 {DATE_CN} {time.strftime('%H:%M:%S')} ====")
    log(f"python {PY}")
    compile_exe()
    prepare_out()
    stage_files()
    mark_beta()
    verify()
    write_docs()
    zip_it()
    log("")
    log(f"好了。发给别人这一份：{ZIP}")
    log(f"文件夹在：{OUT}")
    log("Live2D / 分层形象还没进包（见 STATE.md，排在打包之后单独做）。")
    LOG.write_text("\n".join(_lines), encoding="utf-8")
    print(f"\nlog -> {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
