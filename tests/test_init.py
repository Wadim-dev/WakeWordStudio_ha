"""Setting up, unloading and cleaning up."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sprachmodell import async_remove_config_entry_device, zentrale_holen
from custom_components.sprachmodell.const import DOMAIN


async def test_setup_and_unload(hass: HomeAssistant, geladen) -> None:
    assert geladen.state is ConfigEntryState.LOADED
    assert zentrale_holen(hass) is geladen.runtime_data
    reg = er.async_get(hass)
    assert reg.async_get_entity_id("sensor", DOMAIN, "sprachmodell_pruefliste")
    assert await hass.config_entries.async_unload(geladen.entry_id)
    assert geladen.state is ConfigEntryState.NOT_LOADED
    assert zentrale_holen(hass) is None


async def test_ablage_nicht_erreichbar(hass: HomeAssistant, tmp_path) -> None:
    datei = tmp_path / "keinordner"
    datei.write_text("x")
    e = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"ordner": str(datei)})
    e.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(e.entry_id)
    assert e.state is ConfigEntryState.SETUP_RETRY
    assert e.reason and "keinordner" in e.reason


async def test_aufraeumen_beim_start(hass: HomeAssistant, eintrag) -> None:
    """The old update entity and devices of deleted words are removed on start."""
    eintrag.add_to_hass(hass)
    reg = er.async_get(hass)
    alt = reg.async_get_or_create("update", DOMAIN, "sprachmodell_update", config_entry=eintrag)
    dreg = dr.async_get(hass)
    weg = dreg.async_get_or_create(config_entry_id=eintrag.entry_id, identifiers={(DOMAIN, "wort_geloescht")})
    fremd = dreg.async_get_or_create(config_entry_id=eintrag.entry_id, identifiers={("anders", "x")})
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get(alt.entity_id) is None
    assert dreg.async_get(weg.id) is None and dreg.async_get(fremd.id) is None
    z = eintrag.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    await hass.async_block_till_done()
    hub = dreg.async_get_device(identifiers={(DOMAIN, DOMAIN)})
    wortgeraet = dreg.async_get_device(identifiers={(DOMAIN, f"wort_{w.id}")})
    assert hub.name == "Wake Word Studio" and wortgeraet.name == "Hey Lumi" and wortgeraet.via_device_id == hub.id
    assert not await async_remove_config_entry_device(hass, eintrag, hub)
    assert not await async_remove_config_entry_device(hass, eintrag, wortgeraet)
    await z.wort_loeschen(w.id, False)
    assert await async_remove_config_entry_device(hass, eintrag, wortgeraet)
    await hass.config_entries.async_unload(eintrag.entry_id)


async def test_panel(hass: HomeAssistant, eintrag) -> None:
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")
    eintrag.add_to_hass(hass)
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    panel = hass.data["frontend_panels"]["wake-word-studio"]
    assert panel.sidebar_title == "Wake Word Studio"
    assert panel.config["_panel_custom"]["name"] == "sprachmodell-panel"
    # Neu laden: Panel und Ansichten nur einmal
    assert await hass.config_entries.async_reload(eintrag.entry_id)
    assert "wake-word-studio" in hass.data["frontend_panels"]
    await hass.config_entries.async_unload(eintrag.entry_id)
    assert "wake-word-studio" not in hass.data["frontend_panels"]
