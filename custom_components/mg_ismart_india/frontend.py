"""Dashboard cards: serve the card file and tell the cards which entity is which.

The cards find their entities through the ``mg_ismart_india/devices`` websocket
command, which maps each entity key (``battery``, ``range``, ``door_lock``…)
to the entity ID actually in use. Renamed entities therefore keep working.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_VIN, DOMAIN

_LOGGER = logging.getLogger(__name__)

CARDS_FILE = Path(__file__).parent / "www" / "mg-cards.js"
CARDS_URL = f"/{DOMAIN}/mg-cards.js"


async def async_register_frontend(hass: HomeAssistant, version: str) -> None:
    """Serve the cards and load them on every dashboard."""
    websocket_api.async_register_command(hass, ws_devices)

    http = getattr(hass, "http", None)
    if http is None or "frontend" not in hass.config.components:
        return  # e.g. in tests, or a setup without the web UI
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    try:
        await http.async_register_static_paths(
            [StaticPathConfig(CARDS_URL, str(CARDS_FILE), cache_headers=False)]
        )
    except RuntimeError:  # already registered (integration reloaded)
        pass
    add_extra_js_url(hass, f"{CARDS_URL}?v={version}")


def device_entities(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Every car with its key → entity_id map."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    devices: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        vin = str(entry.data.get(CONF_VIN, ""))
        prefix = f"{vin}_"
        entities: dict[str, str] = {}
        device_id: str | None = None
        for reg in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if not reg.unique_id.startswith(prefix):
                continue
            if reg.disabled_by is None:
                entities[reg.unique_id[len(prefix):]] = reg.entity_id
            device_id = device_id or reg.device_id
        device = dev_reg.async_get(device_id) if device_id else None
        devices.append(
            {
                "entry_id": entry.entry_id,
                "device_id": device_id,
                "name": (device and (device.name_by_user or device.name)) or entry.title,
                "loaded": entry.state is ConfigEntryState.LOADED,
                "entities": entities,
            }
        )
    return devices


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/devices"})
@callback
def ws_devices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    connection.send_result(msg["id"], {"devices": device_entities(hass)})
