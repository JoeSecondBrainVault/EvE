"""Unit and integration tests for Desktop App, Chrome Meet Automation, and MCP tooling."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from eve.config import Settings
from eve.integrations.chrome import (
    list_chrome_profiles,
    normalize_meet_url,
    resolve_chrome_profile,
)
from eve.main import create_app
from eve.mcp.client import MCPClient
from eve.mcp.manager import MCPManager
from eve.mcp.models import MCPServerConfig, MCPTool, MCPToolCallResult
from eve.voice.assistant import VoiceAssistant


def test_normalize_meet_url() -> None:
    assert normalize_meet_url("abc-defg-hij") == "https://meet.google.com/abc-defg-hij"
    assert normalize_meet_url("meet.google.com/abc-defg-hij") == "https://meet.google.com/abc-defg-hij"
    assert normalize_meet_url("https://meet.google.com/xyz-uvw-rst") == "https://meet.google.com/xyz-uvw-rst"


def test_resolve_chrome_profile_parsing(tmp_path: Path) -> None:
    sample_local_state = {
        "profile": {
            "info_cache": {
                "Default": {
                    "name": "Joe USTP",
                    "user_name": "dumapiasjoe@ustp.edu.ph",
                    "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_0",
                },
                "Profile 1": {
                    "name": "Personal",
                    "user_name": "joedumapias@gmail.com",
                    "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_1",
                },
            }
        }
    }
    state_file = tmp_path / "Local State"
    state_file.write_text(json.dumps(sample_local_state), encoding="utf-8")

    with patch("eve.integrations.chrome.CHROME_USER_DATA", tmp_path):
        profiles = list_chrome_profiles()
        assert len(profiles) == 2
        emails = [p["email"] for p in profiles]
        assert "dumapiasjoe@ustp.edu.ph" in emails
        assert "joedumapias@gmail.com" in emails

        matched_ustp = resolve_chrome_profile("ustp.edu.ph")
        assert matched_ustp is not None
        assert matched_ustp["directory"] == "Default"

        matched_personal = resolve_chrome_profile("joedumapias@gmail.com")
        assert matched_personal is not None
        assert matched_personal["directory"] == "Profile 1"


def test_voice_assistant_meet_clarification(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, recordings_dir=tmp_path / "rec", db_path=tmp_path / "test.db")
    settings.ensure_dirs()

    mock_router = MagicMock()
    mock_session_mgr = MagicMock()

    assistant = VoiceAssistant(
        engine=MagicMock(),
        router=mock_router,
        settings=settings,
        tts=None,
        session_manager=mock_session_mgr,
    )

    fake_profiles = [
        {"directory": "Default", "name": "School", "email": "student@ustp.edu.ph"},
        {"directory": "Profile 1", "name": "Personal", "email": "personal@gmail.com"},
    ]

    with patch("eve.integrations.chrome.list_chrome_profiles", return_value=fake_profiles):
        # 1. No email specified -> asks for clarification
        out = assistant._tool_join_google_meet({"meet_url_or_code": "abc-defg-hij"})
        assert out["status"] == "clarification_needed"
        assert len(out["available_emails"]) == 2

        # 2. Email specified -> launches and triggers auto-recording
        with patch("eve.integrations.chrome.subprocess.Popen") as mock_popen, \
             patch("eve.integrations.chrome.find_chrome_executable", return_value=Path("C:/dummy/chrome.exe")):
            session_obj = MagicMock()
            session_obj.id = 99
            mock_session_mgr.start.return_value = session_obj

            res = assistant._tool_join_google_meet({
                "meet_url_or_code": "abc-defg-hij",
                "email_or_profile": "student@ustp.edu.ph",
            })
            assert res["status"] == "launched"
            assert res["recording"] is True
            assert res["session_id"] == 99
            mock_popen.assert_called_once()
            mock_session_mgr.start.assert_called_once()


def test_voice_assistant_safe_apps_allowlist(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, recordings_dir=tmp_path / "rec", db_path=tmp_path / "test.db")
    assistant = VoiceAssistant(
        engine=MagicMock(),
        router=MagicMock(),
        settings=settings,
        tts=None,
    )

    # Rejects unsafe command injection / unknown apps
    res_unsafe = assistant._tool_open_computer_app({"app_name": "cmd.exe /c format c:"})
    assert res_unsafe["status"] == "error"
    assert "not in the safe applications allowlist" in res_unsafe["message"]

    # Allows safe allowlisted apps
    with patch("subprocess.Popen") as mock_popen:
        res_calc = assistant._tool_open_computer_app({"app_name": "calculator"})
        assert res_calc["status"] == "opened"
        mock_popen.assert_called_once()


def test_mcp_manager_config_and_tool_call(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, recordings_dir=tmp_path / "rec", db_path=tmp_path / "test.db")
    mgr = MCPManager(settings)

    # Config file should be created
    assert mgr.config_file.exists()
    servers = mgr.list_servers()
    assert len(servers) >= 1

    # Test saving new server
    new_cfg = MCPServerConfig(
        name="test_server",
        command="python",
        args=["-c", "print('hello')"],
        enabled=False,
        description="Test server",
    )
    assert mgr.save_server(new_cfg) is True
    updated = mgr.list_servers()
    assert any(s["name"] == "test_server" for s in updated)

    # Mock tool dispatch
    mock_client = MagicMock(spec=MCPClient)
    mock_client.is_connected = True
    mock_client.list_tools.return_value = [
        MCPTool(server_name="test_server", name="get_classroom_assignments", description="Lists assignments", input_schema={})
    ]
    mock_client.call_tool.return_value = MCPToolCallResult(
        tool_name="get_classroom_assignments",
        content=[{"type": "text", "text": "Assignments found: 3"}],
    )
    mgr._clients["test_server"] = mock_client

    all_tools = mgr.list_all_tools()
    assert len(all_tools) == 1
    assert all_tools[0].name == "get_classroom_assignments"

    call_res = mgr.call_tool("get_classroom_assignments", {})
    assert call_res.is_error is False
    assert "Assignments found: 3" in call_res.content[0]["text"]


def test_api_desktop_and_mcp_endpoints(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        recordings_dir=tmp_path / "rec",
        db_path=tmp_path / "test.db",
    )
    settings.ensure_dirs()
    app = create_app(settings)

    with TestClient(app) as client:
        token = app.state.api_token
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Chrome Profiles
        with patch("eve.integrations.chrome.list_chrome_profiles", return_value=[{"name": "Joe", "email": "joe@test.com", "directory": "Default"}]):
            resp = client.get("/api/integrations/chrome/profiles", headers=headers)
            assert resp.status_code == 200
            assert len(resp.json()["profiles"]) == 1


        # 2. Safe App Launch
        with patch("subprocess.Popen"):
            resp = client.post("/api/integrations/apps/launch", json={"app_name": "calculator"}, headers=headers)
            assert resp.status_code == 200
            assert resp.json()["status"] == "opened"

        # 3. MCP Servers List
        resp = client.get("/api/mcp/servers", headers=headers)
        assert resp.status_code == 200
        assert "servers" in resp.json()

        # 4. Settings API Keys GET and POST
        resp_keys = client.get("/api/settings/keys", headers=headers)
        assert resp_keys.status_code == 200
        assert "gemini" in resp_keys.json()
        assert "groq" in resp_keys.json()

        with patch("dotenv.set_key"):
            payload = {
                "groq_api_key": "mock_groq_token",  # pragma: allowlist secret
                "gemini_api_key": "mock_gemini_token",  # pragma: allowlist secret
            }
            update_resp = client.post(
                "/api/settings/keys",
                json=payload,
                headers=headers,
            )
            assert update_resp.status_code == 200
            assert update_resp.json()["status"] == "ok"

        # 5. MCP Save validation (Bug 4 fix)
        # Unsafe binary rejected with 400
        unsafe_mcp = {"name": "malicious", "command": "cmd.exe", "args": ["/c", "calc.exe"]}
        resp_unsafe = client.post("/api/mcp/servers", json=unsafe_mcp, headers=headers)
        assert resp_unsafe.status_code == 400
        assert "Disallowed command runtime" in resp_unsafe.json()["detail"]

        # Missing required command field rejected with 422
        resp_invalid = client.post("/api/mcp/servers", json={"name": "incomplete"}, headers=headers)
        assert resp_invalid.status_code == 422

        # Safe binary accepted with 200
        safe_mcp = {"name": "safe_python", "command": "python", "args": ["-m", "eve.mcp.servers.workspace"], "enabled": False}
        resp_safe = client.post("/api/mcp/servers", json=safe_mcp, headers=headers)
        assert resp_safe.status_code == 200
        assert resp_safe.json()["status"] == "ok"

        # 6. Chat search top_k bounded validation (Bug 23 fix)
        resp_too_high = client.get("/api/chat/search?q=test&top_k=99999", headers=headers)
        assert resp_too_high.status_code == 422
        resp_negative = client.get("/api/chat/search?q=test&top_k=-1", headers=headers)
        assert resp_negative.status_code == 422


def test_workspace_mcp_server_jsonrpc() -> None:
    from eve.mcp.servers.workspace import handle_request

    # 1. Initialize
    init_res = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_res is not None
    assert init_res["result"]["serverInfo"]["name"] == "eve-google-workspace"

    # 2. Tools list
    list_res = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert list_res is not None
    tool_names = [t["name"] for t in list_res["result"]["tools"]]
    assert "get_classroom_assignments" in tool_names
    assert "get_calendar_events" in tool_names
    assert "list_unread_emails" in tool_names

    # 3. Tool call without credentials
    with patch("eve.mcp.servers.workspace._get_google_credentials", return_value=None):
        call_res = handle_request({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_classroom_assignments", "arguments": {}},
        })
        assert call_res is not None
        assert "Google account not logged in" in call_res["result"]["content"][0]["text"]

