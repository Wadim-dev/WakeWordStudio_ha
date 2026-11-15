"""Gemeinsame Grundlage der Entitaeten: ein Geraet "Sprachmodell"."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME, PANEL_URL, SIGNAL_NEU


class SprachEntitaet(Entity):
    """Aktualisiert sich, sobald die Integration etwas Neues meldet (kein Abfragen)."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _plattform = "sensor"

    def __init__(self, zentrale, schluessel: str) -> None:
        self.z = zentrale
        self._attr_translation_key = schluessel
        self._attr_unique_id = f"{DOMAIN}_{schluessel}"
        # Feste, sprachunabhaengige Entitaets-IDs (z. B. sensor.sprachmodell_pruefliste)
        self.entity_id = f"{self._plattform}.{DOMAIN}_{schluessel}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "sprachmodell")},
            name=NAME,
            manufacturer="Wadim-dev",
            model="Eigenes Aktivierungswort",
            sw_version=zentrale.version,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"homeassistant://{PANEL_URL}",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_NEU, self.async_write_ha_state))
