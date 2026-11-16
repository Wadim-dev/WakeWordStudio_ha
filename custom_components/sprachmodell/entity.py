"""Common base of the entities.

One device "Wake Word Studio" for the hub and one device per word. Entities update
as soon as the hub reports a change (push, no polling).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAME, PANEL_URL, SIGNAL_NEU

if TYPE_CHECKING:
    from .zentrale import Wort, Zentrale

GERAET_ZENTRALE = (DOMAIN, DOMAIN)


def zentrale_geraet(zentrale: Zentrale) -> DeviceInfo:
    return DeviceInfo(
        identifiers={GERAET_ZENTRALE},
        name=NAME,
        manufacturer=NAME,
        model="Hub",
        sw_version=zentrale.version,
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=f"homeassistant://{PANEL_URL}",
    )


def wort_geraet(wort: Wort) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"wort_{wort.id}")},
        name=wort.wort,
        manufacturer=NAME,
        model="Wake word",
        entry_type=DeviceEntryType.SERVICE,
        via_device=GERAET_ZENTRALE,
        configuration_url=f"homeassistant://{PANEL_URL}/uebersicht?wort={wort.id}",
    )


class SprachEntitaet(Entity):
    """Updates itself as soon as the integration reports something new."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, zentrale: Zentrale, schluessel: str, wort: Wort | None = None) -> None:
        self.z = zentrale
        self.w = wort
        self._attr_translation_key = schluessel
        if wort is None:
            self._attr_unique_id = f"{DOMAIN}_{schluessel}"
            self._attr_device_info = zentrale_geraet(zentrale)
        else:
            self._attr_unique_id = f"{DOMAIN}_{wort.id}_{schluessel}"
            self._attr_device_info = wort_geraet(wort)

    @property
    def wort(self) -> Wort:
        """The word of a per-word entity."""
        assert self.w is not None
        return self.w

    @property
    def available(self) -> bool:
        return self.w is None or self.w.id in self.z.woerter

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_NEU, self.async_write_ha_state))


def plattform_anmelden(
    zentrale: Zentrale,
    name: str,
    global_: list[Entity],
    je_wort: Callable[[Wort], list[Entity]],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the entities and remember how to add them for new words."""
    entitaeten: list[Any] = list(global_)
    for wort in zentrale.woerter.values():
        entitaeten += je_wort(wort)
    async_add_entities(entitaeten)
    zentrale.anleger[name] = lambda wort: async_add_entities(je_wort(wort))
