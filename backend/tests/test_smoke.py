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
        id="AP1:ether1-SW1:ether3",
        from_device="SW1:ether3",
        to_device="AP1:ether1",
        first_seen=now,
        last_seen=now,
        confirmed=True,
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


def test_neighbor_interface_normalization():
    from monitors.topology_discovery import (
        _is_physical_neighbor_interface,
        _neighbor_interface,
    )

    assert _neighbor_interface("ether5,bridge-LAN") == "ether5"
    assert _neighbor_interface("bridge-lan/ether22") == "ether22"
    assert _neighbor_interface("Ethernet1/1") == "Ethernet1/1"
    assert _is_physical_neighbor_interface("ether22") is True
    assert _is_physical_neighbor_interface("sfp-sfpplus1") is True
    assert _is_physical_neighbor_interface("vlan88-mgmt") is False
    assert _is_physical_neighbor_interface("bridge-lan") is False


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
        id="LS:sfp-sfpplus1-SW1:ether1",
        from_device="LS:sfp-sfpplus1-uplink",
        to_device="SW1:ether1",
        first_seen=now,
        last_seen=now,
        confirmed=True,
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
        "to": "SW1:ether1",
        "speed": 1000,
        "type": "wired",
        "discovered": True,
        "confirmed": True,
        "map": "discovery",
    }]


def test_topology_discovery_creates_only_bidirectional_neighbor_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from models import DeviceConfig, DeviceType, Position
    from monitors import topology_discovery as td

    monkeypatch.setattr(td, "PERSISTENCE_FILE", tmp_path / "discovered_topology.json")

    ax2 = DeviceConfig(
        name="AX2",
        host="10.0.0.57",
        type=DeviceType.ROUTER,
        position=Position(),
    )
    crs326 = DeviceConfig(
        name="CRS326-Gun-YB",
        host="10.0.88.26",
        type=DeviceType.SWITCH,
        position=Position(),
    )
    discovery = td.TopologyDiscovery(
        devices=[ax2, crs326],
        auto_add_devices=False,
        auto_add_links=True,
        api_defaults={"username": "prometheus", "password": "test", "api_type": "classic"},
    )

    async def _fake_query(device: DeviceConfig) -> dict:
        if device.name == "AX2":
            return {
                "device_name": "AX2",
                "neighbors": [{
                    "local_device": "AX2",
                    "local_interface": "ether5",
                    "remote_interface_hint": "ether22",
                    "remote_identity": "CRS326-Gun-YB",
                    "remote_address": "10.0.88.26",
                    "remote_mac": "",
                    "remote_platform": "MikroTik",
                    "remote_board": "CRS326-24G-2S+",
                }],
                "interfaces": [{"name": "ether5", "speed": "1Gbps"}],
            }
        return {
            "device_name": "CRS326-Gun-YB",
            "neighbors": [
                {
                    "local_device": "CRS326-Gun-YB",
                    "local_interface": "ether22",
                    "remote_interface_hint": "ether5",
                    "remote_identity": "AX2",
                    "remote_address": "10.0.0.57",
                    "remote_mac": "",
                    "remote_platform": "MikroTik",
                    "remote_board": "hAP ax^2",
                },
                {
                    "local_device": "CRS326-Gun-YB",
                    "local_interface": "ether10",
                    "remote_interface_hint": "eth0",
                    "remote_identity": "UAP-HD",
                    "remote_address": "10.0.0.160",
                    "remote_mac": "",
                    "remote_platform": "Ubiquiti",
                    "remote_board": "",
                },
            ],
            "interfaces": [
                {"name": "ether22", "speed": "1Gbps"},
                {"name": "ether10", "speed": "1Gbps"},
            ],
        }

    discovery._query_device = _fake_query

    changes = asyncio.run(discovery._sweep())

    assert len(changes["added_links"]) == 1
    link = changes["added_links"][0]
    assert link.from_device == "AX2:ether5"
    assert link.to_device == "CRS326-Gun-YB:ether22"
    assert link.confirmed is True
    assert link.speed == 1000
    assert "UAP-HD" not in str(discovery.discovered_links)


def test_topology_discovery_uses_one_way_port_hints_for_known_devices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from models import DeviceConfig, DeviceType, Position
    from monitors import topology_discovery as td

    monkeypatch.setattr(td, "PERSISTENCE_FILE", tmp_path / "discovered_topology.json")

    ls = DeviceConfig(
        name="LS",
        host="10.0.0.1",
        type=DeviceType.ROUTER,
        position=Position(),
    )
    crs317 = DeviceConfig(
        name="CRS317-1G-16S",
        host="10.0.88.17",
        type=DeviceType.SWITCH,
        position=Position(),
    )
    discovery = td.TopologyDiscovery(
        devices=[ls, crs317],
        auto_add_devices=False,
        auto_add_links=True,
        api_defaults={"username": "prometheus", "password": "test", "api_type": "classic"},
    )

    async def _fake_query(device: DeviceConfig) -> dict:
        if device.name == "LS":
            return {
                "device_name": "LS",
                "neighbors": [{
                    "local_device": "LS",
                    "local_interface": "sfp-sfpplus1-to-CRS317",
                    "remote_interface_hint": "sfp-sfpplus1-trunk-uplink",
                    "remote_identity": "CRS317-1G-16S",
                    "remote_address": "10.0.88.17",
                    "remote_mac": "",
                    "remote_platform": "MikroTik",
                    "remote_board": "CRS317-1G-16S+",
                }],
                "interfaces": [{"name": "sfp-sfpplus1-to-CRS317", "type": "sfp-sfpplus"}],
            }
        return {"device_name": device.name, "neighbors": [], "interfaces": []}

    discovery._query_device = _fake_query

    changes = asyncio.run(discovery._sweep())

    assert len(changes["added_links"]) == 1
    link = changes["added_links"][0]
    assert link.from_device == "LS:sfp-sfpplus1-to-CRS317"
    assert link.to_device == "CRS317-1G-16S:sfp-sfpplus1-trunk-uplink"
    assert link.confirmed is False
    assert link.speed == 10000


def test_topology_discovery_does_not_add_one_way_hints_on_confirmed_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from models import DeviceConfig, DeviceType, Position
    from monitors import topology_discovery as td

    monkeypatch.setattr(td, "PERSISTENCE_FILE", tmp_path / "discovered_topology.json")

    ax2 = DeviceConfig(name="AX2", host="10.0.0.57", type=DeviceType.ROUTER, position=Position())
    crs326 = DeviceConfig(name="CRS326-Gun-YB", host="10.0.88.26", type=DeviceType.SWITCH, position=Position())
    crs317 = DeviceConfig(name="CRS317-1G-16S", host="10.0.88.17", type=DeviceType.SWITCH, position=Position())
    discovery = td.TopologyDiscovery(
        devices=[ax2, crs326, crs317],
        auto_add_devices=False,
        auto_add_links=True,
        api_defaults={"username": "prometheus", "password": "test", "api_type": "classic"},
    )

    async def _fake_query(device: DeviceConfig) -> dict:
        if device.name == "AX2":
            return {
                "device_name": "AX2",
                "neighbors": [
                    {
                        "local_device": "AX2",
                        "local_interface": "ether5",
                        "remote_interface_hint": "ether22",
                        "remote_identity": "CRS326-Gun-YB",
                        "remote_address": "10.0.88.26",
                        "remote_mac": "",
                        "remote_platform": "MikroTik",
                        "remote_board": "CRS326-24G-2S+",
                    },
                    {
                        "local_device": "AX2",
                        "local_interface": "ether5",
                        "remote_interface_hint": "sfp-sfpplus8-gun-YB",
                        "remote_identity": "CRS317-1G-16S",
                        "remote_address": "10.0.88.17",
                        "remote_mac": "",
                        "remote_platform": "MikroTik",
                        "remote_board": "CRS317-1G-16S+",
                    },
                ],
                "interfaces": [{"name": "ether5", "speed": "1Gbps"}],
            }
        if device.name == "CRS326-Gun-YB":
            return {
                "device_name": "CRS326-Gun-YB",
                "neighbors": [{
                    "local_device": "CRS326-Gun-YB",
                    "local_interface": "ether22",
                    "remote_interface_hint": "ether5",
                    "remote_identity": "AX2",
                    "remote_address": "10.0.0.57",
                    "remote_mac": "",
                    "remote_platform": "MikroTik",
                    "remote_board": "hAP ax^2",
                }],
                "interfaces": [{"name": "ether22", "speed": "1Gbps"}],
            }
        return {"device_name": device.name, "neighbors": [], "interfaces": []}

    discovery._query_device = _fake_query

    changes = asyncio.run(discovery._sweep())

    assert len(changes["added_links"]) == 1
    assert changes["added_links"][0].from_device == "AX2:ether5"
    assert changes["added_links"][0].to_device == "CRS326-Gun-YB:ether22"
    assert "CRS317-1G-16S" not in str(discovery.discovered_links)


def test_topology_discovery_ignores_ambiguous_one_way_switch_hints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from models import DeviceConfig, DeviceType, Position
    from monitors import topology_discovery as td

    monkeypatch.setattr(td, "PERSISTENCE_FILE", tmp_path / "discovered_topology.json")

    ls = DeviceConfig(name="LS", host="10.0.0.1", type=DeviceType.ROUTER, position=Position())
    crs226 = DeviceConfig(name="CRS226-02", host="10.0.88.227", type=DeviceType.SWITCH, position=Position())
    crs317 = DeviceConfig(name="CRS317-1G-16S", host="10.0.88.17", type=DeviceType.SWITCH, position=Position())
    discovery = td.TopologyDiscovery(
        devices=[ls, crs226, crs317],
        auto_add_devices=False,
        auto_add_links=True,
        api_defaults={"username": "prometheus", "password": "test", "api_type": "classic"},
    )

    async def _fake_query(device: DeviceConfig) -> dict:
        if device.name == "LS":
            return {
                "device_name": "LS",
                "neighbors": [
                    {
                        "local_device": "LS",
                        "local_interface": "sfp-sfpplus1",
                        "remote_interface_hint": "sfp-sfpplus1-uplink",
                        "remote_identity": "CRS226-02",
                        "remote_address": "10.0.88.227",
                        "remote_mac": "",
                        "remote_platform": "MikroTik",
                        "remote_board": "CRS226-24G-2S+",
                    },
                    {
                        "local_device": "LS",
                        "local_interface": "sfp-sfpplus1",
                        "remote_interface_hint": "sfp-sfpplus1-trunk-uplink",
                        "remote_identity": "CRS317-1G-16S",
                        "remote_address": "10.0.88.17",
                        "remote_mac": "",
                        "remote_platform": "MikroTik",
                        "remote_board": "CRS317-1G-16S+",
                    },
                ],
                "interfaces": [{"name": "sfp-sfpplus1", "type": "sfp-sfpplus"}],
            }
        return {"device_name": device.name, "neighbors": [], "interfaces": []}

    discovery._query_device = _fake_query

    changes = asyncio.run(discovery._sweep())

    assert changes["added_links"] == []
    assert discovery.discovered_links == {}


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
