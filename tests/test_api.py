"""HTTP API of the panel and the trainer."""

from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, patch
import zipfile

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest

from .conftest import wav


@pytest.fixture
async def api(hass: HomeAssistant, eintrag):
    assert await async_setup_component(hass, "http", {})
    eintrag.add_to_hass(hass)
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    z = eintrag.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    w.speicher.aufnahme_neu({"id": "a1", "quelle": "echo", "echo": "Kitchen", "art": "wake"}, wav())
    w.speicher.aufnahme_neu({"id": "a2", "quelle": "echo", "echo": "Kitchen", "art": "mistake"}, wav())
    w.speicher.vorschlaege()
    yield z
    await hass.config_entries.async_unload(eintrag.entry_id)


@pytest.fixture
async def admin(hass, hass_client, api):
    return await hass_client()


@pytest.fixture
async def gast(hass, hass_client, hass_read_only_access_token, api):
    return await hass_client(hass_read_only_access_token)


async def test_daten(admin, gast, api) -> None:
    r = await admin.get("/api/sprachmodell/daten?wort=hey_lumi&modelle=1")
    d = await r.json()
    assert r.status == 200 and d["admin"] and d["trainer"]["schluessel"] == api.schluessel
    assert d["wort"]["statistik"]["offen"] == 2 and d["vorhandene_modelle"] == []
    d = await (await gast.get("/api/sprachmodell/daten")).json()
    assert not d["admin"] and d["trainer"]["schluessel"] is None and "wort" not in d


async def test_liste_audio_urteil(admin, gast, api) -> None:
    d = await (await gast.get("/api/sprachmodell/liste?wort=hey_lumi&filter=offen")).json()
    assert d["gesamt"] == 2
    assert (await gast.get("/api/sprachmodell/liste?wort=nix")).status == 404
    r = await gast.get("/api/sprachmodell/audio/hey_lumi/a1")
    assert r.status == 200 and (await r.read())[:4] == b"RIFF"
    r = await gast.get("/api/sprachmodell/audio/hey_lumi/zz")
    assert r.status == 404 and await r.json() == {"message": "aufnahme_nicht_gefunden"}
    r = await gast.post("/api/sprachmodell/urteil", json={"wort": "hey_lumi", "ids": ["a1"], "urteil": "wort", "person": "Anna"})
    assert (await r.json())["geaendert"] == 1
    r = await gast.post("/api/sprachmodell/urteil", json={"wort": "hey_lumi", "ids": ["a1"], "urteil": "falsch"})
    assert r.status == 400 and (await r.json())["message"] == "urteil_unbekannt"
    r = await gast.post("/api/sprachmodell/urteil", json={"wort": "hey_lumi", "ids": ["a1"], "person": "Max"})
    assert (await r.json())["geaendert"] == 1
    r = await gast.post("/api/sprachmodell/urteil", json={"wort": "hey_lumi", "ids": ["a2"], "loeschen": True})
    assert r.status == 403 and (await r.json())["message"] == "nur_admin"
    r = await admin.post("/api/sprachmodell/urteil", json={"wort": "hey_lumi", "ids": ["a2"], "loeschen": True})
    assert (await r.json())["geaendert"] == 1
    r = await gast.post("/api/sprachmodell/urteil", data="kein json")
    assert r.status == 400
    r = await gast.post("/api/sprachmodell/urteil", json=[1])
    assert r.status == 400


def _form(**felder) -> aiohttp.FormData:
    f = aiohttp.FormData(default_to_multipart=True)
    for k, v in felder.items():
        if isinstance(v, bytes):
            f.add_field(k, v, filename="x.bin")
        else:
            f.add_field(k, v)
    return f


async def test_hochladen_und_aufnehmen(gast, api) -> None:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("word/a.wav", wav())
        z.writestr("not_word/b.wav", wav(sekunden=0.7))
    r = await gast.post("/api/sprachmodell/hochladen", data=_form(wort="hey_lumi", person="Anna", datei=puffer.getvalue()))
    assert (await r.json())["wort"] == 1
    r = await gast.post("/api/sprachmodell/hochladen", data=_form(wort="hey_lumi"))
    assert r.status == 400 and (await r.json())["message"] == "keine_datei"
    r = await gast.post("/api/sprachmodell/hochladen", data=_form(wort="hey_lumi", datei=b"kaputt"))
    assert (await r.json())["message"] == "keine_zip"
    r = await gast.post("/api/sprachmodell/aufnahme", data=_form(wort="hey_lumi", urteil="kein_wort", datei=wav()))
    assert r.status == 200 and (await r.json())["id"].startswith("br_")
    r = await gast.post("/api/sprachmodell/aufnahme", data=_form(wort="hey_lumi", datei=wav(sekunden=0.1)))
    assert (await r.json())["message"] == "zu_kurz"
    with patch("custom_components.sprachmodell.api.GROESSTE_AUFNAHME", 10):
        r = await gast.post("/api/sprachmodell/aufnahme", data=_form(wort="hey_lumi", datei=wav()))
    assert r.status == 413


async def test_aktionen(hass: HomeAssistant, admin, gast, api) -> None:
    async def aktion(client, **daten):
        r = await client.post("/api/sprachmodell/aktion", json=daten)
        return r.status, await r.json()

    status, d = await aktion(gast, aktion="wort_neu", einstellungen={"wort": "X"})
    assert status == 403 and d["message"] == "nur_admin"
    status, d = await aktion(admin, aktion="wort_neu", einstellungen={"wort": "Computer", "falsch": 1})
    assert status == 200 and d == {"id": "computer"}
    assert (await aktion(admin, aktion="wort_neu", einstellungen={"wort": ""}))[1]["message"] == "wort_fehlt"
    assert (await aktion(gast, aktion="jetzt_holen")) == (200, {"ok": True})
    assert (await aktion(admin, aktion="einstellungen", einstellungen={"uhrzeit": "04:00"}))[0] == 200
    alt = api.schluessel
    await aktion(admin, aktion="schluessel_neu")
    assert api.schluessel != alt
    await aktion(admin, aktion="reihe", reihe=["computer", "nix"])
    assert (await aktion(gast, aktion="training_starten", wort="hey_lumi"))[0] == 200
    assert (await aktion(gast, aktion="training_starten", wort="computer"))[0] == 200
    await aktion(admin, aktion="reihe", reihe=["computer"])
    assert api.reihe() == ["computer", "hey_lumi"]
    assert (await aktion(gast, aktion="training_abbrechen", wort="computer"))[0] == 200
    assert (await aktion(admin, aktion="wort_aendern", wort="hey_lumi", einstellungen={"farbe": "#fff"}))[0] == 200
    assert (await aktion(gast, aktion="vorschlaege_uebernehmen", wort="hey_lumi", ids=["a1"]))[0] == 200
    assert (await aktion(gast, aktion="vorschlaege_uebernehmen", wort="hey_lumi"))[0] == 200
    assert api.woerter["hey_lumi"].speicher.daten["aufnahmen"]["a2"]["urteil"] == "kein_wort"
    assert (await aktion(admin, aktion="einspielen", wort="hey_lumi", nr="x"))[1]["message"] == "ungueltig"
    assert (await aktion(admin, aktion="einspielen", wort="hey_lumi", nr=5))[1]["message"] == "version_fehlt"
    api.woerter["hey_lumi"].speicher.version_neu(b"TFL3", {})
    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        assert (await aktion(admin, aktion="einspielen", wort="hey_lumi", nr=1))[0] == 200
    assert (await aktion(admin, aktion="auswaehlen", wort="hey_lumi")) == (200, {"gesetzt": []})
    assert (await aktion(admin, aktion="schwelle", wort="hey_lumi", wert=0.9)) == (200, {"gesetzt": []})
    assert (await aktion(admin, aktion="schwelle", wort="hey_lumi"))[1]["message"] == "ungueltig"
    assert (await aktion(gast, aktion="gibtsnicht", wort="hey_lumi"))[1]["message"] == "unbekannte_aktion"
    assert await aktion(gast, aktion="training_starten", wort="nix") == (404, {"message": "wort_nicht_gefunden"})
    r = await gast.post("/api/sprachmodell/hochladen", data="x=1", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status == 400 and (await r.json())["message"] == "keine_datei"
    # a recording of "Computer" that "Hey Lumi" caught goes over, and back again
    status, d = await aktion(gast, aktion="anderes_wort", wort="hey_lumi", id="a1", ziel="computer", person="Anna")
    assert status == 200 and d["ziel"] == "computer"
    assert api.woerter["computer"].speicher.daten["aufnahmen"]["a1"]["urteil"] == "wort"
    assert api.woerter["hey_lumi"].speicher.daten["aufnahmen"]["a1"]["urteil"] == "kein_wort"
    assert (await aktion(gast, aktion="anderes_wort", wort="hey_lumi", id="a1", ziel="computer"))[1]["message"] == "schon_da"
    assert (await aktion(gast, aktion="anderes_wort", wort="hey_lumi", id="a1", ziel="hey_lumi"))[1]["message"] == "gleiches_wort"
    assert (await aktion(gast, aktion="anderes_wort_zurueck", wort="hey_lumi", id="a1", ziel="computer"))[0] == 200
    assert "a1" not in api.woerter["computer"].speicher.daten["aufnahmen"]
    assert (await aktion(admin, aktion="wort_loeschen", wort="computer", dateien=True))[0] == 200
    assert "computer" not in api.woerter
    await hass.async_block_till_done()


async def test_trainer(hass: HomeAssistant, hass_client_no_auth, admin, api) -> None:
    client = await hass_client_no_auth()
    kopf = {"X-Sprachmodell-Schluessel": api.schluessel}
    assert (await client.get("/api/sprachmodell/trainer/auftrag")).status == 401
    assert (await client.get("/api/sprachmodell/trainer/auftrag", headers={"X-Sprachmodell-Schluessel": "falsch"})).status == 401
    d = await (await client.get("/api/sprachmodell/trainer/auftrag", headers=kopf)).json()
    assert d["auftrag"] is None and d["woerter"][0]["id"] == "hey_lumi"
    assert api.trainer_online
    api.auftrag("hey_lumi", "von_hand")
    api.daten["abbrechen"] = "alt"
    d = await (await admin.get("/api/sprachmodell/trainer/auftrag")).json()  # Admin-Zugang (HA-App)
    assert d["auftrag"]["wort_id"] == "hey_lumi" and d["auftrag"]["modell_id"] == "hey_lumi" and d["abbrechen"] == "alt"
    w = api.woerter["hey_lumi"]
    w.speicher.urteilen(["a1"], "wort", None)
    d = await (await client.get("/api/sprachmodell/trainer/liste?wort=hey_lumi", headers=kopf)).json()
    assert [a["id"] for a in d["aufnahmen"]] == ["a1"]
    assert (await client.get("/api/sprachmodell/trainer/audio/hey_lumi/a1", headers=kopf)).status == 200
    r = await client.get("/api/sprachmodell/trainer/modell?wort=hey_lumi", headers=kopf)
    assert r.status == 404 and await r.json() == {"message": "modell_nicht_gefunden"}
    r = await client.post("/api/sprachmodell/trainer/status", headers=kopf, json={"wort_id": "hey_lumi", "phase": "training", "prozent": 50})
    assert r.status == 200 and w.speicher.daten["training"]["prozent"] == 50
    live = {
        "protokoll": [[1700000000, "info", "merkmale: 1/3"], "kaputt", [1, 2]],
        "schritte": [{"phase": "merkmale", "schritt": "merkmale", "start": 1700000000, "fremd": [1]}, "kaputt"],
        "system": {"cpu": 87, "ram_gb": 5.4, "name": "x"}, "start": 1700000000,
        "balken": [{"name": "merkmale:2/3", "prozent": 62.5, "n": "4960", "gesamt": "8000", "tempo": "4.58it/s",
                    "rest_min": 11, "fremd": [1]}, {"name": "ohne Prozent"}, "kaputt"],
    }
    r = await client.post("/api/sprachmodell/trainer/status", headers=kopf,
                          json={"wort_id": "hey_lumi", "phase": "training", "prozent": 51, "live": live})
    assert r.status == 200 and "live" not in w.speicher.daten["training"]
    d = await (await admin.get("/api/sprachmodell/daten?wort=hey_lumi")).json()
    assert d["wort"]["live"]["protokoll"] == [[1700000000, "info", "merkmale: 1/3"]]
    assert d["wort"]["live"]["schritte"] == [{"phase": "merkmale", "schritt": "merkmale", "start": 1700000000}]
    assert d["wort"]["live"]["system"] == {"cpu": 87, "ram_gb": 5.4} and d["wort"]["live"]["start"] == 1700000000
    assert d["wort"]["live"]["balken"] == [{"name": "merkmale:2/3", "prozent": 62.5, "n": "4960", "gesamt": "8000",
                                            "rest_min": 11, "tempo": "4.58it/s"}]
    # details only (end of a run): the stored state stays as it is
    r = await client.post("/api/sprachmodell/trainer/status", headers=kopf,
                          json={"wort_id": "hey_lumi", "live": {"protokoll": [], "start": "x"}})
    assert r.status == 200 and w.speicher.daten["training"]["prozent"] == 51 and w.live["start"] is None
    r = await client.post("/api/sprachmodell/trainer/status", headers=kopf, json="text")
    assert r.status == 400

    def ergebnis(modell: bytes, bericht: str = "{}") -> aiohttp.FormData:
        f = aiohttp.FormData()
        f.add_field("modell", modell, filename="modell.tflite")
        f.add_field("bericht", bericht, filename="bericht.json")
        return f

    url = "/api/sprachmodell/trainer/ergebnis?wort=hey_lumi"
    r = await client.post(url, headers=kopf, data=ergebnis(b"kein modell"))
    assert (await r.json())["message"] == "kein_tflite"
    with patch("custom_components.sprachmodell.api.GROESSTES_MODELL", 4):
        r = await client.post(url, headers=kopf, data=ergebnis(b"TFL3" * 10))
    assert r.status == 413
    r = await client.post(url, headers=kopf, data=ergebnis(b"\0\0\0\0TFL3daten", "kaputt"))
    assert (await r.json()) == {"version": 1, "status": "verworfen"}
    r = await client.post(url, headers=kopf, data=ergebnis(b"\0\0\0\0TFL3besser", json.dumps({"besser": True})))
    assert (await r.json())["version"] == 2
    w.cfg["automatisch_einspielen"] = False
    r = await client.get("/api/sprachmodell/trainer/modell?wort=hey_lumi&nr=2", headers=kopf)
    assert r.status == 200 and (await r.read()).endswith(b"besser")
    w.speicher.daten["aktiv"] = 7
    assert (await client.get("/api/sprachmodell/trainer/modell?wort=hey_lumi", headers=kopf)).status == 404


async def test_nicht_eingerichtet(hass: HomeAssistant, hass_client, admin, api, eintrag) -> None:
    await hass.config_entries.async_unload(eintrag.entry_id)
    r = await admin.get("/api/sprachmodell/daten")
    assert r.status == 503 and (await r.json())["message"] == "nicht_eingerichtet"


async def test_vorhandene_modelle_und_adresse(hass: HomeAssistant, admin, api) -> None:
    import os

    from homeassistant.helpers.network import NoURLAvailableError

    ordner = hass.config.path("custom_wake_words")
    os.makedirs(ordner, exist_ok=True)
    with open(os.path.join(ordner, "alisa.tflite"), "wb") as datei:
        datei.write(b"TFL3")
    for name, inhalt in (("alisa.json", json.dumps({"model": "alisa.tflite", "wake_word": "Алиса", "trained_languages": ["ru"]})),
                         ("weg.json", json.dumps({"model": "weg.tflite"})), ("kaputt.json", "{"), ("notiz.txt", "x")):
        with open(os.path.join(ordner, name), "w", encoding="utf-8") as datei:
            datei.write(inhalt)
    with patch("custom_components.sprachmodell.api.get_url", side_effect=NoURLAvailableError):
        d = await (await admin.get("/api/sprachmodell/daten?modelle=1")).json()
    assert d["vorhandene_modelle"] == [{"modell_id": "alisa", "anzeige": "Алиса", "sprache": "ru"}]
    assert d["trainer"]["adresse"] is None


async def test_tabelle_und_zelle(admin, api) -> None:
    w = api.woerter["hey_lumi"]
    sp = w.speicher
    sp.daten["aufnahmen"]["a1"]["score"] = 0.98
    sp.daten["aufnahmen"]["a2"]["score"] = 0.4
    sp.urteilen(["a1"], "kein_wort", None)
    t = sp.tabelle()
    assert t["zeilen"][""]["kein_wort"][8] == 1 and t["zeilen"][""]["offen"][0] == 1
    assert t["zeilen"]["Kitchen"]["kein_wort"][8] == 1
    d = await (await admin.get("/api/sprachmodell/liste?wort=hey_lumi&filter=alle&zeile=kein_wort&von=0.97&bis=0.99")).json()
    assert [a["id"] for a in d["eintraege"]] == ["a1"]
    d = await (await admin.get("/api/sprachmodell/liste?wort=hey_lumi&filter=alle&zeile=offen&von=0&bis=0.5")).json()
    assert [a["id"] for a in d["eintraege"]] == ["a2"]
    assert (await admin.get("/api/sprachmodell/liste?wort=hey_lumi&zeile=wort&von=x")).status == 400
    sp.daten["aufnahmen"]["a2"]["urteil"] = "wort"
    sp.daten["aufnahmen"]["a2"]["art"] = "nearmiss"
    sp.daten["aufnahmen"]["a3"] = {"id": "a3", "quelle": "echo", "urteil": "wort", "art": "wake", "score": 1.5, "zeit": "x"}
    sp.daten["aufnahmen"]["a4"] = {"id": "a4", "quelle": "echo", "urteil": "verworfen", "score": 0.9, "zeit": "x"}
    sp.daten["aufnahmen"]["a5"] = {"id": "a5", "quelle": "hochgeladen", "urteil": "wort", "score": 0.9, "zeit": "x"}
    t = sp.tabelle()
    assert t["zeilen"][""]["verpasst"][0] == 1 and sum(t["zeilen"][""]["wort"]) == 0


async def test_vorpruefen_und_schnitt(hass: HomeAssistant, hass_client_no_auth, admin, api) -> None:
    """The trainer gets open recordings to listen to while it has nothing to train; HA confirms the clear ones."""
    client = await hass_client_no_auth()
    kopf = {"X-Sprachmodell-Schluessel": api.schluessel}
    d = await (await client.get("/api/sprachmodell/trainer/auftrag", headers=kopf)).json()
    [eintrag] = d["vorpruefen"]
    assert eintrag["wort_id"] == "hey_lumi" and eintrag["wort"] == "Hey Lumi" and sorted(eintrag["ids"]) == ["a1", "a2"]
    r = await client.post("/api/sprachmodell/trainer/gehoert", headers=kopf,
                          json={"wort_id": "hey_lumi", "ergebnisse": {"a1": "Hey, Lumi!", "a2": "hello there", "x": "?"}})
    assert (await r.json()) == {"bestaetigt": 1}
    w = api.woerter["hey_lumi"]
    a1, a2 = w.speicher.daten["aufnahmen"]["a1"], w.speicher.daten["aufnahmen"]["a2"]
    assert a1["urteil"] == "wort" and a1["auto"] and a1["gehoert"] == "Hey, Lumi!"
    assert a2["urteil"] is None and a2["gehoert"] == "hello there"
    # everything heard: nothing more to listen to
    d = await (await client.get("/api/sprachmodell/trainer/auftrag", headers=kopf)).json()
    assert d["vorpruefen"] == []
    d = await (await admin.get("/api/sprachmodell/liste?wort=hey_lumi&filter=auto")).json()
    assert [a["id"] for a in d["eintraege"]] == ["a1"]
    # your own answer replaces the automatic one
    await admin.post("/api/sprachmodell/urteil", json={"wort": "hey_lumi", "ids": ["a1"], "urteil": "kein_wort"})
    assert "auto" not in a1 and a1["urteil"] == "kein_wort"
    # switched off: no listening, nothing confirmed
    w.cfg["vorpruefen"] = False
    w.speicher.aufnahme_neu({"id": "a3", "quelle": "echo", "art": "wake"}, b"RIFF" + b"\0" * 2000)
    d = await (await client.get("/api/sprachmodell/trainer/auftrag", headers=kopf)).json()
    assert d["vorpruefen"] == []
    r = await client.post("/api/sprachmodell/trainer/gehoert", headers=kopf,
                          json={"wort_id": "hey_lumi", "ergebnisse": {"a3": "hey lumi"}})
    assert (await r.json()) == {"bestaetigt": 0}
    r = await client.post("/api/sprachmodell/trainer/gehoert", headers=kopf, json={"wort_id": "hey_lumi", "ergebnisse": []})
    assert r.status == 400
    # nothing handed out while a run is going
    w.cfg["vorpruefen"] = True
    w.speicher.daten["aufnahmen"]["a3"].pop("gehoert", None)
    w.speicher.daten["training"] = {"phase": "training"}
    d = await (await client.get("/api/sprachmodell/trainer/auftrag", headers=kopf)).json()
    assert d["vorpruefen"] == []
    w.speicher.daten["training"] = {"phase": "bereit"}

    # trim by hand: stored, sent to the trainer, removed again
    r = await admin.post("/api/sprachmodell/aktion", json={"aktion": "schnitt", "wort": "hey_lumi", "id": "a1", "von": 0.2, "bis": 0.8})
    assert r.status == 200 and a1["schnitt"] == [0.2, 0.8]
    d = await (await client.get("/api/sprachmodell/trainer/liste?wort=hey_lumi", headers=kopf)).json()
    assert d["aufnahmen"][0]["schnitt"] == [0.2, 0.8]
    r = await admin.post("/api/sprachmodell/aktion", json={"aktion": "schnitt", "wort": "hey_lumi", "id": "a1", "von": 0.2, "bis": 0.3})
    assert (await r.json())["message"] == "schnitt_zu_kurz"
    r = await admin.post("/api/sprachmodell/aktion", json={"aktion": "schnitt", "wort": "hey_lumi", "id": "weg", "von": 0, "bis": 1})
    assert (await r.json())["message"] == "aufnahme_fehlt"
    r = await admin.post("/api/sprachmodell/aktion", json={"aktion": "schnitt", "wort": "hey_lumi", "id": "a1", "von": None, "bis": None})
    assert r.status == 200 and "schnitt" not in a1


async def test_clips_vom_geraet(hass: HomeAssistant, hass_client_no_auth, api) -> None:
    """A device sends its recordings by itself (TECHO5 'Send wake clips to')."""
    client = await hass_client_no_auth()
    kopf = {"Authorization": "Bearer " + api.schluessel}
    assert (await client.get("/api/sprachmodell/clips/ping", headers=kopf)).status == 200
    assert (await client.get("/api/sprachmodell/clips/ping", headers={"Authorization": "Bearer falsch"})).status == 403
    assert (await client.get("/api/sprachmodell/clips/ping")).status == 403
    # TECHO firmware: base address http://<ha>/api/sprachmodell, the device adds /api/clips(/ping)
    assert (await client.get("/api/sprachmodell/api/clips/ping", headers=kopf)).status == 200
    falsch = await client.get("/api/sprachmodell/api/clips/ping", headers={"Authorization": "Bearer x"})
    assert falsch.status == 403 and (await falsch.json())["error"] == "falscher_schluessel"
    # base address named like the integration: http://<ha>/api/wake_word_studio
    assert (await client.get("/api/wake_word_studio/api/clips/ping", headers=kopf)).status == 200
    assert (await client.get("/api/wake_word_studio/api/clips/ping")).status == 403

    def form(meta, audio: bytes) -> aiohttp.FormData:
        f = aiohttp.FormData()
        f.add_field("audio", audio, filename="clip.wav")
        f.add_field("meta", meta if isinstance(meta, str) else json.dumps(meta))
        return f

    meta = {"name": "wake_20261117-101500-1", "device": "kueche", "kind": "wake", "at": "2026-11-17T10:15:00Z",
            "model": "hey_lumi", "slot": 1, "score": 0.97, "cutoff": 0.95}
    w = api.woerter["hey_lumi"]
    # neither the device nor the model name belongs to a word
    r = await client.post("/api/sprachmodell/clips", headers=kopf, data=form({**meta, "model": "okay_nabu"}, wav(ton=1234)))
    assert (await r.json()) == {"ok": True, "stored": "kein_wort"}
    r = await client.post("/api/sprachmodell/clips", headers=kopf, data=form(meta, wav(ton=1234)))
    assert (await r.json()) == {"ok": True, "stored": "neu"}
    a = w.speicher.daten["aufnahmen"]["kueche-wake_20261117-101500-1"]
    assert a["art"] == "wake" and a["score"] == 0.97 and a["quelle"] == "echo" and a["vorschlag"] == "wort"
    # sent again, or the same audio under another name: kept once
    r = await client.post("/api/sprachmodell/clips", headers=kopf, data=form(meta, wav(ton=1234)))
    assert (await r.json()) == {"ok": True, "stored": "doppelt", "duplicate": True}
    r = await client.post("/api/sprachmodell/clips", headers=kopf, data=form({**meta, "name": "anders"}, wav(ton=1234)))
    assert (await r.json())["stored"] == "doppelt"
    r = await client.post("/api/sprachmodell/api/clips", headers=kopf, data=form({**meta, "name": "noch"}, wav(ton=4321)))
    assert (await r.json()) == {"ok": True, "stored": "neu"}
    r = await client.post("/api/wake_word_studio/api/clips", headers=kopf, data=form({**meta, "name": "auch"}, wav(ton=5432)))
    assert (await r.json()) == {"ok": True, "stored": "neu"}
    r = await client.post("/api/sprachmodell/clips", headers=kopf, data=form("kein json", wav()))
    assert (await r.json()) == {"ok": False, "error": "meta_kein_json", "message": "meta_kein_json"}
    r = await client.post("/api/sprachmodell/clips", headers=kopf, data=form({"device": "kueche"}, wav()))
    assert (await r.json())["message"] == "meta_unvollstaendig"
    r = await client.post("/api/sprachmodell/clips", headers=kopf, data=form({**meta, "name": "x"}, b"kein wav"))
    assert (await r.json())["message"] == "wav_format"
    with patch("custom_components.sprachmodell.api.GROESSTER_CLIP", 10):
        r = await client.post("/api/sprachmodell/clips", headers=kopf, data=form(meta, wav()))
    assert r.status == 413
    f = aiohttp.FormData()
    f.add_field("meta", json.dumps(meta))
    r = await client.post("/api/sprachmodell/clips", headers=kopf, data=f)
    assert (await r.json())["message"] == "keine_datei"
