"""Knoepfe: Aufnahmen jetzt holen (Zentrale), Training starten (je Wort)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SprachEntitaet, plattform_anmelden


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    z = entry.runtime_data
    plattform_anmelden(z, "button", [JetztHolen(z)], lambda w: [TrainingStarten(z, w)], async_add_entities)


class TrainingStarten(SprachEntitaet, ButtonEntity):
    _plattform = "button"
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, z, w) -> None:
        super().__init__(z, "training_starten", w)

    async def async_press(self) -> None:
        self.z.auftrag(self.w.id, "von_hand")


class JetztHolen(SprachEntitaet, ButtonEntity):
    _plattform = "button"
    _attr_icon = "mdi:download-outline"

    def __init__(self, z) -> None:
        super().__init__(z, "jetzt_holen")

    async def async_press(self) -> None:
        await self.z.jetzt_holen()
