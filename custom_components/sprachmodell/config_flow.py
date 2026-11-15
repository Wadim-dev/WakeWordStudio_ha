"""Einrichtung: ein Klick, alles hat sinnvolle Standardwerte."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TimeSelector,
)

from .const import (
    ANZEIGE_STANDARD,
    DOMAIN,
    MODELL_ID_STANDARD,
    NAME,
    OPT_AUFBEWAHREN,
    OPT_AUTO,
    OPT_ERINNERUNG,
    OPT_NACHTS,
    OPT_NUR_WORT1,
    OPT_PERSONEN,
    OPT_UHRZEIT,
    ORDNER_STANDARD,
    STANDARD_OPTIONEN,
    WORT_STANDARD,
)


class SprachmodellConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)
        schema = vol.Schema({
            vol.Required("wort", default=WORT_STANDARD): TextSelector(),
            vol.Required("anzeige", default=ANZEIGE_STANDARD): TextSelector(),
            vol.Required("modell_id", default=MODELL_ID_STANDARD): TextSelector(),
            vol.Required("ordner", default=ORDNER_STANDARD): TextSelector(),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SprachmodellOptionen()


class SprachmodellOptionen(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            daten = dict(user_input)
            daten[OPT_PERSONEN] = [p.strip() for p in str(daten.get(OPT_PERSONEN, "")).split(",") if p.strip()]
            return self.async_create_entry(data=daten)
        o = {**STANDARD_OPTIONEN, **self.config_entry.options}
        schema = vol.Schema({
            vol.Optional(OPT_PERSONEN, default=", ".join(o[OPT_PERSONEN])): TextSelector(TextSelectorConfig()),
            vol.Required(OPT_NACHTS, default=o[OPT_NACHTS]): BooleanSelector(),
            vol.Required(OPT_UHRZEIT, default=o[OPT_UHRZEIT]): TimeSelector(),
            vol.Required(OPT_AUTO, default=o[OPT_AUTO]): BooleanSelector(),
            vol.Required(OPT_ERINNERUNG, default=o[OPT_ERINNERUNG]): NumberSelector(
                NumberSelectorConfig(min=0, max=60, step=1, mode=NumberSelectorMode.BOX)),
            vol.Required(OPT_AUFBEWAHREN, default=o[OPT_AUFBEWAHREN]): NumberSelector(
                NumberSelectorConfig(min=7, max=365, step=1, mode=NumberSelectorMode.BOX)),
            vol.Required(OPT_NUR_WORT1, default=o[OPT_NUR_WORT1]): BooleanSelector(),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
