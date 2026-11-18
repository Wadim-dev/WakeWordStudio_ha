"""Hauptschleife: alle 20 Sekunden in Home Assistant nachsehen, Auftraege nacheinander abarbeiten."""

from __future__ import annotations

import json
import logging
import os
import platform
import signal
import sys
import threading
import time
import traceback

from . import __version__
from . import erneuern
from .grenzen import beschleuniger, hardware, kerne, prozesse, ram_gb, steckbrief, tempo
from .ha import HA
from .lauf import Abgebrochen, Lauf

_LOG = logging.getLogger("trainer")
TAKT_S = 20
UPDATE_PAUSE_S = 3600  # a failed self-update is tried again after this long


def optionen() -> dict:
    """Einstellungen der HA-App (/data/options.json) oder aus Umgebungsvariablen."""
    o = {"threads": 0, "ziel_fehlausloeser": 1.0, "schritte": 0}
    try:
        with open("/data/options.json", encoding="utf-8") as datei:
            o.update(json.load(datei))
    except (OSError, ValueError):
        pass
    for k, umwandeln in (("threads", int), ("ziel_fehlausloeser", float), ("schritte", int)):
        if os.environ.get(k.upper()):
            o[k] = umwandeln(os.environ[k.upper()])
    return o


def info() -> dict:
    return {
        "name": os.environ.get("TRAINER_NAME") or platform.node(),
        "name_eigen": bool(os.environ.get("TRAINER_NAME")),
        "ort": os.environ.get("TRAINER_ORT") or "",  # "proxmox" when set up by proxmox.sh
        "version": __version__,
        "cpu": kerne(),
        "ram_gb": ram_gb(),
        "prozesse": prozesse(),
        "art": "app" if os.environ.get("SUPERVISOR_TOKEN") and not os.environ.get("HA_URL") else "docker",
        **steckbrief(os.environ.get("DATEN", "/data")),
        **hardware(),
        "beschleuniger": beschleuniger(warten=False),
        "tempo": tempo(warten=False),
        "selbst_update": erneuern.verfuegbar(),
    }


def ausstehende_senden(ha: HA, daten: str) -> None:
    """Results that could not be delivered (Home Assistant was away for long) are sent once it is back."""
    import shutil
    from pathlib import Path

    import requests

    for ordner in sorted((Path(daten) / "ausstehend").glob("*")):
        try:
            bericht = json.loads((ordner / "bericht.json").read_text(encoding="utf-8"))
            ha.ergebnis(ordner.name, (ordner / "modell.tflite").read_bytes(), bericht)
        except requests.HTTPError as err:
            if err.response is not None and 400 <= err.response.status_code < 500:  # word deleted meanwhile
                _LOG.warning("Kept result for %s not accepted (%s), dropped", ordner.name, err)
                shutil.rmtree(ordner, ignore_errors=True)
            continue
        except Exception as err:  # noqa: BLE001
            _LOG.warning("Kept result for %s not sent yet: %s", ordner.name, err)
            continue
        _LOG.info("Kept result for %s delivered", ordner.name)
        shutil.rmtree(ordner, ignore_errors=True)


def vorpruefen(ha: HA, daten: str, liste: list[dict]) -> None:
    """Pre-review while no training runs: the speech recognition listens to new device recordings and HA confirms
    those in which the word was clearly heard. Runs in the separate voices environment; missing there: nothing."""
    import shutil
    import subprocess
    from pathlib import Path

    python = os.environ.get("STIMMEN_PY", "/opt/stimmen/bin/python")
    if not Path(python).exists():
        return
    for eintrag in liste:
        ordner = Path(daten) / "hoeren" / str(eintrag["wort_id"])
        shutil.rmtree(ordner, ignore_errors=True)
        ordner.mkdir(parents=True, exist_ok=True)
        dateien = []
        for aid in eintrag.get("ids", [])[:40]:
            inhalt = ha.audio(eintrag["wort_id"], aid)
            if inhalt is None:
                continue
            (ordner / f"{aid}.wav").write_bytes(inhalt)
            dateien.append({"id": aid, "datei": str(ordner / f"{aid}.wav")})
        if not dateien:
            continue
        auftrag = ordner / "auftrag.json"
        auftrag.write_text(json.dumps({"sprache": eintrag.get("sprache"), "dateien": dateien}), encoding="utf-8")
        umgebung = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
        try:
            r = subprocess.run([python, "-m", "trainer.werkzeug", "hoeren", str(auftrag)], capture_output=True,
                               text=True, timeout=1800, env=umgebung)
        except subprocess.TimeoutExpired:
            _LOG.warning("Pre-review took too long, skipped")
            continue
        zeile = next((z for z in reversed(r.stdout.splitlines()) if z.startswith("ERGEBNIS ")), None)
        if r.returncode != 0 or zeile is None:
            _LOG.warning("Pre-review failed: %s", (r.stdout + r.stderr).strip().splitlines()[-1:] or r.returncode)
            continue
        ergebnisse = json.loads(zeile[9:])
        try:
            antwort = ha.gehoert(eintrag["wort_id"], ergebnisse)
            _LOG.info("Pre-review: %d recordings heard, %d confirmed", len(ergebnisse), antwort.get("bestaetigt", 0))
        except Exception as err:  # noqa: BLE001
            _LOG.warning("Pre-review not sent: %s", err)
        shutil.rmtree(ordner, ignore_errors=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # stop quickly when Docker stops the container (self-update, docker stop): PID 1 ignores SIGTERM otherwise
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    ha = HA()
    o = optionen()
    if o["threads"]:
        os.environ["TF_NUM_INTRAOP_THREADS"] = str(o["threads"])
    daten = os.environ.get("DATEN", "/data")
    os.makedirs(daten, exist_ok=True)
    _LOG.info("Wake Word Studio Trainer %s starting, data in %s", __version__, daten)

    def _messen() -> None:
        """Try the graphics card once (GPU image), then the short speed test; no run starts meanwhile."""
        b = beschleuniger()
        if b.get("gpu"):
            _LOG.info("Training on the graphics card %s (compute capability %s)", b.get("name"), b.get("cc"))
        elif b.get("bild") == "gpu":
            _LOG.warning("Graphics card not usable for training (%s), using the processor: %s",
                         b.get("grund"), b.get("fehler", ""))
        t = tempo(daten)
        _LOG.info("Speed test: %s", t or "not possible")

    messen = threading.Thread(target=_messen, daemon=True)
    messen.start()
    versucht: dict[str, float] = {}  # self-update: tag -> when it was tried
    ersetzt_ab = 0.0
    erneuerung: threading.Thread | None = None
    lauf: Lauf | None = None
    faden: threading.Thread | None = None
    # Erste Meldung nach dem Start: ein Lauf, den HA noch fuer aktiv haelt, ist verloren (Absturz, Neustart)
    ha.status({"neustart": True, "info": info()})
    while True:
        if faden is None and os.path.isdir(os.path.join(daten, "ausstehend")):
            ausstehende_senden(ha, daten)
        beschaeftigt = messen.is_alive() or (erneuerung is not None and erneuerung.is_alive()) \
            or time.monotonic() < ersetzt_ab
        try:
            antwort = ha.auftrag(frei=faden is None and not beschaeftigt)
        except Exception as err:  # noqa: BLE001
            _LOG.warning("Could not fetch a job: %s", err)
            time.sleep(TAKT_S)
            continue
        if lauf is not None and antwort.get("abbrechen") == lauf.wort_id:
            _LOG.info("Cancelled: %s", lauf.wort_id)
            lauf.abbrechen()
        if faden is not None and not faden.is_alive():
            faden, lauf = None, None
        if lauf is not None:  # heartbeat with the full state: after a restart HA shows the run again at once
            ha.status({**lauf.letzter, "live": lauf.live(), "info": info()})
        if faden is None and beschaeftigt:
            # speed test, fetching a new image, or the self-update is about to replace this container: no run now
            ha.status({"info": info()})
        elif faden is None and (tag := antwort.get("aktualisieren")) and erneuern.verfuegbar() \
                and time.monotonic() - versucht.get(tag, -UPDATE_PAUSE_S) >= UPDATE_PAUSE_S:
            versucht[tag] = time.monotonic()

            def _erneuern(tag: str = tag) -> None:
                nonlocal ersetzt_ab
                try:
                    if erneuern.starten(tag) == "gestartet":
                        ersetzt_ab = time.monotonic() + 600
                except Exception as err:  # noqa: BLE001
                    _LOG.warning("Self-update not possible: %s", err)

            erneuerung = threading.Thread(target=_erneuern, daemon=True)
            erneuerung.start()
            ha.status({"info": info()})
        elif faden is None:
            auftrag = antwort.get("auftrag")
            if auftrag:
                lauf = Lauf(ha, auftrag, daten, o)

                def arbeiten(l=lauf):  # noqa: ANN001
                    try:
                        l.ausfuehren()
                    except Abgebrochen:
                        l.notiz("Cancelled", "warnung")
                        l.melden("bereit", 0, "abgebrochen")
                    except Exception as err:  # noqa: BLE001
                        _LOG.error("Training failed:\n%s", traceback.format_exc())
                        l.notiz(f"Training failed: {err}", "fehler")
                        l.melden("fehler", None, str(err) if isinstance(err, RuntimeError) else f"{type(err).__name__}: {err}")

                faden = threading.Thread(target=arbeiten, daemon=True)
                faden.start()
            else:
                ha.status({"info": info()})
                if antwort.get("vorpruefen"):
                    vorpruefen(ha, daten, antwort["vorpruefen"])
        time.sleep(TAKT_S)
