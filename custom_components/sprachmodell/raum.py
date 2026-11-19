"""Room sound of each device: claps recorded next to the device, kept as room impulse responses.

<ablage>/raeume/<knoten>/

    raum.json       [{"id", "zeit", "hall", "stelle"}] one entry per clap
    <id>.wav        16 kHz, mono, 16 bit, the clap with its echo (cut and faded in the browser)

The trainer mixes them into the training (reverb as the device really hears it in its room), next to the general
room set. All methods are blocking and run in the executor.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
import secrets
import shutil
import threading
from typing import Any

from .speicher import sichere_id, wav_16k, wav_dauer

JE_GERAET = 24  # claps kept per device (the oldest go first)
LAENGSTE_S = 1.6
KUERZESTE_S = 0.05


class Raeume:
    def __init__(self, ablage: str) -> None:
        self.ordner = os.path.join(ablage, "raeume")
        self._sperre = threading.Lock()
        # knoten -> entries, filled by laden() in the executor, so the studio's data needs no file access
        self.stand: dict[str, list[dict[str, Any]]] = {}

    def laden(self) -> None:
        self.stand = {k: e for k in self.knoten() if (e := self._lesen(k))}

    def _pfad(self, knoten: str, *teile: str) -> str:
        return os.path.join(self.ordner, sichere_id(knoten), *teile)

    def _lesen(self, knoten: str) -> list[dict[str, Any]]:
        try:
            with open(self._pfad(knoten, "raum.json"), encoding="utf-8") as datei:
                daten = json.load(datei)
        except (OSError, ValueError):
            return []
        return [e for e in daten if isinstance(e, dict) and e.get("id")] if isinstance(daten, list) else []

    def _schreiben(self, knoten: str, eintraege: list[dict[str, Any]]) -> None:
        pfad = self._pfad(knoten, "raum.json")
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad + ".tmp", "w", encoding="utf-8") as datei:
            json.dump(eintraege, datei)
        os.replace(pfad + ".tmp", pfad)
        self.stand[sichere_id(knoten)] = list(eintraege)

    def knoten(self) -> list[str]:
        try:
            return sorted(n for n in os.listdir(self.ordner) if os.path.isdir(os.path.join(self.ordner, n)))
        except OSError:
            return []

    def zustand(self, knoten: str) -> dict[str, Any] | None:
        """For the studio: how many claps, how many places, mean reverb time and when."""
        eintraege = self.stand.get(sichere_id(knoten))
        if not eintraege:
            return None
        hall = [float(e["hall"]) for e in eintraege if isinstance(e.get("hall"), (int, float))]
        return {
            "n": len(eintraege),
            "stellen": len({e.get("stelle") for e in eintraege}),
            "hall": round(sum(hall) / len(hall), 2) if hall else None,
            "zeit": max(str(e.get("zeit") or "") for e in eintraege),
            "ids": [e["id"] for e in eintraege],
        }

    def hinzufuegen(self, knoten: str, daten: bytes, hall: float | None, stelle: str | None) -> str:
        if not sichere_id(knoten).strip("_"):
            raise ValueError("geraet_unbekannt")
        try:
            daten = wav_16k(daten)
        except (ValueError, EOFError) as err:
            raise ValueError("wav_format") from err
        dauer = wav_dauer(daten)
        if not KUERZESTE_S <= dauer <= LAENGSTE_S:
            raise ValueError("raum_laenge")
        with self._sperre:
            eintraege = self._lesen(knoten)
            rid = datetime.now(UTC).strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(3)
            os.makedirs(self._pfad(knoten), exist_ok=True)
            with open(self._pfad(knoten, rid + ".wav"), "wb") as datei:
                datei.write(daten)
            eintraege.append({
                "id": rid, "zeit": datetime.now(UTC).isoformat(),
                "hall": round(float(hall), 3) if hall is not None and 0 < float(hall) < 5 else None,
                "stelle": sichere_id(stelle or rid),
            })
            for alt in eintraege[:-JE_GERAET]:
                try:
                    os.remove(self._pfad(knoten, alt["id"] + ".wav"))
                except OSError:
                    pass
            self._schreiben(knoten, eintraege[-JE_GERAET:])
        return rid

    def loeschen(self, knoten: str) -> None:
        with self._sperre:
            shutil.rmtree(self._pfad(knoten), ignore_errors=True)
            self.stand.pop(sichere_id(knoten), None)

    def datei(self, knoten: str, rid: str) -> str | None:
        rid = sichere_id(rid)
        if not any(e["id"] == rid for e in self.stand.get(sichere_id(knoten), [])):
            return None
        pfad = self._pfad(knoten, rid + ".wav")
        return pfad if os.path.isfile(pfad) else None

    def fuer_training(self, knoten: list[str]) -> list[dict[str, str]]:
        """Claps the trainer should use: those of the given devices, or of all devices if none of them has any."""
        eigene = [{"knoten": k, "id": e["id"]} for k in knoten for e in self.stand.get(sichere_id(k), [])]
        if eigene:
            return eigene
        return [{"knoten": k, "id": e["id"]} for k, liste in sorted(self.stand.items()) for e in liste]
