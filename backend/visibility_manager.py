"""Device visibility manager — hide/blacklist persistence and state.

Manages two independent states:
- **Hidden**: Device is temporarily invisible on the map but still pinged.
- **Blacklisted**: Device is permanently removed — stops pinging, blocks
  re-discovery by name/host/MAC.

Both states are persisted to ``config/device_visibility.json``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import BlacklistedDevice

logger = logging.getLogger(__name__)

VISIBILITY_FILE = Path(__file__).resolve().parent.parent / "config" / "device_visibility.json"


class VisibilityManager:
    """Manages device hide/blacklist state with JSON persistence."""

    def __init__(self) -> None:
        self.hidden: set[str] = set()
        self.blacklisted: dict[str, BlacklistedDevice] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────

    def _load(self) -> None:
        """Load visibility state from JSON file."""
        if not VISIBILITY_FILE.exists():
            return
        try:
            with open(VISIBILITY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self.hidden = set(data.get("hidden", []))
            for entry in data.get("blacklisted", []):
                dev = BlacklistedDevice(**entry)
                self.blacklisted[dev.id] = dev
            logger.info(
                "Loaded visibility: %d hidden, %d blacklisted",
                len(self.hidden),
                len(self.blacklisted),
            )
        except Exception:
            logger.warning("Failed to load visibility file", exc_info=True)

    async def _save(self) -> None:
        """Save visibility state to JSON file (async)."""

        def _write() -> None:
            VISIBILITY_FILE.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {
                "hidden": sorted(self.hidden),
                "blacklisted": [
                    d.model_dump(mode="json") for d in self.blacklisted.values()
                ],
            }
            with open(VISIBILITY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

        try:
            await asyncio.to_thread(_write)
        except Exception:
            logger.warning("Failed to save visibility file", exc_info=True)

    # ── hide / unhide ────────────────────────────────────────────

    async def hide_device(self, device_id: str) -> None:
        self.hidden.add(device_id)
        await self._save()

    async def unhide_device(self, device_id: str) -> None:
        self.hidden.discard(device_id)
        await self._save()

    def is_hidden(self, device_id: str) -> bool:
        return device_id in self.hidden

    # ── blacklist / unblacklist ──────────────────────────────────

    async def blacklist_device(
        self,
        device_id: str,
        host: str = "",
        mac: str = "",
        reason: str = "",
    ) -> BlacklistedDevice:
        dev = BlacklistedDevice(
            id=device_id,
            host=host,
            mac=mac,
            reason=reason,
            blacklisted_at=datetime.now(timezone.utc),
        )
        self.blacklisted[device_id] = dev
        # Also remove from hidden (no point hiding a blacklisted device).
        self.hidden.discard(device_id)
        await self._save()
        return dev

    async def unblacklist_device(self, device_id: str) -> None:
        self.blacklisted.pop(device_id, None)
        await self._save()

    def is_blacklisted(self, device_id: str) -> bool:
        return device_id in self.blacklisted

    def is_blacklisted_by_identity(
        self,
        name: str = "",
        host: str = "",
        mac: str = "",
    ) -> bool:
        """Check if any blacklisted entry matches the given name, host, or MAC."""
        for entry in self.blacklisted.values():
            if name and entry.id == name:
                return True
            if host and entry.host and entry.host == host:
                return True
            if mac and entry.mac and entry.mac == mac:
                return True
        return False

    # ── queries ──────────────────────────────────────────────────

    def get_hidden_list(self) -> list[str]:
        return sorted(self.hidden)

    def get_blacklisted_list(self) -> list[dict[str, Any]]:
        return [d.model_dump(mode="json") for d in self.blacklisted.values()]
