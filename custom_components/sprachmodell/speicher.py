"""Storage of one word: recordings, verdicts, model versions and training runs.

Jedes Wort hat einen eigenen Ordner (<ablage>/woerter/<wort-id>):

    daten.json              Verzeichnis aller Aufnahmen, Versionen, Laeufe
    aufnahmen/<id>.wav      16 kHz, mono, 16 bit
    modelle/v<n>/modell.tflite + bericht.json

Die Datei daten.json wird immer ganz neu geschrieben (erst .tmp, dann
umbenennen), damit sie bei einem Stromausfall nie halb ist. Alle Methoden
hier sind blockierend und laufen im Executor.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import io
import json
import os
import re
import shutil
import threading
import time
from typing import Any
import wave
import zipfile

from .const import KEIN_WORT, NAME, REPO, URTEILE, VERWORFEN, WORT

DATEI = "daten.json"
VERSION = 1
# Jede fuenfte bewertete Aufnahme bleibt fuer den ehrlichen Test zurueck
TEST_ANTEIL = 5
# Eine Fast-Erkennung so kurz vor einer echten zaehlt als "verpasst"
VERPASST_S = 20


def jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _zeit(text: str | None) -> float:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def sichere_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text))[:80]


def ist_test(aid: str) -> bool:
    """Fest je Aufnahme, damit eine Aufnahme nie zwischen Training und Test wechselt."""
    return int(hashlib.sha1(aid.encode()).hexdigest()[:8], 16) % TEST_ANTEIL == 0


def wav_dauer(daten: bytes) -> float:
    try:
        with wave.open(io.BytesIO(daten)) as w:
            return float(round(w.getnframes() / float(w.getframerate() or 16000), 2))
    except (wave.Error, EOFError):
        return 0.0


def wav_16k(daten: bytes) -> bytes:
    """Auf 16 kHz mono 16 bit bringen (Aufnahmen der Setup-Seite sind es schon)."""
    with wave.open(io.BytesIO(daten)) as w:
        kanaele, breite, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        roh = w.readframes(w.getnframes())
    if (kanaele, breite, rate) == (1, 2, 16000):
        return daten
    import array

    werte = array.array("h")
    if breite == 2:
        werte.frombytes(roh)
    elif breite == 1:
        werte.extend((b - 128) << 8 for b in roh)
    elif breite == 4:
        w32 = array.array("i")
        w32.frombytes(roh)
        werte.extend(v >> 16 for v in w32)
    else:
        raise ValueError("wav_format")
    if kanaele > 1:
        werte = array.array("h", (
            sum(werte[i:i + kanaele]) // kanaele for i in range(0, len(werte), kanaele)
        ))
    if rate != 16000:
        n = int(len(werte) * 16000 / rate)
        werte = array.array("h", (werte[min(len(werte) - 1, int(i * rate / 16000))] for i in range(n)))
    aus = io.BytesIO()
    with wave.open(aus, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(werte.tobytes())
    return aus.getvalue()


class Speicher:
    """Daten auf der Platte, mit Sperre gegen gleichzeitiges Schreiben."""

    def __init__(self, ordner: str) -> None:
        self.ordner = ordner
        self._sperre = threading.RLock()
        self.daten: dict[str, Any] = {}
        self.stand = 0  # zaehlt jede Aenderung, damit die Seite weiss, wann sie neu laden muss

    # --- Grundlagen -------------------------------------------------------

    def pfad(self, *teile: str) -> str:
        return os.path.join(self.ordner, *teile)

    def laden(self) -> None:
        os.makedirs(self.pfad("aufnahmen"), exist_ok=True)
        os.makedirs(self.pfad("modelle"), exist_ok=True)
        try:
            with open(self.pfad(DATEI), encoding="utf-8") as datei:
                daten = json.load(datei)
        except (OSError, ValueError):
            daten = {}
        daten.setdefault("version", VERSION)
        daten.setdefault("aufnahmen", {})
        daten.setdefault("gesehen", [])
        daten.setdefault("versionen", [])
        daten.setdefault("laeufe", [])
        daten.setdefault("aktiv", None)
        daten.setdefault("training", {"phase": "bereit"})
        daten.setdefault("auftrag", None)
        daten.setdefault("zaehler", 0)
        self.daten = daten

    def speichern(self) -> None:
        with self._sperre:
            tmp = self.pfad(DATEI + ".tmp")
            with open(tmp, "w", encoding="utf-8") as datei:
                json.dump(self.daten, datei, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, self.pfad(DATEI))
            self.stand += 1

    # --- Aufnahmen --------------------------------------------------------

    def bekannt(self, aid: str) -> bool:
        return aid in self.daten["aufnahmen"] or aid in self.daten["gesehen"]

    def aufnahme_neu(self, meta: dict[str, Any], wav: bytes) -> dict[str, Any]:
        """Eine Aufnahme ablegen (meta braucht id, quelle; Rest frei)."""
        with self._sperre:
            aid = sichere_id(meta["id"])
            with open(self.pfad("aufnahmen", aid + ".wav"), "wb") as datei:
                datei.write(wav)
            eintrag = {
                "id": aid,
                "quelle": meta.get("quelle", "echo"),
                "echo": meta.get("echo"),
                "knoten": meta.get("knoten"),
                "art": meta.get("art"),
                "zeit": meta.get("zeit") or jetzt(),
                "score": meta.get("score"),
                "cutoff": meta.get("cutoff"),
                "slot": meta.get("slot"),
                "modell": meta.get("modell"),
                "dauer": wav_dauer(wav),
                "urteil": meta.get("urteil"),
                "person": meta.get("person"),
                "bewertet": jetzt() if meta.get("urteil") else None,
                "test": ist_test(aid),
                "notiz": meta.get("notiz"),
            }
            self.daten["aufnahmen"][aid] = eintrag
            return eintrag

    def vorschlaege(self) -> None:
        """Vorschlag je offener Geraete-Aufnahme: die Zentrale raet, man bestaetigt.

        grund ist ein Code, den die Seite in die eingestellte Sprache uebersetzt.
        """
        nach_echo: dict[str, list[dict[str, Any]]] = {}
        for a in self.daten["aufnahmen"].values():
            if a["quelle"] == "echo":
                nach_echo.setdefault(a.get("echo") or "", []).append(a)
        for liste in nach_echo.values():
            liste.sort(key=lambda a: _zeit(a["zeit"]))
            for i, a in enumerate(liste):
                if a.get("urteil"):
                    continue
                art = a.get("art")
                vorschlag, grund = None, None
                if art == "wake":
                    vorschlag, grund = WORT, "aufgewacht"
                elif art == "mistake":
                    vorschlag, grund = KEIN_WORT, "abgebrochen"
                elif art == "nearmiss":
                    t = _zeit(a["zeit"])
                    danach = [
                        b for b in liste[i + 1:]
                        if b.get("art") == "wake" and 0 < _zeit(b["zeit"]) - t <= VERPASST_S
                    ]
                    if danach:
                        vorschlag, grund = WORT, "verpasst"
                    else:
                        vorschlag, grund = KEIN_WORT, "knapp"
                elif art == "noise":
                    vorschlag, grund = KEIN_WORT, "geraeusch"
                a["vorschlag"], a["grund"] = vorschlag, grund

    def urteilen(self, ids: list[str], urteil: str | None, person: str | None) -> int:
        if urteil is not None and urteil not in URTEILE:
            raise ValueError("urteil_unbekannt")
        n = 0
        with self._sperre:
            for aid in ids:
                a = self.daten["aufnahmen"].get(aid)
                if not a:
                    continue
                a["urteil"] = urteil
                a["bewertet"] = jetzt() if urteil else None
                if person is not None:
                    a["person"] = person or None
                n += 1
            self.speichern()
        return n

    def person_setzen(self, ids: list[str], person: str | None) -> int:
        with self._sperre:
            n = 0
            for aid in ids:
                if a := self.daten["aufnahmen"].get(aid):
                    a["person"] = person or None
                    n += 1
            self.speichern()
        return n

    def loeschen(self, ids: list[str]) -> int:
        with self._sperre:
            n = 0
            for aid in ids:
                if self.daten["aufnahmen"].pop(aid, None) is not None:
                    n += 1
                    if aid not in self.daten["gesehen"]:
                        self.daten["gesehen"].append(aid)
                    try:
                        os.remove(self.pfad("aufnahmen", aid + ".wav"))
                    except OSError:
                        pass
            self.speichern()
        return n

    def aufraeumen(self, tage_unbewertet: int) -> int:
        """Unbewertete Geraete-Aufnahmen nach N Tagen, verworfene sofort von der Platte."""
        grenze = time.time() - tage_unbewertet * 86400
        weg = [
            a["id"] for a in self.daten["aufnahmen"].values()
            if a.get("urteil") == VERWORFEN
            or (a["quelle"] == "echo" and not a.get("urteil") and _zeit(a["zeit"]) < grenze)
        ]
        # "gesehen" klein halten: nur so viele, wie ein Geraet hoechstens vorhaelt
        self.daten["gesehen"] = self.daten["gesehen"][-5000:]
        return self.loeschen(weg) if weg else 0

    def zip_einlesen(self, inhalt: bytes, person: str | None) -> dict[str, int]:
        """Zip (z. B. von der Setup-Seite eines Geraets: Ordner word/ und not_word/).

        Ordner- oder Dateinamen mit not_/nicht/gegen gelten als Gegenbeispiele,
        alles andere als das Wort.
        """
        ergebnis = {"wort": 0, "kein_wort": 0, "doppelt": 0, "kaputt": 0}
        try:
            archiv = zipfile.ZipFile(io.BytesIO(inhalt))
        except zipfile.BadZipFile as err:
            raise ValueError("keine_zip") from err
        with self._sperre:
            for info in archiv.infolist():
                name = info.filename
                if info.is_dir() or not name.lower().endswith(".wav") or "__MACOSX" in name:
                    continue
                roh = archiv.read(info)
                pruef = hashlib.sha1(roh).hexdigest()[:16]
                aid = "up_" + pruef
                if self.bekannt(aid):
                    ergebnis["doppelt"] += 1
                    continue
                try:
                    wav = wav_16k(roh)
                except (ValueError, wave.Error, EOFError):
                    ergebnis["kaputt"] += 1
                    continue
                klein = name.lower()
                gegen = bool(re.search(r"(^|/)(not_|nicht|gegen|negativ)", klein))
                urteil = KEIN_WORT if gegen else WORT
                self.aufnahme_neu(
                    {
                        "id": aid, "quelle": "hochgeladen", "art": "aufnahme",
                        "urteil": urteil, "person": person, "notiz": name,
                    },
                    wav,
                )
                ergebnis[urteil] += 1
            self.speichern()
        return ergebnis

    def browser_aufnahme(self, roh: bytes, urteil: str, person: str | None,
                         notiz: str | None) -> dict[str, Any]:
        """Eine in der App aufgenommene Aufnahme (WAV) ablegen."""
        if urteil not in (WORT, KEIN_WORT):
            raise ValueError("urteil_unbekannt")
        try:
            wav = wav_16k(roh)
        except (wave.Error, EOFError) as err:
            raise ValueError("wav_format") from err
        if wav_dauer(wav) < 0.3:
            raise ValueError("zu_kurz")
        aid = "br_" + hashlib.sha1(wav).hexdigest()[:16]
        with self._sperre:
            if self.bekannt(aid):
                return self.daten["aufnahmen"].get(aid) or {"id": aid}
            eintrag = self.aufnahme_neu(
                {"id": aid, "quelle": "browser", "art": "aufnahme", "urteil": urteil,
                 "person": person, "notiz": notiz},
                wav,
            )
            self.speichern()
            return eintrag

    # --- Auswertung -------------------------------------------------------

    def offen(self) -> list[dict[str, Any]]:
        return [
            a for a in self.daten["aufnahmen"].values()
            if a["quelle"] == "echo" and not a.get("urteil")
        ]

    def liste(self, filter_: str, echo: str | None, art: str | None,
              seite: int, je_seite: int = 60) -> dict[str, Any]:
        alle = list(self.daten["aufnahmen"].values())
        if filter_ == "offen":
            alle = [a for a in alle if a["quelle"] == "echo" and not a.get("urteil")]
        elif filter_ == "bewertet":
            alle = [a for a in alle if a.get("urteil")]
        elif filter_ == "hochgeladen":
            alle = [a for a in alle if a["quelle"] == "hochgeladen"]
        elif filter_ == "test":
            alle = [a for a in alle if a.get("urteil") in (WORT, KEIN_WORT) and a.get("test")]
        if echo:
            alle = [a for a in alle if a.get("echo") == echo]
        if art:
            alle = [a for a in alle if a.get("art") == art or a.get("urteil") == art]
        alle.sort(key=lambda a: _zeit(a["zeit"]), reverse=filter_ != "offen")
        return {
            "gesamt": len(alle),
            "seite": seite,
            "seiten": max(1, -(-len(alle) // je_seite)),
            "eintraege": alle[seite * je_seite:(seite + 1) * je_seite],
        }

    def statistik(self) -> dict[str, Any]:
        """Zahlen fuer die Seiten Uebersicht und Qualitaet."""
        alle = list(self.daten["aufnahmen"].values())
        bewertet = [a for a in alle if a.get("urteil") in (WORT, KEIN_WORT)]
        echo_bew = [a for a in bewertet if a["quelle"] == "echo"]
        offen = self.offen()
        personen: dict[str, dict[str, int]] = {}
        for a in bewertet:
            p = personen.setdefault(a.get("person") or "Unbekannt", {"wort": 0, "kein_wort": 0})
            p[a["urteil"]] += 1
        # Wie oft lag der Echo im Alltag richtig?
        aufgewacht = [a for a in echo_bew if a.get("art") in ("wake", "mistake")]
        richtig = sum(1 for a in aufgewacht if a["urteil"] == WORT)
        verpasst = sum(1 for a in echo_bew if a.get("art") in ("nearmiss", "noise") and a["urteil"] == WORT)
        # Schwelle aus deinen Antworten (nur Echo-Aufnahmen mit Wert)
        mit_wert = [a for a in echo_bew if isinstance(a.get("score"), int | float)]
        schwellen = []
        for c100 in range(70, 100):
            c = c100 / 100
            durch = sum(1 for a in mit_wert if a["urteil"] == WORT and a["score"] >= c)
            falsch = sum(1 for a in mit_wert if a["urteil"] == KEIN_WORT and a["score"] >= c)
            schwellen.append({"schwelle": c, "erkannt": durch, "falsch": falsch})
        anzahl_wort = sum(1 for a in mit_wert if a["urteil"] == WORT)
        vorschlag = None
        if anzahl_wort >= 10 and len(mit_wert) - anzahl_wort >= 5:
            # Ein Fehlausloeser wiegt so schwer wie drei verpasste Worte
            bestes = max(schwellen, key=lambda s: (s["erkannt"] - 3 * s["falsch"], s["schwelle"]))
            vorschlag = bestes["schwelle"]
        verteilung = {
            "wort": [round(a["score"], 3) for a in mit_wert if a["urteil"] == WORT],
            "kein_wort": [round(a["score"], 3) for a in mit_wert if a["urteil"] == KEIN_WORT],
        }
        aeltestes = min((_zeit(a["zeit"]) for a in offen), default=None)
        je_echo: dict[str, int] = {}
        for a in offen:
            je_echo[a.get("echo") or "?"] = je_echo.get(a.get("echo") or "?", 0) + 1
        return {
            "aufnahmen": len(alle),
            "bewertet": len(bewertet),
            "offen": len(offen),
            "offen_je_echo": je_echo,
            "aeltestes_offen": datetime.fromtimestamp(aeltestes, UTC).isoformat(timespec="seconds") if aeltestes else None,
            "wort": sum(1 for a in bewertet if a["urteil"] == WORT),
            "kein_wort": sum(1 for a in bewertet if a["urteil"] == KEIN_WORT),
            "test": sum(1 for a in bewertet if a.get("test")),
            "personen": personen,
            "alltag": {
                "aufgewacht": len(aufgewacht),
                "richtig": richtig,
                "falsch": len(aufgewacht) - richtig,
                "verpasst": verpasst,
            },
            "schwellen": schwellen,
            "schwelle_vorschlag": vorschlag,
            "verteilung": verteilung,
        }

    def trainer_liste(self) -> list[dict[str, Any]]:
        """Alles Bewertete fuer den Trainer (ohne Platzhalter)."""
        return [
            {
                "id": a["id"], "urteil": a["urteil"], "person": a.get("person"),
                "quelle": a["quelle"], "echo": a.get("echo"), "art": a.get("art"),
                "score": a.get("score"), "test": bool(a.get("test")), "dauer": a.get("dauer"),
            }
            for a in self.daten["aufnahmen"].values()
            if a.get("urteil") in (WORT, KEIN_WORT)
        ]

    # --- Modell-Versionen -------------------------------------------------

    def version_neu(self, tflite: bytes, bericht: dict[str, Any]) -> dict[str, Any]:
        with self._sperre:
            nr = max((v["nr"] for v in self.daten["versionen"]), default=0) + 1
            ordner = self.pfad("modelle", f"v{nr}")
            os.makedirs(ordner, exist_ok=True)
            with open(os.path.join(ordner, "modell.tflite"), "wb") as datei:
                datei.write(tflite)
            eintrag = {
                "nr": nr,
                "zeit": jetzt(),
                "sha256": hashlib.sha256(tflite).hexdigest(),
                "groesse": len(tflite),
                "bericht": bericht,
                "eingespielt": None,
                "status": "neu",
            }
            with open(os.path.join(ordner, "bericht.json"), "w", encoding="utf-8") as datei:
                json.dump(eintrag, datei, ensure_ascii=False, indent=1)
            self.daten["versionen"].append(eintrag)
            self.speichern()
            return eintrag

    def version(self, nr: int) -> dict[str, Any] | None:
        return next((v for v in self.daten["versionen"] if v["nr"] == nr), None)

    def modell_datei(self, nr: int) -> str:
        return self.pfad("modelle", f"v{nr}", "modell.tflite")

    def einspielen_dateien(self, nr: int, ziel: str, modell_id: str, anzeige: str,
                           cutoff: float, sprache: str) -> None:
        """Modell und Beschreibung nach /config/custom_wake_words schreiben."""
        os.makedirs(ziel, exist_ok=True)
        tmp = os.path.join(ziel, modell_id + ".tflite.tmp")
        shutil.copyfile(self.modell_datei(nr), tmp)
        os.replace(tmp, os.path.join(ziel, modell_id + ".tflite"))
        beschreibung = {
            "type": "micro",
            "wake_word": anzeige,
            "author": f"{NAME} v{nr}",
            "website": REPO,
            "model": modell_id + ".tflite",
            "trained_languages": [sprache],
            "version": 2,
            "micro": {
                "probability_cutoff": cutoff,
                "feature_step_size": 10,
                "sliding_window_size": 5,
                "tensor_arena_size": 30000,
                "minimum_esphome_version": "2024.7.0",
            },
        }
        with open(os.path.join(ziel, modell_id + ".json"), "w", encoding="utf-8") as datei:
            json.dump(beschreibung, datei, ensure_ascii=False, indent=2)
        with self._sperre:
            for v in self.daten["versionen"]:
                if v["nr"] == nr:
                    v["eingespielt"] = jetzt()
                    v["status"] = "aktiv"
                elif v.get("status") == "aktiv":
                    v["status"] = "frueher"
            self.daten["aktiv"] = nr
            self.speichern()

    def vorhandenes_uebernehmen(self, datei: str) -> dict[str, Any] | None:
        """Beim ersten Start das schon eingespielte Modell als Version 1 merken."""
        if self.daten["versionen"] or not os.path.isfile(datei):
            return None
        with open(datei, "rb") as f:
            roh = f.read()
        bericht = {"herkunft": "vor der Integration eingespielt"}
        # Optional: Testergebnisse zur vorhandenen Datei (<modell>.bericht.json daneben)
        zusatz = datei[: -len(".tflite")] + ".bericht.json"
        try:
            with open(zusatz, encoding="utf-8") as f:
                bericht.update(json.load(f))
            os.remove(zusatz)
        except (OSError, ValueError):
            pass
        eintrag = self.version_neu(roh, bericht)
        with self._sperre:
            eintrag["status"] = "aktiv"
            eintrag["eingespielt"] = jetzt()
            self.daten["aktiv"] = eintrag["nr"]
            self.speichern()
        return eintrag
