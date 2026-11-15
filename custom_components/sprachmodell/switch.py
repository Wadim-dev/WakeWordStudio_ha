"""Schalter je Wort: nachts trainieren, bessere Version selbst einspielen."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SprachEntitaet, plattform_anmelden


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    z = entry.runtime_data
    plattform_anmelden(
        z, "switch", [],
        lambda w: [Option(z, w, "nachts_trainieren", "nachts"), Option(z, w, "automatisch_einspielen", "automatisch_einspielen")],
        async_add_entities,
    )


class Option(SprachEntitaet, SwitchEntity):
    _plattform = "switch"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, z, w, schluessel: str, option: str) -> None:
        super().__init__(z, schluessel, w)
        self._option = option

    @property
    def is_on(self) -> bool:
        return bool(self.w.cfg.get(self._option))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.z.wort_aendern(self.w.id, {self._option: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.z.wort_aendern(self.w.id, {self._option: False})
