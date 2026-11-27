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
    assert info["kueche"] == {"name": "Kitchen", "geraet": "Kitchen", "raum": "", "clips": True, "plaetze": ["1", "2"]}
    assert info["wohnzimmer"] == {"name": "Sofa speaker", "geraet": "Sofa speaker", "raum": "", "clips": False, "plaetze": ["1"]}
    assert alle_geraete(hass)["wohnzimmer"] == "Sofa speaker"


async def test_geraet_nur_mit_dienst(hass: HomeAssistant, geraet) -> None:
    """Clip actions without a matching ESPHome entry still count; the name comes from the node."""
    g = geraet("bad_echo", "Bath")
    dr_reg = dr.async_get(hass)
    for d in dr.async_entries_for_config_entry(dr_reg, g.eintrag.entry_id):
        dr_reg.async_remove_device(d.id)
    assert geraete_info(hass)["bad_echo"]["name"] == "Bath"  # entry title
    hass.config_entries.async_update_entry(g.eintrag, data={"host": "x"})  # no stored device name
    assert geraete_info(hass)["bad_echo"] == {"name": "Bad Echo", "geraet": "Bad Echo", "raum": "", "clips": True, "plaetze": ["1"]}


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


async def test_holen_gleicher_ton(hass: HomeAssistant, geladen, geraet) -> None:
    """The same audio under a new name (e.g. sent directly before) is kept once."""
    z = geladen.runtime_data
    g = geraet("kueche", "Kitchen")
    await z.wort_neu({"wort": "Hey Lumi", "geraete": {"kueche": "1"}})
    g.clip("a")
    g.clip("b", daten=g.audio["a"])
    assert await z.sammler.holen() == 1
    assert await z.sammler.holen() == 0  # b counts as seen, not fetched again


async def test_raum_hinter_dem_namen(hass: HomeAssistant, geladen, geraet) -> None:
    """Devices named without their room (Home Assistant names by area + device) are told apart by the area."""
    from homeassistant.helpers import area_registry as ar, floor_registry as fr

    bereiche, etagen, reg = ar.async_get(hass), fr.async_get(hass), dr.async_get(hass)
    og = etagen.async_create("Upstairs")
    kueche = bereiche.async_create("Kitchen", floor_id=og.floor_id)
    dg_bad = bereiche.async_create("Upstairs bath", floor_id=og.floor_id)
    flur = bereiche.async_create("Hall")

    def dev(g):
        return next(d for d in dr.async_entries_for_config_entry(reg, g.eintrag.entry_id) if d.via_device_id is None)

    a, b, c, d, e = geraet("dot_a", "EchoDot"), geraet("dot_b", "EchoDot"), geraet("show", "EchoShow"), geraet("k2", "Kitchen display"), geraet("ohne", "Loose")
    # no areas yet: equal names are told apart by the node, the others stay as they are
    info = geraete_info(hass)
    assert info["dot_a"]["name"] == "EchoDot (dot_a)" and info["dot_b"]["name"] == "EchoDot (dot_b)" and info["show"]["name"] == "EchoShow"
    reg.async_update_device(dev(a).id, area_id=kueche.id)
    reg.async_update_device(dev(b).id, area_id=dg_bad.id)
    reg.async_update_device(dev(c).id, area_id=flur.id)
    reg.async_update_device(dev(d).id, area_id=kueche.id)
    info = geraete_info(hass)
    assert info["dot_a"] == {"name": "EchoDot · Kitchen (Upstairs)", "geraet": "EchoDot", "raum": "Kitchen (Upstairs)", "clips": True, "plaetze": ["1", "2"]}
    assert info["dot_b"]["name"] == "EchoDot · Upstairs bath"      # the area's name already says the floor
    assert info["show"]["name"] == "EchoShow · Hall"               # an area without a floor
    assert info["k2"]["name"] == "Kitchen display"                 # the name already says the room
    assert info["ohne"]["name"] == "Loose" and info["ohne"]["raum"] == ""
    assert len({i["name"] for i in info.values()}) == len(info)
    # two equal devices in the same area still get different names
    reg.async_update_device(dev(b).id, area_id=kueche.id)
    info = geraete_info(hass)
    assert {info["dot_a"]["name"], info["dot_b"]["name"]} == {"EchoDot · Kitchen (Upstairs) (dot_a)", "EchoDot · Kitchen (Upstairs) (dot_b)"}
    reg.async_update_device(dev(b).id, area_id=dg_bad.id)
    # a part of a device (child device) without an area of its own is in its parent's area
    kind = reg.async_get_or_create(config_entry_id=e.eintrag.entry_id, identifiers={("esphome", "ohne_teil")}, name="Part", via_device=("esphome", "ohne"))
    reg.async_update_device(dev(e).id, area_id=flur.id)
    assert geraete_info(hass)["ohne"]["name"] == "Loose · Hall"    # the device itself, not its part, gives the name
    reg.async_update_device(dev(e).id, name_by_user="", area_id=None)
    assert kind.via_device_id == dev(e).id

    # recordings follow: stored under the old name, they show the area after the next fetch, each device on its own
    z = geladen.runtime_data
    wort = await z.wort_neu({"wort": "Hey Lumi", "geraete": {"dot_a": "1", "dot_b": "1"}})
    a.clip("a1", art="nearmiss", zeit="2026-11-16T06:00:00+00:00", daten=wav(ton=700))
    b.clip("b1", art="wake", zeit="2026-11-16T06:00:05+00:00", daten=wav(ton=800))
    wort.speicher.aufnahme_neu({"id": "alt1", "quelle": "echo", "echo": "EchoDot", "knoten": "dot_a", "art": "wake"}, wav(ton=900))
    assert await z.sammler.holen() == 2
    A = wort.speicher.daten["aufnahmen"]
    assert A["alt1"]["echo"] == "EchoDot · Kitchen (Upstairs)"
    je = wort.speicher.statistik()["offen_je_echo"]
    assert je == {"EchoDot · Kitchen (Upstairs)": 2, "EchoDot · Upstairs bath": 1}
    # a wake on the other EchoDot five seconds later does not make this near miss a "missed" one
    nah = next(x for x in A.values() if x.get("art") == "nearmiss")
    assert nah["grund"] == "knapp"
    assert set(wort.speicher.liste("offen", "EchoDot · Upstairs bath", None, 0)["echos"]) == set(je)
