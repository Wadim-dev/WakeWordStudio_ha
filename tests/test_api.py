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
    assert (await gast.get("/api/sprachmodell/audio/hey_lumi/zz")).status == 404
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
    assert (await client.get("/api/sprachmodell/trainer/modell?wort=hey_lumi", headers=kopf)).status == 404
    r = await client.post("/api/sprachmodell/trainer/status", headers=kopf, json={"wort_id": "hey_lumi", "phase": "training", "prozent": 50})
    assert r.status == 200 and w.speicher.daten["training"]["prozent"] == 50
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
