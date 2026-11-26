"""Nothing from the panel or a trainer is stored before it is checked."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest

from custom_components.sprachmodell import pruefung
from custom_components.sprachmodell.const import STANDARD_ZENTRALE

MARKUP = "x\"'><img src=x onerror=alert(1)>"


@pytest.mark.parametrize("wert", ["", "4", "25:00", "04:60", "aa:bb", "04:00x", None, 4, ["04:00"], MARKUP])
def test_uhrzeit_abgelehnt(wert: Any) -> None:
    with pytest.raises(pruefung.Ungueltig):
        pruefung.uhrzeit(wert)


def test_uhrzeit() -> None:
    assert pruefung.uhrzeit("04:00") == "04:00"
    assert pruefung.uhrzeit("23:59:30") == "23:59"  # some browsers add seconds


@pytest.mark.parametrize("wert", ["red", "#12", "#12345", "#1234567", "#ggg", "#fff;x:y", "#fff\"", MARKUP, 5, ["#fff"]])
def test_farbe_abgelehnt(wert: Any) -> None:
    with pytest.raises(pruefung.Ungueltig):
        pruefung.farbe(wert)


def test_farbe() -> None:
    assert pruefung.farbe("#03A9F4") == "#03a9f4"
    assert pruefung.farbe("#fff") == "#ffffff"
    assert pruefung.farbe("") == "" and pruefung.farbe(None) == ""


@pytest.mark.parametrize(("k", "wert"), [
    ("unbewertet_tage", 0), ("unbewertet_tage", 6), ("unbewertet_tage", 366), ("unbewertet_tage", ""),
    ("unbewertet_tage", None), ("unbewertet_tage", "30"), ("unbewertet_tage", 30.5), ("unbewertet_tage", True),
    ("unbewertet_tage", float("nan")), ("unbewertet_tage", float("inf")),
    ("erinnerung_tage", -1), ("erinnerung_tage", 61), ("erinnerung_tage", MARKUP),
    ("nachts_min_neu", 0), ("nachts_min_neu", 501), ("nachts_min_neu", None),
    ("uhrzeit", ""), ("personen", "Alex"), ("personen", ["Alex", 5]), ("personen", [MARKUP * 3]),
    ("personen", ["x"] * 31), ("trainer_neustart", "switch.x"), ("trainer_neustart", "button.x y"),
    ("neustart_tasten", {"a b": "button.x"}), ("neustart_tasten", {"pc": "light.x"}), ("neustart_tasten", []),
    ("alle_plaetze", "ja"), ("alle_plaetze", 1), ("geraet", "gpu"), ("trainer_wahl", "a b"), ("trainer_wahl", MARKUP),
])
def test_zentrale_abgelehnt(k: str, wert: Any) -> None:
    with pytest.raises(pruefung.Ungueltig):
        pruefung.zentrale({k: wert})


def test_zentrale_erlaubt() -> None:
    gut = {"uhrzeit": "03:30", "nachts_min_neu": 1, "erinnerung_tage": 0, "unbewertet_tage": 7, "personen": ["Alex", "Alex", "Mia"],
           "trainer_neustart": "", "neustart_tasten": {"pc": "button.pc_restart"}, "alle_plaetze": True, "geraet": "cpu",
           "trainer_wahl": "proxmox", "fremd": MARKUP}
    aus = pruefung.zentrale(gut)
    assert "fremd" not in aus and aus["personen"] == ["Alex", "Mia"] and aus["unbewertet_tage"] == 7
    assert pruefung.zentrale({"unbewertet_tage": 30.0}) == {"unbewertet_tage": 30}
    assert set(aus) <= set(STANDARD_ZENTRALE)


@pytest.mark.parametrize(("k", "wert"), [
    ("farbe", "red"), ("farbe", MARKUP), ("wort", 5), ("wort", "x" * 61), ("wort", "a\nb"), ("anzeige", "x" * 81),
    ("sprache", "xx"), ("sprache", MARKUP), ("geraete", ["kueche"]), ("geraete", {"kueche": "3"}), ("geraete", {"a b": "1"}),
    ("geraete", {MARKUP: "1"}), ("gruendlich", "ja"), ("gruendlich", 1), ("schwelle_automatisch", None),
])
def test_wort_abgelehnt(k: str, wert: Any) -> None:
    with pytest.raises(pruefung.Ungueltig):
        pruefung.wort({k: wert})


def test_gespeichert_faellt_zurueck() -> None:
    """Values an older version let through must not stop the start: they fall back to the default."""
    alt = {"uhrzeit": "", "unbewertet_tage": 0, "erinnerung_tage": "x", "nachts_min_neu": 20, "personen": ["Alex"]}
    assert pruefung.gespeichert_zentrale(alt) == {"nachts_min_neu": 20, "personen": ["Alex"]}
    assert pruefung.gespeichert_zentrale("kaputt") == {}
    lang = pruefung.gespeichert_zentrale({"personen": ["Alex", 5, "", "M" * 60, "Alex"], "neustart_tasten": {"pc": "button.pc", "a b": "button.x", "nas": "light.x"}})
    assert lang == {"personen": ["Alex", "M" * 40], "neustart_tasten": {"pc": "button.pc"}}
    w = pruefung.gespeichert_wort({"wort": "Hey <b>Lumi", "farbe": "red\";x", "gruendlich": "ja", "geraete": {"kueche": "1"}, "fremd": 1})
    assert w == {"wort": "Hey <b>Lumi", "geraete": {"kueche": "1"}}  # the name stays (it is escaped when shown)


def test_status_nur_bekannte_schluessel() -> None:
    roh = {"wort_id": "hey_lumi", "phase": "training", "prozent": MARKUP, "schritt": "x" * 900, "version": MARKUP,
           "anzahl": MARKUP, MARKUP: 1, "restzeit_min": "5", "neustart": "ja", "info": {"version": "1.0.43", "tief": {"a": {"b": {"c": {"d": 1}}}}},
           "live": {"x": 1}}
    aus = pruefung.status(roh)
    assert set(aus) == {"wort_id", "phase", "prozent", "schritt", "info", "live"}
    assert aus["prozent"] is None and len(aus["schritt"]) == 300
    assert pruefung.status({"prozent": 250})["prozent"] == 100 and pruefung.status({"prozent": -3})["prozent"] == 0
    assert pruefung.status({"prozent": float("nan")})["prozent"] is None
    assert pruefung.status({"phase": "<script>"}) == {} and pruefung.status("text") == {} and pruefung.status(None) == {}
    assert pruefung.status({"restzeit_min": 12.4}) == {"restzeit_min": 12}
    assert MARKUP not in json.dumps({k: v for k, v in aus.items() if k != "info"})


def test_sauber() -> None:
    tief: Any = "ende"
    for _ in range(20):
        tief = {"a": tief}
    aus = pruefung.sauber({"zahl": 1.5, "nan": float("nan"), "inf": float("-inf"), "text": "x" * 900, "liste": list(range(9000)),
                           "tief": tief, "objekt": object(), 5: "k", "ja": True, "nichts": None})
    assert aus["zahl"] == 1.5 and aus["nan"] is None and aus["inf"] is None and len(aus["text"]) == 500
    assert len(aus["liste"]) == 5000 and aus["objekt"] is None and aus["5"] == "k" and aus["ja"] is True
    json.dumps(aus, allow_nan=False)


@pytest.fixture
async def api(hass: HomeAssistant, eintrag):
    assert await async_setup_component(hass, "http", {})
    eintrag.add_to_hass(hass)
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    z = eintrag.runtime_data
    await z.wort_neu({"wort": "Hey Lumi"})
    yield z
    await hass.config_entries.async_unload(eintrag.entry_id)


async def test_einstellungen_werden_vor_dem_speichern_geprueft(hass: HomeAssistant, hass_client, api) -> None:
    """A request with one wrong value is refused as a whole and nothing of it is stored."""
    z = api
    client = await hass_client()

    async def aktion(**daten: Any) -> tuple[int, dict[str, Any]]:
        r = await client.post("/api/sprachmodell/aktion", json=daten)
        return r.status, await r.json()

    vorher = json.dumps(z.daten.get("einstellungen"), sort_keys=True)
    for falsch in ({"uhrzeit": ""}, {"unbewertet_tage": 0}, {"unbewertet_tage": ""}, {"unbewertet_tage": None},
                   {"erinnerung_tage": 5, "uhrzeit": "25:00"}, {"nachts_min_neu": 30, "unbewertet_tage": 1},
                   {"personen": [MARKUP * 2]}, {"erinnerung_tage": MARKUP}):
        assert await aktion(aktion="einstellungen", einstellungen=falsch) == (400, {"message": "einstellung_ungueltig"})
        assert json.dumps(z.daten.get("einstellungen"), sort_keys=True) == vorher
    assert (await aktion(aktion="einstellungen", einstellungen="text"))[0] == 400
    assert (await aktion(aktion="einstellungen", einstellungen={"uhrzeit": "05:15", "unbewertet_tage": 14}))[0] == 200
    assert z.opt("uhrzeit") == "05:15" and z.tage_unbewertet() == 14

    wort = z.woerter["hey_lumi"]
    alt = dict(wort.cfg)
    for falsch in ({"farbe": "red"}, {"farbe": MARKUP}, {"farbe": "#fff", "sprache": "xx"}, {"gruendlich": "ja"}, {"geraete": {"x y": "1"}}):
        assert await aktion(aktion="wort_aendern", wort="hey_lumi", einstellungen=falsch) == (400, {"message": "einstellung_ungueltig"})
        assert wort.cfg == alt
    assert (await aktion(aktion="wort_neu", einstellungen={"wort": "Computer", "farbe": "javascript:x"}))[0] == 400
    assert "computer" not in z.woerter
    assert (await aktion(aktion="wort_aendern", wort="hey_lumi", einstellungen={"farbe": "#ABC"}))[0] == 200
    assert wort.cfg["farbe"] == "#aabbcc"
    for wert in ("nan", "inf", 5, -1, None, MARKUP):
        assert (await aktion(aktion="schwelle", wort="hey_lumi", wert=wert))[0] == 400


async def test_kaputt_gespeichertes_haelt_den_start_nicht_auf(hass: HomeAssistant, eintrag) -> None:
    """Settings an older version stored without checking: the integration still loads, nothing is deleted early."""
    eintrag.add_to_hass(hass)
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    z = eintrag.runtime_data
    z.daten.setdefault("einstellungen", {}).update({"uhrzeit": "", "unbewertet_tage": 0, "erinnerung_tage": None})
    await hass.async_add_executor_job(z.speichern)
    assert z.tage_unbewertet() >= 7  # even before a restart cleans the stored value
    z.nachts_planen()  # must not raise on the empty time
    assert await hass.config_entries.async_unload(eintrag.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    z = eintrag.runtime_data
    assert z.opt("uhrzeit") == STANDARD_ZENTRALE["uhrzeit"] and z.opt("unbewertet_tage") == STANDARD_ZENTRALE["unbewertet_tage"]
    assert "uhrzeit" not in z.daten["einstellungen"] and "unbewertet_tage" not in z.daten["einstellungen"]
    assert z.tage_unbewertet() == STANDARD_ZENTRALE["unbewertet_tage"]
    await hass.config_entries.async_unload(eintrag.entry_id)


async def test_trainer_status_wird_gefiltert(hass: HomeAssistant, hass_client_no_auth, api) -> None:
    z = api
    client = await hass_client_no_auth()
    kopf = {"X-Sprachmodell-Schluessel": z.schluessel}
    r = await client.post("/api/sprachmodell/trainer/status", headers=kopf, json={
        "wort_id": "hey_lumi", "phase": "training", "prozent": MARKUP, "version": MARKUP, "anzahl": MARKUP, MARKUP: MARKUP,
        "schritt": MARKUP, "info": {"version": MARKUP}})
    assert r.status == 200
    t = z.woerter["hey_lumi"].speicher.daten["training"]
    assert t["phase"] == "training" and t["prozent"] is None and t["schritt"] == MARKUP  # a text, escaped when shown
    assert "version" not in t and "anzahl" not in t and MARKUP not in t


async def test_null_tage_loescht_keine_aufnahmen(hass: HomeAssistant, geladen) -> None:
    """A cleared "keep unreviewed for" field once became 0 and the hourly clean-up deleted every unreviewed
    device recording. Neither the request nor a value already stored may do that."""
    from datetime import UTC, datetime, timedelta

    from .conftest import wav

    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    w.speicher.aufnahme_neu({"id": "frisch", "quelle": "echo"}, wav())
    w.speicher.aufnahme_neu({"id": "sechs", "quelle": "echo", "zeit": (datetime.now(UTC) - timedelta(days=6)).isoformat()}, wav())
    for wert in (0, "", None, -5, float("nan")):
        with pytest.raises(ValueError):
            await z.einstellungen_setzen({"unbewertet_tage": wert})
        z.daten.setdefault("einstellungen", {})["unbewertet_tage"] = wert  # as an older version stored it
        await z._stuendlich()
        assert {"frisch", "sechs"} <= set(w.speicher.daten["aufnahmen"])
    assert w.speicher.aufraeumen(0) == 0 and w.speicher.aufraeumen(-3) == 0
    assert {"frisch", "sechs"} <= set(w.speicher.daten["aufnahmen"])


@pytest.mark.parametrize("wert", [0.49, 1.0, 0, -1, "0.8", None, True, float("nan"), float("inf"), MARKUP])
def test_beinahe_grenze_abgelehnt(wert: Any) -> None:
    with pytest.raises(pruefung.Ungueltig):
        pruefung.wort({"beinahe_grenze": wert})


def test_beinahe_grenze_erlaubt() -> None:
    assert pruefung.wort({"beinahe_grenze": 0.9, "beinahe_sofort": True}) == {"beinahe_grenze": 0.9, "beinahe_sofort": True}
    assert pruefung.wort({"beinahe_grenze": 0.5}) == {"beinahe_grenze": 0.5} and pruefung.wort({"beinahe_grenze": 0.99}) == {"beinahe_grenze": 0.99}
    assert pruefung.wort({"beinahe_grenze": 0.8749}) == {"beinahe_grenze": 0.87}
    with pytest.raises(pruefung.Ungueltig):
        pruefung.wort({"beinahe_sofort": "ja"})
    assert pruefung.gespeichert_wort({"beinahe_grenze": 7, "beinahe_sofort": 1}) == {}


async def test_was_zur_pruefung_kommt(hass: HomeAssistant, geladen) -> None:
    """Limit and "all at once" of the pre-review decide which near misses are left for the user."""
    from datetime import UTC, datetime, timedelta

    from .conftest import wav

    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Alisa"})
    alt = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

    def neu(aid: str, **mehr: Any) -> None:
        gehoert = mehr.pop("gehoert", None)
        a = w.speicher.aufnahme_neu({"id": aid, "quelle": "echo", "echo": "Kitchen", "art": "nearmiss", "zeit": alt, **mehr}, wav())
        if gehoert is not None:
            w.speicher.daten["aufnahmen"][a["id"]]["gehoert"] = gehoert

    neu("tief", score=0.61)                                  # not listened to yet
    neu("tief_nichts", score=0.64, gehoert="")               # listened, nothing heard
    neu("tief_aehnlich", score=0.7, gehoert="Lisa komm")     # sounds like the word
    neu("tief_wort", score=0.7, gehoert="Alisa licht an")    # the word itself was heard
    neu("mittel", score=0.85)
    neu("hoch", score=0.97)
    neu("frisch", score=0.6, zeit=datetime.now(UTC).isoformat())
    neu("ohne_wert")
    neu("vor_wake", score=0.6, zeit=(datetime.now(UTC) - timedelta(minutes=10)).isoformat())
    w.speicher.aufnahme_neu({"id": "wake", "quelle": "echo", "echo": "Kitchen", "art": "wake", "score": 0.6,
                             "zeit": (datetime.now(UTC) - timedelta(minutes=10) + timedelta(seconds=5)).isoformat()}, wav())
    w.speicher.aufnahme_neu({"id": "abbruch", "quelle": "echo", "echo": "Kitchen", "art": "mistake", "score": 0.6, "zeit": alt}, wav())
    w.speicher.aufnahme_neu({"id": "eigene", "quelle": "browser", "art": "nearmiss", "score": 0.3, "zeit": alt}, wav())
    w.speicher.vorschlaege()
    A = w.speicher.daten["aufnahmen"]

    def auto() -> set[str]:
        return {i for i, a in A.items() if a.get("auto") and a.get("urteil") == "kein_wort"}

    # default: only what speech recognition cleared
    assert await hass.async_add_executor_job(w.beinahe_nachziehen) == 1 and auto() == {"tief_nichts"}
    # a higher limit alone still waits for speech recognition
    await z.wort_aendern(w.id, {"beinahe_grenze": 0.9})
    assert auto() == {"tief_nichts"}
    # all at once: everything below the limit, except fresh ones, the one before a wake and the word itself
    await z.wort_aendern(w.id, {"beinahe_sofort": True})
    assert auto() == {"tief_nichts", "tief", "tief_aehnlich", "mittel"}
    assert not A["hoch"].get("urteil") and not A["frisch"].get("urteil") and not A["vor_wake"].get("urteil")
    assert not A["wake"].get("urteil") and not A["abbruch"].get("urteil") and not A["eigene"].get("urteil") and not A["ohne_wert"].get("urteil")
    assert not A["tief_wort"].get("urteil")
    # the fresh one follows once it is two minutes old (the regular fetch catches up)
    A["frisch"]["zeit"] = (datetime.now(UTC) - timedelta(minutes=3)).isoformat()
    with patch("custom_components.sprachmodell.sammler.Sammler.holen", return_value=0):
        assert await z.jetzt_holen()
    assert "frisch" in auto()
    # your own answer is never touched, and switching pre-review off stops it
    w.speicher.urteilen(["mittel"], "wort", None)
    await z.wort_aendern(w.id, {"vorpruefen": False, "beinahe_grenze": 0.99})
    assert not A["hoch"].get("urteil") and A["mittel"]["urteil"] == "wort" and "auto" not in A["mittel"]
    await z.wort_aendern(w.id, {"vorpruefen": True})
    assert "hoch" in auto() and A["mittel"]["urteil"] == "wort"
