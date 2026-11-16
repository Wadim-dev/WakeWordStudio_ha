"""Wake Word Studio: review, train and roll out your own wake words.

- ESPHome voice devices are found by themselves. Firmware that keeps wake clips
  (for example the switch "Keep wake clips") saves a few seconds of audio on every
  wake-up and every near miss; the integration collects them and files them under
  the word that sits on that slot of the device.
- The sidebar panel "Wake Word Studio" creates words, assigns device slots, plays
  recordings back for review, records new ones in the browser and takes zip uploads.
- A trainer (Home Assistant app or Docker container) fetches the reviewed recordings,
  trains a new version, tests it honestly against held-back recordings and sends it
  back. If it is better, the integration rolls it out to the devices of the word.
"""

from __future__ import annotations

import os

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.loader import async_get_integration

from .const import DOMAIN, PANEL_ELEMENT, PANEL_ICON, PANEL_TITEL, PANEL_URL, STATIC_URL
from .zentrale import Wort, Zentrale

PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]
_STATISCH = f"{DOMAIN}_statisch"
# Earlier versions had their own update entity (now updates come through HACS)
_ALTE_ENTITAETEN = (("update", f"{DOMAIN}_update"),)

type SprachConfigEntry = ConfigEntry[Zentrale]


async def async_setup_entry(hass: HomeAssistant, entry: SprachConfigEntry) -> bool:
    """Start the hub, the API, the panel and the entities."""
    zentrale = Zentrale(hass, entry)
    zentrale.version = str((await async_get_integration(hass, DOMAIN)).version or "0")
    try:
        await zentrale.starten()
    except OSError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="storage_unavailable",
            translation_placeholders={"folder": zentrale.ablage, "error": str(err)},
        ) from err
    entry.runtime_data = zentrale

    reg = er.async_get(hass)
    for plattform, unique_id in _ALTE_ENTITAETEN:
        if entity_id := reg.async_get_entity_id(plattform, DOMAIN, unique_id):
            reg.async_remove(entity_id)

    if hass.http is not None:
        from .api import ansichten_anmelden

        ansichten_anmelden(hass)
        if "frontend" in hass.config.components:
            await _panel_anmelden(hass, zentrale.version)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _panel_anmelden(hass: HomeAssistant, version: str) -> None:
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
            module_url=f"{STATIC_URL}/sprachmodell-panel.js?v={version}",
            require_admin=False,
            config={},
        )


async def async_unload_entry(hass: HomeAssistant, entry: SprachConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.stoppen()
        frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    return ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: SprachConfigEntry, device: dr.DeviceEntry
) -> bool:
    """A word's device can be deleted by hand once the word is gone."""
    return not entry.runtime_data.geraet_gehoert(device)


def zentrale_holen(hass: HomeAssistant) -> Zentrale | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if isinstance(getattr(entry, "runtime_data", None), Zentrale):
            return entry.runtime_data
    return None


__all__ = ["DOMAIN", "Wort", "Zentrale", "zentrale_holen"]
