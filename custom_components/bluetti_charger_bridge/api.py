"""HTTP client and payload validation for the local bridge."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import aiohttp
from yarl import URL

from .const import DEFAULT_TIMEOUT


class BridgeError(Exception):
    """A transport or non-auth bridge error."""


class BridgeAuthError(BridgeError):
    """The bridge rejected the configured token."""


class BridgePayloadError(BridgeError):
    """The bridge returned JSON outside its documented contract."""


def normalize_url(value: str) -> str:
    """Validate a bridge root URL, preserving a non-root path if configured."""
    try:
        url = URL(value.strip())
    except (TypeError, ValueError) as err:
        raise ValueError("invalid URL") from err
    if url.scheme not in {"http", "https"} or not url.host or url.user or url.password or url.query or url.fragment:
        raise ValueError("invalid URL")
    return str(url.with_path(url.path.rstrip("/"))).rstrip("/")


def _require_object(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BridgePayloadError(message)
    return value


def _require_list(value: Any, message: str) -> list[Any]:
    if not isinstance(value, list):
        raise BridgePayloadError(message)
    return value


def parse_status(payload: Any) -> dict[str, Any]:
    """Validate envelope and collection shapes without inventing missing data."""
    status = _require_object(payload, "status is not an object")
    if status.get("schema_version") != 1 or not isinstance(status.get("updated_at"), str):
        raise BridgePayloadError("unsupported status schema")
    chargers = _require_object(status.get("chargers"), "invalid chargers")
    for charger_id, charger_value in chargers.items():
        if not isinstance(charger_id, str) or not charger_id:
            raise BridgePayloadError("invalid charger identifier")
        charger = _require_object(charger_value, "invalid charger")
        if not isinstance(charger.get("available"), bool):
            raise BridgePayloadError("invalid availability")
        identity = _require_object(charger.get("identity"), "invalid identity")
        quality = _require_object(charger.get("quality"), "invalid quality")
        telemetry = charger.get("telemetry")
        configuration = charger.get("configuration")
        unavailable_without_state = telemetry is None and configuration is None and charger["available"] is False
        if unavailable_without_state:
            telemetry, configuration = {}, {}
            charger["telemetry"] = telemetry
            charger["configuration"] = configuration
        else:
            telemetry = _require_object(telemetry, "invalid telemetry")
            configuration = _require_object(configuration, "invalid configuration")
        if not isinstance(identity.get("mac"), str) or not isinstance(identity.get("name"), str):
            raise BridgePayloadError("invalid identity")
        if quality.get("rssi_dbm") is not None and (
            not isinstance(quality["rssi_dbm"], int) or isinstance(quality["rssi_dbm"], bool)
        ):
            raise BridgePayloadError("invalid signal quality")
        if unavailable_without_state:
            continue
        channels = _require_list(telemetry.get("channels"), "invalid channels")
        fault_words = _require_list(telemetry.get("fault_words"), "invalid fault words")
        for channel in channels:
            _require_object(channel, "invalid channel")
        if not all(isinstance(word, int) and not isinstance(word, bool) for word in fault_words):
            raise BridgePayloadError("invalid fault words")
        if configuration.get("charging_mode") not in {"standard", "silent"}:
            raise BridgePayloadError("invalid charging mode")
    return status


class BridgeClient:
    """Small authenticated client; errors deliberately never include response bodies."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: str) -> None:
        self._session = session
        self.base_url = normalize_url(base_url)
        self._token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with self._session.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                **kwargs,
            ) as response:
                if response.status in (401, 403):
                    raise BridgeAuthError("authentication failed")
                if response.status >= 400:
                    raise BridgeError("HTTP request failed")
                try:
                    data = await response.json(content_type=None)
                except (aiohttp.ClientError, TypeError, ValueError) as err:
                    raise BridgePayloadError("invalid JSON response") from err
        except BridgeError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BridgeError("transport failure") from err
        if not isinstance(data, dict):
            raise BridgePayloadError("response is not an object")
        return data

    async def async_get_status(self) -> dict[str, Any]:
        return parse_status(await self._request_json("GET", "/api/v1/status"))

    async def async_set_charging_mode(self, charger_id: str, mode: str) -> dict[str, Any]:
        if mode not in {"standard", "silent"}:
            raise ValueError("unsupported charging mode")
        result = await self._request_json(
            "PUT",
            f"/api/v1/chargers/{quote(charger_id, safe='')}/charging-mode",
            json={"mode": mode},
        )
        expected_silent = mode == "silent"
        after = result.get("after")
        if (
            result.get("verified") is not True
            or result.get("requested_mode") != mode
            or not isinstance(after, dict)
            or after.get("silent_mode") is not expected_silent
        ):
            raise BridgePayloadError("write not verified")
        return result

    async def async_set_charging_enabled(self, charger_id: str, enabled: bool) -> dict[str, Any]:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        result = await self._request_json(
            "PUT",
            f"/api/v1/chargers/{quote(charger_id, safe='')}/charging-enabled",
            json={"enabled": enabled},
        )
        after = result.get("after")
        if (
            result.get("verified") is not True
            or result.get("requested_enabled") is not enabled
            or not isinstance(after, dict)
            or after.get("charging_enabled") is not enabled
        ):
            raise BridgePayloadError("write not verified")
        return result
