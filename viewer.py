#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
观看机 / Viewer —— 全屏只读观看教师机桌面
==========================================
· 自动发现教师机（UDP），也可手输 IP：  python viewer.py --host 192.168.1.20
· 全屏、无标题栏、置顶；封锁时 Alt+F4 / Alt+Tab / Win 组合键 / 任务管理器 被屏蔽
· 关不掉、被杀掉也会由 watch.py 自动重启；只有教师机 open / end 才会正常退出
· 依赖：pip install pillow        （tkinter 随 Python 自带）
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import sys
import threading
import time
from io import BytesIO
from urllib.parse import quote

try:
    import tkinter as tk
except ImportError:                # 有的精简版 Python（如 Windows 商店版）不带 tkinter
    sys.stderr.write(
        "缺少 tkinter：这个 Python 不带图形库，换一个完整版 Python（python.org 安装）即可。\n"
        f"  解释器：{sys.executable}\n")
    sys.exit(3)

try:
    from PIL import Image, ImageTk
except ImportError as exc:                      # 常见原因：Pillow 未装，或用了另一个 Python 解释器启动
    sys.stderr.write(
        "缺少依赖：请先运行  pip install pillow\n"
        f"  import 失败：{exc!r}\n"
        f"  解释器：{sys.executable}\n"
        f"  sys.path[0]：{sys.path[0] if sys.path else '(空)'}\n"
    )
    # 退出码 3 = 缺依赖：watch.py 见到它就不再无限重启
    sys.exit(3)

try:
    import kiosk_windows
except ImportError:
    kiosk_windows = None

EXIT_OK = 0        # 教师机开放/结束 —— 守护脚本不再重启
EXIT_CRASH = 1     # 意外退出 —— 守护脚本重启


def log(msg: str):
    print(f"[viewer] {time.strftime('%H:%M:%S')} {msg}", flush=True)


# --------------------------------------------------------------------------- #
# MJPEG 分块解析
# --------------------------------------------------------------------------- #
def iter_frames(resp, stop: threading.Event):
    """yield 每一张 JPEG 字节。按 Content-Length 精确读取，边界为 --frame。"""
    buf = bytearray()
    boundary = b"--frame"

    def fill(n=1 << 16):
        data = resp.read1(n)
        if not data:
            raise ConnectionError("教师机断开")
        buf.extend(data)

    def read_until(delim: bytes) -> bytes:
        while True:
            j = buf.find(delim)
            if j >= 0:
                out = bytes(buf[:j])
                del buf[:j + len(delim)]
                return out
            fill()

    read_until(boundary)                       # 头部之前的序列
    while not stop.is_set():
        head = read_until(b"\r\n\r\n")
        length = None
        for line in head.split(b"\r\n"):
            low = line.lower()
            if low.startswith(b"content-length:"):
                try:
                    length = int(low.split(b":", 1)[1])
                except ValueError:
                    length = None
        if length is None:
            data = read_until(boundary).rstrip(b"\r\n")
        else:
            while len(buf) < length:
                fill()
            data = bytes(buf[:length])
            del buf[:length]
            del buf[:2]                        # 帧后 CRLF
        yield data
        read_until(boundary)                   # 吃下一个边界


# --------------------------------------------------------------------------- #
class Viewer:
    def __init__(self, args):
        self.args = args
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self.auto = (args.host or "auto").lower() in ("auto", "", "0")
        self.fixed_host = None if self.auto else args.host
        self.port = args.port
        self.key = args.key

        self.mode = "kiosk"
        self.session = ""
        self.announce = None                    # (ip, port, key, ts)
        self.connected = False
        self.last_err = ""
        self.started = time.time()
        self.last_frame_ts = 0.0
        self.frames = 0

        self._jpeg: bytes | None = None
        self._seq = 0
        self._used_seq = -1

        self.exit_code = EXIT_CRASH
        self.kb = None if args.debug else (kiosk_windows.KeyboardLock() if kiosk_windows else None)
        self.hardened = False
        self.cursor_hidden = False

        self.root = None
        self.canvas = None
        self._photo = None
        self._img_id = None
        self._status_id = None
        self._center_id = None
        self._debug_bar = None
        self._deny_until = 0.0

    # ---------------- 目标与发现 ---------------- #
    def target(self):
        if self.fixed_host:
            return self.fixed_host, self.port, self.key
        if self.announce:
            ip, port, key, _ = self.announce
            return ip, port, key or self.key
        return None

    def discovery_loop(self):
        port = self.args.discover
        if port <= 0:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
            sock.settimeout(1.0)
        except OSError as exc:
            log(f"UDP 发现端口 {port} 不可用：{exc}（改用 --host 手输 IP）")
            return
        log(f"等待教师机 UDP 广播（端口 {port}）…")
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(4096)
                info = json.loads(data.decode("utf-8"))
            except socket.timeout:
                continue
            except (ValueError, UnicodeDecodeError):
                continue
            if info.get("app") != "mydesk":
                continue
            ip, p, key = info.get("ip"), int(info.get("port", 8765)), info.get("key", "")
            if not ip:
                continue
            if not self.announce or (ip, p) != (self.announce[0], self.announce[1]):
                log(f"发现教师机 {ip}:{p} 会话 {info.get('session')}")
            self.announce = (ip, p, key, time.time())
        sock.close()

    def policy_loop(self):
        while not self._stop.is_set():
            t = self.target()
            if t:
                ip, port, key = t
                try:
                    conn = http.client.HTTPConnection(ip, port, timeout=5)
                    conn.request("GET", f"/policy?key={quote(key)}",
                                 headers={"User-Agent": "mydesk-viewer"})
                    resp = conn.getresponse()
                    body = resp.read()
                    conn.close()
                    if resp.status == 200:
                        d = json.loads(body.decode("utf-8"))
                        if d.get("mode") != self.mode:
                            log(f"模式变更 {self.mode} -> {d.get('mode')}")
                        self.mode = d.get("mode", "kiosk")
                        new_session = d.get("session", "")
                        if new_session and new_session != self.session:
                            log(f"新会话 {new_session}")
                            self.session = new_session
                    elif resp.status == 401:
                        self.last_err = "口令不正确"
                except OSError as exc:
                    self.last_err = f"无法连接教师机: {exc.__class__.__name__}"
            time.sleep(self.args.policy_every)

    def stream_loop(self):
        backoff = 1.0
        while not self._stop.is_set():
            t = self.target()
            if not t:
                time.sleep(0.5)
                continue
            ip, port, key = t
            conn = None
            try:
                conn = http.client.HTTPConnection(ip, port, timeout=12)
                conn.request("GET", f"/stream?key={quote(key)}",
                             headers={"User-Agent": "mydesk-viewer"})
                resp = conn.getresponse()
                if resp.status != 200:
                    self.last_err = f"教师机返回 {resp.status}" + (
                        "（口令不正确）" if resp.status == 401 else "")
                    log(self.last_err)
                    time.sleep(backoff)
                    backoff = min(8.0, backoff * 2)
                    continue
                self.connected = True
                self.last_err = ""
                backoff = 1.0
                log(f"已连接教师机 {ip}:{port}")
                for jpeg in iter_frames(resp, self._stop):
                    if self._stop.is_set():
                        break
                    with self._lock:
                        self._jpeg = jpeg
                        self._seq += 1
                    self.frames += 1
                    self.last_frame_ts = time.time()
            except OSError as exc:
                self.last_err = f"连接中断 {exc.__class__.__name__}"
                log(self.last_err)
                time.sleep(backoff)
                backoff = min(8.0, backoff * 2)
            finally:
                self.connected = False
                if conn:
                    try:
                        conn.close()
                    except OSError:
                        pass

    # ---------------- 封锁 / 释放 ---------------- #
    def apply_lock(self, locked: bool):
        if self.args.debug:                 # 调试模式：完全不加锁，随时可退
            return
        if self.kb:
            try:
                self.kb.enable(locked and not self.args.no_keys)
            except Exception as exc:
                log(f"键盘屏蔽失败: {exc}")
        if kiosk_windows and not self.args.no_harden:
            if locked and not self.hardened:
                log(kiosk_windows.harden(True))
                self.hardened = True
            elif not locked and self.hardened:
                log(kiosk_windows.harden(False))
                self.hardened = False
        if os.name == "nt" and not self.args.no_keys:
            try:
                if locked and not self.cursor_hidden:
                    ctypes_show_cursor(False)
                    self.cursor_hidden = True
                elif not locked and self.cursor_hidden:
                    ctypes_show_cursor(True)
                    self.cursor_hidden = False
            except Exception:
                pass

    def exit_now(self, code: int):
        self.exit_code = code
        self._stop.set()
        if self.root is not None:
            try:
                self.root.after(0, self._destroy)
            except Exception:
                pass

    def _destroy(self):
        self.apply_lock(False)
        try:
            if self.root:
                self.root.destroy()
        except Exception:
            pass

    # ---------------- GUI ---------------- #
    def build(self):
        self.root = tk.Tk()
        self.root.title("教师演示 · 调试模式" if self.args.debug else "教师演示 · 只读观看")
        self.root.attributes("-topmost", True)
        if self.args.window:
            self.root.overrideredirect(True)
            self.root.geometry(self.args.window)
        else:
            self.root.attributes("-fullscreen", True)
        self.canvas = tk.Canvas(self.root, bg="#0b1018", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._img_id = self.canvas.create_image(0, 0, image=None, anchor="center")
        self._center_id = self.canvas.create_text(0, 0, text="", fill="#7f8ea6",
                                                  font=("Microsoft YaHei", 20))
        self._status_id = self.canvas.create_text(8, 8, anchor="nw", text="",
                                                  fill="#9fb4d4", font=("Consolas", 10))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if self.args.debug:
            self._build_debug_bar()
            self.root.bind("<Control-q>", lambda e: self.quit_debug())
            self.root.bind("<Escape>", lambda e: self.quit_debug())
        else:
            self.root.bind("<Escape>", lambda e: None)  # 吞掉，避免无响应
        if self.kb is None and kiosk_windows is None:
            log("未找到 kiosk_windows.py，只做窗口级保护")
        self.root.after(40, self.tick)

    def _build_debug_bar(self):
        """调试模式：右上角常驻「退出演示」按钮（在画面之上，鼠标可点）。"""
        bar = tk.Frame(self.root, bg="#2b1c1c", highlightthickness=1, highlightbackground="#c0392b")
        bar.place(relx=1.0, rely=0.0, anchor="ne", x=-14, y=14)
        tk.Label(bar, text="调试模式", bg="#2b1c1c", fg="#ffd479",
                 font=("Microsoft YaHei", 11)).pack(side="left", padx=10, pady=4)
        tk.Button(bar, text="退出演示", bg="#c0392b", fg="white", activebackground="#e74c3c",
                  activeforeground="white", relief="flat", default="normal",
                  font=("Microsoft YaHei", 12, "bold"), padx=18, pady=6,
                  command=self.quit_debug).pack(side="left", padx=8, pady=4)
        self._debug_bar = bar
        log("调试模式：右上角「退出演示」按钮 / Ctrl+Q / Esc 都能退出；不屏蔽热键、不改注册表")

    def quit_debug(self):
        log("调试模式退出（学生点了退出按钮）")
        self.exit_now(EXIT_OK)

    def on_close(self):
        if self.args.debug:
            self.exit_now(EXIT_OK)                         # 调试模式直接允许关闭
            return
        if self.mode == "kiosk":
            self._deny_until = time.time() + 3.0
            return                                         # 封锁中，拒绝关闭
        self.exit_now(EXIT_OK)

    def _fit(self, iw: int, ih: int) -> tuple[int, int]:
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        if cw < 8 or ch < 8:
            cw = self.root.winfo_screenwidth()
            ch = self.root.winfo_screenheight()
        s = min(cw / iw, ch / ih)
        if not self.args.upscale:
            s = min(s, 1.0)
        return max(1, int(iw * s)), max(1, int(ih * s))

    def tick(self):
        if self._stop.is_set():
            return
        try:
            if self.mode == "ending":
                log("教师机已结束演示，退出")
                self.exit_now(EXIT_OK)
                return
            locked = self.mode in ("kiosk", "paused")
            self.apply_lock(locked)

            seq = self._seq
            if seq != self._used_seq:
                self._used_seq = seq
                with self._lock:
                    jpeg = self._jpeg
                if jpeg:
                    try:
                        img = Image.open(BytesIO(jpeg))
                        img.load()
                        if img.width > 1 and img.height > 1:
                            w, h = self._fit(img.width, img.height)
                            if (w, h) != (img.width, img.height):
                                img = img.resize((w, h), Image.BILINEAR)
                            self._photo = ImageTk.PhotoImage(img)
                            cw = max(1, self.canvas.winfo_width())
                            ch = max(1, self.canvas.winfo_height())
                            self.canvas.coords(self._img_id, cw // 2, ch // 2)
                            self.canvas.itemconfig(self._img_id, image=self._photo,
                                                   state="normal")
                    except Exception as exc:
                        self.last_err = f"解码失败 {exc}"

            fresh = time.time() - self.last_frame_ts
            waiting = self.frames == 0 or fresh > 2.5
            if waiting:
                self.canvas.itemconfig(self._img_id, state="hidden")
                tip = ("正在等待教师机画面…\n" if self.frames else "正在连接教师机…\n")
                t = self.target()
                tip += (f"{t[0]}:{t[1]}" if t else "尚未发现教师机（UDP 广播）")
                if self.last_err:
                    tip += f"\n{self.last_err}"
                if self.mode == "paused":
                    tip = "教师机已暂停推流（画面停在最后一帧）"
                if time.time() - self._deny_until > 0 and self._deny_until:
                    tip = "封锁中：由教师机决定何时开放"
                cw = max(1, self.canvas.winfo_width())
                ch = max(1, self.canvas.winfo_height())
                self.canvas.coords(self._center_id, cw // 2, ch // 2)
                self.canvas.itemconfig(self._center_id, text=tip, state="normal")
            else:
                self.canvas.itemconfig(self._center_id, state="hidden")

            t = self.target()
            where = f"{t[0]}:{t[1]}" if t else "未找到"
            status = (f"教师机 {where} · 会话 {self.session or '-'} · "
                      f"{'已连接' if self.connected else '未连接'} · 模式 {self.mode} · "
                      f"帧 {self.frames}")
            if self.args.debug:
                status += "  🔧 调试模式：Esc / Ctrl+Q / 右上角「退出演示」可退出"
            elif self.mode == "open":
                status += "  🔓 可关闭（教师已开放）"
            elif time.time() < self._deny_until:
                status += "  🔒 封锁中，不能退出"
            self.canvas.itemconfig(self._status_id, text=status)

            if self.args.timeout and not self.connected and \
                    time.time() - self.started > self.args.timeout:
                log(f"超过 {self.args.timeout}s 未连上教师机，退出（守护脚本会重启）")
                self.exit_now(EXIT_CRASH)
                return
        except tk.TclError:
            return
        finally:
            if not self._stop.is_set() and self.root is not None:
                try:
                    self.root.after(self.args.tick_ms, self.tick)
                except tk.TclError:
                    pass

    # ---------------- 运行 ---------------- #
    def _smoke(self) -> int:
        """无界面自检：连接教师机，收 N 帧后返回 0（用于验证链路/编码/解析）。"""
        target_frames = self.args.smoke
        deadline = time.time() + self.args.smoke_timeout
        last_print = 0.0
        while time.time() < deadline and self.frames < target_frames:
            time.sleep(0.1)
            if time.time() - last_print > 1.0:
                last_print = time.time()
                log(f"smoke: 帧 {self.frames}/{target_frames} 模式={self.mode} "
                    f"连接={'是' if self.connected else '否'} {self.last_err}")
        got = self.frames >= target_frames
        log(f"smoke 结果: {'OK' if got else 'FAIL'} 收到 {self.frames} 帧 "
            f"模式={self.mode} 错误={self.last_err or '无'}")
        self._stop.set()
        return EXIT_OK if got else EXIT_CRASH

    def run(self):
        threads = [threading.Thread(target=self.stream_loop, daemon=True),
                   threading.Thread(target=self.policy_loop, daemon=True)]
        if self.auto:
            threads.append(threading.Thread(target=self.discovery_loop, daemon=True))
        for t in threads:
            t.start()

        if self.args.smoke:
            code = self._smoke()
            self.exit_code = code
            return code

        self.build()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.exit_code = EXIT_CRASH
        finally:
            self._stop.set()
            self.apply_lock(False)
            if self.kb:
                self.kb.remove()
        return self.exit_code


def ctypes_show_cursor(hidden: bool):
    import ctypes
    ctypes.windll.user32.ShowCursor(False if hidden else True)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="观看机：全屏只读观看教师机桌面")
    p.add_argument("--host", default="auto", help="auto=UDP 自动发现，或教师机 IP")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--key", default="", help="访问口令（auto 时通常由广播带来）")
    p.add_argument("--discover", type=int, default=5007, help="UDP 发现端口，0=关闭")
    p.add_argument("--policy-every", type=float, default=2.0, help="策略轮询间隔秒")
    p.add_argument("--tick-ms", type=int, default=40, help="刷新间隔毫秒（默认 40≈25fps）")
    p.add_argument("--window", default="", help='不用全屏而是指定位置尺寸，如 "1920x1080+1920+0"')
    p.add_argument("--upscale", action="store_true", default=True, help="把画面放大铺满屏幕（默认开）")
    p.add_argument("--no-upscale", dest="upscale", action="store_false")
    p.add_argument("--no-keys", action="store_true", help="不屏蔽键盘组合键")
    p.add_argument("--no-harden", action="store_true", help="不写 HKCU 策略（不禁用任务管理器）")
    p.add_argument("--timeout", type=float, default=0, help="超过 N 秒没连上教师机就退出重启（0=一直等）")
    p.add_argument("--debug", action="store_true",
                   default=os.environ.get("MYDESK_DEBUG", "") == "1",
                   help="调试/试用模式：右上角有「退出演示」按钮，Esc/Ctrl+Q 可退，"
                        "屏蔽热键、禁用任务管理器、隐藏鼠标全都关掉（也可 set MYDESK_DEBUG=1）")
    p.add_argument("--no-debug", dest="debug", action="store_false", help="关闭调试模式（正式机房用）")
    p.add_argument("--smoke", type=int, default=0,
                    help="无界面自检：收到 N 帧就返回 0（验证链路，不开窗口）")
    p.add_argument("--smoke-timeout", type=float, default=25.0, help="自检最长等待秒")
    return p.parse_args(argv)


if __name__ == "__main__":
    code = Viewer(parse_args()).run()
    if code == EXIT_OK:
        log("正常退出（教师机开放或结束）")
    sys.exit(code)
