from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_BATTERY_MODE,
    CONF_BATTERY_POWER,
    CONF_NORDPOOL_PRICE,
    CONF_GRID_POWER,
    CONF_SCAN_INTERVAL,
    CONF_FUSEBOX_FEE,
    CONF_BASELINE_ENABLED,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_FUSEBOX_FEE,
    DEFAULT_BASELINE_ENABLED,
    CONF_NPS_SOURCE,
    DEFAULT_NPS_SOURCE,
)


class MFFRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="MFFR Profit Tracker", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_BATTERY_MODE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["input_select"])  # type: ignore[arg-type]
                ),
                vol.Required(CONF_BATTERY_POWER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor"])  # type: ignore[arg-type]
                ),
                vol.Required(CONF_NORDPOOL_PRICE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor"])  # type: ignore[arg-type]
                ),
                vol.Optional(CONF_GRID_POWER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor"])  # type: ignore[arg-type]
                ),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=60, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_FUSEBOX_FEE, default=DEFAULT_FUSEBOX_FEE): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_BASELINE_ENABLED, default=DEFAULT_BASELINE_ENABLED): selector.BooleanSelector(),
                vol.Optional(CONF_NPS_SOURCE, default=DEFAULT_NPS_SOURCE): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=["ha", "api", "auto"], mode=selector.SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_import(self, user_input: dict[str, Any]) -> config_entries.ConfigEntry:
        return await self.async_step_user(user_input)


class MFFROptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)

        data = {**self.entry.data, **self.entry.options}
        schema = vol.Schema(
            {
                vol.Required(CONF_BATTERY_MODE, default=data.get(CONF_BATTERY_MODE)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["input_select"])  # type: ignore[arg-type]
                ),
                vol.Required(CONF_BATTERY_POWER, default=data.get(CONF_BATTERY_POWER)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor"])  # type: ignore[arg-type]
                ),
                vol.Required(CONF_NORDPOOL_PRICE, default=data.get(CONF_NORDPOOL_PRICE)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor"])  # type: ignore[arg-type]
                ),
                vol.Optional(CONF_GRID_POWER, default=data.get(CONF_GRID_POWER)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor"])  # type: ignore[arg-type]
                ),
                vol.Optional(CONF_SCAN_INTERVAL, default=data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=60, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_FUSEBOX_FEE, default=data.get(CONF_FUSEBOX_FEE, DEFAULT_FUSEBOX_FEE)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_BASELINE_ENABLED, default=data.get(CONF_BASELINE_ENABLED, DEFAULT_BASELINE_ENABLED)): selector.BooleanSelector(),
                vol.Optional(CONF_NPS_SOURCE, default=data.get(CONF_NPS_SOURCE, DEFAULT_NPS_SOURCE)): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=["ha", "api", "auto"], mode=selector.SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


async def async_get_options_flow(entry: config_entries.ConfigEntry) -> MFFROptionsFlow:
    return MFFROptionsFlow(entry)
