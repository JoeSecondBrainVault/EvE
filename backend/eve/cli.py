"""Command-line entry point: ``eve serve | devices | live``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from eve.config import get_settings


def _configure_console() -> None:
    # Windows consoles default to cp1252; Bisaya/Tagalog text must never crash printing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def cmd_serve(_: argparse.Namespace) -> None:
    import uvicorn

    from eve.main import create_app

    s = get_settings()
    print(f"E.V.E. API on http://{s.host}:{s.port}  (token file: {s.data_dir / 'api_token'})")
    uvicorn.run(create_app(s), host=s.host, port=s.port, log_level="info")


def cmd_devices(_: argparse.Namespace) -> None:
    from eve.audio.capture import list_devices

    for dev in list_devices():
        tag = "LOOPBACK" if dev["is_loopback"] else ("INPUT" if dev["max_input_channels"] else "OUTPUT")
        default = " (default)" if dev.get("is_default") else ""
        print(f"[{dev['index']:>3}] {tag:<8} {dev['name']}{default}  {dev['default_sample_rate']:.0f} Hz")


async def _live(args: argparse.Namespace, consent_confirmed: bool = False) -> None:
    from eve.db import make_engine
    from eve.events import EventBus
    from eve.main import default_components
    from eve.session import SessionManager

    s = get_settings()
    s.ensure_dirs()
    comps = default_components()
    print(f"Loading Whisper '{s.whisper_model}' (first run downloads the model)...")
    stt = await asyncio.to_thread(comps.load_stt, s)
    print(f"Model ready on {stt.device.upper()}.")
    bus = EventBus(asyncio.get_running_loop())
    manager = SessionManager(s, make_engine(s.db_path), bus, stt=lambda: stt,
                             capture_factory=comps.capture_factory(s), vad_factory=comps.vad_factory)
    async with bus.subscribe() as queue:
        row = manager.start(title=args.title, course=args.course, consent_confirmed=consent_confirmed)
        print(f"Recording session #{row.id}. Speak or play audio. Press Ctrl+C to stop.\n")
        try:
            while True:
                event = await queue.get()
                kind = event.get("type")
                if kind == "segment":
                    who = "THEM" if event["source"] == "them" else " ME "
                    lang = event.get("language") or "??"
                    print(f"[{event['t0']:7.1f}s] {who} ({lang}) {event['text']}", flush=True)
                elif kind == "warning":
                    print(f"  ! {event['message']}", flush=True)
        finally:
            print("\nStopping and finishing pending transcription...")
            done = manager.stop()
            print(f"Saved session #{done.id}. Audio: {done.recording_dir}")


def cmd_live(args: argparse.Namespace) -> None:
    consent = getattr(args, "yes", False)
    if not consent:
        answer = input("Have all participants been told this session is being recorded? [y/N] ")
        if answer.strip().lower() not in {"y", "yes", "oo", "o"}:
            print("Cancelled. E.V.E. only records with consent.")
            return
        consent = True
    try:
        asyncio.run(_live(args, consent_confirmed=consent))
    except KeyboardInterrupt:
        pass


def cmd_tray(_: argparse.Namespace) -> None:
    import time
    import urllib.request
    from eve.config import get_settings
    from eve.security import load_or_create_token
    from eve.tray import SystemTray

    s = get_settings()
    token = load_or_create_token(s.data_dir)
    api_url = f"http://{s.host}:{s.port}"

    def _start():
        consent = False
        if sys.platform == "win32":
            try:
                import ctypes

                # MB_YESNO = 0x04, MB_ICONQUESTION = 0x20
                res = ctypes.windll.user32.MessageBoxW(
                    0,
                    "Recording Consent Required:\n\nDo all lecture/meeting participants consent to being recorded?",
                    "E.V.E. Recording Consent",
                    0x04 | 0x20,
                )
                consent = res == 6  # IDYES = 6
            except Exception:
                consent = False
        else:
            consent = True

        if not consent:
            print("Recording cancelled: Participant consent was not confirmed.")
            return

        try:
            req = urllib.request.Request(
                f"{api_url}/api/sessions/start",
                data=b'{"title":"Tray Session","consent_confirmed":true}',
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=3.0)  # nosec B310
        except Exception as exc:
            print("Failed to start session from tray:", exc)

    def _stop():
        try:
            req = urllib.request.Request(
                f"{api_url}/api/sessions/stop",
                data=b"{}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=3.0)  # nosec B310
        except Exception as exc:
            print("Failed to stop session from tray:", exc)

    tray = SystemTray(on_start_session=_start, on_stop_session=_stop)
    tray.run_detached()
    print("E.V.E. System Tray active in notification area. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tray.stop()


def cmd_app(_: argparse.Namespace) -> None:
    from eve.app import run_desktop_app

    run_desktop_app()


def main(argv: list[str] | None = None) -> None:
    _configure_console()
    parser = argparse.ArgumentParser(prog="eve", description="E.V.E. personal AI assistant")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("app", help="launch E.V.E. native desktop application").set_defaults(func=cmd_app)
    sub.add_parser("serve", help="run the local API (default)").set_defaults(func=cmd_serve)
    sub.add_parser("devices", help="list audio devices").set_defaults(func=cmd_devices)
    sub.add_parser("tray", help="run system tray icon").set_defaults(func=cmd_tray)
    live = sub.add_parser("live", help="record + live captions in this terminal")
    live.add_argument("--title", default="Console session")
    live.add_argument("--course", default=None)
    live.add_argument("--yes", action="store_true", help="skip the consent prompt (you confirm consent)")
    live.set_defaults(func=cmd_live)
    args = parser.parse_args(argv)
    (args.func if hasattr(args, "func") else cmd_app)(args)


if __name__ == "__main__":
    main()
