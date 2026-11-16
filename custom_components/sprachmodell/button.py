"""Buttons: fetch recordings now (hub), start training (per word)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
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
    plattform_anmelden(z, "button", [JetztHolen(z)], lambda w: [TrainingStarten(z, w)], async_add_entities)


class TrainingStarten(SprachEntitaet, ButtonEntity):
    def __init__(self, z: Zentrale, w: Wort) -> None:
        super().__init__(z, "training_starten", w)

    async def async_press(self) -> None:
        if self.wort.id not in self.z.woerter:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="word_deleted")
        self.z.auftrag(self.wort.id, "von_hand")


class JetztHolen(SprachEntitaet, ButtonEntity):
    def __init__(self, z: Zentrale) -> None:
        super().__init__(z, "jetzt_holen")

    async def async_press(self) -> None:
        if not await self.z.jetzt_holen():
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="fetch_failed")
