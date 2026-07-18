"""Tests for security hardening: env expansion, TLS options, CORS resolution,
login rate limiting, and session cookie Secure flag."""

from __future__ import annotations

import asyncio
import importlib
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

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


def test_main_fails_fast_once_on_missing_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A config with an unset ${VAR} aborts startup at import, exactly once."""
    monkeypatch.delenv("NETMAP_UNSET_SECRET", raising=False)
    bad = _write_config(tmp_path, BASE_CONFIG + """
api_defaults:
  username: admin
  password: "${NETMAP_UNSET_SECRET}"
""")
    monkeypatch.setenv("NETMAP_CONFIG", str(bad))

    # Fails at import time (or at reload if already imported) — exactly once.
    with pytest.raises(ValueError, match="NETMAP_UNSET_SECRET"):
        importlib.reload(importlib.import_module("main"))

    # Reload with a valid config so later tests see a working module.
    good = _write_config(tmp_path, BASE_CONFIG)
    monkeypatch.setenv("NETMAP_CONFIG", str(good))
    importlib.reload(importlib.import_module("main"))


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

    # Default (no known_hosts configured): verification disabled, same
    # behavior as before the hardening PR — MikroTik keys are rarely in
    # the user's known_hosts, so verifying by default breaks deployments.
    assert MikroTikSSHClient("10.0.0.1")._resolve_known_hosts() is None

    # Explicit path to an existing file enables verification.
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
    assert limiter.is_limited("1.2.3.4") == 0.0
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert limiter.is_limited("1.2.3.4") > 0.0
    # Different client IP is unaffected.
    assert limiter.is_limited("5.6.7.8") == 0.0
    # Reset (successful login) clears the counter.
    limiter.reset("1.2.3.4")
    assert limiter.is_limited("1.2.3.4") == 0.0


def test_rate_limiter_evicts_stale_keys():
    from api.auth import LoginRateLimiter

    limiter = LoginRateLimiter(max_attempts=5, window_seconds=60.0)
    limiter._attempts["stale-ip"] = [time.monotonic() - 120.0]

    limiter.record_failure("new-ip")
    assert "stale-ip" not in limiter._attempts
    assert "new-ip" in limiter._attempts


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": headers,
        "client": ("10.0.0.1", 1234),
    })


def test_client_ip_ignores_spoofable_leftmost_xff():
    """Different client-supplied leftmost XFF values must share one bucket.

    Behind nginx (proxy_add_x_forwarded_for) the header is
    "<client-supplied>, <proxy-added>" — only the rightmost entry and
    X-Real-IP come from our proxy and can be trusted.
    """
    from api.auth import LoginRateLimiter, _client_ip

    cfg = SimpleNamespace(auth_trust_headers=True)
    spoofed_a = _request_with_headers([(b"x-forwarded-for", b"1.1.1.1, 9.9.9.9")])
    spoofed_b = _request_with_headers([(b"x-forwarded-for", b"2.2.2.2, 9.9.9.9")])

    assert _client_ip(spoofed_a, cfg) == "9.9.9.9"
    assert _client_ip(spoofed_b, cfg) == "9.9.9.9"

    # X-Real-IP (set by our proxy) is preferred over XFF entirely.
    real_ip = _request_with_headers([
        (b"x-real-ip", b"7.7.7.7"),
        (b"x-forwarded-for", b"1.1.1.1, 9.9.9.9"),
    ])
    assert _client_ip(real_ip, cfg) == "7.7.7.7"

    # Without trust, the socket peer is used (headers ignored).
    untrusted = SimpleNamespace(auth_trust_headers=False)
    assert _client_ip(spoofed_a, untrusted) == "10.0.0.1"

    # Both spoofed requests land in the same rate-limit bucket.
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60.0)
    limiter.record_failure(_client_ip(spoofed_a, cfg))
    limiter.record_failure(_client_ip(spoofed_b, cfg))
    assert limiter.is_limited(_client_ip(spoofed_a, cfg)) > 0.0


def test_successful_logins_are_not_rate_limited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import api.auth as auth_api

    auth_api._login_limiter._attempts.clear()
    client, main_module = _make_client(tmp_path, monkeypatch, AUTH_CONFIG)
    with client:
        main_module.app_state["session_manager"] = _FakeSessionManager(succeed=True)
        # Well above max_attempts — successes never count toward the limit.
        for _ in range(7):
            resp = client.post(
                "/api/auth/login", json={"username": "u", "password": "p"}
            )
            assert resp.status_code == 200


def test_failed_login_counter_resets_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import api.auth as auth_api

    auth_api._login_limiter._attempts.clear()
    client, main_module = _make_client(tmp_path, monkeypatch, AUTH_CONFIG)
    with client:
        mgr = _FakeSessionManager(succeed=False)
        main_module.app_state["session_manager"] = mgr

        for _ in range(4):
            resp = client.post(
                "/api/auth/login", json={"username": "u", "password": "p"}
            )
            assert resp.status_code == 401

        # A success clears the accumulated failures.
        mgr._succeed = True
        resp = client.post("/api/auth/login", json={"username": "u", "password": "p"})
        assert resp.status_code == 200

        # The next failures start a fresh window: 5 more before the 429.
        mgr._succeed = False
        for _ in range(5):
            resp = client.post(
                "/api/auth/login", json={"username": "u", "password": "p"}
            )
            assert resp.status_code == 401

        resp = client.post("/api/auth/login", json={"username": "u", "password": "p"})
        assert resp.status_code == 429


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
