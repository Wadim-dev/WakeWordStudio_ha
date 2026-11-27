"""Finds the voice devices and collects their wake clips.

Every ESPHome voice device with a "Wake word" select is found, whatever it is called;
a trained model can be rolled out to it. Firmware that keeps wake clips (for example
with the switch "Keep wake clips") also offers the actions esphome.<node>_wake_clips and
esphome.<node>_wake_clip_audio. Those devices are asked every two minutes and right away
when their "Wake clips" counter changes. New clips are stored once; nothing is changed on
the device. Which device slot belongs to which word is set in the panel.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, floor_registry as fr

from .speicher import sichere_id

_LOGGER = logging.getLogger(__name__)

LISTE = "_wake_clips"
AUDIO = "_wake_clip_audio"


# Unique id endings of the ESPHome "Wake word" selects (slot 1 and slot 2)
WAHL_ENDUNGEN = {"1": "-wake_word", "2": "-wake_word_2"}


def esphome_eintraege(hass: HomeAssistant) -> dict[str, ConfigEntry]:
    """Node name -> ESPHome config entry (from the entry's stored device name, no ESPHome internals)."""
    eintraege: dict[str, ConfigEntry] = {}
    for eintrag in hass.config_entries.async_entries("esphome"):
        knoten = eintrag.data.get("device_name")
        if eintrag.disabled_by is None and isinstance(knoten, str) and knoten:
            eintraege[knoten.replace("-", "_")] = eintrag
    return eintraege


def _name(hass: HomeAssistant, knoten: str, eintrag: ConfigEntry | None) -> tuple[str, str]:
    """Name as the user sees it in Home Assistant (renamed devices keep their new name) and where it is: the
    area, with the floor behind it. Since Home Assistant names things by area + device, a device is often just
    called "Echo Dot"; the area then tells the rooms apart. A part of a device without an area of its own is in
    its parent's area."""
    name, ort = "", ""
    if eintrag is not None:
        reg = dr.async_get(hass)
        geraete = dr.async_entries_for_config_entry(reg, eintrag.entry_id)
        # the device itself first, its parts (child devices) after it
        for geraet in sorted(geraete, key=lambda g: g.via_device_id is not None):
            if geraet.name_by_user or geraet.name:
                name = str(geraet.name_by_user or geraet.name)
                eltern = reg.async_get(geraet.via_device_id) if geraet.via_device_id else None
                ort = _ort(hass, geraet.area_id or (eltern.area_id if eltern else None))
                break
        if not name and eintrag.title:
            name = str(eintrag.title)
    return name or knoten.replace("_", " ").title(), ort


def _ort(hass: HomeAssistant, area_id: str | None) -> str:
    """Area name, with the floor in brackets unless the area's name already says it."""
    bereich = ar.async_get(hass).async_get_area(area_id) if area_id else None
    if bereich is None:
        return ""
    etage = fr.async_get(hass).async_get_floor(bereich.floor_id) if bereich.floor_id else None
    if etage is not None and etage.name.casefold() not in bereich.name.casefold():
        return f"{bereich.name} ({etage.name})"
    return str(bereich.name)


def _anzeige(name: str, ort: str) -> str:
    """Device name with its area behind it. A name that already says the area stays as it is."""
    raum = ort.split(" (")[0]
    return name if not ort or raum.casefold() in name.casefold() else f"{name} · {ort}"


def geraete_info(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Every ESPHome voice device, whatever it is called.

    A device counts when it has a "Wake word" select (a model can be rolled out to it)
    or offers wake clips (recordings can be collected from it).
    Node name -> {"name" (shown everywhere: device name, its area behind it), "geraet", "raum", "clips", "plaetze"}.
    """
    dienste = hass.services.async_services().get("esphome", {})
    mit_clips = {n[: -len(LISTE)] for n in dienste if n.endswith(LISTE)}
    eintraege = esphome_eintraege(hass)
    reg = er.async_get(hass)
    aus: dict[str, dict[str, Any]] = {}
    for knoten in sorted(set(eintraege) | mit_clips):
        eintrag = eintraege.get(knoten)
        selects = [
            str(e.unique_id) for e in (er.async_entries_for_config_entry(reg, eintrag.entry_id) if eintrag else [])
            if e.domain == "select" and not e.disabled_by
        ]
        plaetze = [p for p, endung in WAHL_ENDUNGEN.items() if any(u.endswith(endung) for u in selects)]
        clips = knoten in mit_clips
        if not plaetze and not clips:
            continue
        geraet, ort = _name(hass, knoten, eintrag)
        aus[knoten] = {"name": _anzeige(geraet, ort), "geraet": geraet, "raum": ort, "clips": clips, "plaetze": plaetze or ["1"]}
    # recordings, filters and counts go by this name: two devices must never share it
    je_name: dict[str, list[str]] = {}
    for knoten, info in aus.items():
        je_name.setdefault(info["name"].casefold(), []).append(knoten)
    for gleiche in je_name.values():
        if len(gleiche) > 1:
            for knoten in gleiche:
                aus[knoten]["name"] = f"{aus[knoten]['name']} ({knoten})"
    return aus


def alle_geraete(hass: HomeAssistant) -> dict[str, str]:
    """Node name -> display name of every voice device."""
    return {k: v["name"] for k, v in geraete_info(hass).items()}


def _audio_aus_antwort(antwort: Any) -> tuple[bytes, int]:
    """Base64-WAV und Seitenzahl aus der Antwort holen, egal wie das Feld heisst."""
    if not isinstance(antwort, dict):
        return b"", 1
    seiten = int(antwort.get("pages") or 1)
    text = None
    for schluessel in ("audio", "data", "wav", "chunk", "base64"):
        if isinstance(antwort.get(schluessel), str):
            text = antwort[schluessel]
            break
    if text is None:
        texte = [w for w in antwort.values() if isinstance(w, str)]
        text = max(texte, key=len) if texte else ""
    try:
        return base64.b64decode("".join(text.split())), seiten
    except (ValueError, TypeError):
        return b"", seiten


class Sammler:
    """Fragt die Geraete der Woerter ab und legt neue Aufnahmen beim passenden Wort ab."""

    def __init__(self, hass: HomeAssistant, zentrale: Any) -> None:
        self.hass = hass
        self.z = zentrale
        self._sperre = asyncio.Lock()
        self.fehler: dict[str, str] = {}

    def _bekannt(self, aid: str) -> bool:
        return aid in self.z.daten.get("gesehen", []) or any(
            w.speicher.bekannt(aid) for w in self.z.woerter.values()
        )

    async def _dienst(self, name: str, daten: dict[str, Any]) -> Any:
        return await self.hass.services.async_call(
            "esphome", name, daten, blocking=True, return_response=True
        )

    async def _liste(self, knoten: str) -> list[dict[str, Any]]:
        clips: list[dict[str, Any]] = []
        seite, seiten = 0, 1
        while seite < seiten and seite < 20:
            antwort = await self._dienst(knoten + LISTE, {"kind": "", "page": seite})
            if not isinstance(antwort, dict):
                break
            seiten = int(antwort.get("pages") or 1)
            neu = [c for c in antwort.get("clips") or [] if isinstance(c, dict) and c.get("id")]
            clips.extend(neu)
            # Neueste zuerst: kennen wir schon alles auf dieser Seite, reicht es
            if neu and all(self._bekannt(sichere_id(f"{knoten}-{c.get('id')}")) for c in neu):
                break
            seite += 1
        return clips

    async def _audio(self, knoten: str, clip_id: str) -> bytes:
        teile: list[bytes] = []
        seite, seiten = 0, 1
        while seite < seiten and seite < 64:
            antwort = await self._dienst(knoten + AUDIO, {"id": clip_id, "page": seite})
            stueck, seiten = _audio_aus_antwort(antwort)
            teile.append(stueck)
            seite += 1
        return b"".join(teile)

    async def holen(self) -> int:
        """Alle benutzten Geraete einmal abfragen. Gibt die Zahl neuer Aufnahmen zurueck."""
        if self._sperre.locked():
            return 0
        async with self._sperre:
            info = geraete_info(self.hass)
            namen = {k: v["name"] for k, v in info.items()}
            for wort in self.z.woerter.values():
                if await self.hass.async_add_executor_job(wort.speicher.namen_angleichen, namen):
                    await self.hass.async_add_executor_job(wort.speicher.speichern)
            neu: dict[str, int] = {}
            for knoten in sorted(self.z.benutzte_geraete()):
                if knoten not in info:
                    self.fehler[knoten] = "nicht_gefunden"
                    continue
                if not info[knoten]["clips"]:
                    # Firmware without wake clips: the model can be rolled out, nothing to collect
                    self.fehler.pop(knoten, None)
                    continue
                try:
                    clips = await self._liste(knoten)
                except (HomeAssistantError, ValueError) as err:
                    # Schalter aus oder Geraet nicht erreichbar
                    self.fehler[knoten] = str(err)
                    continue
                self.fehler.pop(knoten, None)
                for clip in clips:
                    cid = str(clip.get("id") or "")
                    if not cid:
                        continue
                    aid = sichere_id(f"{knoten}-{cid}")
                    if self._bekannt(aid):
                        continue
                    platz = str(clip.get("slot") or "1")
                    wort = self.z.wort_fuer(knoten, platz, clip.get("model"))
                    if wort is None:
                        self.z.daten["gesehen"].append(aid)
                        continue
                    try:
                        wav = await self._audio(knoten, cid)
                    except (HomeAssistantError, ValueError) as err:
                        _LOGGER.debug("Aufnahme %s von %s nicht geholt: %s", cid, knoten, err)
                        continue
                    if len(wav) < 1000 or wav[:4] != b"RIFF":
                        _LOGGER.debug("Aufnahme %s von %s ist kein WAV", cid, knoten)
                        self.z.daten["gesehen"].append(aid)
                        continue
                    art = str(clip.get("kind") or "").replace(" ", "")
                    if wort.speicher.gleicher_ton(wav):  # already arrived by direct upload
                        self.z.daten["gesehen"].append(aid)
                        continue
                    await self.hass.async_add_executor_job(
                        wort.speicher.aufnahme_neu,
                        {
                            "id": aid, "quelle": "echo", "echo": namen.get(knoten, knoten),
                            "knoten": knoten, "art": art,
                            "zeit": clip.get("at"), "score": clip.get("score"),
                            "cutoff": clip.get("cutoff"), "slot": platz,
                            "modell": clip.get("model"),
                        },
                        wav,
                    )
                    neu[wort.id] = neu.get(wort.id, 0) + 1
            for wid in neu:
                wort = self.z.woerter[wid]
                wort.speicher.vorschlaege()
                await self.hass.async_add_executor_job(wort.speicher.speichern)
            if neu:
                await self.hass.async_add_executor_job(self.z.speichern)
            return sum(neu.values())

    async def annehmen(self, meta: dict[str, Any], wav: bytes) -> str:
        """A recording a device sends by itself (TECHO5 "Send wake clips to", the clip upload format also used by
        other trainers). Same storage as the recordings HA fetches; a clip that arrives both ways is kept once.
        Returns neu, doppelt or kein_wort (no word uses this device and slot)."""
        knoten = str(meta.get("device") or "").replace("-", "_")
        cid = str(meta.get("name") or "")
        if not knoten or not cid:
            raise ValueError("meta_unvollstaendig")
        if len(wav) < 1000 or wav[:4] != b"RIFF":
            raise ValueError("wav_format")
        aid = sichere_id(f"{knoten}-{cid}")
        async with self._sperre:
            if self._bekannt(aid):
                return "doppelt"
            platz = str(meta.get("slot") or "1")
            wort = self.z.wort_fuer(knoten, platz, meta.get("model"))
            if wort is None:
                return "kein_wort"
            if wort.speicher.gleicher_ton(wav):
                return "doppelt"
            namen = alle_geraete(self.hass)
            await self.hass.async_add_executor_job(
                wort.speicher.aufnahme_neu,
                {
                    "id": aid, "quelle": "echo", "echo": namen.get(knoten, knoten), "knoten": knoten,
                    "art": str(meta.get("kind") or "").replace(" ", ""), "zeit": meta.get("at"),
                    "score": meta.get("score"), "cutoff": meta.get("cutoff"), "slot": platz,
                    "modell": meta.get("model"),
                },
                wav,
            )
            wort.speicher.vorschlaege()
            await self.hass.async_add_executor_job(wort.speicher.speichern)
        self.z.geaendert()
        return "neu"
