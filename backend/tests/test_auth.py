import os
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.secrets import Cipher, SecretKeyMismatchError, load_or_create_secret
from app.auth.sessions import SessionSigner
from app.config import get_settings
from app.main import create_app


class TestSecrets:
    def test_secret_is_generated_once_and_kept(self, tmp_path: Path) -> None:
        first = load_or_create_secret(None, tmp_path)
        second = load_or_create_secret(None, tmp_path)
        assert first == second and len(first) >= 48
        assert (tmp_path / "secret.key").is_file()
        assert oct(os.stat(tmp_path / "secret.key").st_mode & 0o777) == "0o600"
        assert load_or_create_secret(" explicit ", tmp_path) == "explicit"

    def test_cipher_round_trip_and_legacy_plaintext(self) -> None:
        cipher = Cipher("s3cret")
        stored = cipher.encrypt("hunter2")
        assert stored is not None and stored.startswith("enc:") and "hunter2" not in stored
        assert cipher.decrypt(stored) == "hunter2"
        assert cipher.encrypt(None) is None and cipher.encrypt("") is None
        assert cipher.decrypt("legacy-plain") == "legacy-plain"  # pre-encryption rows
        assert Cipher.is_encrypted(stored) and not Cipher.is_encrypted("legacy-plain")

    def test_wrong_key_is_a_clear_error(self) -> None:
        stored = Cipher("one").encrypt("pw")
        with pytest.raises(SecretKeyMismatchError, match="SECRET_KEY"):
            Cipher("two").decrypt(stored)


class TestSessions:
    def test_issue_and_verify(self) -> None:
        signer = SessionSigner("secret", ttl_seconds=60)
        token = signer.issue(now=1000)
        session = signer.verify(token, now=1030)
        assert session is not None and session.expires_at == 1060

    def test_rejects_tampering_expiry_and_other_keys(self) -> None:
        signer = SessionSigner("secret", ttl_seconds=60)
        token = signer.issue(now=1000)
        assert signer.verify(token, now=1061) is None
        assert signer.verify(token[:-1] + ("0" if token[-1] != "0" else "1")) is None
        assert SessionSigner("other", 60).verify(token, now=1001) is None
        assert signer.verify(None) is None and signer.verify("garbage") is None


@pytest.fixture
def aclient(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom.test:9090")
    monkeypatch.setenv("PROMETHEUS_PASSWORD", "prom-secret")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    monkeypatch.setenv("AUTH_PASSWORD", "open-sesame")
    monkeypatch.setenv("AUTH_API_TOKEN", "tok-123")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_api_requires_login(aclient: TestClient) -> None:
    assert aclient.get("/healthz").status_code == 200
    assert aclient.get("/api/auth").json() == {"enabled": True, "authenticated": False}
    assert aclient.get("/api/projects").status_code == 401
    assert aclient.get("/api/status").status_code == 401
    assert aclient.post("/api/projects/default/chat", json={"message": "x"}).status_code == 401


def test_login_logout_flow(aclient: TestClient) -> None:
    wrong = aclient.post("/api/auth/login", json={"password": "nope"})
    assert wrong.status_code == 401

    ok = aclient.post("/api/auth/login", json={"password": "open-sesame"})
    assert ok.status_code == 200 and ok.json() == {"enabled": True, "authenticated": True}
    cookie = ok.headers.get("set-cookie", "")
    assert (
        "prompilot_session=" in cookie
        and "HttpOnly" in cookie
        and "SameSite=lax" in cookie.replace("Lax", "lax")
    )

    assert aclient.get("/api/projects").status_code == 200  # cookie jar carries the session
    assert aclient.get("/api/status").json()["auth_enabled"] is True

    aclient.post("/api/auth/logout")
    assert aclient.get("/api/projects").status_code == 401


def test_api_token_for_scripts(aclient: TestClient) -> None:
    assert (
        aclient.get("/api/projects", headers={"Authorization": "Bearer tok-123"}).status_code == 200
    )
    assert (
        aclient.get("/api/projects", headers={"Authorization": "Bearer wrong"}).status_code == 401
    )


def test_login_is_throttled_after_failures(aclient: TestClient) -> None:
    for _ in range(5):
        aclient.post("/api/auth/login", json={"password": "nope"})
    assert aclient.post("/api/auth/login", json={"password": "open-sesame"}).status_code == 429
    # the brake releases after 30 s
    aclient.app.state.auth._failures.clear()  # type: ignore[attr-defined]
    assert aclient.post("/api/auth/login", json={"password": "open-sesame"}).status_code == 200


def test_stored_password_is_encrypted(aclient: TestClient, tmp_path: Path) -> None:
    aclient.post("/api/auth/login", json={"password": "open-sesame"})
    aclient.post(
        "/api/projects",
        json={
            "name": "Secure",
            "prometheusUrl": "http://s:9090",
            "prometheusUsername": "alice",
            "prometheusPassword": "pw-123",
        },
    )
    conn = sqlite3.connect(tmp_path / "data" / "prompilot.sqlite")
    rows = dict(conn.execute("SELECT slug, prometheus_password FROM projects").fetchall())
    assert rows["default"].startswith("enc:") and "prom-secret" not in rows["default"]
    assert rows["secure"].startswith("enc:") and "pw-123" not in rows["secure"]
    # ...but the runtime client gets the real one
    runtime = aclient.app.state.projects._runtimes["secure"]  # type: ignore[attr-defined]
    assert runtime.prometheus._http.auth is not None


def test_legacy_plaintext_rows_are_encrypted_on_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    conn = sqlite3.connect(data / "prompilot.sqlite")
    conn.executescript(
        """
        CREATE TABLE projects (
            slug TEXT PRIMARY KEY, name TEXT NOT NULL, prometheus_url TEXT NOT NULL,
            prometheus_username TEXT, prometheus_password TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO projects VALUES ('old', 'Old', 'http://old:9090', 'u', 'plain-pw',
            '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            assert client.get("/api/projects").json()[0]["hasPassword"] is True
            stored = (
                sqlite3.connect(data / "prompilot.sqlite")
                .execute("SELECT prometheus_password FROM projects WHERE slug = 'old'")
                .fetchone()[0]
            )
            assert stored.startswith("enc:")
            runtime = client.app.state.projects._runtimes["old"]  # type: ignore[attr-defined]
            assert runtime.prometheus._http.auth is not None
    finally:
        get_settings.cache_clear()


def test_open_instance_when_no_password(client: TestClient) -> None:
    assert client.get("/api/auth").json() == {"enabled": False, "authenticated": True}
    assert client.get("/api/projects").status_code == 200
    assert (
        client.post("/api/auth/login", json={"password": "anything"}).json()["authenticated"]
        is True
    )


def test_session_ttl_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("AUTH_SESSION_TTL", "12h")
    assert Settings(_env_file=None).auth_session_ttl.total_seconds() == 12 * 3600
    assert time.time() > 0
