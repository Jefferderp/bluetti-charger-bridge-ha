"""Production contract tests for the local bridge integration."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluetti_charger_bridge.api import (
    BridgeAuthError,
    BridgeClient,
    BridgePayloadError,
    normalize_url,
    parse_status,
)
from custom_components.bluetti_charger_bridge.config_flow import ConfigFlow
from custom_components.bluetti_charger_bridge.coordinator import BridgeCoordinator
from custom_components.bluetti_charger_bridge.entity import charger_digest
from custom_components.bluetti_charger_bridge.sensor import SENSOR_DESCRIPTIONS, _entities
from custom_components.bluetti_charger_bridge.switch import ChargerCharging

VALID = {
    "schema_version": 1,
    "updated_at": "2026-01-01T00:00:00Z",
    "chargers": {
        "charger-alpha": {
            "available": True,
            "identity": {"mac": "opaque-identity", "name": "Synthetic charger"},
            "quality": {"error": None, "rssi_dbm": -55},
            "telemetry": {
                "battery_type_input": 1,
                "car_battery_soc_pct": 77,
                "channels": [{"channel": 1, "current_raw": 1, "power_w": 2, "voltage_raw": 3}],
                "energy_flow_flags": 3,
                "fault_words": [1, 2],
                "has_fault": False,
                "input_energy_total": 1,
                "input_voltage_v": 12.1,
                "model": "BC-TEST",
                "output_current_a": 5.0,
                "output_energy_total": 2,
                "output_power_w": 72,
                "output_voltage_v": 14.4,
                "pack_voltage_type": 1,
                "serial": "opaque-serial",
                "working_mode": 2,
            },
            "configuration": {
                "adaptive_mode": True,
                "channel_modes": [1],
                "charging_enabled": True,
                "charging_mode": "standard",
                "control_values": {"limit": 4},
                "factory_set": False,
                "output_voltage_setpoint_v": 14.4,
                "raw_flags": 5,
                "silent_mode": False,
            },
        }
    },
}


async def test_home_assistant_can_start_user_config_flow(hass: HomeAssistant, enable_custom_integrations) -> None:
    """Exercise the same config-flow lookup used by Add Integration."""
    result = await hass.config_entries.flow.async_init("bluetti_charger_bridge", context={"source": SOURCE_USER})

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert set(result["data_schema"].schema) == {CONF_URL, CONF_TOKEN}


def make_response(status: int, payload: object = None) -> tuple[MagicMock, AsyncMock]:
    session = MagicMock()
    response = AsyncMock(status=status)
    response.__aenter__.return_value = response
    response.json.return_value = payload
    session.request.return_value = response
    return session, response


def test_parser_uses_live_nested_contract() -> None:
    assert parse_status(VALID)["chargers"]["charger-alpha"]["telemetry"]["input_voltage_v"] == 12.1


@pytest.mark.parametrize("payload", [None, [], {"schema_version": "1", "chargers": {}}])
def test_parser_rejects_malformed_top_level_payload(payload: object) -> None:
    with pytest.raises(BridgePayloadError):
        parse_status(payload)


def test_parser_rejects_malformed_nested_channel() -> None:
    payload = deepcopy(VALID)
    payload["chargers"]["charger-alpha"]["telemetry"]["channels"] = ["bad"]
    with pytest.raises(BridgePayloadError):
        parse_status(payload)


def test_parser_accepts_first_failed_poll_without_telemetry_or_configuration() -> None:
    payload = {
        "schema_version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "chargers": {
            "charger-alpha": {
                "available": False,
                "identity": {"mac": "opaque-identity", "name": "Synthetic charger"},
                "quality": {"error": "poll failed"},
            }
        },
    }

    charger = parse_status(payload)["chargers"]["charger-alpha"]

    assert charger["telemetry"] == {}
    assert charger["configuration"] == {}


def test_parser_rejects_missing_sections_for_available_charger() -> None:
    payload = deepcopy(VALID)
    del payload["chargers"]["charger-alpha"]["telemetry"]

    with pytest.raises(BridgePayloadError, match="invalid telemetry"):
        parse_status(payload)


def test_parser_rejects_boolean_where_integer_statistics_are_required() -> None:
    payload = deepcopy(VALID)
    payload["chargers"]["charger-alpha"]["telemetry"]["fault_words"] = [True]

    with pytest.raises(BridgePayloadError, match="invalid fault words"):
        parse_status(payload)


@pytest.mark.parametrize(
    ("source", "normalized"),
    [
        (" https://example.invalid/bridge/ ", "https://example.invalid/bridge"),
        ("http://example.invalid", "http://example.invalid"),
    ],
)
def test_normalize_url_accepts_http_urls_and_removes_trailing_slash(source: str, normalized: str) -> None:
    assert normalize_url(source) == normalized


@pytest.mark.parametrize(
    "source",
    [
        "ftp://example.invalid",
        "https://user" + ":pass" + "@example.invalid",
        "https://example.invalid/?query=yes",
        "https://example.invalid/#fragment",
        "/relative/path",
    ],
)
def test_normalize_url_rejects_unsafe_or_ambiguous_urls(source: str) -> None:
    with pytest.raises(ValueError):
        normalize_url(source)


async def test_client_maps_invalid_json_to_payload_error_without_body() -> None:
    session, response = make_response(200)
    response.json.side_effect = aiohttp.ContentTypeError(MagicMock(), ())
    with pytest.raises(BridgePayloadError, match="invalid JSON"):
        await BridgeClient(session, "http://example.invalid", "fake-test-token").async_get_status()


async def test_client_uses_timeout_and_does_not_leak_error_body() -> None:
    session, _ = make_response(500, {"secret": "fake-test-token"})
    client = BridgeClient(session, "http://example.invalid", "fake-test-token")
    with pytest.raises(Exception) as err:
        await client.async_get_status()
    assert "fake-test-token" not in str(err.value)
    assert session.request.call_args.kwargs["timeout"].total == 10


async def test_client_maps_401_and_sends_bearer() -> None:
    session, _ = make_response(401)
    with pytest.raises(BridgeAuthError):
        await BridgeClient(session, "http://example.invalid", "fake-test-token").async_get_status()
    assert session.request.call_args.kwargs["headers"] == {"Authorization": "Bearer fake-test-token"}


async def test_client_encodes_write_and_validates_actual_verified_contract() -> None:
    result = {
        "mac": "opaque-identity",
        "requested_mode": "silent",
        "before": {"silent_mode": False},
        "after": {"silent_mode": True},
        "verified": True,
    }
    session, _ = make_response(200, result)
    await BridgeClient(session, "https://example.invalid", "fake-test-token").async_set_charging_mode(
        "alpha/id", "silent"
    )
    assert session.request.call_args.args[1].endswith("alpha%2Fid/charging-mode")
    assert session.request.call_args.kwargs["json"] == {"mode": "silent"}
    assert session.request.call_args.kwargs["timeout"].total == 75


async def test_client_sets_charging_and_validates_readback() -> None:
    result = {
        "requested_enabled": False,
        "before": {"charging_enabled": True},
        "after": {"charging_enabled": False},
        "verified": True,
    }
    session, _ = make_response(200, result)

    await BridgeClient(session, "https://example.invalid", "fake-test-token").async_set_charging_enabled(
        "alpha/id", False
    )

    assert session.request.call_args.args[1].endswith("alpha%2Fid/charging-enabled")
    assert session.request.call_args.kwargs["json"] == {"enabled": False}
    assert session.request.call_args.kwargs["timeout"].total == 75


@pytest.mark.parametrize(
    "response",
    [
        {"requested_enabled": True, "after": {"charging_enabled": True}, "verified": False},
        {"requested_enabled": False, "after": {"charging_enabled": True}, "verified": True},
        {"requested_enabled": "yes", "after": {"charging_enabled": True}, "verified": True},
    ],
)
async def test_client_rejects_unverified_or_inconsistent_charging_write(response: dict[str, object]) -> None:
    session, _ = make_response(200, response)
    with pytest.raises(BridgePayloadError):
        await BridgeClient(session, "https://example.invalid", "fake-test-token").async_set_charging_enabled(
            "alpha", True
        )


@pytest.mark.parametrize(("method", "requested"), [("async_turn_on", True), ("async_turn_off", False)])
async def test_charging_switch_calls_bridge_and_refreshes(method: str, requested: bool) -> None:
    coordinator = MagicMock()
    coordinator.data = deepcopy(VALID)
    coordinator.client.async_set_charging_enabled = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    entity = ChargerCharging(coordinator, "entry-one", "charger-alpha")

    assert entity.is_on is True
    await getattr(entity, method)()

    coordinator.client.async_set_charging_enabled.assert_awaited_once_with("charger-alpha", requested)
    coordinator.async_request_refresh.assert_awaited_once()
    assert entity.unique_id.endswith("_charging_enabled_control")


@pytest.mark.parametrize(
    "response",
    [
        {"requested_mode": "silent", "after": {"silent_mode": True}, "verified": False},
        {"requested_mode": "standard", "after": {"silent_mode": True}, "verified": True},
        {"requested_mode": "silent", "after": {"silent_mode": False}, "verified": True},
    ],
)
async def test_client_rejects_unverified_or_inconsistent_write(response: dict[str, object]) -> None:
    session, _ = make_response(200, response)
    with pytest.raises(BridgePayloadError):
        await BridgeClient(session, "https://example.invalid", "fake-test-token").async_set_charging_mode(
            "alpha", "silent"
        )


async def test_user_duplicate_aborts_without_replacing_credentials(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = MockConfigEntry(
        domain="bluetti_charger_bridge",
        unique_id="http://duplicate.invalid",
        data={CONF_URL: "http://duplicate.invalid", CONF_TOKEN: "original-token"},
    )
    existing.add_to_hass(hass)
    flow = ConfigFlow()
    flow.hass = hass
    flow.handler = "bluetti_charger_bridge"
    flow.context = {"source": "user"}
    monkeypatch.setattr(ConfigFlow, "_validate", AsyncMock(return_value="http://duplicate.invalid"))

    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_user({CONF_URL: "http://duplicate.invalid", CONF_TOKEN: "replacement-token"})

    assert existing.data[CONF_TOKEN] == "original-token"


async def test_reconfigure_duplicate_aborts_without_replacing_credentials(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = MockConfigEntry(
        domain="bluetti_charger_bridge",
        unique_id="http://current.invalid",
        data={CONF_URL: "http://current.invalid", CONF_TOKEN: "original-token"},
    )
    duplicate = MockConfigEntry(
        domain="bluetti_charger_bridge",
        unique_id="http://duplicate.invalid",
        data={CONF_URL: "http://duplicate.invalid", CONF_TOKEN: "duplicate-token"},
    )
    current.add_to_hass(hass)
    duplicate.add_to_hass(hass)
    flow = ConfigFlow()
    flow.hass = hass
    flow.handler = "bluetti_charger_bridge"
    flow.context = {"source": "reconfigure", "entry_id": current.entry_id}
    monkeypatch.setattr(ConfigFlow, "_validate", AsyncMock(return_value="http://duplicate.invalid"))

    result = await flow.async_step_reconfigure({CONF_URL: "http://duplicate.invalid", CONF_TOKEN: "replacement-token"})

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert current.data[CONF_TOKEN] == "original-token"


def test_identity_is_private_and_entry_scoped() -> None:
    digest = charger_digest("entry-one", "charger-alpha")
    assert len(digest) == 64
    assert digest == charger_digest("entry-one", "charger-alpha")
    assert digest != charger_digest("entry-two", "charger-alpha")
    assert "charger-alpha" not in digest


def test_sensor_entities_include_indexed_and_dynamic_safe_statistics() -> None:
    payload = deepcopy(VALID)
    payload["chargers"]["charger-alpha"]["telemetry"]["fault_words"] = [1, 2, 3]
    payload["chargers"]["charger-alpha"]["configuration"]["channel_modes"] = [1, 2]
    payload["chargers"]["charger-alpha"]["configuration"]["control_values"] = {"limit": 4, "new_metric": 9}
    coordinator = type("C", (), {"data": payload})()

    entities = _entities(coordinator, "entry-one", {"charger-alpha"})
    keys = {entity.unique_id.rsplit("_", 1)[0] for entity in entities}

    assert any(entity.unique_id.endswith("_channel_mode_0") for entity in entities)
    assert any(entity.unique_id.endswith("_channel_mode_1") for entity in entities)
    assert any(entity.unique_id.endswith("_fault_word_0") and entity.native_value == 1 for entity in entities)
    assert any(entity.unique_id.endswith("_fault_word_2") and entity.native_value == 3 for entity in entities)
    assert any("control_value" in entity.unique_id and entity.native_value == 4 for entity in entities)
    assert any("control_value" in entity.unique_id and entity.native_value == 9 for entity in entities)
    assert not keys & {"model", "serial", "name", "mac"}


def test_sensor_contract_exposes_safe_sections_without_identity_or_wrong_energy_semantics() -> None:
    keys = {description.key for description in SENSOR_DESCRIPTIONS}
    assert {"rssi_dbm", "input_energy_total", "output_energy_total", "output_voltage_setpoint_v"} <= keys
    assert {"model", "serial", "name", "mac"}.isdisjoint(keys)
    assert all(
        description.state_class is None for description in SENSOR_DESCRIPTIONS if "energy_total" in description.key
    )


async def test_coordinator_maps_auth_error(hass: HomeAssistant) -> None:
    client = AsyncMock()
    client.async_get_status.side_effect = BridgeAuthError
    with pytest.raises(ConfigEntryAuthFailed):
        await BridgeCoordinator(hass, client, timedelta(seconds=60))._async_update_data()


async def test_diagnostics_redacts_private_values(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    config_entry.runtime_data = type("Runtime", (), {"coordinator": type("C", (), {"data": VALID})()})()
    from custom_components.bluetti_charger_bridge.diagnostics import async_get_config_entry_diagnostics

    result = await async_get_config_entry_diagnostics(hass, config_entry)
    text = str(result)
    for forbidden in (
        config_entry.data[CONF_URL],
        config_entry.data[CONF_TOKEN],
        "charger-alpha",
        "Synthetic charger",
        "opaque-serial",
        "opaque-identity",
    ):
        assert forbidden not in text
    assert result["charger_count"] == 1
