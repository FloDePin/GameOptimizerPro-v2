"""Run one test script on its own, never-shown Windows desktop.

    python tests\\run_hidden_desktop.py tests\\test_ui_round12.py

Some UI tests map real (alpha-0) windows because they need real geometry. On
the user's desktop such a window can take the focus — while a game runs in
fullscreen that is not acceptable. Windows belong to the desktop of the thread
that creates them: this script creates a separate desktop (CreateDesktop — it is
never switched to, so nothing appears on screen and no focus can be taken), moves
its own main thread there before tkinter is imported and runs the test in this
process. The desktop is gone when the process ends. Child processes still start
on the user's desktop (the UI tests fake theirs)."""
import ctypes
import ctypes.wintypes as wt
import os
import runpy
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if os.name != "nt":
        sys.exit("Windows only")
    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    u.CreateDesktopW.restype = wt.HANDLE
    u.CreateDesktopW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD, wt.DWORD,
                                 ctypes.c_void_p]
    u.SetThreadDesktop.argtypes = [wt.HANDLE]
    u.SetThreadDesktop.restype = wt.BOOL
    u.GetThreadDesktop.argtypes = [wt.DWORD]
    u.GetThreadDesktop.restype = wt.HANDLE
    GENERIC_ALL = 0x10000000
    h = u.CreateDesktopW(f"GopTests_{os.getpid()}", None, None, 0, GENERIC_ALL, None)
    if not h:
        sys.exit(f"CreateDesktop failed (Win32 {ctypes.get_last_error()})")
    if not u.SetThreadDesktop(h) or u.GetThreadDesktop(k.GetCurrentThreadId()) != h:
        sys.exit(f"SetThreadDesktop failed (Win32 {ctypes.get_last_error()})")
    path = os.path.abspath(sys.argv[1])
    sys.argv = [path] + sys.argv[2:]
    sys.path.insert(0, os.path.dirname(path))
    os.chdir(ROOT)
    runpy.run_path(path, run_name="__main__")


if __name__ == "__main__":
    main()
