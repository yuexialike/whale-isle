"""换个法子找音箱：不靠 ping，靠 ARP。

月下说得对——手机在 5G、音箱在 2.4G，得先确认「是不是同一个网段」。
这台电脑上还挂着一个 26.x 的虚拟网卡（VPN/TUN），广播包很可能从错的门出去了；
SSDP 连路由都不答，就是这个味道。

所以这次：
  1. 把每块网卡的 IP / 网关 / 名字列清楚（看 26.x 是谁）；
  2. **ARP 扫**：对 192.168.1.1–254 每台都发一个空 UDP（端口 9），
     系统会去 ARP 问「这 IP 是谁」——只要这台机器活着就会回 ARP，
     哪怕它不理 ping、不开任何端口。然后读 ARP 表。
  3. miIO 广播**绑到 192.168.1.20 这个源地址**再发一次，别让虚拟网卡截走。

结果写 data/net-arp.txt。
"""
from __future__ import annotations

import ipaddress
import json
import socket
import struct
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "net-arp.txt"

NET = "192.168.1."
SELF_ADDR = "192.168.1.20"
MIIO_PORT = 54321
HELLO = struct.pack(">HHIII", 0x2131, 0x0020, 0, 0, 0) + b"\x00" * 16


def run(cmd: list[str]) -> str:
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=20).stdout
    except Exception as e:
        return f"(失败 {e})"
    for enc in ("gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("gbk", "replace")


def arp_table() -> dict[str, str]:
    out = {}
    for line in run(["arp", "-a"]).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].count(".") == 3 and "-" in parts[1]:
            ip, mac = parts[0], parts[1].lower()
            if not mac.startswith("ff-ff") and not mac.startswith("01-00"):
                out[ip] = mac
    return out


def arp_sweep(prefix: str = NET, port: int = 9) -> None:
    """把整段都戳一下，逼系统自己去 ARP（不用 ping）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind((SELF_ADDR, 0))
    except OSError:
        pass
    for n in range(1, 255):
        try:
            s.sendto(b"\x00", (f"{prefix}{n}", port))
        except OSError:
            pass
    s.close()


def miio_bcast_bound() -> list[str]:
    """绑 192.168.1.20 当源地址，广播再问一次。"""
    out = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(2.0)
    try:
        s.bind((SELF_ADDR, 0))
        out.append(f"源地址绑成 {SELF_ADDR}")
    except OSError as e:
        out.append(f"绑不上 {SELF_ADDR}: {e}")
    for dest in ("255.255.255.255", "192.168.1.255"):
        try:
            s.sendto(HELLO, (dest, MIIO_PORT))
            data, addr = s.recvfrom(1024)
            out.append(f"{dest} → {addr} 回了 {len(data)} 字节: {' '.join(f'{b:02x}' for b in data[:40])}")
        except socket.timeout:
            out.append(f"{dest} → 没回")
        except OSError as e:
            out.append(f"{dest} → 出错 {e}")
    s.close()
    return out


def main() -> None:
    lines = ["== 网卡（找那个 26.x 是谁）=="]
    lines.append(run(["ipconfig"]).strip())

    lines.append("")
    lines.append("== ARP 扫 192.168.1.0/24 ==")
    before = arp_table()
    t0 = time.monotonic()
    arp_sweep()
    time.sleep(4.0)
    after = arp_table()
    new = {ip: mac for ip, mac in after.items() if ip.startswith(NET)}
    lines.append(f"戳了 254 个地址，{time.monotonic() - t0:.1f}s")
    for ip in sorted(new, key=lambda x: int(x.split('.')[-1])):
        mark = "  ← 新出现" if ip not in before else ""
        lines.append(f"  {ip:16s} {new[ip]}{mark}")
    lines.append(f"共 {len(new)} 台")
    lines.append("")

    lines.append("== miIO 广播（绑住源地址）==")
    lines += miio_bcast_bound()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
