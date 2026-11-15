"""Gemeinsame Grundlage der Entitaeten.

Ein Geraet "Sprachmodell" fuer die Zentrale und je Wort ein eigenes Geraet.
Entitaets-IDs sind fest und sprachunabhaengig, z. B. sensor.sprachmodell_pruefliste
und sensor.sprachmodell_<wort>_trefferquote.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME, PANEL_URL, SIGNAL_NEU

GERAET_ZENTRALE = (DOMAIN, "sprachmodell")


def zentrale_geraet(zentrale) -> DeviceInfo:
    return DeviceInfo(
        identifiers={GERAET_ZENTRALE},
        name=NAME,
        manufacturer="Sprachmodell",
        model="Zentrale",
        sw_version=zentrale.version,
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=f"homeassistant://{PANEL_URL}",
    )


class SprachEntitaet(Entity):
    """Aktualisiert sich, sobald die Integration etwas Neues meldet (kein Abfragen)."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _plattform = "sensor"

    def __init__(self, zentrale, schluessel: str, wort=None) -> None:
        self.z = zentrale
        self.w = wort
        self._attr_translation_key = schluessel
        if wort is None:
            self._attr_unique_id = f"{DOMAIN}_{schluessel}"
            self.entity_id = f"{self._plattform}.{DOMAIN}_{schluessel}"
            self._attr_device_info = zentrale_geraet(zentrale)
        else:
            self._attr_unique_id = f"{DOMAIN}_{wort.id}_{schluessel}"
            self.entity_id = f"{self._plattform}.{DOMAIN}_{wort.id}_{schluessel}"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"wort_{wort.id}")},
                name=f"{NAME} {wort.wort}",
                manufacturer="Sprachmodell",
                model="Aktivierungswort",
                entry_type=DeviceEntryType.SERVICE,
                via_device=GERAET_ZENTRALE,
                configuration_url=f"homeassistant://{PANEL_URL}/uebersicht?wort={wort.id}",
            )

    @property
    def available(self) -> bool:
        return self.w is None or self.w.id in self.z.woerter

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_NEU, self.async_write_ha_state))


def plattform_anmelden(zentrale, name: str, global_: list, je_wort, async_add_entities) -> None:
    """Entitaeten anlegen und merken, wie man sie fuer neue Woerter anlegt."""
    entitaeten = list(global_)
    for wort in zentrale.woerter.values():
        entitaeten += je_wort(wort)
    async_add_entities(entitaeten)
    zentrale.anleger[name] = lambda wort: async_add_entities(je_wort(wort))
