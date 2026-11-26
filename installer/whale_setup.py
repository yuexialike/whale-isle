"""鲸屿 Whale Isle —— 安装器 / 卸载器（自己写的，不靠 Inno）。

2026-11-21 17:16 鱼鱼写。为什么要自己写：Inno Setup 下不下来（官网 404、winget 挂住），
而「软件性质」这件事不能等——要装进系统、开始菜单有、控制面板能卸载。

一个 exe 两副面孔：
    鲸屿-安装版-v1.0.0.exe                 → 装
    鲸屿-安装版-v1.0.0.exe --uninstall     → 卸（安装时也会复制一份小的「鲸屿-卸载.exe」）

为什么默认装到 %LOCALAPPDATA%\\Programs 而不是 Program Files：
  这个程序把 config.json / workspace / data 写在 exe 旁边（firstrun 铺床）。
  放 Program Files 要管理员才能写，第一次开机就废。装用户目录不用 UAC，控制面板照样看得见。

安装包里带着 payload/（就是 D:\鲸屿\鲸屿-v1.0.0 的那份内容），PyInstaller 的 --add-data 塞进来。
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_NAME = "鲸屿 Whale Isle"
APP_VERSION = "1.0.0"
EXE_NAME = "WhaleIsle.exe"
UNINST_EXE = "鲸屿-卸载.exe"
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\WhaleIsle"
DEFAULT_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "WhaleIsle"


def payload_dir() -> Path | None:
    """安装包里那份程序文件在哪。"""
    if getattr(sys, "frozen", False):
        cand = Path(getattr(sys, "_MEIPASS", "")) / "payload"
        if cand.is_dir():
            return cand
        return None
    # 开发时直接指着发行目录
    cand = Path(r"D:\鲸屿\鲸屿-v1.0.0")
    return cand if cand.is_dir() else None


# ---------------------------------------------------------------- 快捷方式
def make_shortcut(lnk: Path, target: Path, workdir: Path, icon: Path | None, desc: str) -> None:
    """用 PowerShell 建 .lnk。必须 -EncodedCommand：中文经命令行传会被 GBK 弄烂。"""
    lnk.parent.mkdir(parents=True, exist_ok=True)
    ps = (
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        f"$s.TargetPath='{target}';"
        f"$s.WorkingDirectory='{workdir}';"
        + (f"$s.IconLocation='{icon},0';" if icon else "")
        + f"$s.Description='{desc}';$s.Save()"
    )
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        capture_output=True,
    )


def desktop_dir() -> Path:
    return Path(os.environ["USERPROFILE"]) / "Desktop"


def start_menu_dir() -> Path:
    return (Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" /
            "Programs" / APP_NAME)


def shortcuts_for(target: Path) -> list[Path]:
    icon = target / "whale-isle.ico"
    return [
        start_menu_dir() / f"{APP_NAME}.lnk",
        desktop_dir() / f"{APP_NAME}.lnk",
    ]


# ---------------------------------------------------------------- 注册表
def write_uninstall_key(target: Path) -> None:
    exe = target / EXE_NAME
    uninst = target / UNINST_EXE
    size_kb = int(sum(p.stat().st_size for p in target.rglob("*") if p.is_file()) / 1024)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINST_KEY) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, "Coopanion")
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, str(exe))
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(target))
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{uninst}" --uninstall')
        winreg.SetValueEx(k, "QuietUninstallString", 0, winreg.REG_SZ, f'"{uninst}" --uninstall /S')
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def read_uninstall_key() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINST_KEY) as k:
            loc, _ = winreg.QueryValueEx(k, "InstallLocation")
            return Path(loc)
    except OSError:
        return None


def delete_uninstall_key() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINST_KEY)
    except OSError:
        pass


# ---------------------------------------------------------------- 装 / 卸
def do_install(target: Path, want_desktop: bool, log=print) -> None:
    src = payload_dir()
    if src is None:
        raise RuntimeError("安装包里的 payload 找不着，这个 exe 不完整")
    if target.exists() and any(target.iterdir()):
        # 覆盖安装：只拷，不先删（保留用户的 config / workspace）
        log(f"目标里已经有东西，按覆盖安装处理：{target}")
    target.mkdir(parents=True, exist_ok=True)

    total = sum(1 for _ in src.rglob("*"))
    done = 0
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        dst = target / rel
        if item.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)
        done += 1
        if done % 200 == 0:
            log(f"  拷了 {done}/{total}")
    log(f"文件拷完：{done} 个 → {target}")

    # 卸载器：要的是**小的那一个**（同一个脚本、不带 payload 编出来的），
    # 不能把整个安装包复制过去——那样装一次白占 386 兆（17:22 踩过）。
    small = Path(getattr(sys, "_MEIPASS", "")) / "uninst" / UNINST_EXE
    if small.exists():
        shutil.copy2(small, target / UNINST_EXE)
        log(f"卸载器装好了（{small.stat().st_size / 1024 / 1024:.1f} MB）")
    elif getattr(sys, "frozen", False):
        me = Path(sys.executable)
        shutil.copy2(me, target / UNINST_EXE)
        log("卸载器装好了（没有小卸载器，只好复制安装包本身）")

    exe = target / EXE_NAME
    icon = target / "whale-isle.ico"
    sm = start_menu_dir()
    make_shortcut(sm / f"{APP_NAME}.lnk", exe, target, icon, APP_NAME)
    make_shortcut(sm / f"卸载 {APP_NAME}.lnk", target / UNINST_EXE, target, icon, f"卸载 {APP_NAME}")
    if want_desktop:
        make_shortcut(desktop_dir() / f"{APP_NAME}.lnk", exe, target, icon, APP_NAME)
    log("快捷方式建好了（开始菜单" + ("＋桌面" if want_desktop else "") + "）")

    write_uninstall_key(target)
    log("注册表写好了：控制面板 → 卸载程序 里能看到 " + APP_NAME)


def do_uninstall(log=print) -> None:
    target = read_uninstall_key()
    if target is None:
        # 退一步：用本 exe 所在的目录
        target = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    if target and target.exists():
        log(f"删目录：{target}")
        shutil.rmtree(target, ignore_errors=True)
    for lnk in shortcuts_for(target or Path()):
        try:
            if lnk.exists():
                lnk.unlink()
                log(f"删快捷方式：{lnk}")
        except OSError:
            pass
    sm = start_menu_dir()
    if sm.exists():
        shutil.rmtree(sm, ignore_errors=True)
    delete_uninstall_key()
    log("注册表那一条也删了")


def self_delete_later() -> None:
    """把自己删掉：起一个 cmd，等两秒再 del。"""
    me = Path(sys.executable).resolve()
    subprocess.Popen(
        ["cmd", "/c", "ping -n 3 127.0.0.1 >nul & del /f /q", str(me)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


# ---------------------------------------------------------------- 界面
class Installer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} 安装程序")
        self.geometry("620x420")
        self.resizable(False, False)

        ttk.Label(self, text=f"{APP_NAME} {APP_VERSION}", font=("Microsoft YaHei UI", 16)).pack(
            anchor="w", padx=18, pady=(18, 2))
        ttk.Label(self, text="一只站在屏幕底边的桌宠。装完在开始菜单里能找到，随时能卸。",
                  foreground="#555").pack(anchor="w", padx=18)

        box = ttk.Frame(self)
        box.pack(fill="x", padx=18, pady=14)
        ttk.Label(box, text="装到哪儿：").pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=4)
        self.v_dir = tk.StringVar(value=str(DEFAULT_DIR))
        ttk.Entry(row, textvariable=self.v_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="换一个…", command=self._browse).pack(side="left", padx=6)

        self.v_desk = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="在桌面上放一个图标", variable=self.v_desk).pack(anchor="w", pady=(6, 0))
        ttk.Label(box, text="（不装到 Program Files：它要把自己的记事本写在旁边，不用管理员才写得进去）",
                  foreground="#777").pack(anchor="w")

        self.txt = tk.Text(self, height=9, wrap="char")
        self.txt.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=18, pady=(0, 16))
        self.btn = ttk.Button(bar, text="装", command=self._install)
        self.btn.pack(side="right")
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=8)

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(title="装到哪儿", initialdir=str(Path(self.v_dir.get()).parent))
        if chosen:
            self.v_dir.set(str(Path(chosen) / "WhaleIsle"))

    def log(self, msg: str) -> None:
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.update_idletasks()

    def _install(self) -> None:
        target = Path(self.v_dir.get())
        self.btn.state(["disabled"])
        try:
            do_install(target, self.v_desk.get(), self.log)
            self.log("\n装好了。点「完成」就能开。")
            self.btn.configure(text="完成", command=self.destroy, state=["normal"])
            if messagebox.askyesno("装好了", f"{APP_NAME} 装好了。\n现在就打开它？"):
                subprocess.Popen([str(target / EXE_NAME)], cwd=str(target))
                self.destroy()
        except Exception as exc:                                   # noqa: BLE001
            self.log(f"出错了：{exc}")
            messagebox.showerror("装不上", str(exc))
            self.btn.state(["!disabled"])


class Uninstaller(tk.Tk):
    def __init__(self, silent: bool = False) -> None:
        super().__init__()
        self.title(f"卸载 {APP_NAME}")
        self.geometry("560x320")
        self.silent = silent
        ttk.Label(self, text=f"卸载 {APP_NAME}", font=("Microsoft YaHei UI", 15)).pack(
            anchor="w", padx=18, pady=(18, 6))
        ttk.Label(
            self,
            text="会删掉程序本体、开始菜单和桌面图标、还有卸载列表里那一条。\n"
                 "装在哪儿的 config.json / workspace（它自己的记事本）也会跟着删。",
            foreground="#555", justify="left").pack(anchor="w", padx=18)
        self.txt = tk.Text(self, height=6, wrap="char")
        self.txt.pack(fill="both", expand=True, padx=18, pady=12)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=18, pady=(0, 16))
        self.btn = ttk.Button(bar, text="卸载", command=self._go)
        self.btn.pack(side="right")
        ttk.Button(bar, text="不卸了", command=self.destroy).pack(side="right", padx=8)
        if silent:
            self.after(100, self._go)

    def log(self, msg: str) -> None:
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.update_idletasks()

    def _go(self) -> None:
        self.btn.state(["disabled"])
        do_uninstall(self.log)
        self.log("\n卸干净了。")
        if not self.silent:
            messagebox.showinfo("卸完了", f"{APP_NAME} 已经卸载。")
            self.destroy()
        self.after(200, self._bye)

    def _bye(self) -> None:
        self.destroy()
        self_delete_later()


def main(argv: list[str]) -> int:
    args = [a.lower() for a in argv]
    if "--uninstall" in args or "-u" in args:
        silent = "/s" in args or "--silent" in args
        if silent:
            do_uninstall(lambda _m: None)
            self_delete_later()
            return 0
        Uninstaller().mainloop()
        return 0
    Installer().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
