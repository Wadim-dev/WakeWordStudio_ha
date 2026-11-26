"""Shared fixtures: a hub in a temporary folder and fake ESPHome voice devices."""

from __future__ import annotations

import base64
import io
from typing import Any
import wave

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sprachmodell.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components in every test."""
    return


def wav(sekunden: float = 1.0, rate: int = 16000, kanaele: int = 1, breite: int = 2, ton: int = 1000) -> bytes:
    """A small WAV file with a constant level."""
    aus = io.BytesIO()
    with wave.open(aus, "wb") as w:
        w.setnchannels(kanaele)
        w.setsampwidth(breite)
        w.setframerate(rate)
        n = int(sekunden * rate) * kanaele
        if breite == 1:
            w.writeframes(bytes([128 + 20]) * n)
        else:
            w.writeframes((ton.to_bytes(breite, "little", signed=True)) * n)
    return aus.getvalue()


@pytest.fixture(autouse=True)
def eigener_config_ordner(hass: HomeAssistant, tmp_path) -> None:
    """Models are written to <config>/custom_wake_words: keep that inside the test folder."""
    (tmp_path / "config").mkdir()
    hass.config.config_dir = str(tmp_path / "config")


@pytest.fixture
def ablage(tmp_path) -> str:
    return str(tmp_path / "ablage")


@pytest.fixture
def eintrag(ablage) -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title="Wake Word Studio", data={"ordner": ablage})


@pytest.fixture
async def geladen(hass: HomeAssistant, eintrag: MockConfigEntry):
    """Integration loaded (without http); unloaded after the test."""
    eintrag.add_to_hass(hass)
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    yield eintrag
    if eintrag.state.recoverable:
        await hass.config_entries.async_unload(eintrag.entry_id)
        await hass.async_block_till_done()


class Geraet:
    """A fake ESPHome voice device with wake clips."""

    def __init__(self, hass: HomeAssistant, knoten: str, name: str, clips: bool = True,
                 plaetze: tuple[str, ...] = ("1", "2"), umbenannt: str | None = None) -> None:
        self.hass, self.knoten, self.name = hass, knoten, name
        self.clips: list[dict[str, Any]] = []
        self.audio: dict[str, bytes] = {}
        self.aufrufe: list[str] = []
        self.fehler: Exception | None = None
        self.eintrag = MockConfigEntry(domain="esphome", title=name,
                                       data={"host": knoten, "device_name": knoten.replace("_", "-")})
        self.eintrag.add_to_hass(hass)
        dev = dr.async_get(hass).async_get_or_create(
            config_entry_id=self.eintrag.entry_id, identifiers={("esphome", knoten)}, name=name
        )
        if umbenannt:
            dr.async_get(hass).async_update_device(dev.id, name_by_user=umbenannt)
        reg = er.async_get(hass)
        for platz in plaetze:
            endung = "wake_word" if platz == "1" else "wake_word_2"
            e = reg.async_get_or_create(
                "select", "esphome", f"{knoten}-{endung}", config_entry=self.eintrag,
                suggested_object_id=f"{knoten}_{endung}",
            )
            hass.states.async_set(e.entity_id, "Okay Nabu", {"options": ["Okay Nabu", "Hey Lumi (custom)"]})
            n = reg.async_get_or_create(
                "number", "esphome", f"{knoten}-assistant_{platz}_wake_word_threshold", config_entry=self.eintrag,
                suggested_object_id=f"{knoten}_assistant_{platz}_wake_word_threshold",
            )
            hass.states.async_set(n.entity_id, "0.97")
        if clips:
            s = reg.async_get_or_create(
                "sensor", "esphome", f"{knoten}-wake_clips", config_entry=self.eintrag,
                suggested_object_id=f"{knoten}_wake_clips",
            )
            self.zaehler = s.entity_id
            hass.states.async_set(s.entity_id, "0")
            hass.services.async_register("esphome", f"{knoten}_wake_clips", self._liste, supports_response=SupportsResponse.ONLY)
            hass.services.async_register("esphome", f"{knoten}_wake_clip_audio", self._audio, supports_response=SupportsResponse.ONLY)

    def clip(self, cid: str, art: str = "wake", slot: str = "1", score: float = 0.99, zeit: str = "2026-11-16T06:00:00+00:00",
             daten: bytes | None = None, model: str | None = None) -> None:
        self.clips.insert(0, {"id": cid, "kind": art, "slot": slot, "score": score, "cutoff": 0.97, "at": zeit, "model": model})
        self.audio[cid] = wav(ton=1000 + len(self.audio)) if daten is None else daten

    async def _liste(self, call: ServiceCall) -> dict[str, Any]:
        self.aufrufe.append("liste")
        if self.fehler:
            raise self.fehler
        seite = int(call.data.get("page", 0))
        je = 5
        teil = self.clips[seite * je:(seite + 1) * je]
        return {"version": 1, "page": seite, "pages": max(1, -(-len(self.clips) // je)), "total": len(self.clips), "clips": teil}

    async def _audio(self, call: ServiceCall) -> dict[str, Any]:
        self.aufrufe.append("audio")
        roh = self.audio[call.data["id"]]
        seite = int(call.data.get("page", 0))
        haelfte = len(roh) // 2 + 1
        stueck = roh[seite * haelfte:(seite + 1) * haelfte]
        return {"page": seite, "pages": 2, "audio": base64.b64encode(stueck).decode()}


@pytest.fixture
def geraet(hass: HomeAssistant):
    """Factory for fake ESPHome voice devices."""
    def machen(knoten: str = "kueche", name: str = "Kitchen", **kw: Any) -> Geraet:
        return Geraet(hass, knoten, name, **kw)
    return machen


# --- no disk access on the event loop ---------------------------------------

_PLATTE: list[str] = []


@pytest.fixture(autouse=True)
def keine_platte_in_der_schleife(hass: HomeAssistant, monkeypatch):
    """Fail a test if the integration looks at or touches the disk on the event loop (os.path.isfile, open ...).

    Tests may call the storage classes directly; only calls that start in a coroutine or callback of the
    integration count, as they would run on the loop in Home Assistant too.
    """
    import builtins
    import inspect
    import os
    import shutil
    import sys
    import threading

    schleife = threading.get_ident()
    teil = os.sep + os.path.join("custom_components", "sprachmodell") + os.sep
    del _PLATTE[:]

    def wache(modul: Any, name: str) -> None:
        echt = getattr(modul, name)

        def ersatz(*args: Any, **kwargs: Any) -> Any:
            if threading.get_ident() == schleife:
                rahmen = sys._getframe(1)
                aussen = None  # the integration frame closest to the loop or the test
                kette = []
                while rahmen is not None:
                    datei = rahmen.f_code.co_filename
                    if teil in datei:
                        aussen = rahmen
                        kette.append(f"{os.path.basename(datei)}:{rahmen.f_code.co_name}")
                    rahmen = rahmen.f_back
                if aussen is not None:
                    vom_test = aussen.f_back is not None and os.sep + "tests" + os.sep in aussen.f_back.f_code.co_filename
                    asynchron = bool(aussen.f_code.co_flags & inspect.CO_COROUTINE)
                    if asynchron or not vom_test:
                        _PLATTE.append(f"{getattr(modul, '__name__', modul)}.{name} <- {' <- '.join(kette[:4])}")
            return echt(*args, **kwargs)

        monkeypatch.setattr(modul, name, ersatz)

    for name in ("isfile", "isdir", "exists", "getsize", "getmtime"):
        wache(os.path, name)
    for name in ("listdir", "makedirs", "remove", "replace", "scandir"):
        wache(os, name)
    for name in ("rmtree", "copyfile", "copytree", "copy2"):
        wache(shutil, name)
    wache(builtins, "open")
    yield
    gefunden = sorted(set(_PLATTE))
    del _PLATTE[:]
    assert not gefunden, "disk access on the event loop:\n" + "\n".join(gefunden)
