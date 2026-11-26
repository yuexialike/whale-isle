"""看一眼打出来的测试包：说明书对没对、里面有没有语音包那段。

放这里是因为 .bat 里不能写中文（写了整份跑不起来，11-01 踩过的坑）。
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

ROOT = Path(r"D:\鲸屿")
cands = sorted([p for p in ROOT.glob("*.zip") if "测试版" in p.name])
if not cands:
    raise SystemExit("发行目录里没找到测试版的 zip")
z = cands[-1]
print(f"zip   {z.name}  {z.stat().st_size/1048576:.1f} MB")

with zipfile.ZipFile(z) as zf:
    names = zf.namelist()
    print(f"      {len(names)} 个文件")
    readme = [n for n in names if n.endswith("README-测试版.txt")]
    if not readme:
        readme = [n for n in names if "README" in n and "_internal" not in n]
    print(f"      README: {readme}")
    if readme:
        text = zf.read(readme[0]).decode("utf-8-sig")
        i = text.find("语音输入")
        print("      语音包那一段：" + ("有" if i > 0 else "缺"))
        if i > 0:
            print("      ---- 摘录 ----")
            print("\n".join("      " + line for line in text[i - 2:i + 500].splitlines()))
    print("      beta.marker: " + ("在" if any(n.endswith("beta.marker") for n in names) else "缺"))
    print("      exe        : " + ("在" if any(n.endswith("WhaleIsle.exe") for n in names) else "缺"))
