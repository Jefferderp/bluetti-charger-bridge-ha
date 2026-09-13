"""Shared polling coordinator."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BridgeAuthError, BridgeClient, BridgeError
from .const import DOMAIN


class BridgeCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, client: BridgeClient, interval: timedelta, config_entry=None) -> None:
        super().__init__(
            hass, logger=logging.getLogger(__name__), name=DOMAIN, update_interval=interval, config_entry=config_entry
        )
        self.client = client

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_get_status()
        except BridgeAuthError as err:
            raise ConfigEntryAuthFailed from err
        except BridgeError as err:
            raise UpdateFailed(str(err)) from err
