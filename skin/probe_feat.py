"""看一眼现有 feat/ 各层的画布尺寸和实际内容范围。

画眼睛之前得先知道每张眼睛图多大、内容落在画布哪儿，
不然画出来的东西对不上 rig 的矩形。

    python probe_feat.py > _coop/probe.log
"""
from pathlib import Path
from PIL import Image

FEAT = Path(__file__).resolve().parent.parent / "figure/whale/schemes/yuyu/feat"
for p in sorted(FEAT.glob("*.png")):
    im = Image.open(p).convert("RGBA")
    box = im.getbbox()
    alpha = im.getchannel("A")
    solid = sum(1 for v in alpha.getdata() if v > 40)
    print(f"{p.name:24s} canvas={im.size[0]}x{im.size[1]} bbox={box} opaque={solid}")
