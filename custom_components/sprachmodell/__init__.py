"""Sprachmodell: eigene Aktivierungswoerter pruefen, trainieren und einspielen.

- Sprachgeraete mit ESPHome (z. B. TECHO, Schalter "Keep wake clips") heben bei
  jedem Aufwachen und jedem knappen Fast-Aufwachen ein paar Sekunden Ton auf.
  Die Integration holt sie ab und ordnet sie dem Wort zu, das auf diesem
  Platz des Geraets sitzt.
- In der Seitenleiste "Sprachmodell" legt man Woerter an, waehlt Geraete,
  hoert Aufnahmen nach, nimmt neue im Browser auf oder laedt Zips hoch.
- Ein Trainer (HA-App oder Docker-Container) holt die bewerteten Aufnahmen,
  trainiert eine neue Version, testet sie ehrlich gegen zurueckgehaltene
  Aufnahmen und schickt sie zurueck. Ist sie besser, spielt die Integration
  sie an den Geraeten des Worts ein; sonst bleibt die alte.
"""

from __future__ import annotations

import os

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN, PANEL_ELEMENT, PANEL_ICON, PANEL_TITEL, PANEL_URL, STATIC_URL
from .zentrale import Wort, Zentrale

PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH, Platform.UPDATE]
_STATISCH = f"{DOMAIN}_statisch"

type SprachConfigEntry = ConfigEntry[Zentrale]


async def async_setup_entry(hass: HomeAssistant, entry: SprachConfigEntry) -> bool:
    """Integration starten."""
    zentrale = Zentrale(hass, entry)
    zentrale.version = str((await async_get_integration(hass, DOMAIN)).version or "0")
    entry.runtime_data = zentrale
    await zentrale.starten()

    from .api import ansichten_anmelden  # noqa: PLC0415 - braucht die Zentrale

    ansichten_anmelden(hass)

    if not hass.data.get(_STATISCH):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, os.path.join(os.path.dirname(__file__), "frontend"), cache_headers=False)]
        )
        hass.data[_STATISCH] = True
    if PANEL_URL not in hass.data.get(frontend.DATA_PANELS, {}):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title=PANEL_TITEL,
            sidebar_icon=PANEL_ICON,
            module_url=f"{STATIC_URL}/sprachmodell-panel.js?v={zentrale.version}",
            require_admin=False,
            config={},
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SprachConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.stoppen()
        frontend.async_remove_panel(hass, PANEL_URL)
    return ok


def zentrale_holen(hass: HomeAssistant) -> Zentrale | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if isinstance(getattr(entry, "runtime_data", None), Zentrale):
            return entry.runtime_data
    return None


__all__ = ["DOMAIN", "Wort", "Zentrale", "zentrale_holen"]
