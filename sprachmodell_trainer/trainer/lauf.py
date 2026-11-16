"""Ein Trainingslauf fuer ein Aktivierungswort.

Ablauf: Grunddaten -> eigene Aufnahmen aus HA -> kuenstliche Stimmen -> Merkmale -> microWakeWord-Training
-> ehrlicher Test neu gegen alt -> Ergebnis an HA. Fortschritt geht laufend an HA (App: Training).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import yaml

from .grenzen import kerne
from .grunddaten import Grunddaten, platz_frei
from .ha import HA

_LOG = logging.getLogger("trainer.lauf")

# Mengen kuenstlicher Aufnahmen (MENGE nur zum Ausprobieren verkleinern)
_M = float(os.environ.get("MENGE", "1"))
POS_EIGEN = int(16000 * _M)
POS_FREMD = int(1200 * _M)  # je fremder Stimme
NEG_AEHNLICH = int(12000 * _M)
NEG_SAETZE = int(8000 * _M)
# More voices with OmniVoice (if installed): built up over several runs, at most OMNI_MIN minutes per run
OMNI_POS = int(6000 * _M)
OMNI_NEG = int(3000 * _M)
OMNI_MIN = float(os.environ.get("OMNI_MIN", "90"))
STIMMEN_PY = os.environ.get("STIMMEN_PY", "/opt/stimmen/bin/python")
HALTE_TEST = max(10, int(200 * _M))  # von einer zurueckgehaltenen Stimme, nur zum Testen
FRAMES = 220
MIN_ECHT_TEST = 5
PLATZ_GB = float(os.environ.get("PLATZ_GB", "8"))  # erster Lauf (Grunddaten), danach reichen 3 GB

VOKALE_LATEIN = "aeiouyäöü"
VOKALE_KYRILL = "аеиоуыэюя"
VOKALE = VOKALE_LATEIN + VOKALE_KYRILL + "áéíóúàèìòùâêîôûёїє"

MIXEDNET = [
    "mixednet", "--pointwise_filters", "64,64,64,64", "--repeat_in_block", "1, 1, 1, 1",
    "--mixconv_kernel_sizes", "[5], [7,11], [9,15], [23]", "--residual_connection", "0,0,0,0",
    "--first_conv_filters", "32", "--first_conv_kernel_size", "5", "--stride", "3",
]
MODELL_DATEI = "tflite_stream_state_internal_quant/stream_state_internal_quant.tflite"

PROTOKOLL_ZEILEN = 80
# Watchdog: a step that neither prints anything nor uses the CPU for this long counts as hung and is
# stopped (then retried with fewer processes). A step that only prints nothing but keeps computing is left alone,
# unless it stays silent for STUMM_MAX_S.
STILL_S = int(os.environ.get("STILL_S", "600"))
STUMM_MAX_S = int(os.environ.get("STUMM_MAX_S", str(3 * 3600)))
SPEICHER_REST_GB = 0.25
PLATZ_REST_GB = 0.5  # below this the step stops instead of writing broken files  # less free memory than this for 30 s: stop the step ourselves before the OOM killer picks
VERSUCHE = 3  # attempts per step: normal, then half the processes, then a single process
SCHRITTE_MAX = 40
_BALKEN = re.compile(r"\d+%\||it/s|s/it|\d+/\d+ \[|Mini-Batch #\d+")  # progress lines overwrite each other

# Anteil am Gesamtfortschritt je Abschnitt
ANTEILE = {"vorbereiten": (0, 8), "daten": (8, 12), "stimmen": (12, 35), "merkmale": (35, 50),
           "training": (50, 92), "test": (92, 100)}


def _zuerst_opfern() -> None:
    """Runs in each step process before it starts: if memory runs out, the system should stop this step (which is
    then repeated with less memory) and not the trainer service itself."""
    try:
        with open("/proc/self/oom_score_adj", "w", encoding="ascii") as datei:
            datei.write("1000")
    except OSError:
        pass


def _cpu_gruppe(gruppe: int) -> float:
    """CPU seconds used so far by all processes of a process group (incl. finished children)."""
    takt = os.sysconf("SC_CLK_TCK") or 100
    summe = 0
    for pfad in Path("/proc").glob("[0-9]*/stat"):
        try:
            felder = pfad.read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if len(felder) > 14 and felder[2] == str(gruppe):
            summe += sum(int(x) for x in felder[11:15])
    return summe / takt


class _Mitschrift(logging.Handler):
    """All trainer log messages of a run (including waiting for HA and downloads) also go to the live log."""

    def __init__(self, lauf: Lauf) -> None:
        super().__init__(logging.INFO)
        self.lauf = lauf

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage().splitlines()[0][:240] if record.getMessage() else ""
        except Exception:  # noqa: BLE001
            return
        if getattr(record, "live_schon", False):  # already added by Lauf.notiz
            return
        art = "fehler" if record.levelno >= logging.ERROR else "warnung" if record.levelno >= logging.WARNING else "info"
        if text:
            self.lauf.protokoll.append([round(record.created), art, text])


class Abgebrochen(Exception):
    """Training wurde in der App abgebrochen."""


def aehnliche_woerter(wort: str) -> list[str]:
    """Verwechslungsgefahr: Woerter, die fast so klingen (fuer jede Sprache, ohne Woerterbuch)."""
    w = wort.strip()
    klein = w.lower()
    aus: set[str] = set()
    teile = w.split()
    if len(teile) > 1:
        aus.update(teile)
        aus.add(" ".join(teile[:-1]))
        aus.add(" ".join(teile[1:]))
    if len(klein) > 3:
        for i in range(len(klein)):
            aus.add(klein[:i] + klein[i + 1:])  # Laut weg
        for i in range(len(klein) - 1):
            aus.add(klein[:i] + klein[i + 1] + klein[i] + klein[i + 2:])  # Laute vertauscht
    rnd = random.Random(klein)
    for i, c in enumerate(klein):
        if c in VOKALE:
            vokale = VOKALE_KYRILL if "\u0400" <= c <= "\u04ff" else VOKALE_LATEIN
            for v in rnd.sample(vokale, 4):
                if v != c:
                    aus.add(klein[:i] + v + klein[i + 1:])
    h = max(2, len(klein) // 2)
    aus.update({klein[:h], klein[h:], klein[:h + 1]})
    aus = {a.strip(" ,") for a in aus if len(a.strip()) >= 2}
    aus.discard(klein)
    aus = {a for a in aus if a.lower() != klein and a.lower().replace(" ", "") != klein.replace(" ", "")}
    return sorted(aus)


def wort_ans_ende(wav: bytes, signalton_s: float = 0.3, nachlauf_s: float = 0.08, laenge_s: float = 1.9) -> bytes:
    """Device recordings are a few seconds long; after waking up, the device plays its sound at the end. Training
    learns best when the word ends where the clip ends: find the end of the last stretch of sound before the
    device sound, keep a little after it and laenge_s before it. Without a clear stretch the clip stays as it is."""
    import io
    import wave

    import numpy as np

    with wave.open(io.BytesIO(wav)) as w:
        rate, breite, kanaele = w.getframerate(), w.getsampwidth(), w.getnchannels()
        roh = w.readframes(w.getnframes())
    if breite != 2 or kanaele != 1:
        return wav
    x = np.frombuffer(roh, dtype=np.int16).astype(np.float32)
    rahmen = rate // 100  # 10 ms
    n = len(x) // rahmen
    if n < 100:  # shorter than a second: nothing to cut
        return wav
    pegel = np.sqrt((x[: n * rahmen].reshape(n, rahmen) ** 2).mean(axis=1))
    suche = pegel[: n - int(signalton_s * 100)] if len(x) > 2.5 * rate else pegel
    grenze = max(float(suche.max()) * 0.12, float(np.percentile(suche, 20)) * 3)
    laut = suche > grenze
    ende, i = None, len(laut) - 1
    while i >= 0 and ende is None:  # last loud stretch of at least 150 ms (gaps under 150 ms allowed)
        if not laut[i]:
            i -= 1
            continue
        j, luecke = i, 0
        while j > 0 and luecke < 15:
            j -= 1
            luecke = 0 if laut[j] else luecke + 1
        if i - j >= 15:
            ende = i
        i = j - 1
    if ende is None:
        return wav
    stopp = min(len(x), int((ende / 100 + nachlauf_s) * rate))
    start = max(0, stopp - int(laenge_s * rate))
    aus = io.BytesIO()
    with wave.open(aus, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(x[start:stopp].astype(np.int16).tobytes())
    return aus.getvalue()


def schneiden(wav: bytes, von: float, bis: float) -> bytes:
    """Only the part from von to bis (seconds) of a WAV recording (set by hand in the app)."""
    import io
    import wave

    with wave.open(io.BytesIO(wav)) as w:
        rate, breite, kanaele = w.getframerate(), w.getsampwidth(), w.getnchannels()
        w.setpos(min(w.getnframes(), int(von * rate)))
        roh = w.readframes(max(0, int((bis - von) * rate)))
    aus = io.BytesIO()
    with wave.open(aus, "wb") as w:
        w.setnchannels(kanaele)
        w.setsampwidth(breite)
        w.setframerate(rate)
        w.writeframes(roh)
    return aus.getvalue()


class Lauf:
    def __init__(self, ha: HA, auftrag: dict[str, Any], daten: str, optionen: dict[str, Any]) -> None:
        self.ha = ha
        self.auftrag = auftrag
        self.wort_id = str(auftrag["wort_id"])
        self.wort = str(auftrag["wort"]).strip()
        self.sprache = str(auftrag.get("sprache") or "en")
        self.daten = daten
        self.o = optionen
        self.ordner = Path(daten) / "woerter" / self.wort_id
        self._stopp = threading.Event()
        self._prozess: subprocess.Popen | None = None
        self._zuletzt = 0.0
        self.start = time.time()
        self.phase = "vorbereiten"
        self.letzter: dict[str, Any] = {"wort_id": self.wort_id}  # last reported state, repeated as heartbeat
        # For the detailed view in HA: last log lines and every step with its start time
        self.protokoll: deque[list[Any]] = deque(maxlen=PROTOKOLL_ZEILEN)
        self.schritte: list[dict[str, Any]] = []

    # --- Steuerung --------------------------------------------------------

    def abbrechen(self) -> None:
        self._stopp.set()
        self._beenden()

    def _beenden(self) -> None:
        """Stop the running step including every worker it started (own process group)."""
        p = self._prozess
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                p.kill()

    def _pruefen(self) -> None:
        if self._stopp.is_set():
            raise Abgebrochen

    def melden(self, phase: str, prozent: float | None, schritt: str, sofort: bool = True, **mehr: Any) -> None:
        from .dienst import info

        schluessel = (phase, schritt.split(":")[0])
        if not sofort and schluessel == getattr(self, "_schluessel", None) and time.time() - self._zuletzt < 10:
            return  # only repeated progress of the same step is throttled, a new step is always reported
        self._schluessel = schluessel
        self._zuletzt = time.time()
        if not self.schritte or (self.schritte[-1]["phase"], self.schritte[-1]["schritt"]) != schluessel:
            if self.schritte:
                self.schritte[-1]["ende"] = round(time.time())
            self.schritte.append({"phase": phase, "schritt": schluessel[1], "start": round(time.time())})
            del self.schritte[:-SCHRITTE_MAX]
        self.schritte[-1]["detail"] = schritt
        stufe = (phase, schritt.split(":")[0], int((prozent or 0) // 10))
        if stufe != getattr(self, "_geloggt", None):  # log each step and every 10 % so `docker logs` shows where it is
            self._geloggt = stufe
            self.notiz(f"{phase}: {schritt}" + ("" if prozent is None else f" {prozent:.0f} %"))
        self.letzter = {"wort_id": self.wort_id, "phase": phase,
                        "prozent": None if prozent is None else round(prozent, 1), "schritt": schritt, **mehr}
        self.ha.status({**self.letzter, "live": self.live(), "info": info()})

    def notiz(self, text: str, art: str = "info", ersetzen: bool = False) -> None:
        """A line for `docker logs` and for the live log in HA. ersetzen: overwrite the last line of the same kind
        (progress bars and training steps would otherwise push everything else out)."""
        text = text.strip()[:240]
        if not text:
            return
        if art in ("info", "warnung"):
            (_LOG.warning if art == "warnung" else _LOG.info)(text, extra={"live_schon": True})
        zeile = [round(time.time()), art, text]
        if ersetzen and self.protokoll and self.protokoll[-1][1] == art:
            self.protokoll[-1] = zeile
        else:
            self.protokoll.append(zeile)

    def live(self) -> dict[str, Any]:
        from .grenzen import auslastung

        return {"protokoll": list(self.protokoll), "schritte": self.schritte, "system": auslastung(self.daten),
                "start": round(self.start)}

    def _abschnitt(self, name: str, anteil: float, schritt: str, sofort: bool = False, **mehr: Any) -> None:
        phase = {"stimmen": "daten"}.get(name, name)
        self.phase = phase
        von, bis = ANTEILE[name]
        self.melden(phase, von + (bis - von) * max(0.0, min(1.0, anteil)), schritt, sofort, **mehr)

    def _werkzeug(self, befehl: str, auftrag: dict, abschnitt: str, von: float, bis: float, schritt: str,
                  python: str | None = None) -> dict:
        """Arbeitsschritt als eigenen Prozess starten, Fortschritt weitergeben, abbrechbar, vom Waechter bewacht."""
        datei = self.ordner / f"auftrag_{befehl}.json"
        datei.write_text(json.dumps(auftrag), encoding="utf-8")
        return self._ausfuehren([python or sys.executable, "-m", "trainer.werkzeug", befehl, str(datei)],
                                abschnitt, von, bis, schritt)

    def _werkzeug_sicher(self, befehl: str, auftrag: dict, abschnitt: str, von: float, bis: float,
                         schritt: str) -> dict:
        """Single-process step: if it hangs or runs out of memory, simply run it again (it resumes)."""
        return self._wiederholen(befehl, lambda _stufe: self._werkzeug(befehl, auftrag, abschnitt, von, bis, schritt))

    def _ausfuehren(self, args: list[str], abschnitt: str, von: float, bis: float, schritt: str,
                    cwd: str | None = None, schritte_gesamt: int | None = None, threads: int | None = None,
                    takt: int | None = None) -> dict:
        self._pruefen()
        umgebung = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent), "TF_CPP_MIN_LOG_LEVEL": "2"}
        if threads or self.o.get("threads"):
            umgebung["TF_NUM_INTRAOP_THREADS"] = umgebung["OMP_NUM_THREADS"] = str(threads or self.o["threads"])
        self.notiz("Running " + " ".join(Path(a).name if "/" in a else a for a in args[1:4]))
        # own process group: the watchdog and cancelling stop the step together with all its workers
        self._prozess = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                         bufsize=1, cwd=cwd, env=umgebung, start_new_session=True,
                                         preexec_fn=_zuerst_opfern)
        self._ausgabe_zeit = time.monotonic()
        self._grund: str | None = None
        waechter = threading.Thread(target=self._waechter, args=(self._prozess,), daemon=True)
        waechter.start()
        letzte: deque[str] = deque(maxlen=40)
        ergebnis: dict = {}
        verlauf: deque[tuple[float, float]] = deque()  # (time, share done) of the last minutes, for the time left
        for zeile in self._prozess.stdout:  # type: ignore[union-attr]
            self._ausgabe_zeit = time.monotonic()
            zeile = zeile.rstrip()
            letzte.append(zeile)
            if self._stopp.is_set():
                self._beenden()
                break
            anteil = None
            if zeile.startswith("FORTSCHRITT "):
                _, a, b = zeile.split()
                anteil = int(a) / max(1, int(b))
            elif zeile.startswith("ERGEBNIS "):
                ergebnis = json.loads(zeile[9:])
            elif schritte_gesamt and takt and (m := re.search(r"Validation Batch #(\d+).*Mini-Batch #(\d+)", zeile)):
                # microWakeWord's line per training step: (evaluation round, step within the round)
                anteil = ((int(m.group(1)) - 1) * takt + int(m.group(2))) / schritte_gesamt
                self._ausgabe(zeile)
            elif schritte_gesamt and (m := re.search(r"Step #?(\d+)", zeile)):
                anteil = int(m.group(1)) / schritte_gesamt
                if "Validation" in zeile:
                    self.notiz(zeile)
                else:
                    self.notiz(zeile, "schritt", ersetzen=True)
            else:
                self._ausgabe(zeile)
            if anteil is not None:
                self._abschnitt(abschnitt, von + (bis - von) * anteil, schritt, **self._restzeit(verlauf, anteil))
        code = self._prozess.wait()
        self._beenden()  # workers left behind by a crashed step
        self._prozess = None
        self._pruefen()
        if self._grund:
            raise RuntimeError(self._grund)
        if code != 0:
            _LOG.error("Step failed:\n%s", "\n".join(letzte))
            if code < 0 or code == 137:  # killed from outside, almost always the out-of-memory killer
                raise RuntimeError(f"SPEICHER Step was stopped by the system (signal {-code if code < 0 else 9}), "
                                   "probably out of memory")
            raise RuntimeError(next((z for z in reversed(letzte) if z.strip()), f"exit {code}")[:300])
        return ergebnis

    @staticmethod
    def _restzeit(verlauf: deque[tuple[float, float]], anteil: float) -> dict[str, int]:
        """Minutes left of the running step, from its pace over the last 15 minutes (shown once it is known)."""
        jetzt = time.monotonic()
        if not verlauf or anteil < verlauf[-1][1]:
            verlauf.clear()  # first value, or the step started again
        if not verlauf or jetzt - verlauf[-1][0] >= 5:
            verlauf.append((jetzt, anteil))
        while len(verlauf) > 2 and jetzt - verlauf[1][0] > 900:
            verlauf.popleft()
        zeit, alt = verlauf[0]
        if jetzt - zeit < 120 or anteil <= alt:
            return {}
        return {"restzeit_min": max(1, round((1 - anteil) * (jetzt - zeit) / (anteil - alt) / 60))}

    def _waechter(self, prozess: subprocess.Popen) -> None:
        """Never wait silently: stop a step that hangs or is about to run out of memory."""
        from .grenzen import frei_gb

        cpu_alt, cpu_zeit = _cpu_gruppe(prozess.pid), time.monotonic()
        knapp_seit: float | None = None
        while prozess.poll() is None:
            time.sleep(5)
            jetzt = time.monotonic()
            frei = frei_gb()
            if frei is not None and frei < SPEICHER_REST_GB:
                knapp_seit = knapp_seit or jetzt
                if jetzt - knapp_seit > 30:
                    self._grund = f"SPEICHER Only {frei:.2f} GB memory left, step stopped before the system kills it"
                    break
            else:
                knapp_seit = None
            if platz_frei(self.daten) < PLATZ_REST_GB:
                self._grund = (f"PLATZ Disk almost full ({platz_frei(self.daten):.1f} GB left), step stopped. "
                               "Free space on the trainer and start again")
                break
            if jetzt - cpu_zeit >= STILL_S:
                cpu = _cpu_gruppe(prozess.pid)
                still = jetzt - self._ausgabe_zeit
                if still >= STILL_S and cpu - cpu_alt < 2:
                    self._grund = f"HAENGT No output and no computing for {round(still / 60)} min, step stopped"
                    break
                if still >= STUMM_MAX_S:
                    self._grund = f"HAENGT No output for {round(still / 60)} min, step stopped"
                    break
                cpu_alt, cpu_zeit = cpu, jetzt
        if self._grund and prozess.poll() is None:
            self.notiz(self._grund.split(" ", 1)[1], "fehler")
            self._beenden()

    def _wiederholen(self, name: str, versuch: Any) -> Any:
        """Run a step; if it hung or ran out of memory, run it again with fewer processes (slower, but it finishes).
        versuch(stufe) gets 0, 1, 2: normal, half the processes, one process."""
        # a run resumed after a trainer restart (auftrag "sparsam") starts right away with less memory
        start = min(int(self.auftrag.get("sparsam") or 0), VERSUCHE - 1)
        for stufe in range(start, VERSUCHE):
            try:
                return versuch(stufe)
            except RuntimeError as err:
                text = str(err)
                art, _, rest = text.partition(" ")
                if art in ("SPEICHER", "HAENGT", "PLATZ"):
                    if stufe == VERSUCHE - 1 or art == "PLATZ":  # fewer processes do not help against a full disk
                        raise RuntimeError(rest) from err
                else:
                    raise
                self.notiz(f"{name}: {text.split(' ', 1)[1]} - trying again with fewer processes "
                           f"({stufe + 2}/{VERSUCHE})", "warnung")
        raise RuntimeError(name)  # not reached

    def _ausgabe(self, zeile: str) -> None:
        """Output of a step for the live log: warnings stay, progress bars overwrite each other."""
        z = zeile.strip()
        if not z:
            return
        if _BALKEN.search(z):
            self.notiz(z, "balken", ersetzen=True)
        elif z.startswith("SPEICHER") or re.search(r"error|fehler|traceback|killed", z, re.IGNORECASE):
            self.notiz(z, "fehler")
        elif re.search(r"warn", z, re.IGNORECASE):
            self.notiz(z, "warnung_aus")
        else:
            self.notiz(z, "aus")

    # --- Ablauf -----------------------------------------------------------

    def ausfuehren(self) -> None:
        mitschrift = _Mitschrift(self)
        logging.getLogger("trainer").addHandler(mitschrift)
        try:
            self._ausfuehren_lauf()
        finally:
            logging.getLogger("trainer").removeHandler(mitschrift)

    def _ausfuehren_lauf(self) -> None:
        self.ordner.mkdir(parents=True, exist_ok=True)
        self._abschnitt("vorbereiten", 0, "grunddaten", True)
        g = Grunddaten(self.daten, lambda s: (self._pruefen(), self._abschnitt("vorbereiten", 0.3, s, True)))
        noetig = PLATZ_GB if not (g.o / "neg" / "speech" / "fertig").exists() else min(PLATZ_GB, 3)
        if platz_frei(self.daten) < noetig:
            raise RuntimeError(f"Not enough disk space: at least {noetig:g} GB free needed")
        neg = g.negative()
        bg = g.hintergrund()
        rir = g.raumklang()
        gerede = g.gerede(self.sprache)
        stimmen = g.stimmen(self.sprache)
        g.aufraeumen()
        self._pruefen()
        if not stimmen.get(self.sprache):
            raise RuntimeError(f"No voice for language {self.sprache}")

        echt = self._echte_aufnahmen()
        tts = self._stimmen(stimmen, gerede)
        merkmale = self._merkmale(echt, tts, bg, rir, gerede, g)
        tflite = self._training(merkmale, self._schlanke_negative(neg))
        bericht = self._test(tflite, echt, tts, bg, gerede)
        self._abschnitt("test", 1, "senden", True)
        try:
            self.ha.ergebnis(self.wort_id, tflite.read_bytes(), bericht)
        except Exception as err:  # noqa: BLE001 - Home Assistant gone for longer than 30 minutes
            ablage = Path(self.daten) / "ausstehend" / self.wort_id
            ablage.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tflite, ablage / "modell.tflite")
            (ablage / "bericht.json").write_text(json.dumps(bericht), encoding="utf-8")
            self.notiz(f"Home Assistant not reachable ({err}); the result is kept and sent as soon as it is back",
                       "warnung")
            self.letzter = {"wort_id": self.wort_id}
            return
        self.letzter = {"wort_id": self.wort_id}  # HA now shows the result; the heartbeat must not report "testing" again
        _LOG.info("Done: %s", json.dumps(bericht, ensure_ascii=False))
        self.notiz("Done, result sent to Home Assistant")
        if self.schritte:
            self.schritte[-1]["ende"] = round(time.time())
        self.ha.status({"wort_id": self.wort_id, "live": self.live()})

    # --- eigene Aufnahmen ---------------------------------------------------

    def _echte_aufnahmen(self) -> dict[str, list[dict]]:
        self._abschnitt("daten", 0, "aufnahmen", True)
        liste = self.ha.liste(self.wort_id)
        basis = self.ordner / "echt"
        aus: dict[str, list[dict]] = {k: [] for k in ("wort_train", "wort_test", "kein_train", "kein_test")}
        behalten = set()
        for i, a in enumerate(liste):
            self._pruefen()
            art = ("wort" if a["urteil"] == "wort" else "kein") + ("_test" if a.get("test") else "_train")
            schnitt = a.get("schnitt")
            # cut by hand wins; device recordings of a wake-up get the word moved to the end (device sound off)
            ende = not schnitt and a.get("quelle") == "echo" and a.get("art") in ("wake", "mistake")
            name = a["id"] + (f"_{schnitt[0]:g}_{schnitt[1]:g}" if schnitt else "_e1" if ende else "")
            ziel = basis / art / f"{name}.wav"
            behalten.add(ziel)
            if not ziel.exists():
                inhalt = self.ha.audio(self.wort_id, a["id"])
                if inhalt is None:  # deleted in the meantime
                    self.notiz(f"Recording {a['id']} no longer exists, skipped", "warnung")
                    behalten.discard(ziel)
                    continue
                if schnitt:
                    inhalt = schneiden(inhalt, float(schnitt[0]), float(schnitt[1]))
                elif ende:
                    inhalt = wort_ans_ende(inhalt)
                ziel.parent.mkdir(parents=True, exist_ok=True)
                tmp = ziel.with_suffix(".tmp")
                tmp.write_bytes(inhalt)
                tmp.replace(ziel)
            aus[art].append({"datei": str(ziel), "person": a.get("person") or ""})
            if i % 20 == 0:
                self._abschnitt("daten", i / max(1, len(liste)), f"aufnahmen:{i}/{len(liste)}")
        if basis.exists():  # umbewertete oder geloeschte Aufnahmen entfernen
            for f in basis.glob("*/*.wav"):
                if f not in behalten:
                    f.unlink()
        self.bewertet = len(liste)
        return aus

    # --- kuenstliche Stimmen ------------------------------------------------

    def _stimmen(self, stimmen: dict[str, list[Path]], gerede: dict[str, Path]) -> dict[str, Path]:
        eigen = [str(p) for p in stimmen[self.sprache]]
        halte = eigen[-1]
        lernen = eigen[:-1] or eigen
        fremd = [str(p[0]) for s, p in stimmen.items() if s != self.sprache and p]
        marke = hashlib.sha1(json.dumps([self.wort.lower(), self.sprache, eigen, fremd]).encode()).hexdigest()
        basis = self.ordner / "tts"
        if (basis / "marke").exists() and (basis / "marke").read_text() != marke:
            shutil.rmtree(basis, ignore_errors=True)  # Wort geaendert: alles neu
            shutil.rmtree(self.ordner / "merkmale", ignore_errors=True)
            shutil.rmtree(self.ordner / "train", ignore_errors=True)
        basis.mkdir(parents=True, exist_ok=True)
        (basis / "marke").write_text(marke)

        w = self.wort
        pos_texte = sorted({w, w + "!", w + "?", w + ".", w.lower(), w.capitalize(), w + ", "})
        aehnlich = self._aehnlich_pruefen(aehnliche_woerter(w), lernen)
        saetze = self._saetze(gerede)
        aufgaben = [
            ("pos_eigen", POS_EIGEN, pos_texte, lernen, None),
            *[(f"pos_fremd_{i}", POS_FREMD, pos_texte, [v], eigen[0]) for i, v in enumerate(fremd)],
            ("neg_aehnlich", NEG_AEHNLICH, aehnlich, lernen, None),
            ("neg_saetze", NEG_SAETZE, saetze, lernen, None),
            ("test_pos", HALTE_TEST, pos_texte, [halte], None),
            ("test_neg", HALTE_TEST, aehnlich, [halte], None),
        ]
        gesamt = sum(a[1] for a in aufgaben)
        erledigt = 0
        aus = {}
        for name, anzahl, texte, voices, lautschrift in aufgaben:
            ziel = basis / name
            aus[name] = ziel
            if len(self._wavs(ziel)) < anzahl:  # new, or more clips wanted than last time: it resumes
                von, bis = erledigt / gesamt, (erledigt + anzahl) / gesamt
                self._werkzeug_sicher("tts", {"ziel": str(ziel), "anzahl": anzahl, "texte": texte, "stimmen": voices,
                                       "lautschrift_von": lautschrift, "prozesse": 2},
                               "stimmen", von, bis, "stimmen")
            erledigt += anzahl
        (basis / "aehnlich.txt").write_text("\n".join(aehnlich), encoding="utf-8")
        aus.update(self._omni(basis, pos_texte, aehnlich + saetze[:300]))
        return aus

    def _aehnlich_pruefen(self, aehnlich: list[str], stimmen: list[str]) -> list[str]:
        """Listening check: a sound-alike that a synthetic voice says exactly like the word (one letter off, an
        unstressed vowel) would teach the model to ignore its own word. Each sound-alike is spoken a few times and
        heard by the speech recognition; those heard as the word are left out. Done once per word (the result is
        kept); without the speech recognition all sound-alikes stay, as before."""
        from .werkzeug import _normal

        basis = self.ordner / "tts"
        merker = basis / "aehnlich_geprueft.json"
        try:
            alt = json.loads(merker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            alt = {}
        if alt.get("texte") == aehnlich:
            weg = set(alt.get("weg") or [])
        elif not Path(STIMMEN_PY).exists():
            return aehnlich
        else:
            probe = self.ordner / "probe"
            shutil.rmtree(probe, ignore_errors=True)
            try:
                self._werkzeug("proben", {"ziel": str(probe), "texte": aehnlich, "stimmen": stimmen, "je": 3},
                               "stimmen", 0, 0.01, "aehnlich_pruefen")
                dateien = [{"id": f.stem, "datei": str(f)} for f in sorted(probe.glob("*.wav"))]
                gehoert = self._werkzeug("hoeren", {"sprache": self.sprache, "dateien": dateien}, "stimmen", 0, 0.01,
                                         "aehnlich_pruefen", python=STIMMEN_PY)
            except Abgebrochen:
                raise
            except RuntimeError as err:
                self.notiz(f"Listening check skipped this time: {err}", "warnung")
                return aehnlich
            finally:
                shutil.rmtree(probe, ignore_errors=True)
            weg = {aehnlich[int(k.split("_")[0])] for k, text in gehoert.items() if _normal(text) == _normal(self.wort)}
            merker.write_text(json.dumps({"texte": aehnlich, "weg": sorted(weg)}, ensure_ascii=False), encoding="utf-8")
            if weg:
                self.notiz(f"Listening check: {len(weg)} of {len(aehnlich)} sound-alikes sound like the word and are "
                           f"left out: {', '.join(sorted(weg))[:160]}")
        rest = [t for t in aehnlich if t not in weg]
        # the sound-alike clips are made again without the left-out ones (also their features)
        ziel = basis / "neg_aehnlich"
        stand = ziel / "texte.json"
        if ziel.exists() and (not stand.exists() or json.loads(stand.read_text(encoding="utf-8")) != rest):
            shutil.rmtree(ziel, ignore_errors=True)
            shutil.rmtree(self.ordner / "merkmale" / "neg_aehnlich", ignore_errors=True)
        ziel.mkdir(parents=True, exist_ok=True)
        stand.write_text(json.dumps(rest, ensure_ascii=False), encoding="utf-8")
        return rest or aehnlich

    def _omni(self, basis: Path, pos_texte: list[str], neg_texte: list[str]) -> dict[str, Path]:
        """More and different voices with OmniVoice, checked by speech recognition. Slow without a graphics card,
        so the stock grows by at most OMNI_MIN minutes per run until it is full. Missing or failing: the run simply
        goes on with Piper alone."""
        ziel = basis / "omni"
        aus = {"omni_pos": ziel / "pos", "omni_neg": ziel / "neg"}
        if not Path(STIMMEN_PY).exists() or OMNI_MIN <= 0:
            return aus
        if len(self._wavs(aus["omni_pos"])) >= OMNI_POS and len(self._wavs(aus["omni_neg"])) >= OMNI_NEG:
            return aus
        self.notiz(f"More voices (OmniVoice): {len(self._wavs(aus['omni_pos']))} of {OMNI_POS} clips so far, "
                   f"up to {OMNI_MIN:g} min this run")
        try:
            self._werkzeug("omni", {
                "sprache": self.sprache, "wort": self.wort, "ziel_pos": str(aus["omni_pos"]),
                "ziel_neg": str(aus["omni_neg"]), "anzahl_pos": OMNI_POS, "anzahl_neg": OMNI_NEG,
                "texte_pos": pos_texte, "texte_neg": neg_texte, "minuten": OMNI_MIN,
            }, "stimmen", 0.95, 1.0, "stimmen_omni", python=STIMMEN_PY)
        except Abgebrochen:
            raise
        except RuntimeError as err:
            self.notiz(f"OmniVoice not used this time: {err}", "warnung")
        return aus

    def _saetze(self, gerede: dict[str, Path]) -> list[str]:
        """Kurze Stuecke echter Saetze der Sprache: Alltagsgerede, das nicht ausloesen darf."""
        datei = gerede["train"] / "saetze.txt"
        saetze = datei.read_text(encoding="utf-8").splitlines() if datei.exists() else []
        rnd = random.Random(1)
        aus = set()
        wl = self.wort.lower()
        for s in rnd.sample(saetze, min(len(saetze), 1500)):
            teile = s.split()
            if not teile:
                continue
            n = rnd.randint(1, min(4, len(teile)))
            i = rnd.randrange(0, len(teile) - n + 1)
            stueck = " ".join(teile[i:i + n]).strip(" ,.;:!?\"'")
            if len(stueck) >= 2 and wl not in stueck.lower():
                aus.add(stueck)
        return sorted(aus) or aehnliche_woerter(self.wort)

    # --- Merkmale -----------------------------------------------------------

    def _merkmale(self, echt: dict, tts: dict, bg: list[Path], rir: Path, gerede: dict[str, Path],
                  g: Grunddaten) -> dict[str, dict]:
        basis = self.ordner / "merkmale"
        bgs = [str(p) for p in bg] + [str(gerede["train"])]
        wdh_echt = lambda n: max(3, min(40, 3000 // max(1, n)))  # noqa: E731
        sets: list[tuple[str, list[str], int, bool, bool, float, float]] = [
            # name, dateien, Wiederholungen, wort?, neu bauen?, Gewicht, Strafe
            ("pos_eigen", self._wavs(tts["pos_eigen"]), 2, True, False, 2.0, 1.0),
            ("pos_fremd", [f for k, p in tts.items() if k.startswith("pos_fremd") for f in self._wavs(p)],
             1, True, False, 1.0, 1.0),
            ("neg_aehnlich", self._wavs(tts["neg_aehnlich"]), 1, False, False, 3.0, 2.0),
            ("neg_saetze", self._wavs(tts["neg_saetze"]), 1, False, False, 1.0, 1.5),
            ("omni_pos", self._wavs(tts["omni_pos"]), 2, True, False, 2.0, 1.0),
            ("omni_neg", self._wavs(tts["omni_neg"]), 1, False, False, 3.0, 2.0),
        ]
        sets = [s for s in sets if s[1]]
        if echt["wort_train"]:
            d = [a["datei"] for a in echt["wort_train"]]
            sets.append(("echt_wort", d, wdh_echt(len(d)), True, True, 2.0, 1.0))
        if echt["kein_train"]:
            d = [a["datei"] for a in echt["kein_train"]]
            sets.append(("echt_kein", d, wdh_echt(len(d)), False, True, 1.5, 3.0))
        gesamt = sum(len(s[1]) * s[2] for s in sets) or 1
        erledigt = 0
        aus: dict[str, dict] = {}
        for name, dateien, wdh, ist_wort, neu, gewicht, strafe in sets:
            ziel = basis / name
            menge = len(dateien) * wdh
            # rebuilt when the set changed (more clips than last time) - the marker holds the number of files
            stand = (ziel / "fertig").read_text().strip() if (ziel / "fertig").exists() else None
            if neu or stand != str(len(dateien)):
                shutil.rmtree(ziel, ignore_errors=True)
                rnd = random.Random(name)
                dateien = sorted(dateien)
                rnd.shuffle(dateien)
                n_val = max(1, len(dateien) // 10) if len(dateien) >= 10 else 0
                for teil, auswahl in (("validation", dateien[:n_val]), ("training", dateien[n_val:])):
                    if not auswahl:
                        continue
                    anteil = len(auswahl) * wdh / gesamt
                    self._merkmale_werkzeug({
                        "ziel": str(ziel / teil / f"{name}_mmap"), "dateien": auswahl, "wiederholungen": wdh,
                        "frames": FRAMES, "trim": True, "bg": bgs, "rir": str(rir), "snr_min": -5,
                        "prozesse": self.o.get("threads") or None,
                    }, erledigt / gesamt, erledigt / gesamt + anteil, "merkmale")
                    erledigt += len(auswahl) * wdh
                if (ziel / "validation").exists():
                    shutil.copytree(ziel / "validation", ziel / "testing", dirs_exist_ok=True)
                (ziel / "fertig").write_text(str(len(dateien)))
            else:
                erledigt += menge
            aus[name] = {"dir": str(ziel), "wort": ist_wort, "gewicht": gewicht, "strafe": strafe}
        # Gerede der Sprache in voller Laenge: einmal je Sprache, fuer alle Woerter
        lang = g.o / "merkmale" / f"gerede_{self.sprache}"
        if not (lang / "fertig").exists():
            shutil.rmtree(lang, ignore_errors=True)
            self._merkmale_werkzeug({"ziel": str(lang / "training" / "gerede_mmap"), "ordner": [str(gerede["train"])],
                                     "wiederholungen": 0, "prozesse": self.o.get("threads") or None},
                                    0.95, 1.0, "merkmale_gerede")
            (lang / "fertig").touch()
        aus["gerede"] = {"dir": str(lang), "wort": False, "gewicht": 8.0, "strafe": 1.0, "lang": True}
        return aus

    def _merkmale_werkzeug(self, auftrag: dict, von: float, bis: float, schritt: str) -> dict:
        """Feature step; hung or out of memory: again with half the processes, then with one."""
        from .grenzen import prozesse

        n = prozesse(auftrag.get("prozesse"))

        def versuch(stufe: int) -> dict:
            if stufe:
                shutil.rmtree(auftrag["ziel"], ignore_errors=True)
            p = 1 if stufe == 2 else max(1, n // 2) if stufe == 1 else n
            self.notiz(f"Computing features with {p} process{'es' if p > 1 else ''}")
            return self._werkzeug("merkmale", {**auftrag, "prozesse": p}, "merkmale", von, bis, schritt)

        return self._wiederholen("Features", versuch)

    @staticmethod
    def _wavs(ordner: Path) -> list[str]:
        return sorted(str(p) for p in Path(ordner).glob("*.wav"))

    # --- Training -----------------------------------------------------------

    def _schlanke_negative(self, neg: dict[str, Path]) -> dict[str, Path]:
        """microWakeWord loads validation and test sets completely into memory at every evaluation. The full base
        sets need far more than small machines have (the container was killed at the first evaluation), so
        evaluation uses evenly chosen samples that fit the memory: more memory, more samples."""
        from .grenzen import ram_gb

        ram = ram_gb() or 4.0
        stufe = int(self.auftrag.get("sparsam") or 0)
        faktor = 1 / (2 ** stufe)
        max_proben = max(500, int(ram * 800 * faktor))
        max_frames = max(30000, int(ram * 50000 * faktor))
        ziel = Path(self.daten) / "schlank" / f"{max_proben}_{max_frames}"
        for alt in (Path(self.daten) / "schlank").glob("*"):  # other sizes (other memory) are no longer needed
            if alt != ziel:
                shutil.rmtree(alt, ignore_errors=True)
        aus = {}
        for name, pfad in neg.items():
            z = ziel / name
            if not (z / "fertig").exists():
                shutil.rmtree(z, ignore_errors=True)
                self._werkzeug_sicher("schlank", {"quelle": str(pfad), "ziel": str(z), "max_proben": max_proben,
                                                  "max_frames": max_frames}, "training", 0, 0, "auswahl")
                (z / "fertig").touch()
            aus[name] = z
        self.notiz(f"Evaluation uses up to {max_proben} samples per set and {max_frames // 6000} min of ambient audio")
        return aus

    def _training(self, merkmale: dict[str, dict], neg: dict[str, Path]) -> Path:
        train = self.ordner / "train"
        weiter = (train / "restore").exists() and not self.o.get("schritte")
        self.weiter = weiter
        if weiter:
            schritte, lr = [3000, 3000], [0.0002, 0.0001]
        else:
            shutil.rmtree(train, ignore_errors=True)
            gesamt = int(self.o.get("schritte") or 15000)
            schritte, lr = [gesamt * 2 // 3, gesamt - gesamt * 2 // 3], [0.0005, 0.0001]

        def satz(d: str, gewicht: float, strafe: float, wahr: bool, art: str) -> dict:
            return {"features_dir": d, "sampling_weight": gewicht, "penalty_weight": strafe, "truth": wahr,
                    "truncation_strategy": art, "type": "mmap"}

        features = [satz(m["dir"], m["gewicht"], m["strafe"], m["wort"],
                         "random" if m.get("lang") else "truncate_start") for m in merkmale.values()]
        features += [
            satz(str(neg["speech"]), 10.0, 1.0, False, "random"),
            satz(str(neg["dinner_party"]), 10.0, 1.0, False, "random"),
            satz(str(neg["no_speech"]), 5.0, 1.0, False, "random"),
            satz(str(neg["dinner_party_eval"]), 0.0, 1.0, False, "split"),
        ]
        cfg = {
            "window_step_ms": 10, "train_dir": str(train), "features": features,
            "training_steps": schritte, "positive_class_weight": [1, 1], "negative_class_weight": [20, 20],
            "learning_rates": lr, "batch_size": 128,
            "time_mask_max_size": [5, 5], "time_mask_count": [2, 2], "freq_mask_max_size": [5, 5], "freq_mask_count": [2, 2],
            "eval_step_interval": min(500, max(10, sum(schritte) // 4)), "clip_duration_ms": 1500,
            "target_minimization": 0.9, "minimization_metric": None, "maximization_metric": "average_viable_recall",
        }
        datei = self.ordner / "training.yaml"
        datei.write_text(yaml.dump(cfg), encoding="utf-8")
        text = "weitertrainieren" if weiter else "training"
        self._abschnitt("training", 0, text, True, schritte=sum(schritte))
        args = [sys.executable, "-m", "microwakeword.model_train_eval", f"--training_config={datei}",
                "--train", "1", "--restore_checkpoint", "1",
                "--test_tf_nonstreaming", "0", "--test_tflite_nonstreaming", "0",
                "--test_tflite_nonstreaming_quantized", "0", "--test_tflite_streaming", "0",
                "--test_tflite_streaming_quantized", "1", "--use_weights", "best_weights", *MIXEDNET]
        def versuch(stufe: int) -> None:
            if stufe:  # smaller batches need less memory; the run continues from its last checkpoint
                cfg["batch_size"] = 128 >> stufe
                datei.write_text(yaml.dump(cfg), encoding="utf-8")
                self.notiz(f"Training with batch size {cfg['batch_size']}")
            self._ausfuehren(args, "training", 0, 1, text, cwd=str(self.ordner), schritte_gesamt=sum(schritte),
                             threads=None if not stufe else max(1, kerne() >> stufe), takt=cfg["eval_step_interval"])

        self._wiederholen("Training", versuch)
        modell = train / MODELL_DATEI
        if not modell.exists():
            raise RuntimeError("Training produced no model")
        return modell

    # --- ehrlicher Test -----------------------------------------------------

    def _test(self, tflite: Path, echt: dict, tts: dict, bg: list[Path], gerede: dict[str, Path]) -> dict:
        positiv = echt["wort_test"]
        quelle = "echt"
        if len(positiv) < MIN_ECHT_TEST:
            quelle = "kuenstlich"
            positiv = positiv + [{"datei": f, "person": ""} for f in self._wavs(tts["test_pos"])[:150]]
        negativ = [a["datei"] for a in echt["kein_test"]] + self._wavs(tts["test_neg"])[:150]
        rede = self._wavs(gerede["test"]) + self._wavs(gerede["dev"])
        random.Random(3).shuffle(rede)
        musik = sorted(str(p) for p in Path(bg[0]).glob("*.wav"))
        random.Random(4).shuffle(musik)
        auftrag = {"positiv": positiv, "negativ": negativ, "gerede": rede, "bg": musik[:300], "max_stunden": 3}

        neu = self._werkzeug_sicher("pruefen", {**auftrag, "modell": str(tflite)}, "test", 0, 0.5, "test_neu")
        alt = None
        alt_bytes = self.ha.modell(self.wort_id) if self.auftrag.get("aktiv") else None
        if alt_bytes:
            alt_datei = self.ordner / "alt.tflite"
            alt_datei.write_bytes(alt_bytes)
            alt = self._werkzeug_sicher("pruefen", {**auftrag, "modell": str(alt_datei)}, "test", 0.5, 1.0,
                                 "test_alt")
        ziel = float(self.o.get("ziel_fehlausloeser") or 1.0)
        cut_neu, werte_neu = self._schwelle(neu, ziel)
        bericht: dict[str, Any] = {
            "neu": werte_neu, "cutoff": cut_neu, "ziel_fehlausloeser": ziel, "test_quelle": quelle,
            "test_positiv": neu["positiv"], "test_negativ": neu["negativ"], "test_stunden": neu["stunden"],
            "je_schwelle": neu["je_schwelle"], "bewertet_genutzt": getattr(self, "bewertet", 0),
            "start": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.start)),
            "dauer_min": round((time.time() - self.start) / 60, 1),
            "weitertrainiert": getattr(self, "weiter", False),
        }
        if alt:
            cut_alt, werte_alt = self._schwelle(alt, ziel)
            bericht["alt"] = {**werte_alt, "cutoff": cut_alt}
            bericht["besser"] = self._besser(werte_neu, werte_alt, ziel)
        else:
            bericht["alt"] = None
            bericht["besser"] = True
        return bericht

    @staticmethod
    def _schwelle(ergebnis: dict, ziel: float) -> tuple[float, dict]:
        """Niedrigste Schwelle, bei der die Fehlausloeser unter dem Ziel bleiben (sonst die strengste)."""
        je = {float(k): v for k, v in ergebnis["je_schwelle"].items()}
        passend = [c for c, v in sorted(je.items())
                   if v["fehlausloeser_pro_stunde"] is None or v["fehlausloeser_pro_stunde"] <= ziel]
        cut = passend[0] if passend else max(je)
        cut = max(cut, 0.8)  # darunter zu riskant fuer unbekannte Raeume
        if cut not in je:
            cut = min((c for c in je if c >= cut), default=max(je))
        w = je[cut]
        return cut, {
            "trefferquote": w["trefferquote"], "trefferquote_musik": w["trefferquote_musik"],
            "fehlausloeser_pro_stunde": None if w["fehlausloeser_pro_stunde"] is None else round(w["fehlausloeser_pro_stunde"], 2),
            "gegenbeispiele": w["gegenbeispiele"], "je_person": w["je_person"],
        }

    @staticmethod
    def _besser(neu: dict, alt: dict, ziel: float) -> bool:
        tn, ta = neu["trefferquote"] or 0, alt["trefferquote"] or 0
        fn, fa = neu["fehlausloeser_pro_stunde"] or 0, alt["fehlausloeser_pro_stunde"] or 0
        if tn >= ta + 0.01 and fn <= max(fa, ziel) * 1.1:
            return True
        if tn >= ta - 0.005 and fn < fa * 0.8:
            return True
        return False
