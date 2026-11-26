# -*- mode: python ; coding: utf-8 -*-
"""打包：一个 exe + 一个文件夹（PyInstaller）。

用法（普通命令提示符或 build.bat）：
    pyinstaller --noconfirm --clean newhouse.spec

打进去的只有程序本身：
  · `template/` 不塞进包里 —— build.bat 打完拷到输出文件夹旁边，
    因为 firstrun 是在 **exe 所在目录**找 template（打包后 home = exe 目录）；
  · `license-key.txt`（私钥）、`make-code.py`（签码用）**绝不进包**；
  · `data/`、`config.json` 也都不进包 —— 第一次开机自己长出来（见 firstrun.py）。
"""
from pathlib import Path

HERE = Path(SPECPATH)  # noqa: F821  PyInstaller 在 spec 里给的变量

a = Analysis(
    [str(HERE / "main.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=[(str(HERE / "whale-isle.ico"), ".")],   # 只带图标：模板由 build.bat 拷，不塞进 _MEI
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc_data",
        "test",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WhaleIsle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                    # UPX 会让 Defender 更爱报毒，不用
    console=False,                # 没有黑窗口，和 pythonw 一样
    icon=str(HERE / "whale-isle.ico"),  # exe 自己的图标（那个从远景深海抠出来的鱼）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WhaleIsle",
)
