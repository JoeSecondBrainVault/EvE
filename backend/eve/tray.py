"""Windows System Tray icon launcher using pystray and Pillow.

Displays interactive status in the Windows notification area:
- Dynamic state indicators: Idle (Green), ● REC (Red), Processing (Amber).
- One-click actions: Start/Stop session, Open Web Dashboard, Sync Google, and Exit.
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from typing import Any, Callable

from PIL import Image, ImageDraw

from eve.config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_tray_icon_image(state: str = "idle") -> Image.Image:
    """Dynamically draws a 64x64 RGBA system tray icon with status badge."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Base circular background: dark slate
    draw.ellipse((4, 4, 60, 60), fill=(15, 23, 42, 255), outline=(51, 65, 85, 255), width=2)

    # Center indicator color by state
    if state == "recording":
        # Crimson Red REC state
        draw.ellipse((16, 16, 48, 48), fill=(239, 68, 68, 255))
    elif state == "processing":
        # Amber Processing state
        draw.ellipse((16, 16, 48, 48), fill=(245, 158, 11, 255))
    else:
        # Emerald Green Idle state
        draw.ellipse((16, 16, 48, 48), fill=(16, 185, 129, 255))

    return image


class SystemTray:
    """Windows System Tray icon manager using pystray."""

    def __init__(
        self,
        settings: Settings | None = None,
        on_start_session: Callable[[], None] | None = None,
        on_stop_session: Callable[[], None] | None = None,
        on_open_dashboard: Callable[[], None] | None = None,
        on_sync_google: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.on_start_session = on_start_session
        def _open_dashboard_auto():
            import urllib.request
            for port in (3001, 3000):
                try:
                    req = urllib.request.Request(f"http://localhost:{port}", headers={"User-Agent": "EVE-Check"})
                    with urllib.request.urlopen(req, timeout=0.5):  # nosec B310
                        webbrowser.open(f"http://localhost:{port}")
                        return
                except Exception:
                    pass
            webbrowser.open("http://localhost:3001")

        self.on_open_dashboard = on_open_dashboard or _open_dashboard_auto
        self.on_sync_google = on_sync_google
        self.on_quit = on_quit
        self._state = "idle"
        self._icon: Any = None
        self._thread: threading.Thread | None = None

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, new_state: str) -> None:
        """Updates the icon state ('idle', 'recording', 'processing')."""
        self._state = new_state
        if self._icon is not None:
            try:
                self._icon.icon = create_tray_icon_image(self._state)
                prefix = "● REC" if new_state == "recording" else ("⏳ Processing" if new_state == "processing" else "Idle")
                self._icon.title = f"E.V.E. - {prefix}"
            except Exception as exc:
                logger.debug("Failed to update tray icon: %s", exc)

    def _build_menu(self) -> Any:
        import pystray

        def _wrap_start(icon: Any, item: Any) -> None:
            if self.on_start_session:
                self.on_start_session()
            self.set_state("recording")

        def _wrap_stop(icon: Any, item: Any) -> None:
            self.set_state("processing")
            if self.on_stop_session:
                self.on_stop_session()

        def _wrap_dash(icon: Any, item: Any) -> None:
            if self.on_open_dashboard:
                self.on_open_dashboard()

        def _wrap_sync(icon: Any, item: Any) -> None:
            if self.on_sync_google:
                self.on_sync_google()

        def _wrap_quit(icon: Any, item: Any) -> None:
            if self.on_quit:
                self.on_quit()
            icon.stop()

        return pystray.Menu(
            pystray.MenuItem("Open E.V.E. Dashboard", _wrap_dash, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Recording Session", _wrap_start),
            pystray.MenuItem("Stop & Analyze Session", _wrap_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sync Google Classroom & Calendar", _wrap_sync),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit E.V.E.", _wrap_quit),
        )

    def run_detached(self) -> None:
        """Starts the system tray icon in a dedicated daemon thread."""
        try:
            import pystray

            icon_img = create_tray_icon_image(self._state)
            self._icon = pystray.Icon(
                "EVE",
                icon_img,
                "E.V.E. - Study & Work Assistant",
                menu=self._build_menu(),
            )
            self._thread = threading.Thread(target=self._icon.run, name="eve-tray", daemon=True)
            self._thread.start()
            logger.info("E.V.E. system tray icon started.")
        except Exception as exc:
            logger.warning("Could not launch system tray icon: %s", exc)

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
