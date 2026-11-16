"""Finding voice devices and collecting their wake clips."""

from __future__ import annotations

import base64

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from custom_components.sprachmodell.sammler import _audio_aus_antwort, alle_geraete, geraete_info

from .conftest import wav


async def test_geraete_finden(hass: HomeAssistant, geraet) -> None:
    geraet("kueche", "Kitchen")
    geraet("wohnzimmer", "Living room", clips=False, plaetze=("1",), umbenannt="Sofa speaker")
    geraet("stumm", "Silent", clips=False, plaetze=())
    info = geraete_info(hass)
    assert set(info) == {"kueche", "wohnzimmer"}
    assert info["kueche"] == {"name": "Kitchen", "clips": True, "plaetze": ["1", "2"]}
    assert info["wohnzimmer"] == {"name": "Sofa speaker", "clips": False, "plaetze": ["1"]}
    assert alle_geraete(hass)["wohnzimmer"] == "Sofa speaker"


async def test_geraet_nur_mit_dienst(hass: HomeAssistant, geraet) -> None:
    """Clip actions without a matching ESPHome entry still count; the name comes from the node."""
    g = geraet("bad_echo", "Bath")
    dr_reg = dr.async_get(hass)
    for d in dr.async_entries_for_config_entry(dr_reg, g.eintrag.entry_id):
        dr_reg.async_remove_device(d.id)
    g.eintrag.runtime_data.device_info.friendly_name = None
    assert geraete_info(hass)["bad_echo"]["name"] == "Bath"  # entry title
    g.eintrag.runtime_data = None
    assert geraete_info(hass)["bad_echo"] == {"name": "Bad Echo", "clips": True, "plaetze": ["1"]}


async def test_holen(hass: HomeAssistant, geladen, geraet) -> None:
    z = geladen.runtime_data
    g = geraet("kueche", "Kitchen")
    geraet("wohnzimmer", "Living room", clips=False)
    wort = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1", "wohnzimmer": "1", "weg": "2"}})
    for i in range(7):
        g.clip(f"c{i}", art="wake" if i % 2 else "nearmiss", zeit=f"2026-11-16T06:0{i}:00+00:00")
    g.clip("platz2", slot="2")
    g.clip("modell", slot="2", model="hey_lumi")
    g.clip("kaputt", daten=b"RIFF")
    g.clips.insert(0, {"kind": "wake"})  # ohne id
    assert await z.sammler.holen() == 8
    assert {a["id"] for a in wort.speicher.daten["aufnahmen"].values()} == {f"kueche-c{i}" for i in range(7)} | {"kueche-modell"}
    assert "kueche-platz2" in z.daten["gesehen"] and "kueche-kaputt" in z.daten["gesehen"]
    assert z.sammler.fehler == {"weg": "nicht_gefunden"}
    a = wort.speicher.daten["aufnahmen"]["kueche-c1"]
    assert a["echo"] == "Kitchen" and a["art"] == "wake" and a["vorschlag"] == "wort"
    # Alles bekannt: nur die erste Seite wird gefragt, nichts neu
    g.aufrufe.clear()
    assert await z.sammler.holen() == 0
    assert g.aufrufe == ["liste"]


async def test_holen_fehler(hass: HomeAssistant, geladen, geraet) -> None:
    z = geladen.runtime_data
    g = geraet("kueche", "Kitchen")
    await z.wort_neu({"wort": "Alexa", "geraete": {"kueche": "1"}})
    g.fehler = HomeAssistantError("Keep wake clips is off")
    assert await z.sammler.holen() == 0
    assert "Keep wake clips" in z.sammler.fehler["kueche"]
    g.fehler = None
    g.clip("a")
    g.audio.pop("a")  # Audio-Abruf scheitert
    hass.services.async_remove("esphome", "kueche_wake_clip_audio")

    async def kaputt(call):
        raise HomeAssistantError("weg")

    from homeassistant.core import SupportsResponse
    hass.services.async_register("esphome", "kueche_wake_clip_audio", kaputt, supports_response=SupportsResponse.ONLY)
    assert await z.sammler.holen() == 0
    assert "kueche" not in z.sammler.fehler


async def test_holen_gesperrt(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    async with z.sammler._sperre:
        assert await z.sammler.holen() == 0


def test_audio_aus_antwort() -> None:
    roh = wav()
    b64 = base64.b64encode(roh).decode()
    assert _audio_aus_antwort({"data": b64, "pages": 3}) == (roh, 3)
    assert _audio_aus_antwort({"x": "a", "irgendwas": b64}) == (roh, 1)
    assert _audio_aus_antwort("nein") == (b"", 1)
    assert _audio_aus_antwort({"audio": "%%%"})[0] == b""
    assert _audio_aus_antwort({"pages": 2}) == (b"", 2)
