"""API + end-to-end pipeline tests using fake capture/VAD/STT."""

import time

import pytest
from fastapi.testclient import TestClient

from conftest import FakeSTT, speech_then_silence
from eve.audio.types import SOURCE_ME, SOURCE_THEM
from eve.main import create_app


@pytest.fixture
def client_factory(settings, make_components):
    clients = []

    def make(frames=None, stt=None):
        comps = make_components(frames=frames, stt=stt)
        client = TestClient(create_app(settings, comps))
        client.__enter__()
        clients.append(client)
        token = client.app.state.api_token
        # wait for the background model loader thread
        for _ in range(100):
            if client.app.state.model_status == "ready":
                break
            time.sleep(0.02)
        return client, {"Authorization": f"Bearer {token}"}, comps

    yield make
    for c in clients:
        c.__exit__(None, None, None)


# ------------------------------------------------------------------ security
def test_health_is_public_but_minimal(client_factory):
    client, _, _ = client_factory()
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api/status", "/api/sessions", "/api/devices"])
def test_protected_routes_require_token(client_factory, path):
    client, _, _ = client_factory()
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_foreign_origin_rejected(client_factory):
    client, auth, _ = client_factory()
    r = client.get("/api/status", headers={**auth, "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_dns_rebinding_host_rejected(client_factory):
    client, auth, _ = client_factory()
    r = client.get("/api/status", headers={**auth, "Host": "attacker.example:8765"})
    assert r.status_code == 400


def test_dashboard_origin_allowed(client_factory):
    client, auth, _ = client_factory()
    r = client.get("/api/status", headers={**auth, "Origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert r.json()["model"] == "ready"


def test_openapi_docs_disabled(client_factory):
    client, _, _ = client_factory()
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_token_persists_and_is_strong(settings, client_factory):
    client, _, _ = client_factory()
    token = (settings.data_dir / "api_token").read_text().strip()
    assert token == client.app.state.api_token
    assert len(token) >= 40


# ------------------------------------------------------------------ websocket auth
def test_websocket_rejects_missing_auth(client_factory):
    client, _, _ = client_factory()
    with client.websocket_connect("/ws/live") as ws:
        ws.send_json({"type": "auth", "token": "nope"})  # nosec B105 - invalid token test
        with pytest.raises(Exception):
            ws.receive_json()


def test_websocket_rejects_foreign_origin(client_factory):
    client, _, _ = client_factory()
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/live", headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_json()


# ------------------------------------------------------------------ sessions
def test_start_requires_consent(client_factory):
    client, auth, _ = client_factory()
    r = client.post("/api/sessions/start", json={"title": "IT 211"}, headers=auth)
    assert r.status_code == 409
    assert "participants" in r.json()["detail"]


def test_stop_without_session_is_409(client_factory):
    client, auth, _ = client_factory()
    assert client.post("/api/sessions/stop", headers=auth).status_code == 409


def test_end_to_end_live_captions_and_persistence(client_factory, settings):
    frames = (speech_then_silence(SOURCE_THEM, 0.0, 1.5, 1.0)
              + speech_then_silence(SOURCE_ME, 3.0, 1.0, 1.0))
    frames.sort(key=lambda f: f.t_end)
    stt = FakeSTT(lambda s: "Karon atong i-discuss ang subnetting" if len(s) > 20000 else "Sir, question po")
    client, auth, comps = client_factory(frames=frames, stt=stt)

    with client.websocket_connect("/ws/live") as ws:
        ws.send_json({"type": "auth", "token": client.app.state.api_token})
        assert ws.receive_json()["type"] == "hello"

        r = client.post("/api/sessions/start",
                        json={"title": "Networking 101", "course": "IT 222", "consent_confirmed": True},
                        headers=auth)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        assert r.json()["course"] == "IT 222"

        # second concurrent session is refused
        r2 = client.post("/api/sessions/start", json={"title": "x", "consent_confirmed": True}, headers=auth)
        assert r2.status_code == 409

        assert ws.receive_json()["type"] == "session_started"
        comps.holder["capture"].finished.wait(5)
        events = [ws.receive_json(), ws.receive_json()]

    assert {e["source"] for e in events} == {SOURCE_THEM, SOURCE_ME}
    them = next(e for e in events if e["source"] == SOURCE_THEM)
    assert them["text"].startswith("Karon")
    assert 0.0 <= them["t0"] < 0.2

    r = client.post("/api/sessions/stop", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "stopped"

    detail = client.get(f"/api/sessions/{sid}", headers=auth).json()
    assert [s["source"] for s in detail["segments"]] == [SOURCE_THEM, SOURCE_ME]
    listing = client.get("/api/sessions", headers=auth).json()
    assert listing[0]["id"] == sid

    rec_dirs = list(settings.recordings_dir.iterdir())
    assert len(rec_dirs) == 1
    assert {p.name for p in rec_dirs[0].iterdir()} == {"them.wav", "me.wav"}


def test_unknown_session_404(client_factory):
    client, auth, _ = client_factory()
    assert client.get("/api/sessions/999", headers=auth).status_code == 404
