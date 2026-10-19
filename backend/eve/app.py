"""Native Windows Desktop Application Launcher for E.V.E. using pywebview (Edge WebView2).

Provides a desktop app experience:
- Zero browser address bars, tabs, or browser chrome.
- Native Windows window with modern dark theme (#020617), smooth DPI scaling, and state persistence.
- Automatically ensures FastAPI backend and Next.js dashboard services are active before presenting the window.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from eve.config import PROJECT_ROOT, Settings, get_settings

logger = logging.getLogger(__name__)


def is_service_ready(url: str, timeout: float = 1.0) -> bool:
    """Returns True if the HTTP endpoint responds with a 2xx or 3xx status code."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EVE-App-Check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def ensure_ollama_running() -> None:
    """Optionally ensures local Ollama daemon is running if installed."""
    if is_service_ready("http://127.0.0.1:11434/api/tags", timeout=0.5):
        return

    import os
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    ollama_path = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
    if ollama_path.exists():
        try:
            env = os.environ.copy()
            env["OLLAMA_FLASH_ATTENTION"] = "1"
            env["OLLAMA_KV_CACHE_TYPE"] = "q8_0"
            subprocess.Popen(
                [str(ollama_path), "serve"],
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            logger.info("Launched headless Ollama daemon with RTX 4060 VRAM optimizations.")
        except Exception as exc:
            logger.debug("Could not auto-start Ollama: %s", exc)


def ensure_backend_running(settings: Settings) -> None:
    """Ensures E.V.E. FastAPI backend is running on 127.0.0.1:8765, launching it if necessary."""
    backend_url = f"http://{settings.host}:{settings.port}/health"
    if is_service_ready(backend_url):
        logger.info("E.V.E. API backend is already active on %s", backend_url)
        return

    logger.info("Starting local E.V.E. FastAPI server in background thread...")

    def _run_server() -> None:
        import uvicorn
        from eve.main import create_app

        app = create_app(settings)
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")

    server_thread = threading.Thread(target=_run_server, name="eve-api-server", daemon=True)
    server_thread.start()

    # Wait up to 10 seconds for backend to become ready
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if is_service_ready(backend_url):
            logger.info("E.V.E. API backend is ready.")
            return
        time.sleep(0.3)

    logger.warning("Backend server did not respond within 10 seconds, proceeding anyway.")


def find_active_dashboard_port() -> int:
    """Detects whether Next.js dashboard is on port 3001 or 3000, launching it if needed."""
    for port in (3001, 3000):
        if is_service_ready(f"http://localhost:{port}"):
            logger.info("Detected running dashboard on port %d", port)
            return port

    # Neither port is listening: start Next.js production build on port 3001
    dash_dir = PROJECT_ROOT / "dashboard"
    logger.info("Launching Next.js Dashboard on port 3001...")
    try:
        subprocess.Popen(
            ["npm.cmd" if sys.platform == "win32" else "npm", "start", "--", "-p", "3001"],
            cwd=str(dash_dir),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception as exc:
        logger.error("Could not spawn Next.js dashboard process: %s", exc)

    # Wait up to 12 seconds for dashboard to become ready
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        if is_service_ready("http://localhost:3001"):
            return 3001
        time.sleep(0.5)

    return 3001


def run_desktop_app(settings: Settings | None = None) -> None:
    """Launches the native E.V.E. desktop window via pywebview (Edge WebView2)."""
    import webview

    settings = settings or get_settings()

    # 0. Ensure local Ollama is active if installed
    ensure_ollama_running()

    # 1. Ensure backend service is responsive
    ensure_backend_running(settings)

    # 2. Determine active dashboard URL
    port = find_active_dashboard_port()
    dashboard_url = f"http://localhost:{port}"

    logger.info("Opening E.V.E. Desktop Application window at %s", dashboard_url)

    # 3. Create native desktop window
    window = webview.create_window(
        title="E.V.E. — Extensible Virtual Entity",
        url=dashboard_url,
        width=1320,
        height=860,
        min_size=(1024, 720),
        background_color="#020617",  # Tailwind slate-950 to prevent white flash
        text_select=True,
        zoomable=True,
    )

    # 4. Resolve app icon path if present
    icon_path = PROJECT_ROOT / "assets" / "eve.ico"
    icon_arg = str(icon_path) if icon_path.exists() else None

    # 5. Start native desktop event loop (blocking until window is closed)
    # Uses Edge WebView2 on Windows automatically
    webview.start(private_mode=False, icon=icon_arg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_desktop_app()
