"""Tests for security hardening: env expansion, TLS options, CORS resolution,
login rate limiting, and session cookie Secure flag."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import NetMapConfig

BASE_CONFIG = """
server:
  host: 127.0.0.1
  port: 8585

ping:
  interval: 2
  timeout: 1

devices: []
maps:
  - name: main
    label: Network Overview
links: []

discovery:
  enabled: false

traffic:
  enabled: false
"""


def _write_config(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "netmap.test.yaml"
    cfg.write_text(body.strip() + "\n", encoding="utf-8")
    return cfg


def _make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                 config_text: str, base_url: str = "http://testserver"):
    """Reload main with the given config and return (TestClient, main module)."""
    cfg = _write_config(tmp_path, config_text)
    monkeypatch.setenv("NETMAP_CONFIG", str(cfg))

    import main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app, base_url=base_url), main_module


class _FakeSession:
    token = "test-token"
    username = "alice"
    role = "Admin"


class _FakeSessionManager:
    """Session manager stub; ``succeed`` controls login outcome."""

    session_ttl = 28800

    def __init__(self, succeed: bool) -> None:
        self._succeed = succeed

    async def login(self, username: str, password: str):
        return _FakeSession() if self._succeed else None


# ----------------------------------------------------------------------
# ${ENV} expansion
# ----------------------------------------------------------------------

def test_env_expansion_raises_on_missing_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("NETMAP_MISSING_SECRET", raising=False)
    cfg = _write_config(tmp_path, BASE_CONFIG + """
api_defaults:
  username: admin
  password: "${NETMAP_MISSING_SECRET}"
""")
    with pytest.raises(ValueError, match="NETMAP_MISSING_SECRET"):
        NetMapConfig(cfg)


def test_env_expansion_substitutes_set_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("NETMAP_TEST_SECRET", "s3cret")
    cfg = _write_config(tmp_path, BASE_CONFIG + """
api_defaults:
  username: admin
  password: "${NETMAP_TEST_SECRET}"
""")
    assert NetMapConfig(cfg).api_defaults["password"] == "s3cret"


# ----------------------------------------------------------------------
# TLS option wiring
# ----------------------------------------------------------------------

def test_create_client_forwards_tls_options():
    from mikrotik.client import MikroTikClassicClient, MikroTikClient, create_client

    classic = create_client(
        "10.0.0.1", api_type="classic",
        use_ssl=True, ssl_verify=True, ssl_verify_hostname=True,
    )
    assert isinstance(classic, MikroTikClassicClient)
    assert classic.use_ssl is True
    assert classic.ssl_verify is True
    assert classic.ssl_verify_hostname is True

    rest = create_client("10.0.0.1", api_type="rest", ssl_verify=True)
    assert isinstance(rest, MikroTikClient)
    asyncio.run(rest.close())

    ssh = create_client("10.0.0.1", api_type="ssh", known_hosts="/tmp/kh")
    assert ssh.known_hosts == "/tmp/kh"


def test_ssh_known_hosts_defaults_and_override(tmp_path: Path):
    from mikrotik.ssh_client import MikroTikSSHClient

    kh = tmp_path / "known_hosts"
    kh.write_text("", encoding="utf-8")
    client = MikroTikSSHClient("10.0.0.1", known_hosts=str(kh))
    assert client._resolve_known_hosts() == str(kh)

    # Missing file falls back to disabled verification (with a warning).
    missing = MikroTikSSHClient("10.0.0.1", known_hosts=str(tmp_path / "nope"))
    assert missing._resolve_known_hosts() is None

    # Explicit opt-out.
    disabled = MikroTikSSHClient("10.0.0.1", known_hosts="none")
    assert disabled._resolve_known_hosts() is None


def test_session_manager_verify_ssl_default():
    from auth import SessionManager

    assert SessionManager("http://localhost:3000").verify_ssl is True
    assert SessionManager("http://localhost:3000", verify_ssl=False).verify_ssl is False


# ----------------------------------------------------------------------
# CORS resolution
# ----------------------------------------------------------------------

def test_cors_origins_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NETMAP_CORS_ORIGINS", raising=False)
    cfg = _write_config(tmp_path, """
server:
  host: 127.0.0.1
  port: 8585
  cors_origins: ["https://netmap.example.com"]

devices: []
maps:
  - name: main
discovery:
  enabled: false
traffic:
  enabled: false
""")
    monkeypatch.setenv("NETMAP_CONFIG", str(cfg))

    import main as main_module

    importlib.reload(main_module)
    assert main_module._resolve_cors_origins() == ["https://netmap.example.com"]


def test_cors_origins_env_takes_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = _write_config(tmp_path, BASE_CONFIG)
    monkeypatch.setenv("NETMAP_CONFIG", str(cfg))
    monkeypatch.setenv(
        "NETMAP_CORS_ORIGINS", "https://a.example, https://b.example"
    )

    import main as main_module

    importlib.reload(main_module)
    assert main_module._resolve_cors_origins() == [
        "https://a.example",
        "https://b.example",
    ]


def test_cors_origins_default_star(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("NETMAP_CORS_ORIGINS", raising=False)
    cfg = _write_config(tmp_path, BASE_CONFIG)
    monkeypatch.setenv("NETMAP_CONFIG", str(cfg))

    import main as main_module

    importlib.reload(main_module)
    assert main_module._resolve_cors_origins() == ["*"]


# ----------------------------------------------------------------------
# Login rate limiting
# ----------------------------------------------------------------------

AUTH_CONFIG = BASE_CONFIG + """
auth:
  enabled: true
  grafana_url: "http://localhost:3000"
"""


def test_login_rate_limited_after_five_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import api.auth as auth_api

    auth_api._login_limiter._attempts.clear()
    client, main_module = _make_client(tmp_path, monkeypatch, AUTH_CONFIG)
    with client:
        main_module.app_state["session_manager"] = _FakeSessionManager(succeed=False)

        for _ in range(5):
            resp = client.post(
                "/api/auth/login", json={"username": "u", "password": "p"}
            )
            assert resp.status_code == 401

        resp = client.post(
            "/api/auth/login", json={"username": "u", "password": "p"}
        )
        assert resp.status_code == 429
        assert "retry-after" in {k.lower() for k in resp.headers}
        assert int(resp.headers["Retry-After"]) >= 1


def test_rate_limiter_sliding_window():
    from api.auth import LoginRateLimiter

    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60.0)
    assert limiter.check("1.2.3.4") == 0.0
    assert limiter.check("1.2.3.4") == 0.0
    assert limiter.check("1.2.3.4") > 0.0
    # Different client IP is unaffected.
    assert limiter.check("5.6.7.8") == 0.0


# ----------------------------------------------------------------------
# Session cookie Secure flag
# ----------------------------------------------------------------------

def test_login_cookie_secure_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import api.auth as auth_api

    auth_api._login_limiter._attempts.clear()
    client, main_module = _make_client(tmp_path, monkeypatch, AUTH_CONFIG + """
  cookie_secure: true
""")
    with client:
        main_module.app_state["session_manager"] = _FakeSessionManager(succeed=True)
        resp = client.post(
            "/api/auth/login", json={"username": "u", "password": "p"}
        )
        assert resp.status_code == 200
        assert "Secure" in resp.headers["set-cookie"]


def test_login_cookie_secure_auto_from_scheme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import api.auth as auth_api

    auth_api._login_limiter._attempts.clear()
    client, main_module = _make_client(
        tmp_path, monkeypatch, AUTH_CONFIG, base_url="https://testserver"
    )
    with client:
        main_module.app_state["session_manager"] = _FakeSessionManager(succeed=True)
        resp = client.post(
            "/api/auth/login", json={"username": "u", "password": "p"}
        )
        assert resp.status_code == 200
        assert "Secure" in resp.headers["set-cookie"]


def test_login_cookie_not_secure_over_plain_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import api.auth as auth_api

    auth_api._login_limiter._attempts.clear()
    client, main_module = _make_client(tmp_path, monkeypatch, AUTH_CONFIG)
    with client:
        main_module.app_state["session_manager"] = _FakeSessionManager(succeed=True)
        resp = client.post(
            "/api/auth/login", json={"username": "u", "password": "p"}
        )
        assert resp.status_code == 200
        assert "Secure" not in resp.headers["set-cookie"]
