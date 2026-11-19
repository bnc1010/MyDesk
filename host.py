#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教师机 / Host —— 把本机桌面实时广播给观看机（只读演示）
================================================================
· 捕获本机桌面 → 缩放 → JPEG → 通过 HTTP multipart(MJPEG) 同时推给所有观看机
· 观看机只能看、不能退出；退出与否由教师机决定（封锁 / 开放 / 暂停 / 结束）
· 局域网 UDP 自动发现：观看机不用输 IP
· 依赖：pip install pillow mss

用法（最简）：
    python host.py
教师机控制台：      http://本机IP:8765/
观看流地址：        http://本机IP:8765/stream?key=口令
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import io
import json
import secrets
import socket
import sys
import time
from datetime import datetime
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

try:
    from PIL import Image, ImageChops, ImageDraw

    try:
        from PIL import ImageGrab          # Windows / macOS 自带抓屏兜底
    except ImportError:
        ImageGrab = None
except ImportError:
    sys.exit("缺少依赖：请先运行  pip install pillow mss")

try:
    import mss
except ImportError:
    mss = None          # 只有抓桌面时需要；--source test 可无 mss 自检

BOUNDARY = b"frame"
MODES = ("kiosk", "open", "paused", "ending")
ACTION_MODES = {"lock": "kiosk", "open": "open", "pause": "paused",
                "resume": "kiosk", "end": "ending"}   # 指令名 -> 模式名

CONSOLE_HELP = """
教师机指令（输入后回车）：
  status            查看状态 / 连接数
  lock              封锁观看机（不可退出、不可关闭）
  open              开放观看机（允许学生关闭观看窗）
  pause             暂停推流（观看机停在最后一帧，仍然封锁）
  resume            恢复推流
  end               结束演示（观看机自动退出，不再重启）
  fps <数值>        实时改帧率，如 fps 15
  width <数值>      实时改输出宽度，如 width 1024   （0=原始分辨率）
  quality <数值>    实时改画质 1-98，如 quality 70
  clients           列出连接中的观看机
  key             重新生成访问口令
  help              显示本帮助
  quit              退出教师机
"""


# --------------------------------------------------------------------------- #
# 画面来源
# --------------------------------------------------------------------------- #
class FrameSource:
    """抓屏 → 缩放 → 编码。画面无变化时返回 None（省带宽）。"""

    def __init__(self, args):
        self.quality = min(98, max(1, args.quality))
        self.width = args.width
        self.max_height = args.max_height
        self.mode = args.source
        self.idle_skip = args.idle_skip
        self.backend = args.backend          # auto | mss | pil
        self.sct = None
        self.monitor = None
        self._prev = None
        self._n = 0

        if self.mode == "desktop":
            if mss is not None and self.backend != "pil":
                self.sct = mss.mss()
                mons = self.sct.monitors
                if args.monitor >= len(mons):
                    sys.exit(f"没有编号 {args.monitor} 的显示器（本机共 {len(mons) - 1} 个）")
                self.monitor = mons[args.monitor]
                self.backend = "mss"
            else:
                try:
                    ImageGrab.grab()               # Pillow 自带抓屏（Windows）
                    self.backend = "pil"
                except Exception as exc:
                    sys.exit(f"抓屏失败（mss 不可用，Pillow ImageGrab 也不可用）：{exc}\n"
                             f"  建议：pip install mss   或先用 --source test 自检")
            if self.backend == "mss":
                print(f"[显示] mss 采集 {self.monitor['width']}x{self.monitor['height']} "
                      f"(monitor {args.monitor}；0=全部屏幕合并)")
            else:
                print("[显示] 使用 Pillow ImageGrab 抓屏（装 mss 可获更好的多屏支持）")

    def _test_pattern(self) -> Image.Image:
        self._n += 1
        img = Image.new("RGB", (1280, 720), (18, 24, 38))
        d = ImageDraw.Draw(img)
        for y in range(720):
            d.line((0, y, 1280, y), fill=(20 + y // 12, 40 + y // 20, 70 + y // 10))
        d.rectangle((60, 60, 60 + (self._n * 13) % 1100, 400), fill=(220, 170, 60))
        d.text((70, 70), f"TEST PATTERN  frame #{self._n}", fill=(255, 255, 255))
        d.text((70, 110), datetime.now().strftime("%H:%M:%S"), fill=(255, 255, 255))
        return img

    def _fit(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        tw, th = self.width, self.max_height
        if tw <= 0 and th <= 0:
            return img
        if tw <= 0:
            tw = max(1, int(w * th / h))
        if th <= 0:
            th = max(1, int(h * tw / w))
        if tw * h > th * w:          # 按高度优先适配
            tw = max(1, int(w * th / h))
        else:
            th = max(1, int(h * tw / w))
        if (tw, th) != (w, h):
            img = img.resize((tw, th), Image.BILINEAR)
        return img

    def grab(self) -> bytes | None:
        img = self._test_pattern() if self.mode == "test" else None
        if img is None:
            if self.backend == "mss":
                shot = self.sct.grab(self.monitor)
                img = Image.frombytes("RGB", shot.size, shot.rgb)
            else:
                img = ImageGrab.grab(all_screens=True).convert("RGB")
        img = self._fit(img)

        if self._prev is not None and self.mode == "desktop":
            bbox = ImageChops.difference(img, self._prev).getbbox()
            if bbox is None:
                return None                       # 完全没变
            changed = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if changed < self.idle_skip * img.width * img.height:
                return None                       # 变化极小，不推帧
        self._prev = img

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=self.quality, optimize=False, progressive=False)
        self.out_size = img.size
        return buf.getvalue()

    def close(self):
        if self.sct is not None:
            try:
                self.sct.close()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# 教师机状态
# --------------------------------------------------------------------------- #
class Host:
    def __init__(self, args):
        self.args = args
        self.key = args.key or secrets.token_hex(4)
        self.mode = "kiosk"
        self.session = f"{int(time.time()) % 100000:05d}"
        self.fps_target = float(args.fps)
        self.clients: dict[int, asyncio.Queue] = {}
        self.client_meta: dict[int, str] = {}
        self._cid = 1
        self.last_frame: bytes | None = None
        self.last_frame_ts = 0.0
        self.frames = 0
        self.bytes_out = 0
        self.encode_ms = 0.0
        self.fps_actual = 0.0
        self._fps_cnt = 0
        self._fps_t0 = time.time()
        self.started = time.time()
        self._last_status = 0.0
        self.out_size = (0, 0)
        self.source = None
        self.stopping = False
        self.loop = None

    # ---- 推帧（丢弃慢客户端积压的旧帧，只保留最新帧） ----
    def broadcast(self, jpeg: bytes):
        self.last_frame = jpeg
        self.last_frame_ts = time.time()
        self.frames += 1
        self.bytes_out += len(jpeg)
        self._fps_cnt += 1
        for q in list(self.clients.values()):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(jpeg)
            except asyncio.QueueFull:
                pass

    def add_client(self, peer: str) -> tuple[int, asyncio.Queue]:
        cid = self._cid
        self._cid += 1
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        self.clients[cid] = q
        self.client_meta[cid] = peer
        return cid, q

    def remove_client(self, cid: int):
        self.clients.pop(cid, None)
        self.client_meta.pop(cid, None)

    def policy(self) -> dict:
        return {
            "mode": self.mode,
            "session": self.session,
            "fps": round(self.fps_actual, 1),
            "width": self.out_size[0],
            "height": self.out_size[1],
            "serverTime": time.time(),
            "viewers": len(self.clients),
        }

    def status_text(self) -> str:
        n = len(self.clients)
        mbps = (self.bytes_out * 8 / 1e6) / max(1.0, time.time() - self.started)
        return (f"[状态] 模式={self.mode}  会话={self.session}  观看机={n}  "
                f"帧率={self.fps_actual:.1f}fps  画面={self.out_size[0]}x{self.out_size[1]}  "
                f"均码率={mbps:.1f}Mbps  口令={self.key}")


# --------------------------------------------------------------------------- #
# HTTP 服务（极简 HTTP/1.1）
# --------------------------------------------------------------------------- #
async def read_request(reader):
    line = await reader.readline()
    if not line:
        return None
    try:
        parts = line.decode("latin-1").split()
        method, path = parts[0].upper(), parts[1]
    except (ValueError, IndexError):
        return None
    while True:
        h = await reader.readline()
        if h in (b"\r\n", b"\n", b""):
            break
    return method, path


def framed(jpeg: bytes) -> bytes:
    return (b"--" + BOUNDARY + b"\r\nContent-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")


PAGE_TPL = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>教师机控制台</title><style>
body{font-family:system-ui,"Microsoft YaHei",sans-serif;background:#101722;color:#e8edf5;margin:24px}
h2{margin:0 0 4px}small{color:#8fa1bb}
.s{background:#182232;border:1px solid #26344a;border-radius:10px;padding:12px 14px;margin:14px 0;line-height:1.7}
button{margin:4px 6px 4px 0;padding:9px 14px;border:0;border-radius:8px;background:#2b6cff;color:#fff;font-size:14px;cursor:pointer}
button.g{background:#2a8f4d}button.r{background:#b0413e}button.k{background:#43506a}
input{padding:8px;border-radius:8px;border:1px solid #2b3a52;background:#0d1420;color:#e8edf5;width:110px}
code{background:#0d1420;padding:2px 6px;border-radius:6px}
</style></head><body>
<h2>教师机控制台 <small>会话 __SESSION__ · 模式 <b id=m>__MODE__</b></small></h2>
<div class=s id=stats>载入中…</div>
<div>
<button class=g onclick="p('resume')">▶ 恢复推流</button>
<button onclick="p('pause')">⏸ 暂停</button>
<button class=k onclick="p('lock')">🔒 封锁观看机</button>
<button class=k onclick="p('open')">🔓 开放观看机</button>
<button class=r onclick="p('end')">■ 结束演示</button>
</div>
<div>帧率 <input id=fps placeholder="15"><button onclick="setv('fps',fps.value)">改</button>
宽度 <input id=width placeholder="1280"><button onclick="setv('width',width.value)">改</button>
画质 <input id=q placeholder="72"><button onclick="setv('quality',q.value)">改</button></div>
<div class=s>
观看机地址：<code id=stream>__STREAM__</code>
<a href="/stream?key=__KEY__" target=_blank>预览自己的流</a> ·
<button class=k onclick="copy()">复制给学生</button>
</div>
<script>
var KEY='__KEY__';
function p(a){fetch('/api/'+a+'?key='+encodeURIComponent(KEY),{method:'POST'}).then(load)}
function setv(k,v){fetch('/api/set?key='+encodeURIComponent(KEY)+'&'+k+'='+encodeURIComponent(v),{method:'POST'}).then(load)}
function copy(){navigator.clipboard.writeText(document.getElementById('stream').textContent);alert('已复制')}
function load(){fetch('/api/policy?key='+encodeURIComponent(KEY)).then(r=>r.json()).then(d=>{
document.getElementById('m').textContent=d.mode;
document.getElementById('stats').innerHTML=
 '观看机：<b>'+d.viewers+'</b> / __MAX__<br>帧率：'+d.fps+' fps · 画面：'+d.width+'×'+d.height+
 '<br>模式：'+d.mode+'（kiosk=不可退出 / open=可关闭 / paused=暂停 / ending=结束）';})}
load();setInterval(load,2000);
</script></body></html>"""

VIEW_TPL = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>教师演示（浏览器应急观看）</title><style>
html,body{margin:0;height:100%;background:#000;overflow:hidden}
img{width:100%;height:100%;object-fit:contain}
#t{position:fixed;left:10px;top:8px;color:#9fd3ff;font:13px system-ui,"Microsoft YaHei",sans-serif;
text-shadow:0 1px 3px #000;opacity:.85}
</style></head><body>
<div id=t>浏览器应急模式 · 教师已按 __MODE__ · F11 全屏（浏览器无法阻止学生关闭窗口，正式机房请用 start_viewer.bat）</div>
<img id=s src="/stream?key=__KEY__" alt="教师桌面">
<script>
var i=document.getElementById('s'),t0=Date.now(),n=0;
i.onerror=function(){retry()};
function retry(){n++;var d=new Date();i.src='/stream?key=__KEY__&r='+n+'#'+d.getTime();
document.getElementById('t').textContent='连接断开，正在重连…（浏览器应急模式）'}
// 教师机若结束演示，本页收不到帧会一直空白；这里做一次心跳检测
setInterval(function(){fetch('/policy?key=__KEY__').then(r=>r.json()).then(d=>{
 document.getElementById('t').textContent='浏览器应急模式 · 教师已按 '+d.mode+
 (d.mode=='ending'?' · 演示已结束':' · F11 全屏');
 if(d.mode=='ending')document.getElementById('t').style.color='#ff9f9f';
}).catch(()=>{})},3000);
</script></body></html>"""


async def handle_client(reader, writer, host: Host):
    peer = "?"
    try:
        peer = writer.get_extra_info("peername")
        peer = peer[0] if peer else "?"
        req = await read_request(reader)
        if not req:
            writer.close()
            return
        method, raw = req
        u = urlparse(raw)
        qs = parse_qs(u.query)
        key = (qs.get("key") or [""])[0]
        path = u.path.rstrip("/") or "/"

        localhost = peer in ("127.0.0.1", "::1", "localhost")
        # 本机教师控制台免口令（方便教师机自己点按钮）；其它机器一律要口令。
        # 加 --strict-key 则连本机也必须要口令（教师机上有别人登录时建议用）。
        local_free = localhost and not getattr(host.args, "strict_key", False)
        if host.key and key != host.key and not local_free:
            await send_text(writer, HTTPStatus.UNAUTHORIZED,
                            "口令不正确：请在地址后加 ?key=教师机口令")
            return

        # ---- 观看流 ----
        if path == "/stream":
            if len(host.clients) >= host.args.max_clients:
                await send_text(writer, HTTPStatus.SERVICE_UNAVAILABLE, "教师机连接数已满")
                return
            cid, q = host.add_client(peer)
            try:
                writer.write(b"HTTP/1.1 200 OK\r\n"
                             b"Content-Type: multipart/x-mixed-replace; boundary=" + BOUNDARY + b"\r\n"
                             b"Cache-Control: no-store, no-cache, must-revalidate\r\n"
                             b"Pragma: no-cache\r\nConnection: close\r\n\r\n")
                await writer.drain()
                if host.last_frame:                      # 新连接立刻给最新一帧
                    writer.write(framed(host.last_frame))
                while not host.stopping:
                    try:
                        jpeg = await asyncio.wait_for(q.get(), timeout=2.0)
                    except asyncio.TimeoutError:
                        continue                          # 心跳：不推空帧，保持连接
                    writer.write(framed(jpeg))
                    await writer.drain()
            finally:
                host.remove_client(cid)
            return

        # ---- 观看机策略（轮询） ----
        if path == "/policy":
            body = json.dumps(host.policy()).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n"
                         b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
            return

        # ---- API（教师网页 / 外部控制） ----
        if path.startswith("/api/"):
            action = path.split("/")[2] if len(path.split("/")) > 2 else ""
            if action == "policy":
                pass                                    # 只读
            elif action in ACTION_MODES:
                host.mode = ACTION_MODES[action]
                print(f"[指令] {action} -> 模式 {host.mode}", flush=True)
            elif action == "set":
                try:
                    if "fps" in qs:
                        host.fps_target = max(1.0, min(60.0, float(qs["fps"][0])))
                    if "width" in qs:
                        host.source.width = max(0, int(float(qs["width"][0])))
                    if "quality" in qs:
                        host.source.quality = max(1, min(98, int(float(qs["quality"][0])))
                                                  )
                except ValueError:
                    await send_text(writer, HTTPStatus.BAD_REQUEST, "数值不正确")
                    return
                host.source._prev = None                # 分辨率变了，重置差分基准
            else:
                await send_text(writer, HTTPStatus.NOT_FOUND, "未知指令")
                return
            if method not in ("POST", "GET"):
                await send_text(writer, HTTPStatus.METHOD_NOT_ALLOWED, "需要 POST")
                return
            body = json.dumps(host.policy()).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n"
                         b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                         b"Connection: close\r\n\r\n" + body)
            await writer.drain()
            return

        # ---- 应急观看页：任何一台装了浏览器但没装 Python 的机器都能看 ----
        if path in ("/view", "/viewer.html"):
            page = (VIEW_TPL
                    .replace("__KEY__", host.key)
                    .replace("__MODE__", host.mode))
            body = page.encode("utf-8")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                         b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
            return

        # ---- 教师机网页 ----
        if path in ("/", "/index.html"):
            page = (PAGE_TPL
                    .replace("__SESSION__", host.session)
                    .replace("__MODE__", host.mode)
                    .replace("__KEY__", host.key)
                    .replace("__MAX__", str(host.args.max_clients))
                    .replace("__STREAM__", f"http://{host.args.public or local_ip()}:{host.args.port}/stream?key={host.key}"))
            body = page.encode("utf-8")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                         b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
            return

        await send_text(writer, HTTPStatus.NOT_FOUND, "404")
    except (ConnectionError, asyncio.IncompleteReadError, BrokenPipeError):
        pass
    except Exception as exc:                          # 单个连接出错不影响教师机
        print(f"[warn] 连接 {peer} 出错: {exc}")
        try:
            await send_text(writer, HTTPStatus.INTERNAL_SERVER_ERROR, "内部错误")
        except Exception:
            pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def send_text(writer, code: HTTPStatus, msg: str):
    body = msg.encode("utf-8")
    writer.write(f"HTTP/1.1 {code.value} {code.phrase}\r\n"
                 f"Content-Type: text/plain; charset=utf-8\r\n"
                 f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
    try:
        await writer.drain()
    except Exception:
        pass


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 任务：抓帧 / UDP 发现 / 控制台
# --------------------------------------------------------------------------- #
async def capture_loop(host: Host):
    loop = asyncio.get_running_loop()
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="cap")
    src = host.source
    try:
        while not host.stopping:
            t0 = time.perf_counter()
            jpeg = None
            budget = host.args.test_frames
            if host.mode in ("kiosk", "open") and (budget <= 0 or host.frames < budget):
                jpeg = await loop.run_in_executor(ex, src.grab)
            elif budget > 0 and host.frames >= budget:
                await asyncio.sleep(1.0)          # 帧数预算用完：只保持连接
            host.encode_ms = (time.perf_counter() - t0) * 1000.0
            if jpeg:
                host.broadcast(jpeg)
            host.out_size = getattr(src, "out_size", host.out_size)

            now = time.time()
            if now - host._fps_t0 >= 1.0:
                host.fps_actual = host._fps_cnt / (now - host._fps_t0)
                host._fps_cnt, host._fps_t0 = 0, now
            if host.args.status_every > 0 and now - host._last_status >= host.args.status_every:
                host._last_status = now
                print(host.status_text(), flush=True)
                print(f"[诊断] 抓帧耗时={host.encode_ms:.0f}ms", flush=True)

            interval = 1.0 / max(1.0, host.fps_target)
            if host.mode in ("paused", "ending"):
                interval = 1.0
            if jpeg is None and host.mode in ("kiosk", "open"):
                interval = min(interval, 1.0)          # 画面静止时最多 1 次/秒空转
            await asyncio.sleep(max(0.0, interval - (time.perf_counter() - t0)))
    finally:
        ex.shutdown(wait=False)
        src.close()


async def announce_loop(host: Host):
    """UDP 广播教师机信息，观看机无需手输 IP。"""
    port = host.args.discover
    if port <= 0:
        return
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 0))
    except OSError as exc:
        print(f"[warn] UDP 发现已关闭: {exc}")
        return
    ip = host.args.public or local_ip()
    targets = {t.strip() for t in host.args.announce.split(",") if t.strip()}
    targets.add("255.255.255.255")
    print(f"[发现] UDP 广播 -> {', '.join(sorted(targets))}:{port}")
    try:
        while not host.stopping:
            msg = json.dumps({"app": "mydesk", "ip": ip, "port": host.args.port,
                              "session": host.session,
                              "key": "" if host.args.no_key_broadcast else host.key}).encode()
            for t in targets:
                try:
                    sock.sendto(msg, (t, port))
                except OSError:
                    pass
            await asyncio.sleep(2.0)
    finally:
        sock.close()


async def console_loop(host: Host):
    if host.args.quiet:
        while not host.stopping:                 # 后台运行：无控制台
            await asyncio.sleep(1.0)
        return
    print(CONSOLE_HELP)
    loop = asyncio.get_running_loop()
    while not host.stopping:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
        except (EOFError, OSError):
            return
        if not line:                                   # 无控制台（如 pythonw）
            return
        cmd = line.strip().split()
        if not cmd:
            continue
        c = cmd[0].lower()
        if c in ("status", "s", "状态"):
            print(host.status_text())
        elif c in ("clients", "观看机", "list"):
            print(f"[连接] {len(host.clients)} 台: {', '.join(sorted(set(host.client_meta.values()))) or '无'}")
        elif c in ("lock", "封锁"):
            host.mode = "kiosk"; print("[指令] 模式 -> kiosk")
        elif c in ("open", "开放"):
            host.mode = "open"; print("[指令] 模式 -> open")
        elif c in ("pause", "暂停"):
            host.mode = "paused"; print("[指令] 模式 -> paused")
        elif c in ("resume", "start", "恢复"):
            host.mode = "kiosk"; print("[指令] 模式 -> kiosk")
        elif c in ("end", "结束"):
            host.mode = "ending"; print("[指令] 模式 -> ending（观看机会自动退出）")
        elif c == "fps" and len(cmd) > 1:
            host.fps_target = max(1.0, min(60.0, float(cmd[1]))); print(f"[指令] 帧率 -> {host.fps_target}")
        elif c == "width" and len(cmd) > 1:
            host.source.width = max(0, int(float(cmd[1]))); host.source._prev = None
            print(f"[指令] 宽度 -> {host.source.width}")
        elif c == "quality" and len(cmd) > 1:
            host.source.quality = max(1, min(98, int(float(cmd[1])))); host.source._prev = None
            print(f"[指令] 画质 -> {host.source.quality}")
        elif c == "key":
            host.key = secrets.token_hex(4)
            print(f"[指令] 新口令 = {host.key}")
        elif c in ("quit", "exit", "退出"):
            host.mode = "ending"
            host.stopping = True
            return
        else:
            print(CONSOLE_HELP)


async def amain(args):
    host = Host(args)
    host.loop = asyncio.get_running_loop()
    host.source = FrameSource(args)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, host), args.bind, args.port,
        reuse_address=True)

    ip = args.public or local_ip()
    print("=" * 62)
    print(f"  教师机控制台   http://{ip}:{args.port}/")
    print(f"  观看机应连接   http://{ip}:{args.port}/stream?key={host.key}")
    print(f"  应急浏览器观看 http://{ip}:{args.port}/view?key={host.key}   （观看机没装 Python 时用这个）")
    print(f"  初始模式 kiosk（观看机不可退出） · 口令 {host.key}")
    print("  提示：Windows 防火墙需放行 python.exe（或让端口 " + str(args.port) + "）")
    print("=" * 62)
    print(host.status_text())

    async def stopper():
        while not host.stopping:
            await asyncio.sleep(0.3)

    try:
        async with server:
            tasks = [asyncio.ensure_future(capture_loop(host)),
                     asyncio.ensure_future(announce_loop(host)),
                     asyncio.ensure_future(console_loop(host))]
            try:
                if args.run_seconds > 0:
                    await asyncio.wait_for(stopper(), timeout=args.run_seconds)
                else:
                    await stopper()
            except asyncio.TimeoutError:
                print(f"[教师机] 已运行 {args.run_seconds}s，自动停止")
            host.stopping = True
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        host.stopping = True


def parse_args():
    p = argparse.ArgumentParser(
        description="教师机：把本机桌面广播给观看机（只读演示，轻量 MJPEG）")
    p.add_argument("--port", type=int, default=8765, help="观看端口（默认 8765）")
    p.add_argument("--bind", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    p.add_argument("--public", default="", help="对外展示的 IP（多网卡/NAT 时用）")
    p.add_argument("--fps", type=float, default=15.0, help="目标帧率（默认 15）")
    p.add_argument("--width", type=int, default=1280, help="输出宽度，0=原始分辨率（默认 1280）")
    p.add_argument("--max-height", type=int, default=0, help="输出高度上限（0=不限）")
    p.add_argument("--quality", type=int, default=72, help="JPEG 画质 1-98（默认 72）")
    p.add_argument("--monitor", type=int, default=1, help="1=主屏，0=所有屏幕合并（默认 1）")
    p.add_argument("--key", default="", help="访问口令（默认随机；控制台可 key 重生成）")
    p.add_argument("--max-clients", type=int, default=32, help="最多观看机数量（默认 32）")
    p.add_argument("--discover", type=int, default=5007, help="UDP 发现端口，0=关闭（默认 5007）")
    p.add_argument("--announce", default="", help="额外广播地址，逗号分隔（如 192.168.1.255）")
    p.add_argument("--no-key-broadcast", action="store_true",
                   help="不把口令写进 UDP 广播（则观看机必须自己带 --key）")
    p.add_argument("--strict-key", action="store_true",
                   help="连本机（127.0.0.1）也要求口令；教师机上还有别人登录时用")
    p.add_argument("--idle-skip", type=float, default=0.0004,
                   help="变化面积低于此比例时不推帧（默认 0.0004）")
    p.add_argument("--source", choices=("desktop", "test"), default="desktop",
                   help="test=合成测试画面（不抓屏，便于排障）")
    p.add_argument("--backend", choices=("auto", "mss", "pil"), default="auto",
                    help="抓屏实现：auto=mss 优先否则 Pillow；pil=强制 Pillow")
    p.add_argument("--status-every", type=float, default=8.0, help="每 N 秒自动打印状态（0=关闭）")
    p.add_argument("--test-frames", type=int, default=0, help="最多推 N 帧（0=不限），排障用")
    p.add_argument("--run-seconds", type=float, default=0, help="运行 N 秒后自动退出（0=一直运行）")
    p.add_argument("--quiet", action="store_true", help="不交互控制台（后台运行）")
    return p.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(amain(parse_args()))
    except KeyboardInterrupt:
        pass
