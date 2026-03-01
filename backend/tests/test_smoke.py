"""Backend smoke tests for health endpoint, config loading, and websocket payload shape."""

from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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


def test_build_all_devices_list_includes_parent_fields(sample_config: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NETMAP_CONFIG", str(sample_config))

    import main as main_module
    from models import DeviceConfig, DeviceType, DiscoveredDevice, Position

    importlib.reload(main_module)

    now = datetime.now(timezone.utc)
    root = DeviceConfig(
        name="r1",
        host="10.0.0.1",
        type=DeviceType.ROUTER,
        profile="core",
        map="main",
        position=Position(x=10, y=20),
    )
    child = DeviceConfig(
        name="ap-1",
        host="10.0.0.2",
        type=DeviceType.AP,
        profile="edge",
        map="main",
        position=Position(x=30, y=40),
    )
    discovered = DiscoveredDevice(
        name="ap-1",
        host="10.0.0.2",
        discovered_by="r1",
        discovered_on="ether2",
        first_seen=now,
        last_seen=now,
        position=Position(x=30, y=40),
    )

    main_module.app_state["config"] = SimpleNamespace(devices=[root, child])
    main_module.app_state["topology_discovery"] = SimpleNamespace(discovered_devices={"ap-1": discovered})
    main_module.app_state["custom_positions"] = {}
    main_module.app_state["device_maps"] = {}
    main_module.app_state["pinned_devices"] = []
    main_module.app_state["visibility_manager"] = None

    devices = main_module._build_all_devices_list()
    by_id = {d["id"]: d for d in devices}

    assert by_id["r1"]["parent"] is None
    assert by_id["ap-1"]["parent"] == "r1"
    assert by_id["ap-1"]["discovered"] is True


def test_topology_update_emits_updated_devices(sample_config: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NETMAP_CONFIG", str(sample_config))

    import main as main_module
    from models import DiscoveredDevice, Position

    importlib.reload(main_module)

    now = datetime.now(timezone.utc)
    added = DiscoveredDevice(
        name="ap-2",
        host="10.0.0.3",
        discovered_by="r1",
        discovered_on="ether3",
        board="hAP ax2",
        platform="MikroTik",
        first_seen=now,
        last_seen=now,
        position=Position(x=100, y=200),
    )
    updated = DiscoveredDevice(
        name="ap-1",
        host="10.0.0.2",
        discovered_by="sw1",
        discovered_on="ether4",
        board="cAP",
        platform="MikroTik",
        first_seen=now,
        last_seen=now,
        position=Position(x=300, y=400),
    )

    sent_messages: list[dict] = []

    async def _capture(msg: dict) -> None:
        sent_messages.append(msg)

    main_module.ws_manager.broadcast = _capture
    main_module.app_state["config"] = SimpleNamespace(api_defaults={})
    main_module.app_state["ping_monitor"] = None
    main_module.app_state["traffic_monitor"] = None
    main_module.app_state["device_maps"] = {}

    asyncio.run(main_module._on_topology_update({
        "added_devices": [added],
        "updated_devices": [updated],
        "added_links": [],
        "removed_links": [],
    }))

    assert len(sent_messages) == 1
    payload = sent_messages[0]
    assert payload["type"] == "topology_update"
    assert payload["added_devices"][0]["parent"] == "r1"
    assert payload["updated_devices"][0]["id"] == "ap-1"
    assert payload["updated_devices"][0]["parent"] == "sw1"
