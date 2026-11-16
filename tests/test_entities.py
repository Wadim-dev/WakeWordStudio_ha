"""Sensors, buttons and switches."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.sprachmodell.const import DOMAIN

from .conftest import wav


def _id(hass: HomeAssistant, plattform: str, uid: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(plattform, DOMAIN, uid)
    assert entity_id
    return entity_id


async def test_entitaeten(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    await hass.async_block_till_done()
    w.speicher.aufnahme_neu({"id": "a", "quelle": "echo", "echo": "Kitchen", "art": "wake"}, wav())
    w.speicher.version_neu(b"TFL3", {"neu": {"trefferquote": 0.912, "fehlausloeser_pro_stunde": 0.456}})
    w.speicher.daten["aktiv"] = 1
    z.trainer_meldet({"info": {"name": "PC", "cpu": 4, "geheim": "x"}})
    z.auftrag(w.id, "von_hand")
    await hass.async_block_till_done()

    s = hass.states.get(_id(hass, "sensor", "sprachmodell_pruefliste"))
    assert s.state == "1" and s.attributes["per_word"] == {"Hey Lumi": 1}
    s = hass.states.get(_id(hass, "sensor", "sprachmodell_trainer"))
    assert s.state == "ready" and s.attributes["name"] == "PC" and "geheim" not in s.attributes
    assert s.attributes["queue"] == ["Hey Lumi"]
    s = hass.states.get(_id(hass, "sensor", "sprachmodell_hey_lumi_training"))
    assert s.state == "waiting" and s.attributes["new_reviews"] == 0
    s = hass.states.get(_id(hass, "sensor", "sprachmodell_hey_lumi_pruefliste"))
    assert s.state == "1" and s.attributes["per_device"] == {"Kitchen": 1}
    assert hass.states.get(_id(hass, "sensor", "sprachmodell_hey_lumi_trefferquote")).state == "91.2"
    assert hass.states.get(_id(hass, "sensor", "sprachmodell_hey_lumi_fehlausloeser")).state == "0.46"
    # Version ist standardmaessig aus
    ver = er.async_get(hass).async_get(_id(hass, "sensor", "sprachmodell_hey_lumi_version"))
    assert ver.disabled_by is er.RegistryEntryDisabler.INTEGRATION and ver.entity_category == "diagnostic"
    er.async_get(hass).async_update_entity(ver.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(geladen.entry_id)
    await hass.async_block_till_done()
    z = geladen.runtime_data
    w = z.woerter["hey_lumi"]
    s = hass.states.get(ver.entity_id)
    assert s.state == "v1" and s.attributes["sha256"]
    z.trainer_meldet({"wort_id": w.id, "phase": "training"})
    await hass.async_block_till_done()
    assert hass.states.get(_id(hass, "sensor", "sprachmodell_trainer")).state == "training"
    z.trainer_kontakt = datetime(2020, 1, 1, tzinfo=UTC)
    z.geaendert()
    await hass.async_block_till_done()
    assert hass.states.get(_id(hass, "sensor", "sprachmodell_trainer")).state == "disconnected"


async def test_knoepfe_und_schalter(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    await hass.async_block_till_done()
    knopf = _id(hass, "button", "sprachmodell_hey_lumi_training_starten")
    await hass.services.async_call("button", "press", {"entity_id": knopf}, blocking=True)
    assert z.reihe() == [w.id]
    holen = _id(hass, "button", "sprachmodell_jetzt_holen")
    await hass.services.async_call("button", "press", {"entity_id": holen}, blocking=True)
    with patch.object(z.sammler, "holen", side_effect=RuntimeError), pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("button", "press", {"entity_id": holen}, blocking=True)
    assert err.value.translation_key == "fetch_failed"
    schalter = _id(hass, "switch", "sprachmodell_hey_lumi_nachts_trainieren")
    assert hass.states.get(schalter).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": schalter}, blocking=True)
    assert hass.states.get(schalter).state == "off" and w.cfg["nachts"] is False
    await hass.services.async_call("switch", "turn_on", {"entity_id": schalter}, blocking=True)
    assert w.cfg["nachts"] is True
    # Wort weg, Entitaet noch da: klare Fehlermeldung
    ent = next(e for e in hass.data["entity_components"]["switch"].entities if e.entity_id == schalter)
    knopf_ent = next(e for e in hass.data["entity_components"]["button"].entities if e.entity_id == knopf)
    del z.woerter[w.id]
    assert not ent.available
    with pytest.raises(HomeAssistantError) as err:
        await ent.async_turn_on()
    assert err.value.translation_key == "word_deleted"
    with pytest.raises(HomeAssistantError):
        await knopf_ent.async_press()
    z.woerter[w.id] = w
