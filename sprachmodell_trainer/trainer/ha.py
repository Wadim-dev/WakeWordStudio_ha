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

    def _url(self, pfad: str) -> str:
        return f"{self.basis}/{pfad}"

    def _get(self, pfad: str, **kw: Any) -> requests.Response:
        for versuch in range(5):
            try:
                r = self.sitzung.get(self._url(pfad), timeout=60, **kw)
                if r.status_code == 401:
                    raise SystemExit("Wrong key - see Wake Word Studio -> Settings -> Trainer.")
                return r
            except requests.RequestException as err:
                _LOG.warning("Home Assistant not reachable (%s), trying again", err)
                time.sleep(5 * (versuch + 1))
        raise ConnectionError("Home Assistant not reachable")

    def auftrag(self) -> dict[str, Any]:
        r = self._get("auftrag")
        r.raise_for_status()
        return r.json()

    def liste(self, wort: str) -> list[dict[str, Any]]:
        r = self._get("liste", params={"wort": wort})
        r.raise_for_status()
        return r.json()["aufnahmen"]

    def audio(self, wort: str, aid: str) -> bytes:
        r = self._get(f"audio/{wort}/{aid}")
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
        r = self.sitzung.post(
            self._url("ergebnis"), params={"wort": wort}, timeout=120,
            files={"modell": ("modell.tflite", tflite, "application/octet-stream"),
                   "bericht": ("bericht.json", json.dumps(bericht), "application/json")},
        )
        r.raise_for_status()
        return r.json()
