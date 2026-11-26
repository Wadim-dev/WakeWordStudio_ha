"""Fair comparison of two stored versions: queued only for a new enough trainer, result kept with the word."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest

from custom_components.sprachmodell.const import VERGLEICH_AB
from custom_components.sprachmodell.zentrale import _pruefen_live, version_ab

MODELLE = os.path.join(os.path.dirname(__file__), "modelle")


def _modell() -> bytes:
    with open(os.path.join(MODELLE, "laeuft.tflite"), "rb") as datei:
        return datei.read()


def test_pruefen_live_bereinigt() -> None:
    """Live figures of the comparison come from the trainer: only numbers pass, a few steps, short names."""
    assert _pruefen_live(None) == {} and _pruefen_live([1]) == {}
    roh = {f"s{i}": {"teil": "stille", "n": 3, "gesamt": 4} for i in range(6)}
    roh["vgl_b"] = {"teil": "<b>gerede" * 5, "n": 5, "gesamt": "x", "hoert": {"ruhig": 4, "boese": "<script>", **{f"k{i}": i for i in range(20)}},
                    "fehl": [1], "min": {"gerede": 12.5}}
    aus = _pruefen_live(roh)
    assert len(aus) == 4 and "vgl_b" in aus and "s0" not in aus
    b = aus["vgl_b"]
    assert len(b["teil"]) == 16 and b["n"] == 5 and "gesamt" not in b
    assert b["hoert"]["ruhig"] == 4 and "boese" not in b["hoert"] and len(b["hoert"]) <= 12
    assert b["fehl"] == {} and b["min"] == {"gerede": 12.5} and b["max_min"] == {}


def test_version_ab() -> None:
    assert version_ab("1.0.40", "1.0.40") and version_ab("1.0.41-gpu", "1.0.40") and version_ab("1.1.0", "1.0.40")
    assert not version_ab("1.0.39", "1.0.40") and not version_ab(None, "1.0.40") and not version_ab("x", "1.0.40")


@pytest.fixture
async def zwei(hass: HomeAssistant, eintrag):
    assert await async_setup_component(hass, "http", {})
    eintrag.add_to_hass(hass)
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    z = eintrag.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    for _ in range(2):
        await z.ergebnis(w, _modell(), {"besser": False, "cutoff": 0.96, "neu": {"trefferquote": 0.9}})
    return z, w


async def test_vergleich_starten(hass: HomeAssistant, zwei) -> None:
    z, w = zwei
    with pytest.raises(ValueError, match="gleiche_version"):
        await z.vergleich_starten(w, 1, 1)
    with pytest.raises(ValueError, match="version_fehlt"):
        await z.vergleich_starten(w, 1, 9)
    z.trainer_meldet({"info": {"version": "1.0.39"}}, "alt")
    with pytest.raises(ValueError, match="trainer_zu_alt"):
        await z.vergleich_starten(w, 2, 1)
    z.trainer_meldet({"info": {"version": VERGLEICH_AB}}, "neu")
    await z.vergleich_starten(w, 2, 1)
    assert w.speicher.daten["auftrag"]["vergleich"] == {"a": 2, "b": 1}
    t = w.speicher.daten["training"]
    assert t["phase"] == "wartet" and t["vergleich"] == {"a": 2, "b": 1} and t["grund"] == "vergleich"
    with pytest.raises(ValueError, match="laeuft_schon"):
        await z.vergleich_starten(w, 1, 2)
    # the trainer restarts mid-test: queued again as the same comparison, not as a training
    w.speicher.daten["training"].update({"phase": "test", "aktualisiert": (datetime.now(UTC) - timedelta(minutes=30)).isoformat()})
    z._verlorene_laeufe()
    assert w.speicher.daten["auftrag"]["vergleich"] == {"a": 2, "b": 1}
    assert w.speicher.daten["training"]["vergleich"] == {"a": 2, "b": 1}
    # an error is listed as a failed comparison
    w.speicher.daten["training"]["phase"] = "test"
    z.trainer_meldet({"wort_id": w.id, "phase": "fehler", "schritt": "kaputt"}, "neu")
    assert w.speicher.daten["laeufe"][-1]["vergleich"] == {"a": 2, "b": 1}
    await hass.async_block_till_done()


async def test_vergleich_api(hass: HomeAssistant, hass_client_no_auth, zwei) -> None:
    z, w = zwei
    client = await hass_client_no_auth()
    kopf = {"X-Sprachmodell-Schluessel": z.schluessel}
    alt, neu = {**kopf, "X-Sprachmodell-Trainer": "alt"}, {**kopf, "X-Sprachmodell-Trainer": "neu"}
    await client.post("/api/sprachmodell/trainer/status", headers=alt, json={"info": {"version": "1.0.39"}})
    await client.post("/api/sprachmodell/trainer/status", headers=neu, json={"info": {"version": VERGLEICH_AB}})
    await z.vergleich_starten(w, 2, 1)
    await z.einstellungen_setzen({"trainer_wahl": "alt"})
    # an older trainer would train instead of comparing: it does not get the job
    d = await (await client.get("/api/sprachmodell/trainer/auftrag", headers=alt)).json()
    assert d["auftrag"] is None
    await z.einstellungen_setzen({"trainer_wahl": "neu"})
    z._abgeholt.clear()
    d = await (await client.get("/api/sprachmodell/trainer/auftrag", headers=neu)).json()
    assert d["auftrag"]["vergleich"] == {"a": 2, "b": 1}
    r = await client.get("/api/sprachmodell/trainer/modell?wort=hey_lumi&nr=1", headers=neu)
    assert r.status == 200 and r.headers["X-Version"] == "1"
    await client.post("/api/sprachmodell/trainer/status", headers=neu, json={"wort_id": "hey_lumi", "phase": "test", "prozent": 40})
    assert (await client.post("/api/sprachmodell/trainer/vergleich", headers=neu, json={"wort_id": "hey_lumi", "bericht": {}})).status == 400
    bericht = {"a": 2, "b": 1, "neu": {"trefferquote": 0.93}, "alt": {"trefferquote": 0.9}, "cutoff": 0.95,
               "vergleich": {"urteil": "gleich", "zeilen": []}, "test_positiv": 40, "je_schwelle": {"0.9": {}}}
    r = await client.post("/api/sprachmodell/trainer/vergleich", headers=neu, json={"wort_id": "hey_lumi", "bericht": bericht})
    assert r.status == 200
    v = w.speicher.daten["vergleiche"]
    assert len(v) == 1 and v[0]["a"] == 2 and v[0]["vergleich"]["urteil"] == "gleich" and "je_schwelle" not in v[0]
    assert w.speicher.daten["training"]["phase"] == "bereit" and w.speicher.daten["training"]["vergleich_fertig"] == {"a": 2, "b": 1}
    assert w.speicher.daten["auftrag"] is None and len(w.speicher.daten["versionen"]) == 2  # no new version
    # the same pair again (either order) replaces the older result
    await z.vergleich_ergebnis(w, {**bericht, "a": 1, "b": 2})
    assert [(x["a"], x["b"]) for x in w.speicher.daten["vergleiche"]] == [(1, 2)]
    await hass.async_block_till_done()
