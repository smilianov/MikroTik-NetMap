from __future__ import annotations

import asyncio

from models import DeviceConfig, DeviceType, LinkConfig, Position
from monitors.topology_discovery import TopologyDiscovery
from topology_evidence import (
    TopologyEvidenceStore,
    build_bridge_host_observations,
    build_romon_edges,
    build_romon_observations,
    build_topology_dry_run_report,
    parse_romon_discover,
)


def test_parse_romon_discover_multiline_path() -> None:
    output = """
Flags: A - ACTIVE
Columns: ADDRESS, COST, HOPS, PATH, L2MTU, IDENTITY, VERSION
  ADDRESS            COST  H  PATH               L2MTU  IDENTITY         VERSION
A 04:F4:1C:20:3F:E7   800  4  74:4D:28:01:6D:04   1500  CCR2004-16G-2S+  7.22.3
                              B8:69:F4:D6:4D:1F
                              DC:2C:6E:1B:CB:61
                              04:F4:1C:20:3F:E7
A 48:A9:8A:A9:DA:F3   800  4  74:4D:28:01:6D:04   1500  hAP_ax^2_Thai    7.22.3
                              B8:69:F4:D6:4D:1F
                              DC:2C:6E:1B:CB:61
                              48:A9:8A:A9:DA:F3
"""

    records = parse_romon_discover(output)

    assert len(records) == 2
    assert records[0].identity == "CCR2004-16G-2S+"
    assert records[0].path == [
        "74:4D:28:01:6D:04",
        "B8:69:F4:D6:4D:1F",
        "DC:2C:6E:1B:CB:61",
        "04:F4:1C:20:3F:E7",
    ]
    assert records[1].identity == "hAP_ax^2_Thai"


def test_build_romon_evidence_deduplicates_shared_path() -> None:
    records = parse_romon_discover(
        """
A 04:F4:1C:20:3F:E7   800  4  74:4D:28:01:6D:04   1500  CCR2004-16G-2S+  7.22.3
                              B8:69:F4:D6:4D:1F
                              DC:2C:6E:1B:CB:61
                              04:F4:1C:20:3F:E7
A 04:F4:1C:BD:3C:99   800  4  74:4D:28:01:6D:04   1500  CRS326-Optical   7.22.3
                              B8:69:F4:D6:4D:1F
                              DC:2C:6E:1B:CB:61
                              04:F4:1C:BD:3C:99
"""
    )

    edges = build_romon_edges("04:F4:1C:C4:D7:2F", records)
    observations = build_romon_observations(
        "04:F4:1C:C4:D7:2F",
        records,
        {
            "04:F4:1C:C4:D7:2F": "LS",
            "74:4D:28:01:6D:04": "CRS317-1G-16S",
        },
    )

    assert edges == [
        {"source": "04:F4:1C:C4:D7:2F", "target": "74:4D:28:01:6D:04", "evidence": "romon_path"},
        {"source": "74:4D:28:01:6D:04", "target": "B8:69:F4:D6:4D:1F", "evidence": "romon_path"},
        {"source": "B8:69:F4:D6:4D:1F", "target": "DC:2C:6E:1B:CB:61", "evidence": "romon_path"},
        {"source": "DC:2C:6E:1B:CB:61", "target": "04:F4:1C:20:3F:E7", "evidence": "romon_path"},
        {"source": "DC:2C:6E:1B:CB:61", "target": "04:F4:1C:BD:3C:99", "evidence": "romon_path"},
    ]
    assert len(observations) == 5
    assert observations[0].source == "romon"
    assert observations[0].evidence_type == "romon_path"
    assert observations[0].source_identity == "LS"
    assert observations[0].target_identity == "CRS317-1G-16S"
    assert observations[0].confidence < 0.5
    assert observations[0].metadata["destination_romon_ids"] == [
        "04:F4:1C:20:3F:E7",
        "04:F4:1C:BD:3C:99",
    ]


def test_topology_discovery_ingests_romon_as_evidence_only(tmp_path, monkeypatch) -> None:
    from monitors import topology_discovery as td

    monkeypatch.setattr(td, "PERSISTENCE_FILE", tmp_path / "discovered_topology.json")

    store = TopologyEvidenceStore()
    discovery = TopologyDiscovery(
        devices=[
            DeviceConfig(
                name="LS",
                host="10.0.0.1",
                type=DeviceType.ROUTER,
                position=Position(),
            )
        ],
        evidence_store=store,
    )
    records = parse_romon_discover(
        """
A 74:4D:28:01:6D:04   200  1  74:4D:28:01:6D:04   1500  CRS317-1G-16S  7.22.3
"""
    )

    observations = discovery.ingest_romon_records(
        "04:F4:1C:C4:D7:2F",
        records,
        {"04:F4:1C:C4:D7:2F": "LS"},
    )

    assert len(observations) == 1
    assert store.count("romon") == 1
    assert discovery.get_evidence_observations("romon")[0].target_identity == "CRS317-1G-16S"
    assert discovery.discovered_links == {}


def test_bridge_host_observations_skip_local_and_deduplicate() -> None:
    observations = build_bridge_host_observations(
        "CRS326-Gun-YB",
        [
            {
                "mac-address": "aa:bb:cc:dd:ee:ff",
                "interface": "ether22",
                "bridge": "bridge",
                "vid": "88",
                "dynamic": "true",
            },
            {
                "mac-address": "AA:BB:CC:DD:EE:FF",
                "interface": "ether22",
                "bridge": "bridge",
                "vid": "88",
            },
            {
                "mac-address": "11:22:33:44:55:66",
                "interface": "bridge",
                "local": "true",
            },
        ],
    )

    assert len(observations) == 1
    assert observations[0].source == "bridge_host"
    assert observations[0].evidence_type == "mac_seen_on_port"
    assert observations[0].source_node == "CRS326-Gun-YB"
    assert observations[0].target_node == "AA:BB:CC:DD:EE:FF"
    assert observations[0].metadata["interface"] == "ether22"
    assert observations[0].metadata["vlan_id"] == "88"
    assert observations[0].confidence < 0.5


def test_topology_discovery_collects_bridge_host_evidence_without_links(tmp_path, monkeypatch) -> None:
    from monitors import topology_discovery as td

    monkeypatch.setattr(td, "PERSISTENCE_FILE", tmp_path / "discovered_topology.json")

    store = TopologyEvidenceStore()
    switch = DeviceConfig(
        name="CRS326-Gun-YB",
        host="10.0.88.26",
        type=DeviceType.SWITCH,
        position=Position(),
    )
    discovery = TopologyDiscovery(
        devices=[switch],
        api_defaults={"username": "prometheus", "password": "test", "api_type": "classic"},
        evidence_store=store,
    )

    async def _fake_query(device: DeviceConfig) -> dict:
        return {
            "device_name": device.name,
            "neighbors": [],
            "interfaces": [],
            "bridge_hosts": [{
                "mac-address": "AA:BB:CC:DD:EE:FF",
                "interface": "ether22",
                "bridge": "bridge",
                "dynamic": "true",
            }],
        }

    discovery._query_device = _fake_query

    changes = asyncio.run(discovery._sweep())

    assert changes["added_links"] == []
    assert discovery.discovered_links == {}
    assert store.count("bridge_host") == 1
    assert store.list_observations("bridge_host")[0].metadata["interface"] == "ether22"


def test_topology_dry_run_reports_missing_evidence_pairs() -> None:
    devices = [
        DeviceConfig(name="LS", host="10.0.0.1", type=DeviceType.ROUTER),
        DeviceConfig(name="CRS317-1G-16S", host="10.0.88.17", type=DeviceType.SWITCH),
        DeviceConfig(name="CRS326-Gun-YB", host="10.0.88.26", type=DeviceType.SWITCH),
    ]
    links = [
        LinkConfig(**{"from": "LS:sfp-sfpplus1", "to": "CRS317-1G-16S:sfp-sfpplus1"})
    ]
    observations = build_romon_observations(
        "04:F4:1C:C4:D7:2F",
        [{
            "address": "B8:69:F4:D6:4D:1F",
            "cost": 400,
            "hops": 2,
            "path": ["74:4D:28:01:6D:04", "B8:69:F4:D6:4D:1F"],
            "identity": "CRS326-Gun-YB",
        }],
        {
            "04:F4:1C:C4:D7:2F": "LS",
            "74:4D:28:01:6D:04": "CRS317-1G-16S",
            "B8:69:F4:D6:4D:1F": "CRS326-Gun-YB",
        },
    )

    report = build_topology_dry_run_report(devices, links, observations)

    assert report["covered_pair_count"] == 1
    assert report["candidate_count"] == 1
    assert report["candidates"][0]["source_device"] == "CRS317-1G-16S"
    assert report["candidates"][0]["target_device"] == "CRS326-Gun-YB"
    assert report["candidates"][0]["status"] == "candidate"
