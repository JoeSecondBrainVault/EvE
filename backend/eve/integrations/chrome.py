"""Google Chrome Profile Inspector & Google Meet Automation Controller.

1. Automatically discovers all authenticated Google accounts/emails from Chrome's User Data.
2. Launches Google Meet with the user's selected Google profile (e.g. student email vs personal).
3. Connects with E.V.E.'s WASAPI loopback capture to record the lecture audio and transcribe.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CHROME_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"

CHROME_EXECUTABLE_CANDIDATES = [
    Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
]


def find_chrome_executable() -> Path:
    """Finds the installed Google Chrome binary on Windows."""
    for candidate in CHROME_EXECUTABLE_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Google Chrome executable not found on this system.")


def list_chrome_profiles() -> list[dict[str, str]]:
    """Scans Chrome's Local State to extract all user profiles with their associated Google emails."""
    local_state_path = CHROME_USER_DATA / "Local State"
    if not local_state_path.exists():
        logger.warning("Chrome Local State file not found at %s", local_state_path)
        return []

    try:
        data = json.loads(local_state_path.read_text(encoding="utf-8"))
        info_cache = data.get("profile", {}).get("info_cache", {})
        profiles = []

        for dir_name, p_data in info_cache.items():
            name = str(p_data.get("name", dir_name))
            email = str(p_data.get("user_name", "")).strip()
            # Only include profiles or accounts
            profiles.append({
                "directory": dir_name,
                "name": name,
                "email": email or "(No email linked)",
                "avatar_icon": str(p_data.get("avatar_icon", "")),
            })

        return profiles
    except Exception as exc:
        logger.error("Failed to parse Chrome Local State: %s", exc)
        return []


def resolve_chrome_profile(email_or_name: str | None) -> dict[str, str] | None:
    """Matches a requested email address or profile name against available Chrome profiles."""
    profiles = list_chrome_profiles()
    if not profiles:
        return None

    if not email_or_name:
        # Default to first profile with an email, or 'Default'
        for p in profiles:
            if "@" in p["email"]:
                return p
        return profiles[0]

    q = email_or_name.strip().lower()

    # Exact email match
    for p in profiles:
        if p["email"].lower() == q:
            return p

    # Partial email or name match
    for p in profiles:
        if q in p["email"].lower() or q in p["name"].lower() or q in p["directory"].lower():
            return p

    return None


def normalize_meet_url(url_or_code: str) -> str:
    """Formats an input code or URL into a valid Google Meet link."""
    clean = url_or_code.strip()
    if clean.startswith("http://") or clean.startswith("https://"):
        return clean

    # e.g. "abc-defg-hij" or "meet.google.com/abc-defg-hij"
    clean = clean.replace("meet.google.com/", "").replace("/", "").strip()
    return f"https://meet.google.com/{clean}"


def launch_meet_in_chrome(
    meet_url_or_code: str,
    email_or_profile: str | None = None,
) -> dict[str, Any]:
    """Launches Google Chrome with the selected profile navigating directly to the Google Meet link."""
    meet_url = normalize_meet_url(meet_url_or_code)
    chrome_exe = find_chrome_executable()

    profile = resolve_chrome_profile(email_or_profile)
    profile_dir = profile["directory"] if profile else "Default"
    profile_email = profile["email"] if profile else "Default"

    args = [
        str(chrome_exe),
        f"--profile-directory={profile_dir}",
        meet_url,
    ]

    logger.info("Launching Chrome for Google Meet with profile %s (%s): %s", profile_dir, profile_email, meet_url)
    subprocess.Popen(args)

    return {
        "status": "launched",
        "meet_url": meet_url,
        "email": profile_email,
        "profile_directory": profile_dir,
    }
