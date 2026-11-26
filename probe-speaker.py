"""摸一摸局域网里有没有小米设备（音箱多半是 miIO 协议，UDP 54321）。

不用 token、不配对，只发一个 hello 广播，问「谁在」。
回来的报文是明文 JSON（带 deviceId / model），够我认出是哪台。

跑：
  D:\\fish\\svc\\venv\\Scripts\\python.exe newhouse\\probe-speaker.py
结果写 data/speaker-probe.txt（UTF-8）。

顺便看一眼这些端口——有些老款小爱会开 HTTP/DLNA：
  80 / 443 / 8080 / 1900(UDP，DLNA) / 54321(UDP，miIO)
"""
from __future__ import annotations

import json
import socket
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "speaker-probe.txt"

MIIO_PORT = 54321
# miIO hello：魔法字 0x21310020 + 一堆 0，标准探测包
HELLO = struct.pack(">HHII", 0x2131, 0x0020, 0, 0) + b"\x00" * 24


def arp_table() -> list[tuple[str, str]]:
    """本机 ARP 缓存里的 (IP, MAC)，先用它知道局域网里都有谁。"""
    try:
        import subprocess
        raw = subprocess.run(["arp", "-a"], capture_output=True, timeout=10).stdout
        text = raw.decode("gbk", "replace")
    except Exception:
        return []
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].count(".") == 3:
            out.append((parts[0], parts[1]))
    return out


def miio_discover(timeout: float = 4.0) -> list[dict]:
    """广播问一句，收集所有回话的。"""
    found: dict[str, dict] = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(1.0)
    try:
        s.sendto(HELLO, ("255.255.255.255", MIIO_PORT))
    except OSError:
        pass

    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data, addr = s.recvfrom(1024)
        except socket.timeout:
            continue
        info: dict = {"ip": addr[0]}
        # 明文部分从第 32 字节开始
        body = data[32:] if len(data) > 32 else data
        try:
            text = body.split(b"\x00", 1)[0].decode("utf-8", "replace")
            obj = json.loads(text)
            if isinstance(obj, dict):
                info.update({k: obj.get(k) for k in ("model", "did", "uid", "token")})
        except Exception:
            info["raw"] = body[:80].hex()
        found[addr[0]] = info
    s.close()
    return list(found.values())


def port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def local_networks() -> list[tuple[str, str, str]]:
    """(本机 IP, 网关, 子网前缀)——先知道自己站在哪个网段上。"""
    out = []
    try:
        import subprocess
        raw = subprocess.run(["ipconfig"], capture_output=True, timeout=10).stdout
        text = raw.decode("gbk", "replace")
    except Exception:
        return out
    ip = mask = gw = ""
    for line in text.splitlines():
        s = line.strip()
        if "IPv4" in s and ":" in s:
            ip = s.rsplit(":", 1)[1].strip()
        elif ("子网掩码" in s or "Subnet Mask" in s) and ":" in s:
            mask = s.rsplit(":", 1)[1].strip()
        elif ("默认网关" in s or "Default Gateway" in s) and ":" in s:
            gw = s.rsplit(":", 1)[1].strip()
        if ip and mask:
            prefix = ".".join(ip.split(".")[:3]) + "."
            if not any(p[0] == prefix for p in out):
                out.append((ip, gw or "", prefix))
            ip = mask = gw = ""
    return out


def ping_sweep(prefix: str, first: int = 1, last: int = 254, workers: int = 64) -> list[str]:
    """整段扫一遍 ping，回来的 IP 列出来。"""
    import subprocess
    from concurrent.futures import ThreadPoolExecutor

    def one(n: int) -> str | None:
        try:
            r = subprocess.run(["ping", "-n", "1", "-w", "250", f"{prefix}{n}"],
                               capture_output=True, timeout=3)
            return f"{prefix}{n}" if r.returncode == 0 else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return [ip for ip in ex.map(one, range(first, last + 1)) if ip]


def miio_hello_to(ip: str, timeout: float = 1.5) -> dict | None:
    """对某台机器单独问一遍 miIO。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(HELLO, (ip, MIIO_PORT))
        data, _ = s.recvfrom(1024)
    except OSError:
        return None
    finally:
        s.close()
    body = data[32:] if len(data) > 32 else data
    try:
        obj = json.loads(body.split(b"\x00", 1)[0].decode("utf-8", "replace"))
        return obj if isinstance(obj, dict) else {"raw": body[:60].hex()}
    except Exception:
        return {"raw": body[:60].hex()}


def http_banner(ip: str, port: int, timeout: float = 1.2) -> str:
    """抓一行 HTTP 头/标题，认得出是谁家的东西。"""
    import urllib.request
    for scheme in ("http",):
        try:
            req = urllib.request.Request(f"{scheme}://{ip}:{port}/", headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                head = r.headers.get("Server", "")
                body = r.read(600).decode("utf-8", "replace")
            import re
            title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
            return (head + (" / " + title.group(1).strip()[:40] if title else "")).strip() or "有 HTTP"
        except Exception as e:
            return f"{type(e).__name__}"
    return ""


def ssdp_discover(timeout: float = 3.0) -> list[str]:
    """SSDP 找 DLNA/UPnP 设备——不少音箱、电视会答这个。"""
    msg = ("M-SEARCH * HTTP/1.1\r\n"
           "HOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\n'
           "MX: 2\r\n"
           "ST: ssdp:all\r\n\r\n").encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.8)
    found: dict[str, str] = {}
    try:
        s.sendto(msg, ("239.255.255.250", 1900))
    except OSError:
        pass
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data, addr = s.recvfrom(2048)
        except socket.timeout:
            continue
        text = data.decode("utf-8", "replace")
        server = ""
        for line in text.splitlines():
            if line.lower().startswith("server:"):
                server = line.split(":", 1)[1].strip()
        found[addr[0]] = server or text.splitlines()[0][:60]
    s.close()
    return [f"{ip}  {name}" for ip, name in found.items()]


def main() -> None:
    lines = ["== 本机在哪 == "]
    nets = local_networks()
    for ip, gw, prefix in nets:
        lines.append(f"本机 {ip}  网关 {gw}  扫 {prefix}0/24")

    for _, _, prefix in nets:
        alive = ping_sweep(prefix)
        lines.append(f"扫完 {prefix}0/24：{len(alive)} 台回话 -> {', '.join(alive)}")
        for ip in alive:
            mi = miio_hello_to(ip)
            if mi:
                lines.append(f"  {ip} miIO 回话: {json.dumps(mi, ensure_ascii=False)[:200]}")
            for port in (80, 443, 8080, 8443, 8000, 3232):
                if port_open(ip, port):
                    lines.append(f"  {ip}:{port} 开着 → {http_banner(ip, port) if port in (80, 8080, 8000) else '(非 HTTP 或要 TLS)'}")

    lines.append("")
    lines.append("== ARP 表（局域网里认识的设备）==")
    for ip, mac in arp_table():
        lines.append(f"{ip:<16} {mac}")

    lines.append("")
    lines.append("== SSDP / DLNA ==")
    ssdp = ssdp_discover()
    lines.extend(ssdp or ["没人答（可能就是不放 DLNA）"])

    lines.append("")
    lines.append("== miIO 广播（小米设备）==")
    devices = miio_discover()
    if not devices:
        lines.append("没回话。（没连同一网段、或者固件把这协议关了）")
    for d in devices:
        lines.append(json.dumps(d, ensure_ascii=False))

    for d in devices:
        ip = d.get("ip")
        if not ip:
            continue
        lines.append("")
        lines.append(f"== {ip} 的端口 ==")
        for port in (80, 443, 8080, 8899, 54321):
            lines.append(f"{port}: {'开' if port_open(ip, port) else '关'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("ok ->", OUT)


if __name__ == "__main__":
    sys.exit(main())
