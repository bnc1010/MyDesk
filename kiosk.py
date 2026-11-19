#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kiosk.py —— 教师机远程控制（命令行版，等同于网页上的按钮）
==========================================================
    python kiosk.py status                 # 自动发现教师机并看状态
    python kiosk.py open                   # 开放观看机（学生可以关闭观看窗）
    python kiosk.py lock                   # 封锁观看机（不能退出）
    python kiosk.py pause / resume / end
    python kiosk.py open --host 192.168.1.20 --key ab12cd34
    python kiosk.py status --follow        # 持续刷新状态
"""
from __future__ import annotations

import argparse
import http.client
import json
import socket
import sys
import time
from urllib.parse import quote

ACTION_MODES = ("lock", "open", "pause", "resume", "end")
API_PATH = {"status": "policy"}            # status 只读，走 /api/policy


def discover(port: int, wait: float = 6.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(wait)
    end = time.time() + wait
    while time.time() < end:
        try:
            data, _ = sock.recvfrom(4096)
            info = json.loads(data.decode("utf-8"))
        except (socket.timeout, ValueError, UnicodeDecodeError):
            continue
        if info.get("app") == "mydesk":
            sock.close()
            return info
    sock.close()
    return None


def call(host: str, port: int, key: str, path: str) -> dict:
    conn = http.client.HTTPConnection(host, port, timeout=6)
    method = "POST" if path != "policy" else "GET"
    conn.request(method, f"/api/{path}?key={quote(key)}")
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    conn.close()
    if resp.status != 200:
        raise SystemExit(f"教师机返回 {resp.status}: {body}")
    return json.loads(body)


def show(d: dict):
    print(f"模式={d.get('mode')}  观看机={d.get('viewers')}  "
          f"帧率={d.get('fps')}fps  画面={d.get('width')}x{d.get('height')}  "
          f"会话={d.get('session')}")


def main():
    ap = argparse.ArgumentParser(description="教师机远程控制")
    ap.add_argument("action", nargs="?", default="status",
                    choices=("status",) + ACTION_MODES)
    ap.add_argument("--host", default="", help="教师机 IP（不给则 UDP 自动发现）")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--key", default="")
    ap.add_argument("--discover", type=int, default=5007)
    ap.add_argument("--follow", action="store_true", help="持续刷新状态")
    args = ap.parse_args()

    host, port, key = args.host, args.port, args.key
    if not host:
        info = discover(args.discover)
        if not info:
            raise SystemExit("未发现教师机：请在教师机上运行 host.py，或加 --host IP --key 口令")
        host, port = info["ip"], int(info.get("port", port))
        key = key or info.get("key", "")
        print(f"发现教师机 {host}:{port} 会话 {info.get('session')}")

    try:
        while True:
            d = call(host, port, key, "policy" if args.action == "status" else args.action)
            show(d)
            if not args.follow or args.action != "status":
                break
            time.sleep(2.0)
    except (OSError, http.client.HTTPException) as exc:
        raise SystemExit(f"连接教师机失败：{exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
