"""Charging enable controls."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import BridgeEntity


class ChargerCharging(BridgeEntity, SwitchEntity):
    """Enable or disable charging with bridge-verified readback."""

    def __init__(self, coordinator: Any, entry_id: str, upstream_id: str) -> None:
        super().__init__(coordinator, entry_id, upstream_id)
        self._attr_translation_key = "charging_enabled_control"
        self._attr_unique_id = f"{self._digest}_charging_enabled_control"

    @property
    def is_on(self) -> bool | None:
        value = self.configuration.get("charging_enabled")
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_set_charging_enabled(self.upstream_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_set_charging_enabled(self.upstream_id, False)
        await self.coordinator.async_request_refresh()


def _entities(coordinator: Any, entry_id: str, ids: set[str]) -> list[ChargerCharging]:
    return [ChargerCharging(coordinator, entry_id, upstream_id) for upstream_id in ids]


async def async_setup_entry(hass: HomeAssistant, entry: Any, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    known = set(coordinator.data["chargers"])
    async_add_entities(_entities(coordinator, entry.entry_id, known))

    def add_new() -> None:
        nonlocal known
        fresh = set(coordinator.data["chargers"]) - known
        if fresh:
            known |= fresh
            async_add_entities(_entities(coordinator, entry.entry_id, fresh))

    entry.async_on_unload(coordinator.async_add_listener(add_new))
