"""
GameOptimizerPro v2.1 — GitHub Update Checker
Prüft beim Start ob eine neue Version auf GitHub verfügbar ist.
Non-blocking, läuft im Hintergrund-Thread.
"""

import threading, json, re, urllib.request, urllib.error
from typing import Optional, Callable

CURRENT_VERSION = "2.0"
GITHUB_REPO     = "FloDePin/GameOptimizerPro-v2"
GITHUB_API_URL  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASE  = f"https://github.com/{GITHUB_REPO}/releases/latest"


def _parse_version(ver: str) -> tuple[int, ...]:
    """Parse 'v2.1', '2.0' or 'v2.7.0-beta' into a numeric tuple.
    Only the core before any '-'/'+' suffix is used, so pre-release tags like
    'v2.7.0-beta' parse to (2, 7, 0) instead of collapsing to (0,)."""
    ver = ver.lstrip("vV").strip()
    core = re.split(r"[-+]", ver, maxsplit=1)[0]   # drop '-beta', '+build' etc.
    nums = re.findall(r"\d+", core)
    return tuple(int(x) for x in nums) if nums else (0,)


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

        except urllib.error.URLError:
            # Offline / no network — expected, stay quiet
            self._checked = True
            if self._on_result:
                self._on_result(False, CURRENT_VERSION, GITHUB_RELEASE)
        except Exception:
            # Anything else (JSON/parse/attr error): don't crash the check,
            # but treat it as "no update" rather than silently hiding a URLError
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
