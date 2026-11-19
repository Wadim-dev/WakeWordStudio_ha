"""Connection to the Wake Word Studio integration in Home Assistant.

As a Home Assistant app: through the Supervisor (SUPERVISOR_TOKEN), nothing to set.
As a Docker container: HA_URL and KEY (shown in the panel: Settings -> Trainer; SCHLUESSEL also works).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

_LOG = logging.getLogger("trainer.ha")
WARTEN_S = 30 * 60  # how long to wait for Home Assistant (restart, update, backup)


def kennung(daten: str | None = None) -> str:
    """Stable id of this trainer, kept in its data folder: Home Assistant tells several trainers apart by it."""
    import secrets

    pfad = os.path.join(daten or os.environ.get("DATEN", "/data"), "trainer_id")
    try:
        with open(pfad, encoding="utf-8") as datei:
            wert = datei.read().strip()
        if wert:
            return wert[:40]
    except OSError:
        pass
    wert = secrets.token_hex(6)
    try:
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as datei:
            datei.write(wert)
    except OSError as err:
        _LOG.warning("Trainer id not saved (%s): it changes with every start", err)
    return wert


def _ha_startet(r: requests.Response) -> bool:
    """True while Home Assistant restarts: proxy/server errors, or HA's own 404 because the
    integration's API is not registered yet (the integration answers 404 with a JSON body)."""
    if r.status_code in (502, 503, 504):
        return True
    return r.status_code == 404 and "json" not in r.headers.get("Content-Type", "")


class HA:
    def __init__(self) -> None:
        token = os.environ.get("SUPERVISOR_TOKEN")
        self.sitzung = requests.Session()
        if os.environ.get("HA_URL"):
            self.basis = os.environ["HA_URL"].rstrip("/") + "/api/sprachmodell/trainer"
            schluessel = os.environ.get("KEY") or os.environ.get("SCHLUESSEL", "")
            if schluessel:
                self.sitzung.headers["X-Sprachmodell-Schluessel"] = schluessel
            elif os.environ.get("HA_TOKEN"):
                self.sitzung.headers["Authorization"] = "Bearer " + os.environ["HA_TOKEN"]
        elif token:
            self.basis = "http://supervisor/core/api/sprachmodell/trainer"
            self.sitzung.headers["Authorization"] = "Bearer " + token
        else:
            raise SystemExit("HA_URL and KEY are missing (see Wake Word Studio -> Settings -> Trainer).")
        self.kennung = kennung()
        self.sitzung.headers["X-Sprachmodell-Trainer"] = self.kennung

    def _url(self, pfad: str) -> str:
        return f"{self.basis}/{pfad}"

    def _anfrage(self, art: str, pfad: str, **kw: Any) -> requests.Response:
        """Request that waits for Home Assistant: a restart or update of Home Assistant
        must not end a training run. Retries for up to WARTEN_S on connection errors,
        5xx answers and HA's own 404 while the integration is still starting."""
        ende = time.monotonic() + WARTEN_S
        pause = 5.0
        while True:
            try:
                r = self.sitzung.request(art, self._url(pfad), **kw)
                if r.status_code == 401:
                    raise SystemExit("Wrong key - see Wake Word Studio -> Settings -> Trainer.")
                if not _ha_startet(r) or (r.status_code == 404 and self._integration_da()):
                    return r
                grund = f"HTTP {r.status_code}"
            except requests.RequestException as err:
                grund = str(err)
            if time.monotonic() > ende:
                raise ConnectionError(f"Home Assistant not reachable: {grund}")
            _LOG.warning("Home Assistant not reachable (%s), trying again in %d s", grund, pause)
            time.sleep(pause)
            pause = min(pause * 1.5, 30.0)

    def _integration_da(self) -> bool:
        """A plain 404 means either "not there" (older integration versions) or "HA is still
        starting". A harmless status call tells them apart: it only works once the integration runs."""
        try:
            return self.sitzung.post(self._url("status"), json={}, timeout=30).status_code == 200
        except requests.RequestException:
            return False

    def _get(self, pfad: str, **kw: Any) -> requests.Response:
        return self._anfrage("GET", pfad, timeout=60, **kw)

    def auftrag(self, frei: bool = True) -> dict[str, Any]:
        """Next job. frei=False: this trainer is busy (run, speed test, update) and takes no new run now."""
        r = self._get("auftrag", params=None if frei else {"frei": "0"})
        r.raise_for_status()
        return r.json()

    def liste(self, wort: str) -> list[dict[str, Any]]:
        r = self._get("liste", params={"wort": wort})
        r.raise_for_status()
        return r.json()["aufnahmen"]

    def audio(self, wort: str, aid: str) -> bytes | None:
        """WAV of a recording, None if it was deleted meanwhile."""
        r = self._get(f"audio/{wort}/{aid}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    def raum(self, knoten: str, rid: str) -> bytes | None:
        """One clap recorded next to a device (its room sound), None if it was deleted meanwhile."""
        r = self._get(f"raum/{knoten}/{rid}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    def modell(self, wort: str) -> bytes | None:
        r = self._get("modell", params={"wort": wort})
        return r.content if r.status_code == 200 else None

    def status(self, daten: dict[str, Any]) -> None:
        try:
            self.sitzung.post(self._url("status"), json=daten, timeout=30)
        except requests.RequestException as err:
            _LOG.warning("Status not sent: %s", err)

    def ergebnis(self, wort: str, tflite: bytes, bericht: dict[str, Any]) -> dict[str, Any]:
        r = self._anfrage(
            "POST", "ergebnis", params={"wort": wort}, timeout=120,
            files={"modell": ("modell.tflite", tflite, "application/octet-stream"),
                   "bericht": ("bericht.json", json.dumps(bericht), "application/json")},
        )
        r.raise_for_status()
        return r.json()

    def gehoert(self, wort: str, ergebnisse: dict[str, str]) -> dict[str, Any]:
        """What the speech recognition heard in each recording (pre-review)."""
        r = self._anfrage("POST", "gehoert", json={"wort_id": wort, "ergebnisse": ergebnisse}, timeout=60)
        r.raise_for_status()
        return r.json()
