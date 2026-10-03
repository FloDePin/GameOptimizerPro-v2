"""
GameOptimizerPro v2.0 — keep the PC awake while a test runs

An Auto-Tune takes 30–95 minutes; on a plan with sleep after 30 minutes Windows
would suspend the PC in the middle of a stress step (and turn the screen off
while the live graph is running). SetThreadExecutionState is per thread: call
keep_awake(True) in the thread that runs the test and keep_awake(False) in the
same thread when it ends (it is also released when the thread exits).
"""

import os

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def keep_awake(on: bool) -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if on else 0)
        return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))
    except Exception:
        return False
