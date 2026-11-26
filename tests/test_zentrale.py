"""The hub: words, training queue, results, rollout, reminders and repairs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import CoreState, HomeAssistant
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
    geraet("kueche", "Kitchen")
    w = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}})
    w.cfg["anzeige"] = "Hey Lumi (custom)"
    z.auftrag(w.id, "von_hand")
    assert z.reihe() == [w.id] and z.naechster_auftrag() is w
    assert z.naechster_auftrag() is None  # just handed out: a second trainer does not get it as well
    z._abgeholt[w.id] -= 1000
    assert z.naechster_auftrag() is w  # the trainer never confirmed: offered again
    assert w.speicher.daten["training"]["phase"] == "wartet"
    z.trainer_meldet({"info": {"name": "PC"}})
    assert z.trainer_online and z.trainer_info == {"name": "PC"}
    z.trainer_meldet({"wort_id": w.id, "phase": "daten", "prozent": 5})
    assert z.reihe() == [] and w.speicher.daten["training"]["start"]
    z.trainer_meldet({"wort_id": w.id, "phase": "daten", "prozent": 9})
    assert w.speicher.daten["training"]["prozent"] == 9
    z.trainer_meldet({"wort_id": "gibtsnicht"})
    # Trainer restarts mid-run (memory): the run is queued again and the trainer is asked to use less memory
    for n in (1, 2):
        z.trainer_meldet({"neustart": True})
        t = w.speicher.daten["training"]
        assert t["phase"] == "wartet" and t["grund"] == "fortsetzen" and t["neustarts"] == n
        assert z.reihe() == [w.id] and w.speicher.daten["auftrag"]["sparsam"] == n
        z.trainer_meldet({"wort_id": w.id, "phase": "training", "prozent": 50})
        assert w.speicher.daten["training"]["neustarts"] == n
    # third time: the run ends with an error
    z.trainer_meldet({"neustart": True})
    assert w.speicher.daten["training"]["phase"] == "fehler"
    assert w.speicher.daten["laeufe"][-1]["hinweis"] == "trainer_getrennt"
    # Ergebnis: besser -> Dateien schreiben, Neustart-Meldung, nach dem Neustart auswaehlen
    sel = async_mock_service(hass, "select", "select_option")
    num = async_mock_service(hass, "number", "set_value")
    reg = ir.async_get(hass)
    e = await z.ergebnis(w, b"TFL3neu", {"besser": True, "cutoff": 0.96, "neu": {"trefferquote": 0.9}})
    await hass.async_block_till_done()
    assert e["status"] == "aktiv" and w.speicher.daten["aktiv"] == 1
    assert w.speicher.daten["laeufe"][-1]["ergebnis"] == "eingespielt"
    assert z.daten["nach_neustart"] == [w.id]
    meldung = reg.async_get_issue(DOMAIN, "restart_to_roll_out")
    assert meldung.is_fixable and meldung.translation_placeholders == {"words": "Hey Lumi"}
    beschreibung = json.load(open(hass.config.path("custom_wake_words", "hey_lumi.json"), encoding="utf-8"))
    assert beschreibung["micro"]["probability_cutoff"] == 0.96
    hass.states.async_set("select.kueche_wake_word", "Okay Nabu", {"options": ["Okay Nabu", "Hey Lumi (custom)"]})
    await z.nach_neustart()
    assert sel[-1].data == {"entity_id": "select.kueche_wake_word", "option": "Hey Lumi (custom)"}
    assert z.daten["nach_neustart"] == [] and reg.async_get_issue(DOMAIN, "restart_to_roll_out") is None
    # the threshold follows the tested value by itself
    assert num[-1].data == {"entity_id": ["number.kueche_assistant_1_wake_word_threshold"], "value": 0.96}
    assert w.speicher.daten["schwelle_auto"]["quelle"] == "test" and w.speicher.daten["aktiv_seit"]
    assert await z.schwelle_setzen(w, 0.951) == ["number.kueche_assistant_1_wake_word_threshold"]
    assert num[-1].data["value"] == 0.95
    assert z.schwellen_jetzt(w) == {"Kitchen": 0.97}
    # nicht besser: bleibt
    e2 = await z.ergebnis(w, b"TFL3schlecht", {"besser": False})
    assert e2["status"] == "verworfen" and w.speicher.daten["aktiv"] == 1
    # as good (difference within chance): stays as well, but says so, and remembers which version it was compared with
    e3 = await z.ergebnis(w, b"TFL3gleich", {"besser": False, "alt": {"trefferquote": 1.0},
                                              "vergleich": {"urteil": "gleich", "grund": "gleich", "zeilen": []}})
    assert e3["status"] == "verworfen" and e3["bericht"]["alt_nr"] == 1
    assert w.speicher.daten["laeufe"][-1]["ergebnis"] == "gleich" and w.speicher.daten["training"]["gleich"]
    with pytest.raises(ValueError, match="version_fehlt"):
        await z.einspielen(w, 99)
    # abbrechen
    z.auftrag(w.id, "nachts")
    z.trainer_meldet({"wort_id": w.id, "phase": "training"}, "pc")
    z.abbrechen(w.id)
    assert z.daten["abbrechen_bei"] == {w.id: "pc"} and w.speicher.daten["training"] == {"phase": "bereit"}
    assert z.abbruch_fuer("proxmox") is None  # only the trainer running it is told
    assert z.abbruch_fuer("pc") == w.id and z.abbruch_fuer("pc") is None
    z.auftrag(w.id, "nachts")
    z.abbrechen(w.id)
    assert z.reihe() == []
    await hass.async_block_till_done()


async def test_verlorener_lauf(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    w.speicher.daten["training"] = {"phase": "training", "aktualisiert": (datetime.now(UTC) - timedelta(minutes=30)).isoformat()}
    z._verlorene_laeufe()  # silent for 30 min: queued again with less memory
    assert w.speicher.daten["training"]["phase"] == "wartet" and w.speicher.daten["auftrag"]["sparsam"] == 1
    w.speicher.daten["training"].update({"phase": "training", "neustarts": 2,
                                         "aktualisiert": (datetime.now(UTC) - timedelta(minutes=30)).isoformat()})
    z._verlorene_laeufe()  # already restarted twice: error
    assert w.speicher.daten["training"]["phase"] == "fehler"
    await hass.async_block_till_done()


async def test_ha_neustart_waehrend_training(hass: HomeAssistant, geladen) -> None:
    """A Home Assistant restart must not end a run: the trainer keeps working and reports again."""
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    alt = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    w.speicher.daten["training"] = {"phase": "training", "prozent": 40, "start": alt, "aktualisiert": alt}
    await hass.async_add_executor_job(w.speicher.speichern)
    assert await hass.config_entries.async_reload(geladen.entry_id)
    await hass.async_block_till_done()
    z = geladen.runtime_data
    t = z.woerter[w.id].speicher.daten["training"]
    assert t["phase"] == "training" and t["prozent"] == 40 and t["start"] == alt
    z._verlorene_laeufe()  # fresh grace period of 20 minutes
    assert z.woerter[w.id].speicher.daten["training"]["phase"] == "training"
    # Heartbeat with the full state keeps it going
    z.trainer_meldet({"wort_id": w.id, "phase": "training", "prozent": 55, "schritt": "training"})
    assert z.woerter[w.id].speicher.daten["training"]["prozent"] == 55
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
    assert z.reihe() == []  # one new review is not enough by default (20)
    with pytest.raises(ValueError):
        await z.einstellungen_setzen({"nachts_min_neu": None})
    z.daten["einstellungen"]["nachts_min_neu"] = None  # as an older version could have stored it
    await z._nachts()
    assert z.reihe() == []  # broken value falls back to the default
    del z.daten["einstellungen"]["nachts_min_neu"]
    await z.einstellungen_setzen({"nachts_min_neu": 1})
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


async def test_trainer_ausgebremst(hass: HomeAssistant, geladen, freezer: FrozenDateTimeFactory) -> None:
    z = geladen.runtime_data
    reg = ir.async_get(hass)
    w = await z.wort_neu({"wort": "Hey Lumi"})
    z.auftrag(w.id, "von_hand")
    assert z.trainer_last() == {} and z.engpass() is None
    langsam = {"cpu": 8, "speicher_warten": 70, "platte_warten": 3}
    z.trainer_meldet({"wort_id": w.id, "phase": "training", "prozent": 20, "live": {"system": langsam}})
    assert z.engpass() == "memory" and z.trainer_last()["cpu"] == 8
    z.reparaturen_pruefen()
    assert reg.async_get_issue(DOMAIN, "trainer_slow") is None  # not yet: has to last 15 minutes
    freezer.tick(timedelta(minutes=16))
    z.trainer_meldet({"wort_id": w.id, "phase": "training", "prozent": 21, "live": {"system": langsam}})
    z.reparaturen_pruefen()
    assert reg.async_get_issue(DOMAIN, "trainer_slow").translation_key == "trainer_slow_memory"
    # disk instead of memory
    z.trainer_meldet({"wort_id": w.id, "phase": "training", "prozent": 22, "live": {"system": {"cpu": 8, "platte_warten": 60}}})
    assert z.engpass() == "disk"
    # stale live data counts as nothing
    freezer.tick(timedelta(minutes=6))
    assert z.engpass() is None
    # running smoothly again: message gone
    z.trainer_meldet({"wort_id": w.id, "phase": "training", "prozent": 23, "live": {"system": {"cpu": 90, "speicher_warten": 70}}})
    assert z.engpass() is None
    z.reparaturen_pruefen()
    assert reg.async_get_issue(DOMAIN, "trainer_slow") is None
    w.live["zeit"] = "kaputt"
    assert z.trainer_last() == {}


async def test_tage(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    jetzt_ = datetime.now(UTC)
    w.speicher.daten["aufnahmen"] = {
        "a": {"quelle": "echo", "zeit": jetzt_.isoformat()},
        "b": {"quelle": "echo", "zeit": (jetzt_ - timedelta(days=2)).isoformat()},
        "c": {"quelle": "echo", "zeit": (jetzt_ - timedelta(days=40)).isoformat()},
        "d": {"quelle": "aufnahme", "zeit": jetzt_.isoformat()},
        "e": {"quelle": "echo", "zeit": "kaputt"},
    }
    tage = w.speicher.tage()
    assert len(tage) == 14 and tage[-1] == 1 and tage[-3] == 1 and sum(tage) == 2


async def test_neustart_zum_einspielen(hass: HomeAssistant, geladen) -> None:
    """Integration reloaded (HA keeps running): the message stays; HA starting: words are selected later."""
    z = geladen.runtime_data
    reg = ir.async_get(hass)
    w = await z.wort_neu({"wort": "Hey Lumi"})
    z.daten["nach_neustart"] = [w.id, "weg"]
    await hass.async_add_executor_job(z.speichern)
    assert await hass.config_entries.async_reload(geladen.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get_issue(DOMAIN, "restart_to_roll_out").translation_placeholders == {"words": "Hey Lumi"}
    z = geladen.runtime_data
    with patch.object(type(z), "nach_neustart", AsyncMock()) as nach:
        hass.set_state(CoreState.starting)
        assert await hass.config_entries.async_reload(geladen.entry_id)
        hass.set_state(CoreState.running)
        async_fire_time_changed(hass, datetime.now(UTC) + timedelta(seconds=91))
        await hass.async_block_till_done()
    assert nach.called
    # repair flow restarts Home Assistant
    from custom_components.sprachmodell.repairs import async_create_fix_flow

    neustart = async_mock_service(hass, "homeassistant", "restart")
    flow = await async_create_fix_flow(hass, "restart_to_roll_out", None)
    flow.hass = hass
    assert (await flow.async_step_init())["type"] == "form"
    assert (await flow.async_step_confirm({}))["type"] == "create_entry"
    await hass.async_block_till_done()
    assert len(neustart) == 1
    with pytest.raises(ValueError):
        await async_create_fix_flow(hass, "anderes", None)
    await hass.config_entries.async_unload(geladen.entry_id)
    assert reg.async_get_issue(DOMAIN, "restart_to_roll_out") is None


async def test_schwelle_automatisch(hass: HomeAssistant, geladen, geraet) -> None:
    """Hourly: the threshold follows your answers to recordings of the active version, not far below the tested value."""
    z = geladen.runtime_data
    geraet("kueche", "Kitchen")
    w = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}})
    num = async_mock_service(hass, "number", "set_value")
    sp = w.speicher
    sp.daten["versionen"] = [{"nr": 1, "status": "aktiv", "eingespielt": "2026-01-01T00:00:00+00:00", "bericht": {"cutoff": 0.97}}]
    sp.daten["aktiv_seit"] = "2026-01-02T00:00:00+00:00"
    await z.schwelle_pruefen()
    assert not num  # too few answers yet
    for i in range(12):
        sp.daten["aufnahmen"][f"w{i}"] = {"id": f"w{i}", "quelle": "echo", "art": "wake", "score": 0.80 + i * 0.01, "urteil": "wort", "zeit": "2026-01-03T00:00:00Z"}
    for i in range(6):
        sp.daten["aufnahmen"][f"f{i}"] = {"id": f"f{i}", "quelle": "echo", "art": "mistake", "score": 0.75, "urteil": "kein_wort", "zeit": "2026-01-03T00:00:00Z"}
    # an old recording of the previous version does not count
    sp.daten["aufnahmen"]["alt"] = {"id": "alt", "quelle": "echo", "art": "mistake", "score": 0.99, "urteil": "kein_wort", "zeit": "2026-01-01T12:00:00Z"}
    st = sp.statistik()
    assert st["schwelle_vorschlag"] == pytest.approx(0.80) and st["schwelle_basis"] == {"wort": 12, "kein_wort": 6}
    await z.schwelle_pruefen()
    assert num[-1].data["value"] == 0.94  # not more than 0.03 below the tested 0.97
    assert sp.daten["schwelle_auto"]["quelle"] == "antworten" and sp.daten["schwelle_auto"]["wert"] == 0.94
    # already there: nothing to do
    hass.states.async_set("number.kueche_assistant_1_wake_word_threshold", "0.94")
    anzahl = len(num)
    await z.schwelle_pruefen()
    assert len(num) == anzahl
    # switched off: nothing changes
    await z.wort_aendern(w.id, {"schwelle_automatisch": False})
    hass.states.async_set("number.kueche_assistant_1_wake_word_threshold", "0.9")
    await z.schwelle_pruefen()
    assert len(num) == anzahl


async def test_senden_zustand(hass: HomeAssistant, geladen, geraet) -> None:
    """TECHO "Send wake clips to": what the guide in Settings shows per device, renamed entities included."""
    z = geladen.runtime_data
    g = geraet("kueche", "Kitchen")
    assert z.geraete_zustand()[0]["senden"] is None  # firmware without the select
    reg = er.async_get(hass)

    def anlegen(domain: str, objekt: str, zustand: str, umbenannt: str | None = None, **attr) -> str:
        e = reg.async_get_or_create(domain, "esphome", f"kueche-{objekt}", config_entry=g.eintrag,
                                    suggested_object_id=umbenannt or f"kueche_{objekt}")
        hass.states.async_set(e.entity_id, zustand, attr)
        return e.entity_id

    ziel = anlegen("select", "send_wake_clips_to", "Off", umbenannt="kueche_mikrofon_ziel",
                   options=["Off", "Tater Trainer", "wakesmith", "Custom"])
    seite = anlegen("switch", "setup_page", "off")
    anlegen("sensor", "setup_page_asking", "unknown")
    behalten = anlegen("switch", "keep_wake_clips", "off")
    anlegen("sensor", "ip_address", "fd24::1, 192.168.1.44, 2a00::2")
    status = anlegen("sensor", "wake_clip_sending", "unknown")
    offen = anlegen("sensor", "wake_clips_unsent", "3")
    s = z.geraete_zustand()[0]["senden"]
    assert s == {
        "ziel": "Off", "ziel_entitaet": ziel, "ziel_optionen": ["Off", "Tater Trainer", "wakesmith", "Custom"],
        "seite": "off", "seite_entitaet": seite, "behalten": "off", "behalten_entitaet": behalten,
        "ip": "192.168.1.44", "status": "unknown", "status_entitaet": status, "offen": "3", "offen_entitaet": offen,
    }


async def test_trainer_bild_bereit(hass: HomeAssistant, geladen, aioclient_mock, freezer: FrozenDateTimeFactory) -> None:
    """A Docker trainer older than the integration: the studio knows whether the new image is published yet."""
    from custom_components.sprachmodell.const import BILD_MANIFEST, BILD_TOKEN, TRAINER_VERSION

    z = geladen.runtime_data
    z.trainer_info = {"art": "app", "version": "0.1"}
    assert z.bild_tag() is None and z.bild_bereit() is None  # the app builds its own image
    z.trainer_info = {"art": "docker", "version": TRAINER_VERSION}
    assert z.bild_tag() is None  # already current
    z.trainer_info = {"art": "docker", "version": "0.1", "beschleuniger": {"bild": "gpu"}}
    assert z.bild_tag() == TRAINER_VERSION + "-gpu"
    z.trainer_info = {"art": "docker", "version": "0.1"}
    aioclient_mock.get(BILD_TOKEN, json={"token": "t"})
    aioclient_mock.head(f"{BILD_MANIFEST}/{TRAINER_VERSION}", status=404)
    assert z.bild_bereit() is None  # unknown until the first answer
    await hass.async_block_till_done()
    assert z.bild_bereit() is False
    aioclient_mock.clear_requests()
    aioclient_mock.get(BILD_TOKEN, json={"token": "t"})
    aioclient_mock.head(f"{BILD_MANIFEST}/{TRAINER_VERSION}", status=200)
    assert z.bild_bereit() is False  # not again within 5 minutes
    await hass.async_block_till_done()
    assert not aioclient_mock.mock_calls
    z._bild[TRAINER_VERSION] = (False, 0.0)  # 5 minutes later
    z.bild_bereit()
    await hass.async_block_till_done()
    assert z.bild_bereit() is True
    # no internet: stays as it was
    z.trainer_info = {"art": "docker", "version": "0.1", "beschleuniger": {"bild": "gpu"}}
    aioclient_mock.clear_requests()
    aioclient_mock.get(BILD_TOKEN, exc=TimeoutError())
    assert z.bild_bereit() is None
    await hass.async_block_till_done()
    assert z.bild_bereit() is None


MODELLE = os.path.join(os.path.dirname(__file__), "modelle")


def _modell(name: str) -> bytes:
    with open(os.path.join(MODELLE, name + ".tflite"), "rb") as datei:
        return datei.read()


async def test_modell_das_am_geraet_nicht_laeuft(hass: HomeAssistant, geladen) -> None:
    """A model with an operation the devices lack (MUL, like the old averaged ones) never counts as better and
    cannot be rolled out; a model with only supported operations goes through as before."""
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi", "automatisch_einspielen": True})
    e = await z.ergebnis(w, _modell("mul"), {"besser": True, "cutoff": 0.96})
    assert e["status"] == "verworfen" and e["bericht"]["laeuft_nicht"] == ["MUL"]
    assert w.speicher.daten["laeufe"][-1]["ergebnis"] == "laeuft_nicht"
    assert not w.speicher.daten["aktiv"] and z.daten.get("nach_neustart", []) == []
    assert not os.path.exists(hass.config.path("custom_wake_words", "hey_lumi.tflite"))
    with pytest.raises(ValueError, match="modell_laeuft_nicht"):
        await z.einspielen(w, e["nr"])
    gut = await z.ergebnis(w, _modell("laeuft"), {"besser": True, "cutoff": 0.96})
    assert gut["status"] == "aktiv" and w.speicher.daten["aktiv"] == gut["nr"]
    assert "laeuft_nicht" not in gut["bericht"]
    assert w.speicher.daten["laeufe"][-1]["ergebnis"] == "eingespielt"


async def test_schwelle_von_hand(hass: HomeAssistant, geladen, geraet) -> None:
    """Your own threshold on the quality page: set on the devices, kept (automatic adjustment off), range checked."""
    z = geladen.runtime_data
    geraet("kueche", "Kitchen")
    w = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}})
    assert w.cfg.get("schwelle_automatisch")
    num = async_mock_service(hass, "number", "set_value")
    with pytest.raises(ValueError):
        await z.schwelle_von_hand(w, 0.3)
    assert not num
    await z.schwelle_von_hand(w, 0.931)
    assert num[-1].data["value"] == 0.93
    assert w.speicher.daten["schwelle_hand"]["wert"] == 0.93 and not w.cfg.get("schwelle_automatisch")
    assert w.speicher.statistik()["schwelle_hand"]["wert"] == 0.93
    # the hourly follow-up leaves it alone now
    anzahl = len(num)
    await z.schwelle_pruefen()
    assert len(num) == anzahl
