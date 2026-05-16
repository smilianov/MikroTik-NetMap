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
    assert cfg.discovery_map == "discovery"
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


def test_reload_config_endpoint_reloads_yaml(client: TestClient, sample_config: Path):
    sample_config.write_text(
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

devices:
  - name: LS
    host: 127.0.0.1
    type: router
    position:
      x: 0
      y: 0
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

    response = client.post("/api/config/reload")
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    assert payload["devices"] == 1
    assert payload["links"] == 0

    devices = client.get("/api/devices").json()
    assert [d["id"] for d in devices] == ["LS"]


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


def test_build_all_devices_list_infers_configured_link_parents(sample_config: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NETMAP_CONFIG", str(sample_config))

    import main as main_module
    from models import DeviceConfig, DeviceType, LinkConfig, Position

    importlib.reload(main_module)

    root = DeviceConfig(
        name="LS",
        host="10.0.0.1",
        type=DeviceType.ROUTER,
        position=Position(x=0, y=0),
    )
    crs317 = DeviceConfig(
        name="CRS317-1G-16S",
        host="10.0.88.17",
        type=DeviceType.SWITCH,
        position=Position(x=0, y=100),
    )
    crs326 = DeviceConfig(
        name="CRS326-Gun-YB",
        host="10.0.88.26",
        type=DeviceType.SWITCH,
        position=Position(x=0, y=200),
    )
    crs312 = DeviceConfig(
        name="CRS312-4C+8XG",
        host="10.0.88.13",
        type=DeviceType.SWITCH,
        position=Position(x=0, y=300),
    )
    hap = DeviceConfig(
        name="hAP_ax^2_Thai",
        host="10.0.0.39",
        type=DeviceType.ROUTER,
        position=Position(x=0, y=400),
    )

    links = [
        LinkConfig(**{"from": "LS:sfp-sfpplus1", "to": "CRS317-1G-16S:auto"}),
        LinkConfig(**{"from": "CRS317-1G-16S:sfp-sfpplus8", "to": "CRS326-Gun-YB:sfp-sfpplus1"}),
        LinkConfig(**{"from": "CRS326-Gun-YB:ether22", "to": "CRS312-4C+8XG:combo2"}),
        LinkConfig(**{"from": "CRS312-4C+8XG:ether4", "to": "hAP_ax^2_Thai:ether2-3BB"}),
    ]

    main_module.app_state["config"] = SimpleNamespace(
        devices=[root, crs317, crs326, crs312, hap],
        links=links,
    )
    main_module.app_state["topology_discovery"] = None
    main_module.app_state["custom_positions"] = {}
    main_module.app_state["device_maps"] = {}
    main_module.app_state["pinned_devices"] = []
    main_module.app_state["visibility_manager"] = None

    devices = main_module._build_all_devices_list()
    by_id = {d["id"]: d for d in devices}

    assert by_id["LS"]["parent"] is None
    assert by_id["CRS317-1G-16S"]["parent"] == "LS"
    assert by_id["CRS326-Gun-YB"]["parent"] == "CRS317-1G-16S"
    assert by_id["CRS312-4C+8XG"]["parent"] == "CRS326-Gun-YB"
    assert by_id["hAP_ax^2_Thai"]["parent"] == "CRS312-4C+8XG"


def test_discovery_map_keeps_auto_layer_separate(sample_config: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NETMAP_CONFIG", str(sample_config))

    import main as main_module
    from models import DeviceConfig, DeviceType, DiscoveredDevice, DiscoveredLink, LinkConfig, Position

    importlib.reload(main_module)

    now = datetime.now(timezone.utc)
    root = DeviceConfig(
        name="LS",
        host="10.0.0.1",
        type=DeviceType.ROUTER,
        map="main",
        position=Position(x=0, y=0),
    )
    child = DeviceConfig(
        name="SW1",
        host="10.0.0.2",
        type=DeviceType.SWITCH,
        map="main",
        position=Position(x=0, y=100),
    )
    discovered = DiscoveredDevice(
        name="AP1",
        host="10.0.0.3",
        discovered_by="SW1",
        discovered_on="ether3",
        first_seen=now,
        last_seen=now,
        position=Position(x=0, y=200),
    )
    discovered_link = DiscoveredLink(
        id="SW1:ether3-AP1:auto",
        from_device="SW1:ether3",
        to_device="AP1:auto",
        first_seen=now,
        last_seen=now,
    )

    main_module.app_state["config"] = SimpleNamespace(
        devices=[root, child],
        maps=[SimpleNamespace(name="main", label="Manual", parent=None, background=None)],
        links=[LinkConfig(**{"from": "LS:ether1", "to": "SW1:ether1"})],
        discovery_enabled=True,
        discovery_map="auto",
        discovery_map_label="Auto Discovery",
    )
    main_module.app_state["topology_discovery"] = SimpleNamespace(
        discovered_devices={"AP1": discovered},
        discovered_links={discovered_link.id: discovered_link},
    )
    main_module.app_state["custom_positions"] = {}
    main_module.app_state["device_maps"] = {}
    main_module.app_state["pinned_devices"] = []
    main_module.app_state["visibility_manager"] = None
    main_module.app_state["manual_link_manager"] = None
    main_module.app_state["custom_maps"] = []
    main_module.app_state["map_labels"] = {}

    maps = main_module._get_maps_list()
    devices = main_module._build_all_devices_list()
    links = main_module._build_all_links_list()

    assert [m["name"] for m in maps] == ["main", "auto"]
    assert {d["id"]: d["map"] for d in devices}["AP1"] == "auto"
    assert links[0]["map"] == "main"
    assert links[1]["map"] == "auto"


def test_build_all_links_list_includes_manual_link_id(sample_config: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NETMAP_CONFIG", str(sample_config))

    import main as main_module
    from models import DeviceConfig, DeviceType, Position

    importlib.reload(main_module)

    root = DeviceConfig(name="CRS326-Gun-YB", host="10.0.88.26", type=DeviceType.SWITCH, position=Position())
    hap = DeviceConfig(name="hAP_ax^2_Thai", host="10.0.0.57", type=DeviceType.ROUTER, position=Position())
    manual = {
        "id": "CRS326-Gun-YB:port-hAP_ax^2_Thai:port",
        "from": "hAP_ax^2_Thai:port",
        "to": "CRS326-Gun-YB:port",
        "speed": 1000,
        "type": "wired",
        "map": "main",
    }

    main_module.app_state["config"] = SimpleNamespace(devices=[root, hap], links=[])
    main_module.app_state["topology_discovery"] = None
    main_module.app_state["device_maps"] = {}
    main_module.app_state["manual_link_manager"] = SimpleNamespace(get_all=lambda: [manual])

    links = main_module._build_all_links_list()

    assert links == [{
        "id": manual["id"],
        "from": manual["from"],
        "to": manual["to"],
        "speed": 1000,
        "type": "wired",
        "manual": True,
        "map": "main",
    }]


def test_discovery_map_filters_virtual_neighbor_mesh(sample_config: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NETMAP_CONFIG", str(sample_config))

    import main as main_module
    from models import DeviceConfig, DeviceType, DiscoveredLink, LinkConfig, Position

    importlib.reload(main_module)

    now = datetime.now(timezone.utc)
    root = DeviceConfig(name="LS", host="10.0.0.1", type=DeviceType.ROUTER, position=Position())
    sw1 = DeviceConfig(name="SW1", host="10.0.0.2", type=DeviceType.SWITCH, position=Position())
    sw2 = DeviceConfig(name="SW2", host="10.0.0.3", type=DeviceType.SWITCH, position=Position())

    physical = DiscoveredLink(
        id="LS:sfp-sfpplus1-SW1:auto",
        from_device="LS:sfp-sfpplus1-uplink",
        to_device="SW1:auto",
        first_seen=now,
        last_seen=now,
    )
    mgmt_mesh = DiscoveredLink(
        id="SW1:vlan88-SW2:vlan88",
        from_device="SW1:vlan88-mgmt",
        to_device="SW2:vlan88-mgmt",
        first_seen=now,
        last_seen=now,
        confirmed=True,
    )
    vpn_remote = DiscoveredLink(
        id="LS:sstp-remote-Remote:auto",
        from_device="LS:<sstp-remote>",
        to_device="Remote:auto",
        first_seen=now,
        last_seen=now,
    )
    bridge_path = DiscoveredLink(
        id="SW1:bridge-sfp-SW2:auto",
        from_device="SW1:bridge1/sfp-sfpplus24",
        to_device="SW2:auto",
        first_seen=now,
        last_seen=now,
    )

    main_module.app_state["config"] = SimpleNamespace(
        devices=[root, sw1, sw2],
        maps=[SimpleNamespace(name="main", label="Manual", parent=None, background=None)],
        links=[LinkConfig(**{"from": "LS:ether1", "to": "SW1:ether1"})],
        discovery_enabled=True,
        discovery_map="discovery",
        discovery_map_label="Auto Discovery",
    )
    main_module.app_state["topology_discovery"] = SimpleNamespace(
        discovered_devices={},
        discovered_links={
            physical.id: physical,
            mgmt_mesh.id: mgmt_mesh,
            vpn_remote.id: vpn_remote,
            bridge_path.id: bridge_path,
        },
    )
    main_module.app_state["device_maps"] = {}
    main_module.app_state["manual_link_manager"] = None

    links = main_module._build_all_links_list()
    discovered = [link for link in links if link.get("discovered")]

    assert discovered == [{
        "from": "LS:sfp-sfpplus1-uplink",
        "to": "SW1:auto",
        "speed": 1000,
        "type": "wired",
        "discovered": True,
        "confirmed": False,
        "map": "discovery",
    }]


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
    assert payload["added_devices"][0]["map"] == "discovery"
    assert payload["updated_devices"][0]["id"] == "ap-1"
    assert payload["updated_devices"][0]["parent"] == "sw1"
