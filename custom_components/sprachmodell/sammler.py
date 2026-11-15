"""Holt die Aufwach-Aufnahmen von den Sprachgeraeten (ESPHome, Schalter "Keep wake clips").

Jedes passende ESPHome-Geraet bietet die Aktionen esphome.<knoten>_wake_clips und
esphome.<knoten>_wake_clip_audio. Die Integration fragt alle zwei Minuten und
sofort, wenn sich der Zaehler "Wake clips" eines Geraets aendert. Neue
Aufnahmen werden geholt und auf der Platte abgelegt; was schon bekannt ist,
wird nicht noch einmal geholt. Auf dem Geraet bleibt alles, wie es ist.
Welche Geraete (und welcher Platz) zu welchem Wort gehoeren, stellt man in der App ein.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .speicher import sichere_id

_LOGGER = logging.getLogger(__name__)

LISTE = "_wake_clips"
AUDIO = "_wake_clip_audio"


def esphome_eintraege(hass: HomeAssistant) -> dict[str, Any]:
    """Knotenname -> ESPHome-Eintrag."""
    eintraege: dict[str, Any] = {}
    for eintrag in hass.config_entries.async_entries("esphome"):
        info = getattr(getattr(eintrag, "runtime_data", None), "device_info", None)
        if info is not None:
            eintraege[str(info.name).replace("-", "_")] = eintrag
    return eintraege


def alle_geraete(hass: HomeAssistant) -> dict[str, str]:
    """Knotenname -> Anzeigename aller Geraete mit Aufwach-Aufnahmen."""
    dienste = hass.services.async_services().get("esphome", {})
    knoten = sorted(n[: -len(LISTE)] for n in dienste if n.endswith(LISTE))
    eintraege = esphome_eintraege(hass)
    namen: dict[str, str] = {}
    for k in knoten:
        eintrag = eintraege.get(k)
        info = getattr(getattr(eintrag, "runtime_data", None), "device_info", None)
        namen[k] = (
            getattr(info, "friendly_name", None) or getattr(eintrag, "title", None)
            or k.replace("_", " ").title()
        )
    return namen




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
            neu = [c for c in antwort.get("clips") or [] if isinstance(c, dict)]
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
            namen = alle_geraete(self.hass)
            benutzt = self.z.benutzte_geraete()
            neu: dict[str, int] = {}
            for knoten in benutzt:
                if knoten not in namen:
                    self.fehler[knoten] = "nicht_gefunden"
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
