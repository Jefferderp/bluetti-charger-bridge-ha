"""Shared private-identity-safe entity base."""

from __future__ import annotations

from hashlib import sha256

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def charger_digest(entry_id: str, upstream_id: str) -> str:
    return sha256(f"{entry_id}:{upstream_id}".encode()).hexdigest()


class BridgeEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str, upstream_id: str) -> None:
        super().__init__(coordinator)
        self.entry_id, self.upstream_id, self._digest = entry_id, upstream_id, charger_digest(entry_id, upstream_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}:{self._digest}")},
            name=f"Charger {self._digest[:8]}",
            manufacturer="BLUETTI",
            model="Battery charger",
        )

    @property
    def charger(self):
        return (self.coordinator.data or {}).get("chargers", {}).get(self.upstream_id)

    @property
    def available(self) -> bool:
        return super().available and bool(self.charger and self.charger.get("available"))

    @property
    def telemetry(self):
        return (self.charger or {}).get("telemetry", {})

    @property
    def configuration(self):
        return (self.charger or {}).get("configuration", {})

    @property
    def quality(self):
        return (self.charger or {}).get("quality", {})
