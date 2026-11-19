#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows 只读封锁辅助（观看机用）
================================
1) 键盘屏蔽：屏蔽 Alt+F4 / Alt+Tab / Alt+Esc / Alt+Space / Win 组合键 / Ctrl+Shift+Esc
   （低层键盘钩子，只屏蔽 keydown，keyrelease 一律放行，避免按键卡死）
2) 可选加固：HKCU 策略禁用任务管理器（无需管理员权限），退出时自动恢复

注意：Ctrl+Alt+Del 无法被任何普通程序屏蔽（系统硬约束），Windows 也不允许普通程序
完全阻止关机/注销；因此防退出必须配合「守护自动重启」（watch.py）才可靠。
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

WH_KEYBOARD_LL = 13
HC_ACTION = 2           # 回调的 nCode：正常事件（0=HC_NOREMOVE，<0 必须直接放行）
LLKF_UP = 0x01

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12          # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_F4 = 0x73
VK_BACK = 0x08

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KeyboardLock:
    """低层键盘钩子。必须在拥有消息循环的线程（tk mainloop 所在线程）安装。"""

    def __init__(self):
        self.active = False
        self.installed = False
        self._proc = None
        self._hh = None
        self._hits = 0

    def _key_down(self, vk: int) -> bool:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

    def _blocked(self, vk: int) -> bool:
        alt = self._key_down(VK_MENU)
        win = self._key_down(VK_LWIN) or self._key_down(VK_RWIN)
        ctrl = self._key_down(VK_CONTROL)
        shift = self._key_down(VK_SHIFT)

        if vk in (VK_LWIN, VK_RWIN):
            return True                                     # 屏蔽 Win 组合键
        if alt and vk in (VK_F4, VK_TAB, VK_ESCAPE, VK_SPACE, VK_MENU):
            return True                                     # Alt+F4 / Alt+Tab / Alt+Esc / Alt+Space
        if win:
            return True                                     # Win+D / Win+L / Win+R ...
        if ctrl and shift and vk == VK_ESCAPE:
            return True                                     # Ctrl+Shift+Esc 任务管理器
        if ctrl and alt and vk == VK_BACK:                  # Ctrl+Alt+Backspace
            return True
        return False

    def install(self) -> bool:
        if os.name != "nt" or self.installed:
            return self.installed
        user32 = ctypes.windll.user32
        # 显式声明原型，否则 64 位下 CallNextHookEx 的 lParam 会 OverflowError
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                             wintypes.HINSTANCE, ctypes.c_uint]

        def callback(code, wparam, lparam):
            # nCode: HC_ACTION(2)/HC_NOREMOVE(0) 才处理；nCode<0 必须直接传给下一个钩子
            if code >= 0 and self.active:
                try:
                    ks = KBDLLHOOKSTRUCT.from_address(lparam)
                    if not (ks.flags & LLKF_UP) and self._blocked(ks.vkCode):
                        self._hits += 1
                        return 1                            # 吞掉这个按键
                except Exception:
                    pass
            return user32.CallNextHookEx(self._hh, code, wparam, lparam)

        self._proc = HOOKPROC(callback)
        self._cb = callback                      # 供自检直接调用（hooktest.py）
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype = ctypes.c_int
        self._hh = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        self.installed = bool(self._hh)
        return self.installed

    def remove(self):
        if self.installed and self._hh:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(self._hh)
            except Exception:
                pass
            self._hh = None
            self.installed = False
        self.active = False

    def enable(self, on: bool):
        if on and not self.installed:
            self.install()
        self.active = bool(on)


# --------------------------------------------------------------------------- #
# HKCU 策略加固（任务管理器）
# --------------------------------------------------------------------------- #
_POLICY_KEYS = (
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Policies\System", "DisableTaskMgr"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "DisableTaskMgr"),
)


def harden(enable: bool) -> str:
    """enable=True 禁用任务管理器；False 恢复。返回结果说明。"""
    if os.name != "nt":
        return "非 Windows，跳过策略加固"
    import winreg

    hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    done, failed = [], []
    for hive_name, path, value in _POLICY_KEYS:
        key = None
        try:
            key = winreg.CreateKeyEx(hives[hive_name], path, 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, value, 0, winreg.REG_DWORD, 1)
            else:
                try:
                    winreg.DeleteValue(key, value)
                except OSError:
                    pass
            done.append(f"{path}\\{value}")
        except OSError as exc:
            failed.append(f"{path} : {exc}")
        finally:
            if key is not None:
                try:
                    winreg.CloseKey(key)
                except OSError:
                    pass
    tail = ""
    if failed:
        tail = f"（{len(failed)} 项被系统拒绝：{failed[0]}）"
    return ("已禁用任务管理器 " if enable else "已恢复任务管理器 ") + f"{len(done)} 项{tail}"
