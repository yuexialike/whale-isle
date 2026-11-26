"""专门问一下 192.168.1.81 是不是小爱（Play 2019 / L05B）。

上次那个 hello 包写长了——标准是 32 字节：
  magic(2) length(2) unknown(4) deviceId(4) stamp(4) checksum(16)
我发的是 36 字节，多塞了四个 0，很多固件会直接丢掉。

这次：
  1. 单播（不经广播，路由器不会拦）连发几个，收回应；
  2. 广播再来一次；
  3. mDNS 问 _miio._udp.local / _xiaomi._udp.local，看它自己报不报名；
  4. 顺手 UDP 扫几个它可能开着的口。

结果写 data/miio-81.txt。
"""
from __future__ import annotations

import json
import socket
import struct
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "miio-81.txt"

TARGET = "192.168.1.81"
MIIO_PORT = 54321

HELLO = struct.pack(">HHIII", 0x2131, 0x0020, 0, 0, 0) + b"\x00" * 16   # 正好 32 字节


def hexdump(b: bytes, n: int = 64) -> str:
    return " ".join(f"{x:02x}" for x in b[:n])


def try_miio(ip: str, port: int = MIIO_PORT, tries: int = 3, wait: float = 1.0) -> list[str]:
    out = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(wait)
    for i in range(tries):
        try:
            s.sendto(HELLO, (ip, port))
        except OSError as e:
            out.append(f"发不出去: {e}")
            break
        try:
            data, addr = s.recvfrom(1024)
        except socket.timeout:
            out.append(f"第 {i+1} 次: 没回")
            continue
        out.append(f"第 {i+1} 次: {addr} 回了 {len(data)} 字节  {hexdump(data)}")
        body = data[32:] if len(data) > 32 else b""
        if body:
            out.append("  正文: " + body.split(b"\x00", 1)[0].decode("utf-8", "replace")[:300])
        break
    s.close()
    return out


def mdns_name(name: str, wait: float = 2.5) -> list[str]:
    """手搓一个 mDNS 查询（不用第三方库）。"""
    def enc(n: str) -> bytes:
        out = b""
        for part in n.split("."):
            if part:
                out += bytes([len(part)]) + part.encode()
        return out + b"\x00"

    tid = 0x1234
    header = struct.pack(">HHHHHH", tid, 0x0000, 1, 0, 0, 0)
    q = enc(name) + struct.pack(">HH", 12, 1)          # PTR / IN
    packet = header + q

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.5)
    found: list[str] = []
    try:
        s.sendto(packet, ("224.0.0.251", 5353))
    except OSError as e:
        s.close()
        return [f"发不出去: {e}"]

    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            data, addr = s.recvfrom(4096)
        except socket.timeout:
            continue
        if addr[0] == "0.0.0.0":
            continue
        # 粗略把可打印的域名抠出来
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
        txt = ".".join(p for p in txt.split(".") if p)
        found.append(f"{addr[0]}: {txt[:160]}")
    s.close()
    return found


def udp_probe(ip: str, ports=(54321, 4321, 5353, 1900, 8080, 9999)) -> list[str]:
    out = []
    for p in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        try:
            s.sendto(b"\x00", (ip, p))
            s.recvfrom(256)
            out.append(f"  UDP {p}: 有回应")
        except socket.timeout:
            pass
        except OSError:
            pass
        finally:
            s.close()
    return out


def main() -> None:
    lines = [f"目标 {TARGET}  小爱音箱 Play 2019 (L05B)", ""]

    lines.append("== miIO 单播 32 字节 hello ==")
    lines += try_miio(TARGET)
    lines.append("")

    lines.append("== miIO 广播 255.255.255.255 ==")
    lines += try_miio("255.255.255.255", tries=1)
    lines.append("")

    lines.append("== mDNS ==")
    for name in ("_miio._udp.local", "_xiaomi._udp.local", "_http._tcp.local"):
        got = mdns_name(name)
        lines.append(f"{name}: " + ("；".join(got) if got else "没人答"))
    lines.append("")

    lines.append("== UDP 端口 ==")
    got = udp_probe(TARGET)
    lines += got if got else ["  都对不上话"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
