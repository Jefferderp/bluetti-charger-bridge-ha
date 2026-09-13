# BLUETTI Charger Bridge

[![Open HACS and add this repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Jefferderp&repository=bluetti-charger-bridge-ha&category=integration)
[![Open your Home Assistant instance and show the add integration dialog](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=bluetti_charger_bridge)

A local-polling Home Assistant integration for the BLUETTI Charger Bridge API.

## Install

**HACS:** use the first badge above, or add `https://github.com/Jefferderp/bluetti-charger-bridge-ha` as an **Integration** custom repository, install it, and restart Home Assistant.

**Manual:** copy `custom_components/bluetti_charger_bridge` into your Home Assistant `custom_components` directory and restart.

## Configure

Add **BLUETTI Charger Bridge** in Settings → Devices & services. Enter an `http` or `https` bridge root URL reachable from Home Assistant and a required Bearer access token. A trailing slash is removed; a non-root path is preserved. URLs with embedded credentials, queries, or fragments are rejected. Tokens are stored by Home Assistant in the config entry and sent as an `Authorization: Bearer ***` header for reads and writes.

The integration polls every 60 seconds by default; Options permits intervals of 15 seconds or longer. It exposes safe scalar telemetry, signal quality, per-channel values, fault/configuration values, and an authenticated **Charging mode** select (`standard`/`silent`). A selection is accepted only when the bridge returns `verified: true`, the requested mode, and matching post-write `silent_mode`; it then refreshes status.

Input and output energy totals are exposed only as diagnostic raw counters: the upstream does not document their units or monotonic semantics. Identity fields (model, serial, device name, MAC), raw maps, URLs, tokens, and free-form errors are not exposed in entities or diagnostics. New chargers and channels are discovered dynamically; absent or unavailable chargers become unavailable.

## Compatibility and troubleshooting

Requires Home Assistant **2025.1.4+**. The bridge must implement `GET /api/v1/status` schema version 1 and `PUT /api/v1/chargers/{id}/charging-mode`. Authentication failures trigger Home Assistant reauthentication. Check bridge reachability from the Home Assistant host, token permissions, and status schema.

## License

MIT. This project is independent and is not affiliated with BLUETTI.
