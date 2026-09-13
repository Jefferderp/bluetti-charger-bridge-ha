"""Charging mode control entities."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .entity import BridgeEntity


class ChargerMode(BridgeEntity, SelectEntity):
    _attr_options = ["standard", "silent"]

    def __init__(self, coordinator, entry_id, upstream_id):
        super().__init__(coordinator, entry_id, upstream_id)
        self._attr_translation_key = "charging_mode"
        self._attr_unique_id = f"{self._digest}_charging_mode"

    @property
    def current_option(self):
        return self.configuration.get("charging_mode")

    async def async_select_option(self, option):
        await self.coordinator.client.async_set_charging_mode(self.upstream_id, option)
        await self.coordinator.async_request_refresh()


def _entities(c, entry_id, ids):
    return [ChargerMode(c, entry_id, uid) for uid in ids]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.coordinator
    known = set(coordinator.data["chargers"])
    async_add_entities(_entities(coordinator, entry.entry_id, known))

    def add_new():
        nonlocal known
        fresh = set(coordinator.data["chargers"]) - known
        if fresh:
            known |= fresh
            async_add_entities(_entities(coordinator, entry.entry_id, fresh))

    entry.async_on_unload(coordinator.async_add_listener(add_new))
