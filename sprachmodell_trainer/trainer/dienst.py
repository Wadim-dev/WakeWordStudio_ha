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
from .grenzen import kerne, prozesse, ram_gb
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
    return {
        "name": os.environ.get("TRAINER_NAME") or platform.node(),
        "version": __version__,
        "cpu": kerne(),
        "ram_gb": ram_gb(),
        "prozesse": prozesse(),
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
    _LOG.info("Wake Word Studio Trainer %s starting, data in %s", __version__, daten)
    lauf: Lauf | None = None
    faden: threading.Thread | None = None
    # Erste Meldung nach dem Start: ein Lauf, den HA noch fuer aktiv haelt, ist verloren (Absturz, Neustart)
    ha.status({"neustart": True, "info": info()})
    while True:
        try:
            antwort = ha.auftrag()
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
        if faden is None:
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
        time.sleep(TAKT_S)
