"""Google Workspace MCP Server (stdio JSON-RPC 2.0).

Exposes Google Classroom, Gmail, and Google Calendar as Model Context Protocol (MCP) tools.
Uses GoogleAuthManager to load user credentials from Windows Credential Manager.
"""

from __future__ import annotations

import datetime
import json
import logging
import sys
from typing import Any

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[MCP:Workspace] %(message)s")
logger = logging.getLogger("mcp.workspace")

TOOLS = [
    {
        "name": "get_classroom_assignments",
        "description": "Lists active Google Classroom courses and pending student coursework/assignments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "course_name": {
                    "type": "string",
                    "description": "Optional course name filter (e.g. 'Networking')",
                }
            },
        },
    },
    {
        "name": "get_calendar_events",
        "description": "Retrieves upcoming events and deadlines from the user's Google Calendar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of events to fetch (default 10)",
                }
            },
        },
    },
    {
        "name": "list_unread_emails",
        "description": "Lists recent unread emails from the student's Gmail inbox (announcements from professors, submissions).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Maximum emails to fetch (default 5)",
                }
            },
        },
    },
]


def _get_google_credentials() -> Any:
    """Attempts to load Google OAuth credentials from E.V.E.'s GoogleAuthManager."""
    try:
        from eve.config import get_settings
        from eve.integrations.google import GoogleAuthManager

        settings = get_settings()
        mgr = GoogleAuthManager(settings)
        return mgr.get_credentials()
    except Exception as exc:
        logger.warning("Could not obtain Google credentials: %s", exc)
        return None


def execute_classroom_assignments(args: dict[str, Any]) -> str:
    creds = _get_google_credentials()
    if not creds:
        return (
            "Google account not logged in. Please click 'Connect Google' in the "
            "E.V.E. Settings page to authenticate your student email."
        )

    try:
        from googleapiclient.discovery import build

        classroom = build("classroom", "v1", credentials=creds, cache_discovery=False)
        courses_resp = classroom.courses().list(studentId="me", courseStates=["ACTIVE"]).execute()
        courses = courses_resp.get("courses", [])

        course_filter = args.get("course_name", "").strip().lower()
        output_lines = [f"Found {len(courses)} active course(s):"]

        for c in courses:
            cname = c.get("name", "Untitled")
            cid = c.get("id")
            if course_filter and course_filter not in cname.lower():
                continue

            output_lines.append(f"\nCourse: {cname} (ID: {cid})")
            cw_resp = classroom.courses().courseWork().list(courseId=cid).execute()
            items = cw_resp.get("courseWork", [])
            if not items:
                output_lines.append("  • No active coursework.")
            for cw in items[:5]:
                title = cw.get("title", "Untitled Assignment")
                due = cw.get("dueDate", {})
                due_str = f"{due.get('year')}-{due.get('month')}-{due.get('day')}" if due else "No deadline"
                output_lines.append(f"  • {title} (Due: {due_str})")

        return "\n".join(output_lines)
    except Exception as exc:
        logger.error("Error fetching classroom assignments: %s", exc)
        return f"Error querying Google Classroom: {exc}"


def execute_calendar_events(args: dict[str, Any]) -> str:
    creds = _get_google_credentials()
    if not creds:
        return "Google account not logged in. Please log in on the E.V.E. Settings page."

    try:
        from googleapiclient.discovery import build

        cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        max_res = int(args.get("max_results", 10))

        events_resp = (
            cal.events()
            .list(
                calendarId="primary",
                timeMin=now_iso,
                maxResults=max_res,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_resp.get("items", [])
        if not events:
            return "No upcoming calendar events found."

        output_lines = [f"Upcoming Google Calendar Events ({len(events)}):"]
        for ev in events:
            start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
            summary = ev.get("summary", "Untitled Event")
            output_lines.append(f"• {start} — {summary}")

        return "\n".join(output_lines)
    except Exception as exc:
        logger.error("Error fetching calendar events: %s", exc)
        return f"Error querying Google Calendar: {exc}"


def execute_unread_emails(args: dict[str, Any]) -> str:
    creds = _get_google_credentials()
    if not creds:
        return "Google account not logged in. Please log in on the E.V.E. Settings page."

    try:
        from googleapiclient.discovery import build

        gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
        max_res = int(args.get("max_results", 5))

        list_resp = (
            gmail.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=max_res)
            .execute()
        )
        messages = list_resp.get("messages", [])
        if not messages:
            return "No unread messages found in your Gmail inbox."

        output_lines = [f"Recent Unread Emails ({len(messages)}):"]
        for m in messages:
            msg = gmail.users().messages().get(userId="me", id=m["id"], format="metadata").execute()
            snippet = msg.get("snippet", "")
            headers = msg.get("payload", {}).get("headers", [])
            subject = "(No subject)"
            sender = "(Unknown sender)"
            for h in headers:
                if h["name"].lower() == "subject":
                    subject = h["value"]
                elif h["name"].lower() == "from":
                    sender = h["value"]
            output_lines.append(f"• From: {sender}\n  Subject: {subject}\n  Preview: {snippet[:100]}...\n")

        return "\n".join(output_lines)
    except Exception as exc:
        logger.error("Error fetching unread emails: %s", exc)
        return f"Error querying Gmail: {exc}"


def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "eve-google-workspace", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        # Notification: no response required
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "get_classroom_assignments":
            text_result = execute_classroom_assignments(arguments)
        elif tool_name == "get_calendar_events":
            text_result = execute_calendar_events(arguments)
        elif tool_name == "list_unread_emails":
            text_result = execute_unread_emails(arguments)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Unknown tool: '{tool_name}'"}],
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "isError": False,
                "content": [{"type": "text", "text": text_result}],
            },
        }

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method '{method}' not found"},
    }


def main() -> None:
    logger.info("Starting Google Workspace MCP stdio server...")
    for line in sys.stdin:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            req = json.loads(line_str)
            resp = handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            logger.error("Error processing JSON-RPC message: %s", exc)


if __name__ == "__main__":
    main()
