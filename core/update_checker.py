"""
GameOptimizerPro v2.1 — GitHub Update Checker
Prüft beim Start ob eine neue Version auf GitHub verfügbar ist.
Non-blocking, läuft im Hintergrund-Thread.
"""

import threading, json, urllib.request, urllib.error
from typing import Optional, Callable

CURRENT_VERSION = "2.6"
GITHUB_REPO     = "FloDePin/GameOptimizerPro-v2"
GITHUB_API_URL  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASE  = f"https://github.com/{GITHUB_REPO}/releases/latest"


def _parse_version(ver: str) -> tuple[int, ...]:
    """Parse 'v2.1' or '2.0' into (2, 0)."""
    ver = ver.lstrip("v").strip()
    try:
        return tuple(int(x) for x in ver.split("."))
    except:
        return (0,)


def _is_newer(remote: str, local: str) -> bool:
    return _parse_version(remote) > _parse_version(local)


class UpdateChecker:
    def __init__(self):
        self._latest_version: Optional[str] = None
        self._update_available = False
        self._checked = False
        self._on_result: Optional[Callable] = None

    def on_result(self, cb: Callable):
        """cb(update_available: bool, version: str, download_url: str)"""
        self._on_result = cb

    def check_async(self):
        """Run update check in background thread."""
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            req = urllib.request.Request(
                GITHUB_API_URL,
                headers={"User-Agent": "GameOptimizerPro-UpdateCheck"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data   = json.loads(resp.read().decode())
                tag    = data.get("tag_name", "")
                assets = data.get("assets", [])
                dl_url = GITHUB_RELEASE

                # Prefer ZIP asset if available
                for asset in assets:
                    if asset.get("name", "").endswith(".zip"):
                        dl_url = asset.get("browser_download_url", dl_url)
                        break

                self._latest_version  = tag
                self._update_available = _is_newer(tag, CURRENT_VERSION)
                self._checked         = True

                if self._on_result:
                    self._on_result(self._update_available, tag, dl_url)

        except (urllib.error.URLError, Exception):
            # Silent fail — no internet or repo doesn't exist yet
            self._checked = True
            if self._on_result:
                self._on_result(False, CURRENT_VERSION, GITHUB_RELEASE)

    @property
    def update_available(self) -> bool:
        return self._update_available

    @property
    def latest_version(self) -> Optional[str]:
        return self._latest_version

    @property
    def current_version(self) -> str:
        return CURRENT_VERSION
