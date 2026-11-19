# mydesk —— 轻量机房桌面演示（教师机 → 观看机只读）

把一个教师的桌面实时广播给机房里的其它电脑：观看机全屏只读、**不能退出**，
只有教师机可以「开放 / 封锁 / 结束」。不需要服务器、不需要安装任何服务端软件，
局域网内点对点直接推流。

---

## 1. 它由什么组成

| 文件 | 装在哪 | 作用 |
|---|---|---|
| `host.py` | **教师机**（1 台） | 抓屏 → 缩放 → JPEG → HTTP 多路推流 + 教师控制台 + UDP 自动发现 |
| `viewer.py` | **观看机**（N 台） | 全屏只读显示、防退出、按教师机指令切换状态 |
| `watch.py` | **观看机** | 守护进程：观看机被杀掉/崩溃就自动重启（教师机结束则不再重启） |
| `kiosk_windows.py` | 观看机 | Windows 热键屏蔽 + 禁用任务管理器（HKCU 策略） |
| `kiosk.py` | 教师机 | 命令行控制观看机（open / lock / pause / resume / end） |
| `run.py` | 任意 | 菜单式一键操作，不想记参数就用它 |
| `probe.py` | 排障 | 自己收流统计帧数、看教师机真实帧率 |
| `hooktest.py` | 排障 | 自检键盘钩子（模拟 Alt+F4/Win 键，看是否被吞） |
| `pyenv.bat` | 被其它 .bat 调用 | 自动挑出「能用的 Python」，避开 Microsoft Store 版桩 |
| `start_host.bat` / `start_viewer.bat` / `start_viewer_debug.bat` / `stop_viewer.bat` | — | 启动、停止（debug 版带退出按钮） |
| `setup_firewall.bat` | 教师机 | 放行 TCP 8765 + UDP 5007（管理员运行） |
| `install_autostart.bat` / `uninstall_autostart.bat` | 观看机 | 开机自动进入只读观看（可选） |
| `pack_exe.bat` | 有 Python 的机器 | 打包成 `host.exe` / `viewer.exe` / `watch.exe`，观看机无需装 Python |

协议：**HTTP `multipart/x-mixed-replace`（MJPEG）** —— 浏览器也能直接看，
所以任何电脑（包括 Mac/Linux/平板）用浏览器打开 `http://教师机IP:8765/stream?key=口令` 就能看。

---

## 2. 三分钟跑通

```bat
setup.bat                :: 两台机器都先跑一次，装 pillow + mss
```

**教师机**

```bat
start_host.bat
```
输出类似：

```
  教师机控制台   http://192.168.10.72:8765/
  观看机应连接   http://192.168.10.72:8765/stream?key=a1b2c3d4
  初始模式 kiosk（观看机不可退出） · 口令 a1b2c3d4
```

**观看机**（每台只要双击，不用输 IP）

```bat
start_viewer.bat
```

**结束演示**（教师机上）：教师机控制台输入 `end`（回车），或网页上点「结束演示」，
或 `python kiosk.py end`。观看机会自己退出，守护进程也不会重启它们。

> 第一次在教师机上如果 Windows 防火墙弹窗，点「允许」；或者管理员运行
> `setup_firewall.bat`。

### 2.1 报「no usable Python found」或「Install failed」怎么办

`.bat` 会用 `pyenv.bat` 自己找 Python，顺序是：`MYDESK_PY` → `python.exe`（PATH）→
官方安装目录 → `pythonw.exe`。找不到就打印 FIX 1/2/3。三件事最容易踩：

| 情况 | 怎么办 |
|---|---|
| 这台机器没装 Python（`python --version` 没反应） | 到 <https://www.python.org/downloads/> 装 Python 3.12，**安装时勾选 “Add python.exe to PATH”**，然后重跑 `setup.bat` |
| 装了 Python 但 .bat 找不到（公司机器、便携版、WSL 之类） | 直接告诉它路径：`set MYDESK_PY=C:\Users\你\AppData\Local\Programs\Python\Python312\python.exe` 然后重跑 |
| Python 是 Microsoft Store 版（`WindowsApps\...python.exe`） | 它能跑，但 `pip install` 经常被封。仍然换成 python.org 版最省事；`pyenv.bat` 会打印 `pillow : MISSING` 提醒你 |
| 观看机装不上 `pillow`（没网） | `start_viewer.bat` 会直接告诉你缺模块，不会白跑；离线方案见第 6 节的 wheels |

**不用管 `python3` / `pip3`。** Windows 上一般只有 `python` / `pip`（或 `py -3`），
`python3`、`pip3` 只是 Microsoft Store 版 Python 的别名，而且那些别名经常是「桩」
（执行了只打印「请到商店安装」）。本工具的所有 `.bat` 都不依赖 `python3`/`pip3`：
`pyenv.bat` 会自己找出真正能跑的解释器（Store 版真正的解释器其实在
`%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe`），
然后统一用 `那个python.exe -m pip install ...` 和 `那个python.exe 脚本.py`。

`pyenv.bat` 每次都会打印它在用哪个解释器、tkinter 与 pillow 是否齐全，出错先看这四行。

---

## 3. 教师机的三种控制方式

1. **控制台**（`start_host.bat` 那个窗口直接输命令）
   `status` 状态 · `clients` 观看机列表 · `lock` 封锁 · `open` 开放 · `pause` 暂停画面 ·
   `resume` 恢复 · `end` 结束 · `fps 12` `width 1024` `quality 68` 改码率 ·
   `key` 换口令 · `quit` 退出
2. **网页**：浏览器打开 `http://教师机IP:8765/` → 按钮 + 实时状态
3. **命令行**：`python kiosk.py open`（自动发现教师机）或 `python kiosk.py open --host 192.168.1.20 --key a1b2c3d4`

四种模式与观看机的行为：

| 模式 | 画面 | 学生能关窗口吗 | 守护进程会重启吗 |
|---|---|---|---|
| `kiosk`（默认） | 一直推 | ❌ 拒绝 + 提示「封锁中」 | ✅ 会 |
| `paused` | 停在最后一帧 | ❌ | ✅ |
| `open` | 继续推 | ✅ 可关（窗口不再全屏置顶，热键解锁） | ❌ 不会 |
| `ending` | 无 | 观看机**自己退出** | ❌ 不会 |

---

## 4. 「不能退出」到底拦了什么

观看机同时做了四件事：

1. 全屏 + 无边框 + 永远置顶（`-topmost`），关掉窗口按钮（`WM_DELETE_WINDOW` 直接拒绝）；
2. 低级键盘钩子屏蔽：`Alt+F4`、`Alt+Tab`、`Alt+Esc`、`Alt+空格`、`Win+D`、`Win+L`、
   `Win+M`、`Win+E`、`Win+R`、`Ctrl+Shift+Esc`…
3. `HKCU\...\Policies\System\DisableTaskMgr` 和 `...\Policies\Explorer\DisableTaskMgr` → 任务管理器打不开（退出时自动恢复，`--no-harden` 可关闭这个行为）；
4. `watch.py` 守护：观看机进程被强杀/崩溃 → 1.5 秒内重启（连不上教师机会退避 1→8 秒重试，不会自己退出）。

**做不到、也不该做的事**：`Ctrl+Alt+Del` 是系统安全序列，任何普通程序都屏蔽不了；
关机/注销/断电/开任务管理器杀进程（需要管理员）也无法阻止。要真正锁死机房，
需要 Windows 访问控制（标准用户 + Software Restriction Policy）或第三方 Kiosk 软件 —— 本工具的定位是
**让普通学生「看不见、出不去、也不知道怎么停」**，不是对抗管理员的安全边界。

### 4.1 调试 / 试用模式（学生端有退出按钮）

试用时最怕的就是「一跑就把机器锁住了，退不出来」。调试模式把这些锁全部关掉：

```bat
start_viewer_debug.bat                :: 观看机调试版启动，右上角有红色「退出演示」按钮
python viewer.py --debug              :: 手敲也行
python watch.py --debug               :: 带守护，但崩了也不重启（试用时最省心）
set MYDESK_DEBUG=1                    :: 环境变量方式，之后 start_viewer.bat 也自动进调试模式
```

调试模式下：

| 行为 | 正式（start_viewer.bat） | 调试（--debug） |
|---|---|---|
| 退出方式 | 只有教师机 `open` / `end` | 右上角「退出演示」按钮、`Esc`、`Ctrl+Q`、窗口关闭按钮 |
| 屏蔽 Alt+F4 / Alt+Tab / Win 键 | ✅ | ❌ 完全不开 |
| 写注册表禁用任务管理器 | ✅ | ❌ 不写 |
| 隐藏鼠标 | ✅ | ❌ 不隐藏 |
| 崩了自动重启 | ✅ | ❌ 不会 |
| 教师机 `end` | 观看机退出 | 一样退出 |

窗口标题和状态栏都会显示「调试模式」，一眼能看出这台机器没锁。
正式上机房时把 `start_viewer.bat` 的 `--debug` 去掉（或 `set MYDESK_DEBUG=0`）即可。

如果只是临时想停掉已经在跑的正式观看机：观看机上双击 `stop_viewer.bat`（管理员运行更稳）。

---

## 5. 带宽与画质（1–10 台观看机）

实测（教师机 1 台 → 1 台观看机，1280×720 / 15fps / JPEG 72）：
**抓帧 55–100 ms/帧，实际 13–17 fps，单路平均约 4–6 Mbps**；画面静止时自动不推帧
（`--idle-skip`，静止时约 0.3 Mbps），所以静止的桌面几乎不占带宽。

每加一台观看机，带宽就是 N × 单路。10 台约 40–60 Mbps（千兆局域网完全没问题；
2.4GHz Wi-Fi 会嫌挤）。想更省：

```bat
start_host.bat --fps 10 --width 1024 --quality 62
```

画质/帧率可以随时用控制台 `fps`、`width`、`quality` 改，观看机不用重启。

---

## 6. 常见坑

| 现象 | 处理 |
|---|---|
| `setup.bat` 说 `No usable Python found` 或 `pip install FAILED` | 见第 2.1 节：装 python.org 的 Python 3.12（勾选 “Add python.exe to PATH”），或 `set MYDESK_PY=C:\...\python.exe` 直接指路径 |
| 观看机日志 `No module named 'PIL'` | 那个 Python 没装 pillow（常见于 Microsoft Store 版 Python）。先跑 `setup.bat`；`start_viewer.bat` 现在会先打印 `pillow : MISSING` 再拒绝启动，不会反复重启 |
| 观看机一直「正在寻找教师机」 | 教师机防火墙：管理员跑 `setup_firewall.bat`；或观看机手输 `start_viewer.bat --host 192.168.1.20 --key 口令` |
| 跨 VLAN / 广播到不了 | 教师机 `--announce 192.168.1.255,10.0.0.255`，或观看机直接 `--host` |
| 多网卡 / NAT 后显示错 IP | 教师机 `--public 192.168.1.20` |
| 想两台教师机各推一路 | 一台用 `--port 8766`，另一台 `--port 8767`；观看机各自 `--port`，或用不同 `--discover` 端口 |
| 观看机黑屏但教师机显示有 1 台连接 | `python probe.py 教师机IP 8765 口令` 看真实帧数 |
| 观看机画面卡 | 教师机看 `[诊断] 抓帧耗时`；超过 100 ms 就降 `--width`/`--fps` |
| 想看别人电脑的画面（反向控制） | 本工具只读、单向；需要控制请用 RustDesk / Sunshine 等远程桌面 |
| 观看机日志出现「N 项被系统拒绝」 | 组策略/安全软件不允许写 HKCU 策略，任务管理器禁用失败——热键屏蔽与守护重启仍然生效；教师机上用 `gpedit.msc`/本地安全策略放开，或观看机加 `--no-harden` 跳过这一步 |
| 装不上 `mss`（离线机） | 教师机会自动退回 Pillow 的 `ImageGrab`；也可显式 `start_host.bat --backend pil`（抓帧会慢一点，本机实测 55–100 ms/帧） |
| 观看机完全没有 Python（也不想装） | 应急方案：教师机照常运行，观看机用浏览器打开 `http://教师机IP:8765/view?key=口令` 按 F11 全屏。但浏览器**不能**被强制「不可退出」，只能算临时看一眼；正式机房还是要 `start_viewer.bat` 或 `pack_exe.bat` 的 exe 版 |
| 教师机上还有别人（学生）登录账号 | 教师机默认对 `127.0.0.1` 免口令（方便本机点控制台按钮）。这种情况请加 `--strict-key`，本机也要口令 |

自检（不开窗口，验证链路通不通）：

```bat
python probe.py 127.0.0.1 8765 口令
python viewer.py --smoke 60 --key 口令
python hooktest.py          :: 键盘钩子自检（模拟 Alt+F4/Win 键有没有被吞）
```

---

## 7. 观看机零安装（exe 版）

在一台有 Python + 能联网的机器上：

```bat
pip install pyinstaller pillow mss
pack_exe.bat
```

得到 `host.exe` / `viewer.exe` / `watch.exe`：教师机放 `host.exe`，
观看机放 `watch.exe`（双击即只读观看，被杀会自动重启）。

---

## 8. 设计说明（为什么这样做最轻量）

- **JPEG 逐帧而非 H.264**：没有编码库依赖、任何语言/浏览器都能解码、
  观看机崩溃重连后立刻拿到最新一帧（不用等关键帧），桌面静止时不推帧 —— 桌面演示场景里
  这是最省事的取舍。代价：动态画面（视频、滚动）带宽比 H.264 高，不适合放视频。
- **只读、单向**：观看机不把键盘鼠标送回去，教师机也看不到学生机 —— 这是「机房演示」
  而不是远程控制，攻击面和带宽都更小。要控制别人电脑请用 RustDesk / Sunshine。
- **教师机单点推流**：机房 10 台以内最简单可靠。规模更大时 `--width 1024 --fps 10`，
  或让一台机器做中转（把 `viewer.py` 的帧转发…… 本版未做，需要时告诉我）。
- **控制方向只有一个**：观看机不能自己解锁，只能被教师机开放或结束，否则「不能退出」形同虚设。
- **口令只防「随便连」**：MJPEG 是明文 HTTP，口令只是最低门槛，别在公网用。
  要公网演示请自己加 HTTPS/反向代理或走 VPN。默认口令随机（每次启动不同），
  正式机房建议固定 `start_host.bat --key 你的口令`。
- **防退出的定位**：挡住「普通学生随手关掉窗口」，不是对抗管理员的安全边界。
  `Ctrl+Alt+Del`、关机、注销、断电都拦不住（见第 4 节）。
