"""Knoepfe: Training starten, Aufnahmen jetzt holen."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SprachEntitaet


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    z = entry.runtime_data
    async_add_entities([TrainingStarten(z), JetztHolen(z)])


class TrainingStarten(SprachEntitaet, ButtonEntity):
    _plattform = "button"
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, z) -> None:
        super().__init__(z, "training_starten")

    async def async_press(self) -> None:
        self.z.auftrag("von Hand")


class JetztHolen(SprachEntitaet, ButtonEntity):
    _plattform = "button"
    _attr_icon = "mdi:download-outline"

    def __init__(self, z) -> None:
        super().__init__(z, "jetzt_holen")

    async def async_press(self) -> None:
        await self.z._takt()  # noqa: SLF001
