#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
watch.py —— 观看机守护启动器
============================
启动 viewer.py 并在它被杀掉/崩溃后自动重启（退出码非 0 就重启）。
只有教师机把模式设为 open 或 end 时，观看机才返回 0 并让守护停止。
本脚本自带单实例锁，可用「每 1 分钟」计划任务做外部复活而不会重复启动。

用法（把 viewer 的选项原样传过来）：
    python watch.py                     # 自动发现教师机
    python watch.py --host 192.168.1.20 --key ab12cd34
日志：viewer.log（同目录）
"""
from __future__ import annotations

import argparse
import datetime
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CREATE_NO_WINDOW = 0x08000000


EXIT_OK = 0
EXIT_CRASH = 1
EXIT_DEP = 3          # viewer.py 缺少依赖（pillow 等）：重启没有意义


def viewer_command(extra: list[str]) -> list[str]:
    if getattr(sys, "frozen", False):                       # 打包成 exe 的情况
        exe = os.path.join(HERE, "viewer.exe")
        target = exe if os.path.exists(exe) else "viewer.exe"
        return [target] + extra
    py = sys.executable
    if os.name == "nt":
        cand = os.path.join(os.path.dirname(py), "pythonw.exe")   # 无黑窗
        if os.path.exists(cand):
            py = cand
    return [py, os.path.join(HERE, "viewer.py")] + extra


def acquire_lock(port: int) -> socket.socket | None:
    """单实例锁：占用 127.0.0.1:port 成功就返回 socket，失败说明已有守护在跑。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--watch-delay", type=float, default=1.5)
    ap.add_argument("--watch-log", default=os.path.join(HERE, "viewer.log"))
    ap.add_argument("--watch-port", type=int, default=47651)
    ap.add_argument("--watch-no-lock", action="store_true")
    args, extra = ap.parse_known_args()

    holder = None
    if not args.watch_no_lock:
        holder = acquire_lock(args.watch_port)
        if holder is None:
            print("[watch] 已有守护在运行，本次退出")
            return 0

    cmd = viewer_command(extra)
    debug_mode = any(a == "--debug" for a in extra)     # 调试模式：崩了也不复活，方便试用
    restarts = 0
    if debug_mode:
        print("[watch] 调试模式：观看机退出或崩溃都不会自动重启")
        try:
            with open(args.watch_log, "a", encoding="utf-8", errors="replace") as logf:
                logf.write("[watch] 调试模式：不会自动重启\n")
        except OSError:
            pass
    try:
        while True:
            started = time.time()
            try:
                with open(args.watch_log, "a", encoding="utf-8", errors="replace") as logf:
                    logf.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} 启动观看机 =====\n")
                    logf.write(f"  命令: {' '.join(cmd)}\n")
                    logf.flush()
                    # 让子进程的输出固定用 UTF-8，否则日志里会出现 GBK 乱码（viewer.log 用 utf-8 打开）
                    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
                    kwargs = {"stdout": logf, "stderr": subprocess.STDOUT,
                              "stdin": subprocess.DEVNULL, "cwd": HERE, "env": env}
                    if os.name == "nt":
                        kwargs["creationflags"] = CREATE_NO_WINDOW
                    rc = subprocess.call(cmd, **kwargs)
            except FileNotFoundError as exc:
                print(f"[watch] 启动失败：{exc}")
                return 1
            except KeyboardInterrupt:
                return 0

            dur = time.time() - started
            if rc == 0:
                print("[watch] 观看机已按教师机指令正常退出，守护结束")
                return 0
            if debug_mode:
                print(f"[watch] 调试模式：观看机退出 code={rc}，不重启")
                return rc
            if rc == EXIT_DEP:
                msg = ("观看机缺少依赖（pillow / tkinter），重启也没有意义："
                       "请在观看机上运行 setup.bat，或用 pyenv.bat 检查找到的 Python。")
                print("[watch] " + msg)
                try:
                    with open(args.watch_log, "a", encoding="utf-8", errors="replace") as logf:
                        logf.write(f"[watch] {msg}\n")
                except OSError:
                    pass
                return 3
            restarts += 1
            delay = args.watch_delay if dur > 3.0 else min(15.0, 2.0 * restarts)
            print(f"[watch] 观看机异常退出 code={rc}（存活 {dur:.1f}s），{delay:.1f}s 后重启 "
                  f"（累计重启 {restarts} 次）")
            time.sleep(delay)
    finally:
        if holder:
            holder.close()


if __name__ == "__main__":
    sys.exit(main())
