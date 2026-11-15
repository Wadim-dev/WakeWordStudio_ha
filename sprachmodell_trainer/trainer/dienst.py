"""Hauptschleife: alle 20 Sekunden in Home Assistant nachsehen, Auftraege nacheinander abarbeiten."""

from __future__ import annotations

import json
import logging
import os
import platform
import threading
import time
import traceback

from . import __version__
from .ha import HA
from .lauf import Abgebrochen, Lauf

_LOG = logging.getLogger("trainer")
TAKT_S = 20


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
    ram = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as datei:
            for zeile in datei:
                if zeile.startswith("MemTotal:"):
                    ram = round(int(zeile.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return {
        "name": os.environ.get("TRAINER_NAME") or platform.node(),
        "version": __version__,
        "cpu": os.cpu_count(),
        "ram_gb": ram,
        "art": "app" if os.environ.get("SUPERVISOR_TOKEN") and not os.environ.get("HA_URL") else "docker",
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ha = HA()
    o = optionen()
    if o["threads"]:
        os.environ["TF_NUM_INTRAOP_THREADS"] = str(o["threads"])
    daten = os.environ.get("DATEN", "/data")
    os.makedirs(daten, exist_ok=True)
    _LOG.info("Sprachmodell Trainer %s startet, Daten in %s", __version__, daten)
    lauf: Lauf | None = None
    faden: threading.Thread | None = None
    while True:
        try:
            antwort = ha.auftrag()
        except Exception as err:  # noqa: BLE001
            _LOG.warning("Auftrag nicht abgeholt: %s", err)
            time.sleep(TAKT_S)
            continue
        if lauf is not None and antwort.get("abbrechen") == lauf.wort_id:
            _LOG.info("Abbruch fuer %s", lauf.wort_id)
            lauf.abbrechen()
        if faden is not None and not faden.is_alive():
            faden, lauf = None, None
        if lauf is not None:  # Lebenszeichen, damit HA weiss, dass der Lauf weitergeht
            ha.status({"wort_id": lauf.wort_id, "info": info()})
        if faden is None:
            auftrag = antwort.get("auftrag")
            if auftrag:
                lauf = Lauf(ha, auftrag, daten, o)

                def arbeiten(l=lauf):  # noqa: ANN001
                    try:
                        l.ausfuehren()
                    except Abgebrochen:
                        l.melden("bereit", 0, "abgebrochen")
                    except Exception as err:  # noqa: BLE001
                        _LOG.error("Training fehlgeschlagen:\n%s", traceback.format_exc())
                        l.melden("fehler", None, str(err) if isinstance(err, RuntimeError) else f"{type(err).__name__}: {err}")

                faden = threading.Thread(target=arbeiten, daemon=True)
                faden.start()
            else:
                ha.status({"info": info()})
        time.sleep(TAKT_S)
