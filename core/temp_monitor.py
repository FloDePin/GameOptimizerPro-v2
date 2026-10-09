"""
GameOptimizerPro v2.1 — GPU Temperature Warning
Sendet Windows Toast Notification wenn GPU-Temp über Limit steigt.
Cooldown: nach einer Warnung 5 Minuten keine neue für dieselbe GPU.
"""

import threading, time, subprocess, os
from typing import Optional, Callable


class TempMonitor:
    DEFAULT_LIMIT  = 90    # °C
    CHECK_INTERVAL = 10    # Sekunden
    COOLDOWN       = 300   # 5 Minuten zwischen Warnungen

    def __init__(self, monitor, limit_c: int = DEFAULT_LIMIT):
        self._monitor   = monitor
        self._limit     = limit_c
        self._running   = False
        self._thread: Optional[threading.Thread] = None
        self._last_warn = 0.0   # timestamp of last warning
        self._on_warn:  Optional[Callable] = None

    @property
    def limit(self) -> int:
        return self._limit

    @limit.setter
    def limit(self, val: int):
        self._limit = max(60, min(105, val))

    def on_warning(self, cb: Callable):
        self._on_warn = cb

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                stats = self._monitor.read()
                temp  = stats.temp
                if temp >= self._limit:
                    now = time.time()
                    if now - self._last_warn >= self.COOLDOWN:
                        self._last_warn = now
                        self._send_toast(temp)
                        if self._on_warn:
                            self._on_warn(temp, self._limit)
            except Exception:
                pass
            time.sleep(self.CHECK_INTERVAL)

    def _send_toast(self, temp: int):
        """Send Windows Toast Notification via PowerShell."""
        try:
            ps = f'''
$title = "GPU Temperatur-Warnung ⚠"
$msg   = "GPU: {temp}°C — Limit: {self._limit}°C"
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$template.SelectSingleNode("//text[@id=1]").InnerText = $title
$template.SelectSingleNode("//text[@id=2]").InnerText = $msg
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("GameOptimizerPro").Show($toast)
'''
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            si = None
            if os.name == "nt":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
                 "-Command", ps],
                capture_output=True, timeout=5,
                creationflags=flags, startupinfo=si
            )
        except Exception:
            pass
