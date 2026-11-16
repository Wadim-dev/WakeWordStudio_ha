"""Set up with a storage folder, change it later (data moves along)."""

from __future__ import annotations

import os
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sprachmodell.config_flow import ordner_pruefen, umziehen
from custom_components.sprachmodell.const import DOMAIN


async def test_einrichten(hass: HomeAssistant, tmp_path) -> None:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": "relativ/ordner"})
    assert r["errors"] == {"ordner": "not_absolute"}
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": hass.config.path("www", "x")})
    assert r["errors"] == {"ordner": "not_allowed"}
    voll = tmp_path / "voll"
    voll.mkdir()
    (voll / "fremd.txt").write_text("x")
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": str(voll)})
    assert r["errors"] == {"ordner": "not_empty"}
    with patch("custom_components.sprachmodell.config_flow.os.makedirs", side_effect=PermissionError):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": str(tmp_path / "gesperrt")})
    assert r["errors"] == {"ordner": "not_writable"}
    ziel = str(tmp_path / "studio")
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": ziel + "/"})
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["title"] == "Wake Word Studio"
    assert r["data"] == {"ordner": ziel}
    await hass.async_block_till_done()
    eintrag = hass.config_entries.async_entries(DOMAIN)[0]
    assert eintrag.state is ConfigEntryState.LOADED and os.path.isfile(os.path.join(ziel, "zentrale.json"))
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert r["type"] is FlowResultType.ABORT and r["reason"] in ("already_configured", "single_instance_allowed")
    await hass.config_entries.async_unload(eintrag.entry_id)


async def test_umziehen(hass: HomeAssistant, geladen, ablage, tmp_path) -> None:
    z = geladen.runtime_data
    await z.wort_neu({"wort": "Hey Lumi"})
    r = await geladen.start_reconfigure_flow(hass)
    assert r["step_id"] == "reconfigure" and r["description_placeholders"] == {"current": ablage}
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": ablage})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "unchanged"
    r = await geladen.start_reconfigure_flow(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": os.path.join(ablage, "innen")})
    assert r["errors"] == {"ordner": "nested"}
    neu = str(tmp_path / "neu")
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": neu})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert geladen.data["ordner"] == neu and geladen.state is ConfigEntryState.LOADED
    assert not os.path.exists(ablage)
    assert "hey_lumi" in geladen.runtime_data.woerter and geladen.runtime_data.ablage == neu


async def test_umziehen_fehlgeschlagen(hass: HomeAssistant, geladen, ablage, tmp_path) -> None:
    await geladen.runtime_data.wort_neu({"wort": "Hey Lumi"})
    with open(os.path.join(ablage, "zz_notiz.txt"), "w", encoding="utf-8") as datei:
        datei.write("x")
    with open(os.path.join(ablage, "aa_notiz.txt"), "w", encoding="utf-8") as datei:
        datei.write("x")
    r = await geladen.start_reconfigure_flow(hass)
    echt = __import__("shutil").copy2
    aufrufe = []

    def copy2(quelle, ziel, **kw):
        aufrufe.append(quelle)
        if quelle.endswith("zz_notiz.txt"):
            raise OSError("voll")
        return echt(quelle, ziel, **kw)

    liste = os.listdir
    with patch("custom_components.sprachmodell.config_flow.shutil.copy2", side_effect=copy2), \
         patch("custom_components.sprachmodell.config_flow.os.listdir", side_effect=lambda p: sorted(liste(p))):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ordner": str(tmp_path / "neu")})
    assert r["errors"] == {"ordner": "move_failed"}
    await hass.async_block_till_done()
    assert geladen.state is ConfigEntryState.LOADED and geladen.data["ordner"] == ablage
    assert os.listdir(tmp_path / "neu") == []
    assert "hey_lumi" in geladen.runtime_data.woerter


def test_umziehen_vorhandene_daten(tmp_path) -> None:
    alt, neu = tmp_path / "alt", tmp_path / "neu"
    (alt / "woerter").mkdir(parents=True)
    neu.mkdir()
    (neu / "zentrale.json").write_text("{}")
    assert umziehen(str(alt), str(neu)) is False and alt.exists()
    assert umziehen(str(tmp_path / "gibtsnicht"), str(tmp_path / "x")) is False


def test_ordner_pruefen(tmp_path) -> None:
    cfg = str(tmp_path / "config")
    assert ordner_pruefen("/", cfg) == "not_allowed"
    assert ordner_pruefen(cfg, cfg) == "not_allowed"
    assert ordner_pruefen(os.path.join(cfg, "custom_components", "x"), cfg) == "not_allowed"
    assert ordner_pruefen(str(tmp_path / "a"), cfg, alt=str(tmp_path / "a" / "b")) == "nested"
    mit_daten = tmp_path / "daten"
    mit_daten.mkdir()
    (mit_daten / "zentrale.json").write_text("{}")
    assert ordner_pruefen(str(mit_daten), cfg) is None


async def test_alter_eintrag_ohne_ordner(hass: HomeAssistant) -> None:
    """Entries of earlier versions have no folder: the default is used and shown."""
    e = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    e.add_to_hass(hass)
    with patch("custom_components.sprachmodell.zentrale.ablage_standard", return_value=hass.config.path("sprachmodell")), \
         patch("custom_components.sprachmodell.config_flow.ablage_standard", return_value=hass.config.path("sprachmodell")):
        assert await hass.config_entries.async_setup(e.entry_id)
        r = await e.start_reconfigure_flow(hass)
    assert r["description_placeholders"] == {"current": hass.config.path("sprachmodell")}
    await hass.config_entries.async_unload(e.entry_id)
