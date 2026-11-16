"""The hub: words, training queue, results, rollout, reminders and repairs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

from custom_components.sprachmodell.const import DOMAIN
from custom_components.sprachmodell.zentrale import ablage_standard, sprache_aus

from .conftest import wav


async def test_woerter_anlegen_aendern_loeschen(hass: HomeAssistant, geladen, geraet) -> None:
    z = geladen.runtime_data
    geraet("kueche", "Kitchen")
    with pytest.raises(ValueError, match="wort_fehlt"):
        await z.wort_neu({"wort": "  "})
    a = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}, "unbekannt": 1})
    b = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}, "sprache": "de"})
    await hass.async_block_till_done()
    assert (a.id, b.id) == ("hey_lumi", "hey_lumi_2")
    assert a.geraete == {} and b.geraete == {"kueche": "1"}  # ein Platz gehoert nur einem Wort
    assert a.anzeige == "Hey Lumi (custom)" and b.sprache == "de" and a.modell_id == "hey_lumi"
    assert z.wort_fuer("kueche", "1", None) is b and z.wort_fuer("kueche", "2", "HEY_LUMI") is a
    assert z.wort_fuer("kueche", "2", "nix") is None
    with pytest.raises(ValueError, match="wort_fehlt"):
        await z.wort_aendern(a.id, {"wort": ""})
    assert a.wort == "Hey Lumi"
    await z.wort_aendern(a.id, {"geraete": {"kueche": "1"}, "anzeige": "Lumi", "modell_id": "nein"})
    assert a.anzeige == "Lumi" and a.modell_id == "hey_lumi" and b.geraete == {}
    reg = er.async_get(hass)
    assert reg.async_get_entity_id("sensor", DOMAIN, "sprachmodell_hey_lumi_2_training")
    await z.wort_loeschen(b.id, dateien_auch=True)
    await hass.async_block_till_done()
    assert not os.path.isdir(b.speicher.ordner)
    assert reg.async_get_entity_id("sensor", DOMAIN, "sprachmodell_hey_lumi_2_training") is None
    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "wort_hey_lumi_2")}) is None


async def test_vorhandenes_modell_wird_v1(hass: HomeAssistant, geladen) -> None:
    ordner = hass.config.path("custom_wake_words")
    os.makedirs(ordner)
    with open(os.path.join(ordner, "alisa.tflite"), "wb") as datei:
        datei.write(b"TFL3alt")
    w = await geladen.runtime_data.wort_neu({"wort": "Алиса", "modell_id": "alisa"})
    assert w.id == "alisa" and w.speicher.daten["aktiv"] == 1


async def test_training_ablauf(hass: HomeAssistant, geladen, geraet) -> None:
    z = geladen.runtime_data
    g = geraet("kueche", "Kitchen")
    w = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}})
    w.cfg["anzeige"] = "Hey Lumi (custom)"
    z.auftrag(w.id, "von_hand")
    assert z.reihe() == [w.id] and z.naechster_auftrag() is w
    assert w.speicher.daten["training"]["phase"] == "wartet"
    z.trainer_meldet({"info": {"name": "PC"}})
    assert z.trainer_online and z.trainer_info == {"name": "PC"}
    z.trainer_meldet({"wort_id": w.id, "phase": "daten", "prozent": 5})
    assert z.reihe() == [] and w.speicher.daten["training"]["start"]
    z.trainer_meldet({"wort_id": w.id, "phase": "daten", "prozent": 9})
    assert w.speicher.daten["training"]["prozent"] == 9
    z.trainer_meldet({"wort_id": "gibtsnicht"})
    # Trainer startet neu: laufender Lauf ist verloren
    z.trainer_meldet({"neustart": True})
    assert w.speicher.daten["training"]["phase"] == "fehler"
    assert w.speicher.daten["laeufe"][-1]["hinweis"] == "trainer_getrennt"
    # Ergebnis: besser -> einspielen, Geraete neu laden, spaeter auswaehlen
    sel = async_mock_service(hass, "select", "select_option")
    num = async_mock_service(hass, "number", "set_value")
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as neu_laden:
        e = await z.ergebnis(w, b"TFL3neu", {"besser": True, "cutoff": 0.96, "neu": {"trefferquote": 0.9}})
        await hass.async_block_till_done()
    assert e["status"] == "aktiv" and w.speicher.daten["aktiv"] == 1
    assert w.speicher.daten["laeufe"][-1]["ergebnis"] == "eingespielt"
    neu_laden.assert_called_once_with(g.eintrag.entry_id)
    beschreibung = json.load(open(hass.config.path("custom_wake_words", "hey_lumi.json"), encoding="utf-8"))
    assert beschreibung["micro"]["probability_cutoff"] == 0.96
    hass.states.async_set("select.kueche_wake_word", "Okay Nabu", {"options": ["Okay Nabu", "Hey Lumi (custom)"]})
    async_fire_time_changed(hass, datetime.now(UTC) + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert sel[-1].data == {"entity_id": "select.kueche_wake_word", "option": "Hey Lumi (custom)"}
    assert await z.schwelle_setzen(w, 0.951) == ["number.kueche_assistant_1_wake_word_threshold"]
    assert num[-1].data["value"] == 0.95
    assert z.schwellen_jetzt(w) == {"Kitchen": 0.97}
    # nicht besser: bleibt
    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        e2 = await z.ergebnis(w, b"TFL3schlecht", {"besser": False})
    assert e2["status"] == "verworfen" and w.speicher.daten["aktiv"] == 1
    with pytest.raises(ValueError, match="version_fehlt"):
        await z.einspielen(w, 99)
    # abbrechen
    z.auftrag(w.id, "nachts")
    z.trainer_meldet({"wort_id": w.id, "phase": "training"})
    z.abbrechen(w.id)
    assert z.daten["abbrechen"] == w.id and w.speicher.daten["training"] == {"phase": "bereit"}
    z.auftrag(w.id, "nachts")
    z.abbrechen(w.id)
    assert z.reihe() == []
    await hass.async_block_till_done()


async def test_verlorener_lauf(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    w.speicher.daten["training"] = {"phase": "training", "aktualisiert": (datetime.now(UTC) - timedelta(minutes=30)).isoformat()}
    z._verlorene_laeufe()
    assert w.speicher.daten["training"]["phase"] == "fehler"
    await hass.async_block_till_done()


async def test_nachts_und_einstellungen(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    await z.einstellungen_setzen({"uhrzeit": "03:30", "gibtsnicht": 1, "personen": ["Anna"]})
    assert z.opt("uhrzeit") == "03:30" and "gibtsnicht" not in z.daten["einstellungen"]
    assert z.personen() == ["Anna"]
    await z._nachts()
    assert z.reihe() == []  # nichts Neues bewertet
    w.speicher.aufnahme_neu({"id": "x", "quelle": "browser", "urteil": "wort"}, wav())
    await z._nachts()
    assert z.reihe() == [w.id]
    await hass.async_block_till_done()


async def test_personen_aus_ha(hass: HomeAssistant, geladen) -> None:
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    hass.states.async_set("person.max", "home")
    assert geladen.runtime_data.personen() == ["Anna", "person.max"]


async def test_erinnerung_und_aufraeumen(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    w.speicher.aufnahme_neu({"id": "alt", "quelle": "echo", "zeit": (datetime.now(UTC) - timedelta(days=10)).isoformat()}, wav())
    w.speicher.aufnahme_neu({"id": "weg", "quelle": "echo", "urteil": "verworfen"}, wav())
    with patch("custom_components.sprachmodell.zentrale.persistent_notification") as pn:
        await z._stuendlich()
        assert "1 recordings" in pn.async_create.call_args.args[1]
        hass.config.language = "de"
        z.erinnern()
        assert "Aufnahmen warten" in pn.async_create.call_args.args[1]
        await z.einstellungen_setzen({"erinnerung_tage": 30})
        pn.async_dismiss.assert_called()
        await z.einstellungen_setzen({"erinnerung_tage": 0})
    assert "weg" not in w.speicher.daten["aufnahmen"]


async def test_reparaturen(hass: HomeAssistant, geladen, geraet, freezer: FrozenDateTimeFactory) -> None:
    z = geladen.runtime_data
    reg = ir.async_get(hass)
    w = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"weg": "1"}})
    z.reparaturen_pruefen()
    assert reg.async_get_issue(DOMAIN, "device_missing_hey_lumi_weg") is None
    freezer.tick(timedelta(minutes=16))
    z.auftrag(w.id, "von_hand")
    z.reparaturen_pruefen()
    assert reg.async_get_issue(DOMAIN, "device_missing_hey_lumi_weg").translation_placeholders == {"word": "Hey Lumi", "device": "weg"}
    assert reg.async_get_issue(DOMAIN, "trainer_missing") is None
    freezer.tick(timedelta(hours=25))
    z.reparaturen_pruefen()
    assert reg.async_get_issue(DOMAIN, "trainer_missing")
    # Geraet ist wieder da, Trainer meldet sich: beides weg
    geraet("weg", "Back again")
    z.trainer_meldet({})
    z.reparaturen_pruefen()
    assert reg.async_get_issue(DOMAIN, "device_missing_hey_lumi_weg") is None
    assert reg.async_get_issue(DOMAIN, "trainer_missing") is None
    freezer.tick(timedelta(minutes=16))
    hass.services.async_remove("esphome", "weg_wake_clips")
    z.reparaturen_pruefen()
    await hass.config_entries.async_unload(geladen.entry_id)
    assert not [i for i in reg.issues.values() if i.domain == DOMAIN]


async def test_zaehler_loest_holen_aus(hass: HomeAssistant, geladen, geraet) -> None:
    z = geladen.runtime_data
    g = geraet("kueche", "Kitchen")
    await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}})
    g.clip("a")
    hass.states.async_set(g.zaehler, "1")
    hass.states.async_set(g.zaehler, "2")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, datetime.now(UTC) + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert z.offen_gesamt() == 1
    assert z.geraete_zustand()[0]["zaehler"] == 2
    hass.states.async_set(g.zaehler, "kaputt")
    assert z.geraete_zustand()[0]["zaehler"] is None


async def test_jetzt_holen_fehler(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    with patch.object(z.sammler, "holen", side_effect=RuntimeError("x")):
        assert await z.jetzt_holen() is False


async def test_geraete_zustand(hass: HomeAssistant, geladen, geraet) -> None:
    z = geladen.runtime_data
    geraet("kueche", "Kitchen")
    geraet("satellit", "Satellite", clips=False, plaetze=("1",))
    w = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "2"}})
    hass.states.async_set("number.kueche_assistant_1_wake_word_threshold", "unknown")
    zustand = {g["knoten"]: g for g in z.geraete_zustand()}
    assert zustand["kueche"]["plaetze"]["2"]["wort"] == w.id and zustand["kueche"]["clips"]
    assert zustand["kueche"]["plaetze"]["1"]["schwelle"] is None
    assert list(zustand["satellit"]["plaetze"]) == ["1"] and not zustand["satellit"]["clips"]
    assert zustand["satellit"]["zaehler"] is None


def test_hilfen(hass: HomeAssistant) -> None:
    hass.config.language = "pt-BR"
    assert sprache_aus(hass) == "pt"
    hass.config.language = "xx"
    assert sprache_aus(hass) == "en"
    assert ablage_standard(hass).endswith("sprachmodell")
