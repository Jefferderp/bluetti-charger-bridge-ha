"""Safe boolean bridge state entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory

from .entity import BridgeEntity


class ChargerBinarySensor(BridgeEntity, BinarySensorEntity):
    """A boolean scalar; malformed or missing data stays unknown."""

    def __init__(
        self,
        coordinator: Any,
        entry_id: str,
        upstream_id: str,
        key: str,
        section: str,
        device_class: BinarySensorDeviceClass | None = None,
        category: EntityCategory | None = None,
    ) -> None:
        super().__init__(coordinator, entry_id, upstream_id)
        self._key = key
        self._section = section
        self._attr_unique_id = f"{self._digest}_{key}"
        self._attr_translation_key = key
        self._attr_device_class = device_class
        self._attr_entity_category = category

    @property
    def is_on(self) -> bool | None:
        value = getattr(self, self._section).get(self._key)
        return value if isinstance(value, bool) else None


def _entities(coordinator: Any, entry_id: str, ids: set[str]) -> list[ChargerBinarySensor]:
    return [
        ChargerBinarySensor(
            coordinator, entry_id, upstream_id, "has_fault", "telemetry", BinarySensorDeviceClass.PROBLEM
        )
        for upstream_id in ids
    ] + [
        ChargerBinarySensor(coordinator, entry_id, upstream_id, key, "configuration", category=category)
        for upstream_id in ids
        for key, category in (
            ("charging_enabled", None),
            ("adaptive_mode", None),
            ("factory_set", EntityCategory.DIAGNOSTIC),
            ("silent_mode", None),
        )
    ]


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
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
