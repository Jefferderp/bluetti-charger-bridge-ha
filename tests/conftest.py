from __future__ import annotations

import pytest
from homeassistant.const import CONF_TOKEN, CONF_URL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluetti_charger_bridge.const import DOMAIN


@pytest.fixture
def config_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: "http://example.invalid", CONF_TOKEN: "fake-test-token"},
        options={"poll_interval": 60},
        unique_id="http://example.invalid",
    )
