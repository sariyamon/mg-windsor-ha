"""End-to-end tests: config flow, entities, commands, errors."""

from __future__ import annotations

from mg_ismart_india_client import MgIndiaCommandIndeterminate, MgIndiaLoginRejected, MgIndiaMfaRequired
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from custom_components.mg_ismart_india.const import CONF_PHONE, CONF_PIN_HASH, CONF_VIN, DOMAIN

from .conftest import VIN, make_status

USER = {CONF_PHONE: "+91 98765 43210", CONF_PASSWORD: "secret", CONF_PIN: "1234"}


async def test_config_flow_creates_entry(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "MG Windsor"
    data = result["data"]
    assert data[CONF_PHONE] == "9876543210"
    assert data[CONF_VIN] == VIN
    assert CONF_PIN not in data and len(data[CONF_PIN_HASH]) == 32
    assert mock_client.login.await_count == 1


@pytest.mark.parametrize(
    ("exc", "error"),
    [(MgIndiaMfaRequired("mfa"), "mfa_required"), (MgIndiaLoginRejected("bad"), "invalid_auth")],
)
async def test_config_flow_errors(hass: HomeAssistant, mock_client, exc, error) -> None:
    mock_client.login.side_effect = exc
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_bad_phone(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**USER, CONF_PHONE: "12345"})
    assert result["errors"] == {CONF_PHONE: "invalid_phone"}
    mock_client.login.assert_not_called()


async def _setup(hass: HomeAssistant, pin: bool = True) -> MockConfigEntry:
    data = {CONF_PHONE: "9876543210", CONF_PASSWORD: "secret", CONF_VIN: VIN}
    if pin:
        data[CONF_PIN_HASH] = "X" * 32
    entry = MockConfigEntry(domain=DOMAIN, unique_id=VIN, data=data, title="MG Windsor")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass)
    s = lambda e: hass.states.get(e)  # noqa: E731
    assert s("sensor.mg_windsor_battery").state == "72.0"
    assert s("sensor.mg_windsor_range").state == "245.0"
    assert float(s("sensor.mg_windsor_charging_power").state) == pytest.approx(6.65)
    assert s("sensor.mg_windsor_charge_time_remaining").state == "95"
    assert s("binary_sensor.mg_windsor_charging").state == "on"
    assert s("binary_sensor.mg_windsor_charger_plugged_in").state == "on"
    assert s("binary_sensor.mg_windsor_doors").state == "off"
    assert s("lock.mg_windsor_doors").state == "locked"
    assert s("switch.mg_windsor_air_conditioning").state == "off"
    assert s("device_tracker.mg_windsor_location").attributes["latitude"] == 11.05
    assert s("button.mg_windsor_find_my_car") is not None
    assert s("button.mg_windsor_open_tailgate") is not None
    assert s("sensor.mg_windsor_tyre_pressure_front_left").state == "36.0"
    mock_client.status.assert_awaited_with(include_charge=True)


async def test_not_charging(hass: HomeAssistant, mock_client) -> None:
    mock_client.status.return_value = make_status(charge=None)
    await _setup(hass)
    # Battery falls back to the status fuel level for EVs.
    assert hass.states.get("sensor.mg_windsor_battery").state == "72"
    assert hass.states.get("sensor.mg_windsor_range").state == "240"
    assert hass.states.get("binary_sensor.mg_windsor_charging").state == "unknown"


async def test_lock_and_climate_commands(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass)
    await hass.services.async_call("lock", "unlock", {"entity_id": "lock.mg_windsor_doors"}, blocking=True)
    mock_client.control_door_lock.assert_awaited_with(False)
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.mg_windsor_air_conditioning"}, blocking=True)
    mock_client.control_climate.assert_awaited_with(True)
    await hass.services.async_call("button", "press", {"entity_id": "button.mg_windsor_find_my_car"}, blocking=True)
    mock_client.find_my_car.assert_awaited_once()


async def test_command_unconfirmed_raises(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass)
    mock_client.control_door_lock.side_effect = MgIndiaCommandIndeterminate("no reply")
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await hass.services.async_call("lock", "lock", {"entity_id": "lock.mg_windsor_doors"}, blocking=True)


async def test_no_pin_no_controls(hass: HomeAssistant, mock_client) -> None:
    mock_client.has_pin = False
    await _setup(hass, pin=False)
    assert hass.states.get("lock.mg_windsor_doors") is None
    assert hass.states.get("switch.mg_windsor_air_conditioning") is None
    assert hass.states.get("sensor.mg_windsor_battery") is not None


async def test_auth_failure_starts_reauth(hass: HomeAssistant, mock_client) -> None:
    mock_client.status.side_effect = MgIndiaLoginRejected("password changed")
    data = {CONF_PHONE: "9876543210", CONF_PASSWORD: "old", CONF_VIN: VIN}
    entry = MockConfigEntry(domain=DOMAIN, unique_id=VIN, data=data)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_options_set_pin_and_interval(hass: HomeAssistant, mock_client) -> None:
    mock_client.has_pin = False
    entry = await _setup(hass, pin=False)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 15, CONF_PIN: "4321"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["scan_interval"] == 15
    assert len(entry.data[CONF_PIN_HASH]) == 32
