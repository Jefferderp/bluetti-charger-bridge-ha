"""Privacy-safe diagnostics."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_POLL_INTERVAL


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    data = entry.runtime_data.coordinator.data if entry.runtime_data else {}
    chargers = (data or {}).get("chargers", {})
    return {
        "entry": {"poll_interval": entry.options.get(CONF_POLL_INTERVAL, 60)},
        "schema_version": (data or {}).get("schema_version"),
        "charger_count": len(chargers),
        "available_count": sum(bool(item.get("available")) for item in chargers.values()),
    }
