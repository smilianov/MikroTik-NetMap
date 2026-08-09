from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config import NetMapConfig
from mikrotik.client import MikroTikClassicClient, create_client
from mikrotik.tls import PinnedTlsContext, TlsFingerprintMismatch
from models import DeviceConfig
from monitors import topology_discovery, traffic_monitor


def test_classic_client_pins_the_authenticated_pool_socket(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Pool:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.socket_timeout = 0

        def get_api(self) -> object:
            return object()

    monkeypatch.setitem(
        sys.modules, "routeros_api", SimpleNamespace(RouterOsApiPool=Pool)
    )
    client = MikroTikClassicClient(
        "10.0.0.1",
        port=8729,
        use_ssl=True,
        tls_fingerprint_sha256="aa" * 32,
    )

    client._connect_sync()

    assert captured["use_ssl"] is True
    assert isinstance(captured["ssl_context"], PinnedTlsContext)


def test_pinned_tls_rejects_mismatch_and_closes_socket() -> None:
    socket = MagicMock()
    socket.getpeercert.return_value = b"wrong"
    context = MagicMock()
    context.wrap_socket.return_value = socket

    with pytest.raises(TlsFingerprintMismatch):
        PinnedTlsContext("aa" * 32, ssl_context=context).wrap_socket(object())

    socket.close.assert_called_once()


def test_pinned_tls_returns_the_exact_verified_socket() -> None:
    certificate = b"expected"
    socket = MagicMock()
    socket.getpeercert.return_value = certificate
    context = MagicMock()
    context.wrap_socket.return_value = socket

    result = PinnedTlsContext(
        hashlib.sha256(certificate).hexdigest(), ssl_context=context
    ).wrap_socket(object())

    assert result is socket


def test_factory_propagates_classic_tls_binding() -> None:
    client = create_client(
        "10.0.0.1",
        api_type="classic",
        port=8729,
        use_ssl=True,
        tls_fingerprint_sha256="aa" * 32,
    )

    assert isinstance(client, MikroTikClassicClient)
    assert client.use_ssl is True
    assert client.tls_fingerprint_sha256 == "aa" * 32


def test_config_propagates_pinned_tls_defaults_to_devices(tmp_path: Path) -> None:
    config = tmp_path / "netmap.yaml"
    config.write_text(
        "server: {host: 127.0.0.1}\n"
        "api_defaults:\n"
        "  username: prometheus\n"
        "  password: secret\n"
        "  api_type: classic\n"
        "  port: 8729\n"
        "  use_ssl: true\n"
        f"  tls_fingerprint_sha256: {'aa' * 32}\n"
        "devices:\n- {name: r1, host: 10.0.0.1}\n",
        encoding="utf-8",
    )

    parsed = NetMapConfig(config)

    assert parsed.devices[0].port == 8729
    assert parsed.devices[0].use_ssl is True
    assert parsed.devices[0].tls_fingerprint_sha256 == "aa" * 32


def test_config_rejects_unpinned_classic_tls_device(tmp_path: Path) -> None:
    config = tmp_path / "netmap.yaml"
    config.write_text(
        "server: {host: 127.0.0.1}\n"
        "devices:\n- name: r1\n  host: 10.0.0.1\n"
        "  api_type: classic\n  port: 8729\n  use_ssl: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="tls_fingerprint_sha256"):
        NetMapConfig(config)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module,build,query",
    [
        (
            traffic_monitor,
            lambda device: traffic_monitor.TrafficMonitor([device]),
            lambda monitor, device: monitor._query_device(device),
        ),
        (
            topology_discovery,
            lambda device: topology_discovery.TopologyDiscovery([device]),
            lambda monitor, device: monitor._query_device(device),
        ),
    ],
)
async def test_monitors_propagate_device_tls_pin(
    monkeypatch, module, build, query
) -> None:
    captured: dict[str, object] = {}

    class Client:
        async def get_interfaces(self):
            return []

        async def get_neighbors(self):
            return []

        async def get_ethernet_interfaces(self):
            return []

        async def get_bridge_hosts(self):
            return []

        async def close(self):
            return None

    def factory(**kwargs):
        captured.update(kwargs)
        return Client()

    monkeypatch.setattr(module, "create_client", factory)
    device = DeviceConfig(
        name="r1",
        host="10.0.0.1",
        username="prometheus",
        password="secret",
        api_type="classic",
        port=8729,
        use_ssl=True,
        tls_fingerprint_sha256="aa" * 32,
    )

    await query(build(device), device)

    assert captured["use_ssl"] is True
    assert captured["tls_fingerprint_sha256"] == "aa" * 32
