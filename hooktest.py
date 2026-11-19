"""自检键盘钩子：装钩子不崩、CallNextHookEx 在 64 位下不溢出、屏蔽判定正确。

沙盒里 SendInput 被 UIPI 挡掉（返回 0），无法注入真实按键，
所以这里直接调用钩子回调、喂进构造好的 KBDLLHOOKSTRUCT，并临时伪造修饰键状态。
"""
import ctypes

from kiosk_windows import (HC_ACTION, KBDLLHOOKSTRUCT, LLKF_UP, VK_CONTROL, VK_ESCAPE,
                           VK_F4, VK_LWIN, VK_MENU, VK_SHIFT, VK_TAB, KeyboardLock)

lock = KeyboardLock()
print("install:", lock.install())
lock.enable(True)
print("active:", lock.active)


def fire(vk, modifiers=(), up=False):
    """模拟一次按键事件（modifiers 里列出「假装按下」的键）。"""
    ks = KBDLLHOOKSTRUCT()
    ks.vkCode, ks.scanCode, ks.time = vk, 0, 0
    ks.flags = LLKF_UP if up else 0
    real = lock._key_down
    lock._key_down = lambda v: v in modifiers
    try:
        return lock._cb(HC_ACTION, 0x1234567890, ctypes.addressof(ks))
    finally:
        lock._key_down = real


cases = [
    ("Win 键按下", fire(VK_LWIN), 1),
    ("Alt+F4 按下", fire(VK_F4, (VK_MENU,)), 1),
    ("Alt+Tab 按下", fire(VK_TAB, (VK_MENU,)), 1),
    ("Ctrl+Shift+Esc", fire(VK_ESCAPE, (VK_CONTROL, VK_SHIFT)), 1),
    ("Alt+F4 抬起", fire(VK_F4, (VK_MENU,), up=True), 0),
    ("普通键 A", fire(0x41), 0),
    ("普通键 Ctrl", fire(VK_CONTROL), 0),
]
for name, ret, want in cases:
    print(f"  {name:16s} -> {ret}  {'OK' if ret == want else 'FAIL(期望' + str(want) + ')'}")

got = lock._hits
lock.remove()
print(f"拦截计数={got}（应为 4）")
print("verdict:", "OK 钩子生效" if got == 4 else "FAIL")
