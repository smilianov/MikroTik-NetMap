"""Backend smoke tests for health endpoint, config loading, and websocket payload shape."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import NetMapConfig


@pytest.fixture
def sample_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "netmap.test.yaml"
    cfg.write_text(
        """
server:
  host: 127.0.0.1
  port: 8585
  cors_origins: ["*"]

ping:
  interval: 2
  timeout: 1

api_defaults:
  username: prometheus
  api_type: classic
  port: 8728

devices: []
maps:
  - name: main
    label: Network Overview
links: []

discovery:
  enabled: false

traffic:
  enabled: false

auth:
  enabled: false
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def client(sample_config: Path, monkeypatch: pytest.MonkeyPatch):
    # main.py resolves NETMAP_CONFIG at import-time, so set env first and reload.
    monkeypatch.setenv("NETMAP_CONFIG", str(sample_config))

    import main as main_module

    importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client


def test_config_loader_parses_minimal_file(sample_config: Path):
    cfg = NetMapConfig(sample_config)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8585
    assert cfg.discovery_enabled is False
    assert cfg.traffic_enabled is False
    assert len(cfg.devices) == 0


def test_health_endpoint_smoke(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert "devices" in payload
    assert "ping_running" in payload
    assert "auth_enabled" in payload


def test_websocket_initial_ping_state_shape(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()

    assert first["type"] == "ping_state"
    assert "timestamp" in first
    assert isinstance(first["devices"], list)
