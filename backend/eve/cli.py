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


async def _live(args: argparse.Namespace) -> None:
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
        row = manager.start(title=args.title, course=args.course, consent_confirmed=True)
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
    if not args.yes:
        answer = input("Have all participants been told this session is being recorded? [y/N] ")
        if answer.strip().lower() not in {"y", "yes", "oo", "o"}:
            print("Cancelled. E.V.E. only records with consent.")
            return
    try:
        asyncio.run(_live(args))
    except KeyboardInterrupt:
        pass


def cmd_tray(_: argparse.Namespace) -> None:
    import time
    from eve.tray import SystemTray

    tray = SystemTray()
    tray.run_detached()
    print("E.V.E. System Tray active in notification area. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tray.stop()


def main(argv: list[str] | None = None) -> None:
    _configure_console()
    parser = argparse.ArgumentParser(prog="eve", description="E.V.E. personal AI assistant")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the local API (default)").set_defaults(func=cmd_serve)
    sub.add_parser("devices", help="list audio devices").set_defaults(func=cmd_devices)
    sub.add_parser("tray", help="run system tray icon").set_defaults(func=cmd_tray)
    live = sub.add_parser("live", help="record + live captions in this terminal")
    live.add_argument("--title", default="Console session")
    live.add_argument("--course", default=None)
    live.add_argument("--yes", action="store_true", help="skip the consent prompt (you confirm consent)")
    live.set_defaults(func=cmd_live)
    args = parser.parse_args(argv)
    (args.func if hasattr(args, "func") else cmd_serve)(args)


if __name__ == "__main__":
    main()
