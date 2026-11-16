"""Diagnostics never contain the trainer key or names of people."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant

from custom_components.sprachmodell.diagnostics import async_get_config_entry_diagnostics

from .conftest import wav


async def test_diagnose(hass: HomeAssistant, geladen, geraet) -> None:
    z = geladen.runtime_data
    geraet("kueche", "Kitchen")
    w = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}})
    await z.einstellungen_setzen({"personen": ["Anna", "Max"]})
    w.speicher.aufnahme_neu({"id": "a", "quelle": "browser", "urteil": "wort", "person": "Anna"}, wav())
    w.speicher.version_neu(b"TFL3", {"neu": {"trefferquote": 0.9, "je_person": {"Anna": {}}}})
    d = await async_get_config_entry_diagnostics(hass, geladen)
    text = json.dumps(d)
    assert z.schluessel not in text and "Anna" not in text
    assert d["schluessel"] == "**REDACTED**" and d["settings"]["personen"] == "**REDACTED**"
    assert d["words"]["hey_lumi"]["statistics"]["bewertet"] == 1
    assert d["words"]["hey_lumi"]["versions"][0]["result"]["trefferquote"] == 0.9
    assert d["devices"][0]["name"] == "Kitchen"
