"""Switches per word: train at night, roll out a better version by itself, keep the threshold right by itself,
let the speech recognition pre-review new recordings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SprachEntitaet, plattform_anmelden

if TYPE_CHECKING:
    from . import SprachConfigEntry
    from .zentrale import Wort, Zentrale

PARALLEL_UPDATES = 1


async def async_setup_entry(hass: HomeAssistant, entry: SprachConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    z = entry.runtime_data
    plattform_anmelden(
        z, "switch", [],
        lambda w: [
            Option(z, w, "nachts_trainieren", "nachts"),
            Option(z, w, "automatisch_einspielen", "automatisch_einspielen"),
            Option(z, w, "schwelle_automatisch", "schwelle_automatisch"),
            Option(z, w, "vorpruefen", "vorpruefen"),
        ],
        async_add_entities,
    )


class Option(SprachEntitaet, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, z: Zentrale, w: Wort, schluessel: str, option: str) -> None:
        super().__init__(z, schluessel, w)
        self._option = option

    @property
    def is_on(self) -> bool:
        return bool(self.wort.cfg.get(self._option))

    async def _setzen(self, an: bool) -> None:
        if self.wort.id not in self.z.woerter:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="word_deleted")
        await self.z.wort_aendern(self.wort.id, {self._option: an})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._setzen(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._setzen(False)
