"""Regression tests for device-removal bugfixes.

Covers:
- TopologyDiscovery.remove_device AttributeError (self._devices -> self.devices)
  and the full blacklist endpoint flow.
- PingMonitor keeping its own device list (no mutation of cfg.devices).
- PingMonitor sweep tolerating a device removed mid-sweep.
- ConnectionManager.broadcast sending outside the lock and pruning dead clients.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import DeviceConfig, DeviceType, DiscoveredDevice, DiscoveredLink, Position


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient against a minimal config (same shape as test_smoke's)."""
    import importlib

    from fastapi.testclient import TestClient

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
    # main.py resolves NETMAP_CONFIG at import-time, so set env first and reload.
    monkeypatch.setenv("NETMAP_CONFIG", str(cfg))

    import main as main_module

    importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client


def _make_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from monitors import topology_discovery as td

    monkeypatch.setattr(td, "PERSISTENCE_FILE", tmp_path / "discovered_topology.json")

    sw1 = DeviceConfig(
        name="sw1",
        host="10.0.0.2",
        type=DeviceType.SWITCH,
        position=Position(),
    )
    discovery = td.TopologyDiscovery(
        devices=[sw1],
        api_defaults={"username": "admin", "password": "x"},
    )

    now = datetime.now(timezone.utc)
    discovery.discovered_devices["ap1"] = DiscoveredDevice(
        name="ap1",
        host="10.0.0.3",
        discovered_by="sw1",
        discovered_on="ether2",
        first_seen=now,
        last_seen=now,
        position=Position(),
    )
    link = DiscoveredLink(
        id="ap1:ether1-sw1:ether2",
        from_device="sw1:ether2",
        to_device="ap1:ether1",
        first_seen=now,
        last_seen=now,
        confirmed=True,
    )
    discovery.discovered_links[link.id] = link
    discovery.add_queryable_device("ap1", "10.0.0.3")
    return discovery, link


def test_topology_remove_device_removes_queryable_device_and_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """remove_device must not raise AttributeError and must clean all state."""
    discovery, link = _make_discovery(tmp_path, monkeypatch)
    assert any(d.name == "ap1" for d in discovery.devices)

    removed = discovery.remove_device("ap1")

    assert removed == [link.id]
    assert "ap1" not in discovery.discovered_devices
    assert link.id not in discovery.discovered_links
    assert all(d.name != "ap1" for d in discovery.devices)


def test_blacklist_endpoint_removes_device_everywhere(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """POST /api/devices/{id}/blacklist returns 200 and removes the device
    from visibility, ping monitor, and topology discovery."""
    import main as main_module
    import visibility_manager as vm_mod
    from monitors.ping_monitor import PingMonitor
    from visibility_manager import VisibilityManager

    monkeypatch.setattr(vm_mod, "VISIBILITY_FILE", tmp_path / "device_visibility.json")

    discovery, link = _make_discovery(tmp_path, monkeypatch)

    sw1 = DeviceConfig(
        name="sw1",
        host="10.0.0.2",
        type=DeviceType.SWITCH,
        position=Position(),
    )
    cfg_devices = [sw1]
    ping = PingMonitor(devices=cfg_devices)
    ping.add_device(DeviceConfig(name="ap1", host="10.0.0.3"))

    vis = VisibilityManager()
    main_module.app_state["visibility_manager"] = vis
    main_module.app_state["ping_monitor"] = ping
    main_module.app_state["topology_discovery"] = discovery

    response = client.post("/api/devices/ap1/blacklist", json={"reason": "test"})

    assert response.status_code == 200
    assert response.json()["action"] == "blacklisted"
    assert vis.is_blacklisted("ap1")
    assert "ap1" not in ping.states
    assert all(d.name != "ap1" for d in ping.devices)
    assert "ap1" not in discovery.discovered_devices
    assert link.id not in discovery.discovered_links
    assert all(d.name != "ap1" for d in discovery.devices)
    # The config device list itself must not be mutated by any of this.
    assert [d.name for d in cfg_devices] == ["sw1"]


def test_ping_monitor_add_device_does_not_mutate_caller_list():
    """Discovered devices appended by add_device must not leak into cfg.devices."""
    from monitors.ping_monitor import PingMonitor

    sw1 = DeviceConfig(
        name="sw1",
        host="10.0.0.2",
        type=DeviceType.SWITCH,
        position=Position(),
    )
    cfg_devices = [sw1]
    ping = PingMonitor(devices=cfg_devices)

    ping.add_device(DeviceConfig(name="ap1", host="10.0.0.3"))

    assert [d.name for d in ping.devices] == ["sw1", "ap1"]
    assert [d.name for d in cfg_devices] == ["sw1"]


def test_ping_sweep_tolerates_device_removed_mid_sweep(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """A device removed while a sweep is in flight must not raise KeyError
    or produce a spurious 'Ping task exception' warning."""
    import monitors.ping_monitor as pm

    sw1 = DeviceConfig(name="sw1", host="10.0.0.2")
    ap1 = DeviceConfig(name="ap1", host="10.0.0.3")
    ping = pm.PingMonitor(devices=[sw1, ap1])

    async def fake_ping(host: str, **kwargs):
        if host == sw1.host:
            # Simulate blacklist removal racing the in-flight sweep.
            ping.remove_device("ap1")
        return SimpleNamespace(is_alive=True, avg_rtt=1.0)

    monkeypatch.setattr(pm, "async_ping", fake_ping)

    with caplog.at_level("WARNING", logger="monitors.ping_monitor"):
        updated = asyncio.run(ping._sweep())

    assert [s.device_id for s in updated] == ["sw1"]
    assert "Ping task exception" not in caplog.text


def test_broadcast_prunes_dead_clients_and_delivers_to_rest():
    from api.websocket import ConnectionManager

    class FakeWS:
        def __init__(self, fail: bool = False) -> None:
            self.fail = fail
            self.sent: list[str] = []

        async def send_text(self, text: str) -> None:
            if self.fail:
                raise RuntimeError("connection dead")
            self.sent.append(text)

    async def run() -> tuple[ConnectionManager, FakeWS]:
        mgr = ConnectionManager()
        good = FakeWS()
        mgr._connections.extend([FakeWS(fail=True), good])
        await mgr.broadcast({"type": "test"})
        return mgr, good

    mgr, good = asyncio.run(run())

    assert len(good.sent) == 1
    assert mgr.client_count == 1


def test_broadcast_does_not_hold_lock_while_sending():
    """A hung client must not stall connect/disconnect behind the lock."""
    from api.websocket import ConnectionManager

    started = asyncio.Event()
    release = asyncio.Event()

    class SlowWS:
        async def send_text(self, text: str) -> None:
            started.set()
            await release.wait()

    class NewWS:
        async def accept(self) -> None:
            pass

    async def run() -> ConnectionManager:
        mgr = ConnectionManager()
        mgr._connections.append(SlowWS())
        task = asyncio.create_task(mgr.broadcast({"type": "test"}))
        await started.wait()
        # Must complete even though broadcast is stuck awaiting send_text.
        await asyncio.wait_for(mgr.connect(NewWS()), timeout=1)
        release.set()
        await task
        return mgr

    mgr = asyncio.run(run())
    assert mgr.client_count == 2
