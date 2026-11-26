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

from .bausteine import KeinModell, fehlende_bausteine
from .const import BEINAHE_AUTO_UNTER, KEIN_WORT, NAME, REPO, URTEILE, VERWORFEN, WORT

DATEI = "daten.json"
VERSION = 1
# Jede fuenfte bewertete Aufnahme bleibt fuer den ehrlichen Test zurueck
TEST_ANTEIL = 5
# Recordings from TEST_NEU_AB on: every third day goes to the test as a whole (recordings of one day share voices
# and noise, so single clips held back would flatter the result), and the test grows faster. Older recordings keep
# their place, so a version is never tested with recordings it was trained on.
TEST_ANTEIL_NEU = 3
TEST_NEU_AB = "2026-11-17T00:00:00+00:00"
# Eine Fast-Erkennung so kurz vor einer echten zaehlt als "verpasst"
VERPASST_S = 20


def jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _zeit(text: str | None) -> float:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


TABELLE_GRENZEN = [0.0, 0.5, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.99, 1.01]
TABELLE_ZEILEN = ("wort", "verpasst", "kein_wort", "offen")


def _zweifel(a: dict[str, Any]) -> float | None:
    """How much the device disagreed with your answer: 0 = it agreed fully, 1 = it was sure of the opposite."""
    score = a.get("score")
    if not isinstance(score, int | float) or a.get("urteil") not in (WORT, KEIN_WORT):
        return None
    score = min(1.0, max(0.0, float(score)))
    return 1.0 - score if a["urteil"] == WORT else score


def _zeile(a: dict[str, Any]) -> str | None:
    """Row of a device recording in the table: said the word (woke up), missed it, did not say it, not reviewed."""
    if a.get("quelle") != "echo":
        return None
    urteil = a.get("urteil")
    if urteil == WORT:
        return "verpasst" if a.get("art") in ("nearmiss", "noise") else "wort"
    if urteil == KEIN_WORT:
        return "kein_wort"
    return "offen" if not urteil else None


def sichere_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text))[:80]


def ist_test(aid: str, zeit: str | None = None) -> bool:
    """Fest je Aufnahme, damit eine Aufnahme nie zwischen Training und Test wechselt."""
    if zeit and _zeit(zeit) >= _zeit(TEST_NEU_AB):
        tag = datetime.fromtimestamp(_zeit(zeit), UTC).date().isoformat()
        return int(hashlib.sha1(tag.encode()).hexdigest()[:8], 16) % TEST_ANTEIL_NEU == 0
    return int(hashlib.sha1(aid.encode()).hexdigest()[:8], 16) % TEST_ANTEIL == 0


def _normal(text: str) -> str:
    """Lower case, ё as е, only letters and digits (to compare what was heard with the word)."""
    return "".join(c for c in str(text).lower().replace("ё", "е") if c.isalnum())


def _typ(a: dict[str, Any]) -> str:
    """What kind of recording, as the list shows it (recorded in the browser counts on its own)."""
    return "browser" if a.get("quelle") == "browser" else str(a.get("art") or "")


def _nichts_gehoert(a: dict[str, Any]) -> bool:
    """Speech recognition listened and understood nothing."""
    return a.get("gehoert") == ""


def _nichts_sammeln(a: dict[str, Any]) -> bool:
    """May go to 'unusable' with one tap: unanswered device recording, nothing understood, and the device did NOT
    wake up. A wake with nothing understood is either a real false wake (the most valuable thing to train against)
    or the word said too quietly for speech recognition: both need your ear, never a bulk action."""
    return (_nichts_gehoert(a) and not a.get("urteil") and a.get("quelle") == "echo"
            and a.get("art") not in ("wake", "mistake"))


def wort_gehoert(gehoert: str, wort: str) -> bool:
    w = _normal(wort)
    return bool(w) and w in _normal(gehoert)


def wort_aehnlich(gehoert: str, wort: str) -> bool:
    """Something in what was heard sounds close to the word (e.g. "Лиза" for "Алиса"): leave it for you."""
    import difflib

    w = _normal(wort)
    if not w:
        return False
    teile = [t for t in (_normal(x) for x in str(gehoert).split()) if t]
    n = max(1, len(str(wort).split()))
    kandidaten = ["".join(teile[i:i + k]) for k in range(1, n + 2) for i in range(len(teile) - k + 1)]
    return any(difflib.SequenceMatcher(None, w, x).ratio() >= 0.6 for x in kandidaten)


def beinahe_nicht(a: dict[str, Any], wort: str) -> bool:
    """An open near miss from a device, well below the threshold, in which speech recognition heard neither the
    word nor anything like it: not the word (pre-review marks it auto, you can change it in History)."""
    score = a.get("score")
    return (not a.get("urteil") and a.get("quelle") == "echo" and a.get("art") == "nearmiss"
            and isinstance(score, int | float) and score < BEINAHE_AUTO_UNTER and "gehoert" in a
            and not wort_gehoert(a["gehoert"], wort) and not wort_aehnlich(a["gehoert"], wort))


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
            zeit = meta.get("zeit") or jetzt()
            eintrag = {
                "id": aid,
                "quelle": meta.get("quelle", "echo"),
                "echo": meta.get("echo"),
                "knoten": meta.get("knoten"),
                "art": meta.get("art"),
                "zeit": zeit,
                "score": meta.get("score"),
                "cutoff": meta.get("cutoff"),
                "slot": meta.get("slot"),
                "modell": meta.get("modell"),
                "dauer": wav_dauer(wav),
                "urteil": meta.get("urteil"),
                "person": meta.get("person"),
                "bewertet": jetzt() if meta.get("urteil") else None,
                "test": ist_test(aid, zeit),
                "notiz": meta.get("notiz"),
                "ton": hashlib.sha1(wav).hexdigest()[:16],
            }
            self.daten["aufnahmen"][aid] = eintrag
            return eintrag

    def gleicher_ton(self, wav: bytes) -> bool:
        """True if exactly this audio is already stored (a clip that arrived both by upload and by fetching)."""
        ton = hashlib.sha1(wav).hexdigest()[:16]
        return any(a.get("ton") == ton for a in self.daten["aufnahmen"].values())

    def namen_angleichen(self, namen: dict[str, str]) -> bool:
        """Give every device recording the device's current name (node -> name).

        A renamed device then shows up once everywhere (table, filters, history)
        instead of once per name it ever had. Returns True when something changed."""
        geaendert = False
        with self._sperre:
            for a in self.daten["aufnahmen"].values():
                if a.get("quelle") != "echo":
                    continue
                knoten = a.get("knoten") or next(
                    (k for k in namen if str(a.get("id", "")).startswith(sichere_id(k) + "-")), None)
                if knoten in namen and (a.get("echo") != namen[knoten] or a.get("knoten") != knoten):
                    a["echo"], a["knoten"] = namen[knoten], knoten
                    geaendert = True
        return geaendert

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
                a.pop("auto", None)  # your own answer replaces the pre-review's
                if person is not None:
                    a["person"] = person or None
                n += 1
            self.speichern()
        return n

    def zum_hoeren(self, anzahl: int) -> list[str]:
        """Open device recordings the speech recognition has not listened to yet (newest first)."""
        offen = [a for a in self.offen() if "gehoert" not in a]
        offen.sort(key=lambda a: _zeit(a["zeit"]), reverse=True)
        return [a["id"] for a in offen[:anzahl]]

    def gehoert_setzen(self, ergebnisse: dict[str, str], wort: str, bestaetigen: bool) -> int:
        """Store what the speech recognition heard. With bestaetigen: an open recording in which the word was
        clearly heard counts as "said the word" (marked auto, so you can see and change it). Returns how many."""
        n = 0
        with self._sperre:
            for aid, text in ergebnisse.items():
                a = self.daten["aufnahmen"].get(sichere_id(aid))
                if not a:
                    continue
                a["gehoert"] = str(text or "")[:200]
                if bestaetigen and not a.get("urteil") and wort_gehoert(a["gehoert"], wort):
                    a["urteil"], a["bewertet"], a["auto"] = WORT, jetzt(), True
                    n += 1
            self.speichern()
        return n + (self.beinahe_nachziehen(wort) if bestaetigen else 0)

    def beinahe_nachziehen(self, wort: str) -> int:
        """Mark open low near misses without the word as "not said" (auto). Returns how many."""
        n = 0
        with self._sperre:
            for a in self.daten["aufnahmen"].values():
                if beinahe_nicht(a, wort):
                    a["urteil"], a["bewertet"], a["auto"] = KEIN_WORT, jetzt(), True
                    n += 1
            if n:
                self.speichern()
        return n

    def schnitt_setzen(self, aid: str, von: float | None, bis: float | None) -> dict[str, Any]:
        """Use only part of a recording for training and test (seconds). None/None: the whole recording again."""
        with self._sperre:
            a = self.daten["aufnahmen"].get(aid)
            if not a:
                raise ValueError("aufnahme_fehlt")
            if von is None and bis is None:
                a.pop("schnitt", None)
            else:
                dauer = float(a.get("dauer") or 0) or 60.0
                v = max(0.0, min(float(von or 0), dauer))
                b = min(dauer, max(float(bis if bis is not None else dauer), v))
                if b - v < 0.2:
                    raise ValueError("schnitt_zu_kurz")
                a["schnitt"] = [round(v, 2), round(b, 2)]
            self.speichern()
            return dict(a)

    def an_wort_geben(self, aid: str, ziel: Speicher, von: dict[str, str], zu: dict[str, str],
                      person: str | None) -> dict[str, Any]:
        """A recording of another word (e.g. "hey casita" caught by "hey jarvis"): it goes to the other word as
        "said the word" and stays here as "not the word" - for this word it really is not. von/zu: {id, wort}."""
        if ziel is self:
            raise ValueError("gleiches_wort")
        with self._sperre, ziel._sperre:
            a = self.daten["aufnahmen"].get(aid)
            if not a:
                raise ValueError("aufnahme_fehlt")
            if aid in ziel.daten["aufnahmen"]:
                raise ValueError("schon_da")
            with open(self.pfad("aufnahmen", aid + ".wav"), "rb") as datei:
                wav = datei.read()
            # the score and cut-off belong to this word's model, so they don't go along (the other word's
            # statistics stay clean); the kind stays, the trainer uses it to find the word in a wake-up clip
            neu = ziel.aufnahme_neu({
                "id": aid, "quelle": a["quelle"], "echo": a.get("echo"), "knoten": a.get("knoten"),
                "art": a.get("art"), "zeit": a.get("zeit"), "urteil": WORT,
                "person": person if person is not None else a.get("person"), "notiz": a.get("notiz"),
            }, wav)
            if a.get("schnitt"):
                neu["schnitt"] = list(a["schnitt"])
            if a.get("gehoert") is not None:
                neu["gehoert"] = a["gehoert"]
            neu["von_wort"] = {"id": von["id"], "wort": von["wort"], "score": a.get("score")}
            a["zu_wort"] = {"id": zu["id"], "wort": zu["wort"], "vorher": a.get("urteil"),
                            "bewertet": a.get("bewertet"), "auto": bool(a.get("auto"))}
            a["urteil"], a["bewertet"] = KEIN_WORT, jetzt()
            a.pop("auto", None)
            ziel.speichern()
            self.speichern()
            return dict(neu)

    def zurueckholen(self, aid: str, ziel: Speicher) -> None:
        """Undo an_wort_geben: the copy at the other word goes, the answer here is what it was before."""
        with self._sperre, ziel._sperre:
            a = self.daten["aufnahmen"].get(aid)
            if not a or not a.get("zu_wort"):
                raise ValueError("aufnahme_fehlt")
            zu = a.pop("zu_wort")
            a["urteil"], a["bewertet"] = zu.get("vorher"), zu.get("bewertet")
            if zu.get("auto"):
                a["auto"] = True
            if ziel.daten["aufnahmen"].pop(aid, None) is not None:
                try:
                    os.remove(ziel.pfad("aufnahmen", aid + ".wav"))
                except OSError:
                    pass
                ziel.speichern()
            self.speichern()

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
        if not isinstance(tage_unbewertet, int) or tage_unbewertet < 1:
            return 0  # never "everything": the caller checks the setting, this is the last guard
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

    def nichts_sammeln(self, filter_: str, echo: str | None = None, typ: str | None = None,
                       person: str | None = None) -> list[str]:
        """Exactly the recordings the one-tap 'unusable' counts in the list with the same filters."""
        treffer = self.liste(filter_, echo, None, 0, je_seite=1_000_000, typ=typ, person=person)["eintraege"]
        return [a["id"] for a in treffer if _nichts_sammeln(a)]

    def liste(self, filter_: str, echo: str | None, art: str | None,
              seite: int, je_seite: int = 60, zelle: tuple[str, float, float] | None = None,
              sortierung: str | None = None, typ: str | None = None, person: str | None = None,
              nichts: bool = False) -> dict[str, Any]:
        alle = list(self.daten["aufnahmen"].values())
        if zelle:  # one cell of the table on the quality page: row and score range
            zeile, von, bis = zelle
            alle = [a for a in alle if _zeile(a) == zeile and isinstance(a.get("score"), int | float)
                    and von <= a["score"] < bis]
        if filter_ == "offen":
            alle = [a for a in alle if a["quelle"] == "echo" and not a.get("urteil")]
        elif filter_ == "bewertet":
            alle = [a for a in alle if a.get("urteil")]
        elif filter_ == "hochgeladen":
            alle = [a for a in alle if a["quelle"] == "hochgeladen"]
        elif filter_ == "auto":
            alle = [a for a in alle if a.get("auto")]
        elif filter_ == "test":
            alle = [a for a in alle if a.get("urteil") in (WORT, KEIN_WORT) and a.get("test")]
        # counts for the chips: each one before its own filter and after all the others,
        # so a chip always says how many you would see after tapping it
        def passt(a: dict[str, Any], ohne: str) -> bool:
            return ((ohne == "echo" or not echo or a.get("echo") == echo)
                    and (ohne == "typ" or not typ or _typ(a) == typ)
                    and (ohne == "person" or not person or a.get("person") == person)
                    and (ohne == "nichts" or not nichts or _nichts_gehoert(a)))

        echos: dict[str, int] = {}
        arten: dict[str, int] = {}
        personen: dict[str, int] = {}
        for a in alle:
            if a.get("echo") and passt(a, "echo"):
                echos[a["echo"]] = echos.get(a["echo"], 0) + 1
            if passt(a, "typ"):
                arten[_typ(a)] = arten.get(_typ(a), 0) + 1
            if a.get("person") and passt(a, "person"):
                personen[a["person"]] = personen.get(a["person"], 0) + 1
        nichts_n = sum(1 for a in alle if _nichts_gehoert(a) and passt(a, "nichts"))
        alle = [a for a in alle if passt(a, "")]
        nichts_offen = sum(1 for a in alle if _nichts_sammeln(a))
        anzahl = {u: sum(1 for a in alle if a.get("urteil") == u) for u in (WORT, KEIN_WORT)}
        if art:
            alle = [a for a in alle if a.get("art") == art or a.get("urteil") == art]
        alle.sort(key=lambda a: _zeit(a["zeit"]), reverse=filter_ != "offen")
        if sortierung == "zweifel":
            # your answer against the device's confidence: "said" with a low score, "not said" with a high one first;
            # recordings without a score go last (stable sort keeps them newest first)
            def rang(a: dict[str, Any]) -> float:
                z = _zweifel(a)
                return 2.0 if z is None else -z

            alle.sort(key=rang)
        # a page that no longer exists (the list got shorter while you worked in it) becomes the last one
        seiten = max(1, -(-len(alle) // je_seite))
        seite = max(0, min(seite, seiten - 1))
        return {
            "anzahl": anzahl,
            "echos": echos,
            "arten": arten,
            "personen": personen,
            "nichts": nichts_n,
            "nichts_offen": nichts_offen,
            "gesamt": len(alle),
            "seite": seite,
            "seiten": seiten,
            "eintraege": alle[seite * je_seite:(seite + 1) * je_seite],
        }

    def tabelle(self) -> dict[str, Any]:
        """Device recordings by your answer (rows) and the device's score (columns), for all devices and per device.
        Cells where you and the model disagree strongly are worth listening to again."""
        def leer() -> dict[str, list[int]]:
            return {z: [0] * (len(TABELLE_GRENZEN) - 1) for z in TABELLE_ZEILEN}

        aus: dict[str, dict[str, list[int]]] = {"": leer()}
        for a in self.daten["aufnahmen"].values():
            zeile, score = _zeile(a), a.get("score")
            if zeile is None or not isinstance(score, int | float):
                continue
            spalte = next((i for i in range(len(TABELLE_GRENZEN) - 1) if score < TABELLE_GRENZEN[i + 1]), None)
            if spalte is None:
                continue
            for schluessel in ("", a.get("echo") or "?"):
                aus.setdefault(schluessel, leer())[zeile][spalte] += 1
        return {"grenzen": TABELLE_GRENZEN, "zeilen": aus}

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
        # a recording handed over from another word was heard by that word's model, not by this one
        eigene = [a for a in echo_bew if not a.get("von_wort")]
        aufgewacht = [a for a in eigene if a.get("art") in ("wake", "mistake")]
        richtig = sum(1 for a in aufgewacht if a["urteil"] == WORT)
        verpasst = sum(1 for a in eigene if a.get("art") in ("nearmiss", "noise") and a["urteil"] == WORT)
        # Threshold from your answers: only device recordings scored by the model that is on the devices now
        seit = self.aktiv_seit()
        mit_wert = [
            a for a in echo_bew
            if isinstance(a.get("score"), int | float) and (seit is None or _zeit(a.get("zeit")) >= _zeit(seit))
        ]
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
            "test_wort": sum(1 for a in bewertet if a.get("test") and a["urteil"] == WORT),
            "auto": sum(1 for a in bewertet if a.get("auto")),
            "personen": personen,
            "alltag": {
                "aufgewacht": len(aufgewacht),
                "richtig": richtig,
                "falsch": len(aufgewacht) - richtig,
                "verpasst": verpasst,
            },
            "schwellen": schwellen,
            "schwelle_vorschlag": vorschlag,
            "schwelle_seit": seit,
            "schwelle_basis": {"wort": anzahl_wort, "kein_wort": len(mit_wert) - anzahl_wort},
            "schwelle_auto": self.daten.get("schwelle_auto"),
            "schwelle_hand": self.daten.get("schwelle_hand"),
            "tabelle": self.tabelle(),
            "verteilung": verteilung,
        }

    def tage(self, anzahl: int = 14) -> list[int]:
        """Device recordings per day for the last days (oldest first), for the small chart on the hub."""
        heute = datetime.now().astimezone().date()
        aus = [0] * anzahl
        for a in self.daten["aufnahmen"].values():
            if a.get("quelle") != "echo":
                continue
            z = _zeit(a.get("zeit"))
            if not z:
                continue
            alter = (heute - datetime.fromtimestamp(z).astimezone().date()).days
            if 0 <= alter < anzahl:
                aus[anzahl - 1 - alter] += 1
        return aus

    def trainer_liste(self) -> list[dict[str, Any]]:
        """Alles Bewertete fuer den Trainer (ohne Platzhalter)."""
        return [
            {
                "id": a["id"], "urteil": a["urteil"], "person": a.get("person"),
                "quelle": a["quelle"], "echo": a.get("echo"), "art": a.get("art"),
                "score": a.get("score"), "test": bool(a.get("test")), "dauer": a.get("dauer"),
                "schnitt": a.get("schnitt"),
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

    def aktiv_seit(self) -> str | None:
        """Since when the active version is on the devices (after the restart), else when it was rolled out."""
        if self.daten.get("aktiv_seit"):
            return str(self.daten["aktiv_seit"])
        aktiv = next((v for v in self.daten["versionen"] if v.get("status") == "aktiv"), None)
        return str(aktiv["eingespielt"]) if aktiv and aktiv.get("eingespielt") else None

    def aktive_schwelle(self) -> float | None:
        """The threshold the active version was tested with."""
        aktiv = next((v for v in self.daten["versionen"] if v.get("status") == "aktiv"), None)
        try:
            return float((aktiv or {}).get("bericht", {}).get("cutoff"))
        except (TypeError, ValueError):
            return None

    def version(self, nr: int) -> dict[str, Any] | None:
        return next((v for v in self.daten["versionen"] if v["nr"] == nr), None)

    def arena(self, nr: int) -> int:
        """Device memory the model needs: one model 30000 bytes, an averaged one as many times as it has parts."""
        try:
            return max(30000, int(((self.version(nr) or {}).get("bericht") or {}).get("tensor_arena") or 30000))
        except (TypeError, ValueError):
            return 30000

    def laeuft_nicht(self, nr: int) -> list[str]:
        """Operations of version nr the devices cannot run (empty when it runs everywhere)."""
        try:
            with open(self.modell_datei(nr), "rb") as datei:
                return fehlende_bausteine(datei.read())
        except (KeinModell, OSError):
            return []

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
                "tensor_arena_size": self.arena(nr),
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
