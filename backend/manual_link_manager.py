"""Manual link manager — persistence for UI-created links.

Manages links created by the user through the web UI.
These supplement auto-discovered links and YAML-configured links.
Persisted to ``config/manual_links.json``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MANUAL_LINKS_FILE = Path(__file__).resolve().parent.parent / "config" / "manual_links.json"


def _make_link_id(from_dev: str, to_dev: str) -> str:
    """Create a canonical link ID (sorted so A-B == B-A)."""
    left, right = (from_dev, to_dev) if from_dev <= to_dev else (to_dev, from_dev)
    return f"{left}-{right}"


class ManualLinkManager:
    """Manages manually-created links with JSON persistence."""

    def __init__(self) -> None:
        self._links: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not MANUAL_LINKS_FILE.exists():
            return
        try:
            with open(MANUAL_LINKS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for link in data:
                link_id = link.get("id", _make_link_id(link["from"], link["to"]))
                link["id"] = link_id
                self._links[link_id] = link
            logger.info("Loaded %d manual links from %s", len(self._links), MANUAL_LINKS_FILE)
        except Exception:
            logger.warning("Failed to load manual links", exc_info=True)

    def _save_sync(self) -> None:
        MANUAL_LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MANUAL_LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(self._links.values()), f, indent=2)

    async def _save(self) -> None:
        try:
            await asyncio.to_thread(self._save_sync)
        except Exception:
            logger.warning("Failed to save manual links", exc_info=True)

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._links.values())

    def get_link(self, link_id: str) -> dict[str, Any] | None:
        return self._links.get(link_id)

    async def create_link(
        self,
        from_device: str,
        to_device: str,
        speed: int = 1000,
        link_type: str = "wired",
    ) -> dict[str, Any]:
        link_id = _make_link_id(from_device, to_device)
        link = {
            "id": link_id,
            "from": from_device,
            "to": to_device,
            "speed": speed,
            "type": link_type,
        }
        self._links[link_id] = link
        await self._save()
        logger.info("Created manual link: %s", link_id)
        return link

    async def update_link(
        self, link_id: str, updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        link = self._links.get(link_id)
        if not link:
            return None
        for key in ("speed", "type", "from", "to"):
            if key in updates:
                link[key] = updates[key]
        # Recalculate ID if endpoints changed.
        if "from" in updates or "to" in updates:
            new_id = _make_link_id(link["from"], link["to"])
            if new_id != link_id:
                del self._links[link_id]
                link["id"] = new_id
                self._links[new_id] = link
        await self._save()
        logger.info("Updated manual link: %s", link["id"])
        return link

    async def delete_link(self, link_id: str) -> bool:
        if link_id not in self._links:
            return False
        del self._links[link_id]
        await self._save()
        logger.info("Deleted manual link: %s", link_id)
        return True
