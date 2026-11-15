"""Schalter: nachts trainieren, bessere Version selbst einspielen."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import OPT_AUTO, OPT_NACHTS
from .entity import SprachEntitaet


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    z = entry.runtime_data
    async_add_entities([Option(z, "nachts_trainieren", OPT_NACHTS), Option(z, "automatisch_einspielen", OPT_AUTO)])


class Option(SprachEntitaet, SwitchEntity):
    _plattform = "switch"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, z, schluessel: str, option: str) -> None:
        super().__init__(z, schluessel)
        self._option = option

    @property
    def is_on(self) -> bool:
        return bool(self.z.opt(self._option))

    def _setzen(self, wert: bool) -> None:
        self.hass.config_entries.async_update_entry(
            self.z.entry, options={**self.z.entry.options, self._option: wert}
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._setzen(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._setzen(False)
