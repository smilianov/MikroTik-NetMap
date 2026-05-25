"""Topology evidence collection primitives.

Evidence observations are deliberately separate from rendered map links. They
can support future debug views and dry-run decisions without mutating the
production topology.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class RomonRecord(BaseModel):
    """One RouterOS `/tool romon discover` row."""

    address: str
    cost: int
    hops: int
    path: list[str]
    l2mtu: int | None = None
    identity: str = ""
    version: str = ""


class TopologyEvidenceObservation(BaseModel):
    """A read-only topology observation from a discovery source."""

    id: str
    source: str
    evidence_type: str
    source_node: str
    target_node: str
    source_identity: str | None = None
    target_identity: str | None = None
    confidence: float = 0.0
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class TopologyDryRunCandidate(BaseModel):
    """Candidate link implied by evidence but not currently configured."""

    source_device: str
    target_device: str
    confidence: float
    evidence_count: int
    evidence_sources: list[str]
    evidence_types: list[str]
    status: str
    reason: str


def strip_terminal(text: str) -> str:
    """Remove ANSI escapes and terminal control bytes from RouterOS output."""
    text = ANSI_RE.sub("", text)
    text = text.replace("\r", "\n")
    text = text.replace("\x1bZ", "")
    return text.replace("\x1b", "")


def normalize_mac(value: str) -> str:
    return str(value or "").strip().upper()


def parse_romon_discover(text: str) -> list[RomonRecord]:
    """Parse RouterOS `/tool romon discover` terminal output."""
    records: "OrderedDict[str, RomonRecord]" = OrderedDict()
    current: RomonRecord | None = None

    for raw_line in strip_terminal(text).splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith(("Flags:", "Columns:", "--", "[")):
            continue

        if line.lstrip().startswith("A "):
            parts = line.split()
            if len(parts) < 7 or not MAC_RE.fullmatch(parts[1]):
                current = None
                continue

            address = normalize_mac(parts[1])
            path_first = normalize_mac(parts[4])
            l2mtu = int(parts[5]) if parts[5].isdigit() else None
            remainder = " ".join(parts[6:]).rstrip(">")

            version_match = re.search(r"\s+(\d+(?:\.\d+)+(?:\S*)?)$", remainder)
            if version_match:
                identity = remainder[: version_match.start()].strip()
                version = version_match.group(1).rstrip(">")
            else:
                identity = remainder.strip()
                version = ""

            current = RomonRecord(
                address=address,
                cost=int(parts[2]),
                hops=int(parts[3]),
                path=[path_first],
                l2mtu=l2mtu,
                identity=identity,
                version=version,
            )
            records[address] = current
            continue

        if current:
            for mac in [normalize_mac(m) for m in MAC_RE.findall(line)]:
                if mac not in current.path:
                    current.path.append(mac)

    return list(records.values())


def _coerce_romon_records(records: list[RomonRecord | dict[str, Any]]) -> list[RomonRecord]:
    return [record if isinstance(record, RomonRecord) else RomonRecord(**record) for record in records]


def _observation_id(source: str, evidence_type: str, source_node: str, target_node: str) -> str:
    material = f"{source}|{evidence_type}|{source_node}|{target_node}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def build_romon_edges(
    root_id: str | None,
    records: list[RomonRecord | dict[str, Any]],
) -> list[dict[str, str]]:
    """Build deduplicated logical RoMON path edges from records."""
    edges: "OrderedDict[tuple[str, str], dict[str, str]]" = OrderedDict()
    for record in _coerce_romon_records(records):
        path = [normalize_mac(mac) for mac in record.path]
        if root_id:
            path = [normalize_mac(root_id), *path]
        for source, target in zip(path, path[1:]):
            edges.setdefault(
                (source, target),
                {"source": source, "target": target, "evidence": "romon_path"},
            )
    return list(edges.values())


def build_romon_observations(
    root_id: str | None,
    records: list[RomonRecord | dict[str, Any]],
    identity_by_id: dict[str, str] | None = None,
) -> list[TopologyEvidenceObservation]:
    """Convert RoMON records into read-only topology evidence observations."""
    identities = {normalize_mac(k): v for k, v in (identity_by_id or {}).items()}
    root = normalize_mac(root_id) if root_id else None
    edge_metadata: "OrderedDict[tuple[str, str], dict[str, Any]]" = OrderedDict()

    for record in _coerce_romon_records(records):
        identities.setdefault(normalize_mac(record.address), record.identity)
        path = [normalize_mac(mac) for mac in record.path]
        if root:
            path = [root, *path]

        for source, target in zip(path, path[1:]):
            data = edge_metadata.setdefault(
                (source, target),
                {
                    "destination_romon_ids": [],
                    "destination_identities": [],
                    "max_hops": 0,
                    "max_cost": 0,
                },
            )
            if record.address not in data["destination_romon_ids"]:
                data["destination_romon_ids"].append(record.address)
            if record.identity and record.identity not in data["destination_identities"]:
                data["destination_identities"].append(record.identity)
            data["max_hops"] = max(data["max_hops"], record.hops)
            data["max_cost"] = max(data["max_cost"], record.cost)

    observations: list[TopologyEvidenceObservation] = []
    for (source, target), metadata in edge_metadata.items():
        observations.append(
            TopologyEvidenceObservation(
                id=_observation_id("romon", "romon_path", source, target),
                source="romon",
                evidence_type="romon_path",
                source_node=source,
                target_node=target,
                source_identity=identities.get(source),
                target_identity=identities.get(target),
                confidence=0.35,
                metadata={
                    **metadata,
                    "root_romon_id": root,
                    "note": "RoMON path is management evidence, not physical-link proof.",
                },
            )
        )
    return observations


def _truthy_routeros(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "yes", "1"}


def build_bridge_host_observations(
    device_name: str,
    bridge_hosts: list[dict[str, Any]],
) -> list[TopologyEvidenceObservation]:
    """Convert `/interface/bridge/host` rows into MAC-on-port observations."""
    observations: list[TopologyEvidenceObservation] = []
    seen: set[tuple[str, str, str, str]] = set()

    for host in bridge_hosts:
        mac = normalize_mac(str(host.get("mac-address") or host.get("mac") or ""))
        interface = str(
            host.get("interface")
            or host.get("on-interface")
            or host.get("port")
            or ""
        ).strip()
        if not MAC_RE.fullmatch(mac) or not interface:
            continue
        if _truthy_routeros(host.get("local")):
            continue

        bridge = str(host.get("bridge") or "").strip()
        vlan_id = str(host.get("vid") or host.get("vlan-id") or "").strip()
        key = (device_name, mac, interface, vlan_id)
        if key in seen:
            continue
        seen.add(key)

        observations.append(
            TopologyEvidenceObservation(
                id=_observation_id(
                    "bridge_host",
                    "mac_seen_on_port",
                    device_name,
                    f"{mac}|{interface}|{vlan_id}",
                ),
                source="bridge_host",
                evidence_type="mac_seen_on_port",
                source_node=device_name,
                target_node=mac,
                source_identity=device_name,
                confidence=0.2,
                metadata={
                    "interface": interface,
                    "bridge": bridge,
                    "vlan_id": vlan_id,
                    "dynamic": host.get("dynamic"),
                    "age": host.get("age"),
                },
            )
        )

    return observations


def _endpoint_device(endpoint: str) -> str:
    return str(endpoint or "").split(":", 1)[0].strip()


def _device_name(device: Any) -> str:
    if isinstance(device, dict):
        return str(device.get("name") or "").strip()
    return str(getattr(device, "name", "") or "").strip()


def _link_pair(link: Any) -> frozenset[str] | None:
    if isinstance(link, dict):
        source = _endpoint_device(str(link.get("from") or link.get("from_device") or ""))
        target = _endpoint_device(str(link.get("to") or link.get("to_device") or ""))
    else:
        source = _endpoint_device(str(getattr(link, "from_device", "") or ""))
        target = _endpoint_device(str(getattr(link, "to_device", "") or ""))
    if not source or not target or source == target:
        return None
    return frozenset((source, target))


def build_topology_dry_run_report(
    devices: list[Any],
    links: list[Any],
    observations: list[TopologyEvidenceObservation],
) -> dict[str, Any]:
    """Summarize candidate topology links from evidence without mutating state."""
    known_devices = {_device_name(device) for device in devices if _device_name(device)}
    configured_pairs = {
        pair for link in links if (pair := _link_pair(link)) is not None
    }
    candidates: dict[frozenset[str], dict[str, Any]] = {}
    covered_pairs: set[frozenset[str]] = set()
    unresolved_observations = 0

    for observation in observations:
        source = observation.source_identity or observation.source_node
        target = observation.target_identity or observation.target_node
        if source not in known_devices or target not in known_devices or source == target:
            unresolved_observations += 1
            continue

        pair = frozenset((source, target))
        if pair in configured_pairs:
            covered_pairs.add(pair)
            continue

        data = candidates.setdefault(
            pair,
            {
                "source_device": source,
                "target_device": target,
                "confidence": 0.0,
                "evidence_count": 0,
                "evidence_sources": set(),
                "evidence_types": set(),
            },
        )
        data["confidence"] = max(data["confidence"], observation.confidence)
        data["evidence_count"] += 1
        data["evidence_sources"].add(observation.source)
        data["evidence_types"].add(observation.evidence_type)

    candidate_items: list[TopologyDryRunCandidate] = []
    for data in candidates.values():
        evidence_types = sorted(data["evidence_types"])
        if "romon_path" in evidence_types and len(evidence_types) == 1:
            reason = "RoMON path only; requires neighbor or bridge-host confirmation."
        elif "mac_seen_on_port" in evidence_types and len(evidence_types) == 1:
            reason = "Bridge host MAC evidence only; requires device identity confirmation."
        else:
            reason = "Multiple evidence sources observed this device pair."

        candidate_items.append(
            TopologyDryRunCandidate(
                source_device=data["source_device"],
                target_device=data["target_device"],
                confidence=data["confidence"],
                evidence_count=data["evidence_count"],
                evidence_sources=sorted(data["evidence_sources"]),
                evidence_types=evidence_types,
                status="candidate",
                reason=reason,
            )
        )

    candidate_items.sort(
        key=lambda item: (-item.confidence, item.source_device, item.target_device)
    )
    return {
        "candidates": [item.model_dump(mode="json") for item in candidate_items],
        "candidate_count": len(candidate_items),
        "covered_pair_count": len(covered_pairs),
        "unresolved_observation_count": unresolved_observations,
        "evidence_count": len(observations),
    }


class TopologyEvidenceStore:
    """Thread-safe in-memory store for topology evidence observations."""

    def __init__(self) -> None:
        self._observations: list[TopologyEvidenceObservation] = []
        self._lock = threading.Lock()

    def replace_source(
        self,
        source: str,
        observations: list[TopologyEvidenceObservation],
    ) -> None:
        with self._lock:
            self._observations = [
                observation
                for observation in self._observations
                if observation.source != source
            ]
            self._observations.extend(observations)

    def add_many(self, observations: list[TopologyEvidenceObservation]) -> None:
        with self._lock:
            self._observations.extend(observations)

    def list_observations(self, source: str | None = None) -> list[TopologyEvidenceObservation]:
        with self._lock:
            observations = list(self._observations)
        if source is None:
            return observations
        return [observation for observation in observations if observation.source == source]

    def count(self, source: str | None = None) -> int:
        return len(self.list_observations(source))
