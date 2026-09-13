"""Safe scalar bridge statistics."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import EntityDescription

from .entity import BridgeEntity


@dataclass(frozen=True, kw_only=True)
class BridgeSensorDescription(EntityDescription):
    """Immutable description of one scalar or indexed bridge statistic."""

    section: str
    source_key: str
    channel_key: str | None = None
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    state_class: SensorStateClass | None = None


SENSOR_DESCRIPTIONS = (
    BridgeSensorDescription(
        key="rssi_dbm",
        translation_key="rssi_dbm",
        section="quality",
        source_key="rssi_dbm",
        unit="dBm",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BridgeSensorDescription(
        key="input_voltage_v",
        translation_key="input_voltage_v",
        section="telemetry",
        source_key="input_voltage_v",
        unit="V",
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    BridgeSensorDescription(
        key="output_voltage_v",
        translation_key="output_voltage_v",
        section="telemetry",
        source_key="output_voltage_v",
        unit="V",
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    BridgeSensorDescription(
        key="output_current_a",
        translation_key="output_current_a",
        section="telemetry",
        source_key="output_current_a",
        unit="A",
        device_class=SensorDeviceClass.CURRENT,
    ),
    BridgeSensorDescription(
        key="output_power_w",
        translation_key="output_power_w",
        section="telemetry",
        source_key="output_power_w",
        unit="W",
        device_class=SensorDeviceClass.POWER,
    ),
    BridgeSensorDescription(
        key="car_battery_soc_pct",
        translation_key="car_battery_soc_pct",
        section="telemetry",
        source_key="car_battery_soc_pct",
        unit="%",
        device_class=SensorDeviceClass.BATTERY,
    ),
    BridgeSensorDescription(
        key="input_energy_total",
        translation_key="input_energy_total",
        section="telemetry",
        source_key="input_energy_total",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BridgeSensorDescription(
        key="output_energy_total",
        translation_key="output_energy_total",
        section="telemetry",
        source_key="output_energy_total",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BridgeSensorDescription(
        key="battery_type_input",
        translation_key="battery_type_input",
        section="telemetry",
        source_key="battery_type_input",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BridgeSensorDescription(
        key="energy_flow_flags",
        translation_key="energy_flow_flags",
        section="telemetry",
        source_key="energy_flow_flags",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BridgeSensorDescription(
        key="pack_voltage_type",
        translation_key="pack_voltage_type",
        section="telemetry",
        source_key="pack_voltage_type",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BridgeSensorDescription(
        key="working_mode",
        translation_key="working_mode",
        section="telemetry",
        source_key="working_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BridgeSensorDescription(
        key="output_voltage_setpoint_v",
        translation_key="output_voltage_setpoint_v",
        section="configuration",
        source_key="output_voltage_setpoint_v",
        unit="V",
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    BridgeSensorDescription(
        key="raw_flags",
        translation_key="raw_flags",
        section="configuration",
        source_key="raw_flags",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)
CONFIGURATION_LIST_DESCRIPTIONS = (
    BridgeSensorDescription(
        key="channel_mode",
        translation_key="channel_mode",
        section="configuration",
        source_key="channel_modes",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)
CHANNEL_DESCRIPTIONS = (
    BridgeSensorDescription(
        key="channel_current_raw",
        translation_key="channel_current_raw",
        section="telemetry",
        source_key="channels",
        channel_key="current_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BridgeSensorDescription(
        key="channel_power_w",
        translation_key="channel_power_w",
        section="telemetry",
        source_key="channels",
        channel_key="power_w",
        unit="W",
        device_class=SensorDeviceClass.POWER,
    ),
    BridgeSensorDescription(
        key="channel_voltage_raw",
        translation_key="channel_voltage_raw",
        section="telemetry",
        source_key="channels",
        channel_key="voltage_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)
FAULT_WORD_DESCRIPTION = BridgeSensorDescription(
    key="fault_word",
    translation_key="fault_word",
    section="telemetry",
    source_key="fault_words",
    entity_category=EntityCategory.DIAGNOSTIC,
)
CONTROL_VALUE_DESCRIPTION = BridgeSensorDescription(
    key="control_value",
    translation_key="control_value",
    section="configuration",
    source_key="control_values",
    entity_category=EntityCategory.DIAGNOSTIC,
)


def _safe_scalar(value: Any) -> str | int | float | None:
    return value if isinstance(value, (str, int, float)) and not isinstance(value, bool) else None


class ChargerSensor(BridgeEntity, SensorEntity):
    """A safe scalar or indexed bridge statistic."""

    entity_description: BridgeSensorDescription

    def __init__(
        self,
        coordinator: Any,
        entry_id: str,
        upstream_id: str,
        description: BridgeSensorDescription,
        channel: int | None = None,
        control_key: str | None = None,
    ) -> None:
        super().__init__(coordinator, entry_id, upstream_id)
        self.entity_description, self._channel, self._control_key = description, channel, control_key
        suffix = f"_{channel}" if channel is not None else ""
        if control_key is not None:
            # Never echo the upstream key: it is operator/device-supplied text.
            # The hashed digest used for identity is also the display label.
            suffix = f"_{sha256(control_key.encode()).hexdigest()[:16]}"
        self._attr_unique_id = f"{self._digest}_{description.key}{suffix}"
        self._attr_translation_key = description.translation_key
        if channel is not None:
            self._attr_translation_placeholders = {"index": str(channel)}
        elif control_key is not None:
            self._attr_translation_placeholders = {"key": suffix[1:9]}
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_entity_category = description.entity_category
        self._attr_state_class = description.state_class

    @property
    def native_value(self) -> Any:
        section = getattr(self, self.entity_description.section)
        if self._control_key is not None:
            values = section.get("control_values")
            return _safe_scalar(values.get(self._control_key)) if isinstance(values, dict) else None
        if self._channel is None:
            return _safe_scalar(section.get(self.entity_description.source_key))
        if self.entity_description.source_key in {"channel_modes", "fault_words"}:
            values = section.get(self.entity_description.source_key)
            return (
                _safe_scalar(values[self._channel])
                if isinstance(values, list) and self._channel < len(values)
                else None
            )
        channels = section.get("channels")
        if isinstance(channels, list):
            for item in channels:
                if isinstance(item, dict) and item.get("channel") == self._channel:
                    return _safe_scalar(item.get(self.entity_description.channel_key or ""))
        return None


def _channels(coordinator: Any, upstream_id: str) -> set[int]:
    values = coordinator.data.get("chargers", {}).get(upstream_id, {}).get("telemetry", {}).get("channels", [])
    return {
        item["channel"]
        for item in values
        if isinstance(item, dict) and isinstance(item.get("channel"), int) and not isinstance(item["channel"], bool)
    }


def _indexes(coordinator: Any, upstream_id: str, section: str, key: str) -> range:
    values = coordinator.data.get("chargers", {}).get(upstream_id, {}).get(section, {}).get(key, [])
    return range(len(values)) if isinstance(values, list) else range(0)


def _control_keys(coordinator: Any, upstream_id: str) -> set[str]:
    values = (
        coordinator.data.get("chargers", {}).get(upstream_id, {}).get("configuration", {}).get("control_values", {})
    )
    return (
        {key for key, value in values.items() if isinstance(key, str) and _safe_scalar(value) is not None}
        if isinstance(values, dict)
        else set()
    )


def _entities(coordinator: Any, entry_id: str, ids: set[str]) -> list[ChargerSensor]:
    return (
        [
            ChargerSensor(coordinator, entry_id, upstream_id, description)
            for upstream_id in ids
            for description in SENSOR_DESCRIPTIONS
        ]
        + [
            ChargerSensor(coordinator, entry_id, upstream_id, description, channel)
            for upstream_id in ids
            for channel in _channels(coordinator, upstream_id)
            for description in CHANNEL_DESCRIPTIONS
        ]
        + [
            ChargerSensor(coordinator, entry_id, upstream_id, description, index)
            for upstream_id in ids
            for description, key in (
                (CONFIGURATION_LIST_DESCRIPTIONS[0], "channel_modes"),
                (FAULT_WORD_DESCRIPTION, "fault_words"),
            )
            for index in _indexes(coordinator, upstream_id, description.section, key)
        ]
        + [
            ChargerSensor(coordinator, entry_id, upstream_id, CONTROL_VALUE_DESCRIPTION, control_key=key)
            for upstream_id in ids
            for key in _control_keys(coordinator, upstream_id)
        ]
    )


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    coordinator = entry.runtime_data.coordinator
    known_ids = set(coordinator.data["chargers"])
    known_dynamic = set()
    async_add_entities(_entities(coordinator, entry.entry_id, known_ids))
    known_dynamic = {
        (entity.upstream_id, entity.unique_id) for entity in _entities(coordinator, entry.entry_id, known_ids)
    }

    def add_new() -> None:
        nonlocal known_ids, known_dynamic
        current_ids = set(coordinator.data["chargers"])
        fresh_ids = current_ids - known_ids
        candidates = _entities(coordinator, entry.entry_id, current_ids)
        fresh = [entity for entity in candidates if (entity.upstream_id, entity.unique_id) not in known_dynamic]
        if fresh:
            known_dynamic |= {(entity.upstream_id, entity.unique_id) for entity in fresh}
            async_add_entities(fresh)
        known_ids |= fresh_ids

    entry.async_on_unload(coordinator.async_add_listener(add_new))
