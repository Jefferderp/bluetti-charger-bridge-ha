"""Configuration, reauthentication, and reconfiguration flows."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BridgeAuthError, BridgeClient, BridgeError, BridgePayloadError, normalize_url
from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN, MIN_POLL_INTERVAL

TOKEN_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.URL)),
        vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
    }
)
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL)
        )
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Manage a bridge endpoint without silently taking over duplicates."""

    VERSION = 1

    async def _validate(self, data: dict[str, str]) -> str:
        url = normalize_url(data[CONF_URL])
        await BridgeClient(async_get_clientsession(self.hass), url, data[CONF_TOKEN]).async_get_status()
        return url

    @staticmethod
    def _error(err: Exception) -> str:
        if isinstance(err, ValueError):
            return "invalid_url"
        if isinstance(err, BridgeAuthError):
            return "invalid_auth"
        if isinstance(err, BridgePayloadError):
            return "invalid_response"
        if isinstance(err, BridgeError):
            return "cannot_connect"
        return "unknown"

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = await self._validate(user_input)
            except Exception as err:  # Flow errors must not expose secrets or response data.
                errors[CONF_URL if isinstance(err, ValueError) else "base"] = self._error(err)
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="BLUETTI Charger Bridge", data={CONF_URL: url, CONF_TOKEN: user_input[CONF_TOKEN]}
                )
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, str]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, str] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entry = self._get_reauth_entry()
            data = {**entry.data, CONF_TOKEN: user_input[CONF_TOKEN]}
            try:
                await self._validate(data)
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            except Exception as err:
                errors["base"] = self._error(err)
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, str] | None = None) -> FlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = await self._validate(user_input)
                existing = self._async_current_entries()
                if any(other.entry_id != entry.entry_id and other.unique_id == url for other in existing):
                    return self.async_abort(reason="already_configured")
                self.hass.config_entries.async_update_entry(
                    entry, data={CONF_URL: url, CONF_TOKEN: user_input[CONF_TOKEN]}, unique_id=url
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
            except Exception as err:
                errors[CONF_URL if isinstance(err, ValueError) else "base"] = self._error(err)
        return self.async_show_form(step_id="reconfigure", data_schema=DATA_SCHEMA, errors=errors)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Configure only safe polling behavior."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, self.config_entry.options)
        )
