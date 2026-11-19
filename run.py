#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py —— 教师机/机房一键菜单（给不想记参数的人）
    python run.py
选择编号即可；教师机、观看机、开放/封锁/结束、状态都在同一个菜单里。
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python"


def run(script: str, *args: str) -> int:
    return subprocess.call([PY, os.path.join(HERE, script), *args])


def main() -> int:
    print("=" * 58)
    print("  机房桌面演示 (mydesk)")
    print("=" * 58)
    print("  1  教师机：开始演示本机关面")
    print("  2  观看机：只读观看本机关面")
    print("  3  开放观看机：允许学生关闭观看窗口")
    print("  4  封锁观看机：学生不能退出")
    print("  5  结束演示：观看机自动退出")
    print("  6  查看教师机状态 / 观看机数量")
    print("  7  观看机自检（不显示窗口，只测连接）")
    print("  8  观看机【调试模式】：右上角有退出按钮，不屏蔽热键、不会自动重启")
    print("  0  退出")
    print("-" * 58)
    while True:
        try:
            c = input("请选择 > ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if c in ("0", "q", "quit", "exit"):
            return 0
        elif c == "1":
            print("[提示] 浏览器打开 http://本机IP:8765/ 可用按钮控制观看机")
            print("[提示] 观看机只要运行 start_viewer.bat，无需输入 IP")
            print("[提示] Ctrl+C 停止演示（观看机会停在最后画面）")
            run("host.py", "--fps", "15", "--width", "1280", "--quality", "72")
        elif c == "2":
            run("watch.py")
        elif c in ("3", "4", "5", "6"):
            action = {"3": "open", "4": "lock", "5": "end", "6": "status"}[c]
            run("kiosk.py", action)
        elif c == "7":
            run("viewer.py", "--smoke", "60")
        elif c == "8":
            print("[提示] 右上角红色「退出演示」按钮 / Ctrl+Q / Esc 就能退出；不会屏蔽热键、不会自动重启")
            run("watch.py", "--debug")
        else:
            print("无效选择")
        print()


if __name__ == "__main__":
    sys.exit(main())
