"""Config flow for the MG iSMART India integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_PIN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from mg_ismart_india_client import (
    MgIndiaApiError,
    MgIndiaClient,
    MgIndiaLoginRejected,
    MgIndiaMfaRequired,
    hash_control_pin,
)
from mg_ismart_india_client.crypto import normalize_phone

from .const import (
    CONF_ACTIVE_INTERVAL,
    CONF_PAUSED,
    CONF_PHONE,
    CONF_PIN_HASH,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_TOKEN,
    CONF_SESSION_UID,
    CONF_VIN,
    DEFAULT_ACTIVE_INTERVAL_MIN,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    MAX_ACTIVE_INTERVAL_MIN,
    MAX_SCAN_INTERVAL_MIN,
    MIN_ACTIVE_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
)
from .coordinator import MgConfigEntry

_LOGGER = logging.getLogger(__name__)


def _minutes(low: int, high: int) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=low, max=high, step=1, unit_of_measurement="min",
            mode=NumberSelectorMode.BOX,
        )
    )

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEL)
        ),
        vol.Required(CONF_PASSWORD): _PASSWORD,
        vol.Optional(CONF_PIN): _PASSWORD,
        vol.Optional(CONF_VIN): str,
    }
)


async def _validate(
    flow: ConfigFlow, phone: str, password: str, vin: str | None, pin: str | None
) -> tuple[dict[str, str], dict[str, Any]]:
    """Log in once and pick the vehicle. Returns (errors, entry data)."""
    errors: dict[str, str] = {}
    try:
        phone = normalize_phone(phone)
    except MgIndiaApiError:
        return {CONF_PHONE: "invalid_phone"}, {}
    pin_hash = None
    if pin:
        try:
            pin_hash = hash_control_pin(pin.strip())
        except MgIndiaApiError:
            return {CONF_PIN: "invalid_pin"}, {}
    client = MgIndiaClient(
        async_get_clientsession(flow.hass),
        phone=phone,
        password=password,
        vin=(vin or "").strip().upper() or None,
        pin_hash=pin_hash,
    )
    try:
        # One login only: MG India counts every attempt against a daily quota.
        await client.login()
        await client.vehicles()
        if pin_hash:
            await client.verify_pin()
    except MgIndiaMfaRequired:
        errors["base"] = "mfa_required"
    except MgIndiaLoginRejected:
        errors["base"] = "invalid_auth"
    except MgIndiaApiError as err:
        if "PIN" in str(err):
            errors[CONF_PIN] = "invalid_pin"
        elif "absent from the account" in str(err):
            errors[CONF_VIN] = "vin_not_found"
        else:
            _LOGGER.warning("MG iSMART India setup failed: %s", err)
            errors["base"] = "cannot_connect"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error during MG iSMART India setup")
        errors["base"] = "unknown"
    if errors:
        return errors, {}
    if client.vehicle is None:
        return {"base": "no_vehicle"}, {}
    data = {
        CONF_PHONE: phone,
        CONF_PASSWORD: password,
        CONF_VIN: client.vehicle.vin,
        "title": f"MG {client.vehicle.model or client.vehicle.name}",
    }
    if client.uid and client.token:
        # Reuse this login's session at startup instead of logging in again.
        data[CONF_SESSION_UID] = client.uid
        data[CONF_SESSION_TOKEN] = client.token
    if pin_hash:
        data[CONF_PIN_HASH] = pin_hash
    return {}, data


class MgIsmartIndiaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MG iSMART India."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, data = await _validate(
                self,
                user_input[CONF_PHONE],
                user_input[CONF_PASSWORD],
                user_input.get(CONF_VIN),
                user_input.get(CONF_PIN),
            )
            if not errors:
                await self.async_set_unique_id(data[CONF_VIN])
                self._abort_if_unique_id_configured()
                title = data.pop("title")
                return self.async_create_entry(title=title, data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {k: v for k, v in (user_input or {}).items() if k != CONF_PASSWORD}
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, data = await _validate(
                self,
                entry.data[CONF_PHONE],
                user_input[CONF_PASSWORD],
                entry.data.get(CONF_VIN),
                user_input.get(CONF_PIN),
            )
            if not errors:
                data.pop("title")
                if CONF_PIN_HASH not in data and CONF_PIN_HASH in entry.data:
                    data[CONF_PIN_HASH] = entry.data[CONF_PIN_HASH]
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_PASSWORD): _PASSWORD, vol.Optional(CONF_PIN): _PASSWORD}
            ),
            description_placeholders={"phone": entry.data[CONF_PHONE]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: MgConfigEntry) -> MgOptionsFlow:
        return MgOptionsFlow()


class MgOptionsFlow(OptionsFlowWithReload):
    """Polling interval and remote-control PIN."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry
        if user_input is not None:
            pin = (user_input.pop(CONF_PIN, "") or "").strip()
            if pin:
                try:
                    pin_hash = hash_control_pin(pin)
                except MgIndiaApiError:
                    errors[CONF_PIN] = "invalid_pin"
                else:
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_PIN_HASH: pin_hash}
                    )
            if not errors:
                return self.async_create_entry(
                    data={
                        CONF_SCAN_INTERVAL: max(
                            int(user_input[CONF_SCAN_INTERVAL]), MIN_SCAN_INTERVAL_MIN
                        ),
                        CONF_ACTIVE_INTERVAL: max(
                            int(user_input[CONF_ACTIVE_INTERVAL]),
                            MIN_ACTIVE_INTERVAL_MIN,
                        ),
                        CONF_PAUSED: bool(user_input.get(CONF_PAUSED, False)),
                    }
                )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=max(
                        int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN)),
                        MIN_SCAN_INTERVAL_MIN,
                    ),
                ): _minutes(MIN_SCAN_INTERVAL_MIN, MAX_SCAN_INTERVAL_MIN),
                vol.Required(
                    CONF_ACTIVE_INTERVAL,
                    default=entry.options.get(
                        CONF_ACTIVE_INTERVAL, DEFAULT_ACTIVE_INTERVAL_MIN
                    ),
                ): _minutes(MIN_ACTIVE_INTERVAL_MIN, MAX_ACTIVE_INTERVAL_MIN),
                vol.Required(
                    CONF_PAUSED, default=bool(entry.options.get(CONF_PAUSED, False))
                ): BooleanSelector(),
                vol.Optional(CONF_PIN): _PASSWORD,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
