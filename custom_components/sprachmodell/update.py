"""Update-Funktion: neue Dateien der Integration selbst einspielen (wie bei Bosch lokal).

Neue Dateien legt man nach /config/custom_templates/sprachmodell_update
(manifest.json zuletzt). Die Entitaet zeigt dann ein Update an; Installieren
kopiert die Dateien in den eigenen Ordner, loescht den Update-Ordner und
startet HA neu. Geprueft wird einmal pro Minute (nur ob die Datei da ist).
Bilder liegen als Text (Base64, Endung .png.b64), entfernen.json (Liste von
Dateinamen) loescht nicht mehr gebrauchte Dateien der Integration.
"""

from __future__ import annotations

from datetime import timedelta
import base64
import json
import os
import re
import shutil
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAME

SCAN_INTERVAL = timedelta(minutes=1)
# Erster vorhandener Ordner gilt
ORDNER = (("custom_templates", "sprachmodell_update"),)
# Nur diese Dateien werden uebernommen (Unterordner: translations, brand, frontend)
ENDUNGEN = (".py", ".json", ".png.b64", ".js", ".md")
UNTERORDNER = ("translations", "brand", "frontend")
REPO = "https://github.com/Wadim-dev/sprachmodell_ha"


def _version(pfad: str) -> str | None:
    """Version aus einer manifest.json (nur wenn sie zu dieser Integration gehoert)."""
    try:
        with open(pfad, encoding="utf-8") as datei:
            manifest = json.load(datei)
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict) or manifest.get("domain") != DOMAIN:
        return None
    return str(manifest.get("version") or "") or None


def _hinweise(pfad: str, version: str | None) -> str | None:
    """Abschnitt der Version aus CHANGELOG.md (## 1.2.3 ... bis zur naechsten ##)."""
    try:
        with open(pfad, encoding="utf-8") as datei:
            text = datei.read()
    except OSError:
        return None
    if version:
        treffer = re.search(
            r"^## \[?" + re.escape(version) + r"\b.*?(?=^## |\Z)", text, re.M | re.S
        )
        if treffer:
            return treffer.group(0).strip()
    return None


def _entfernen(quelle: str, ziel: str) -> None:
    """Dateien aus entfernen.json loeschen (nur innerhalb der Integration)."""
    try:
        with open(os.path.join(quelle, "entfernen.json"), encoding="utf-8") as datei:
            namen = json.load(datei)
    except (OSError, ValueError):
        return
    basis = os.path.realpath(ziel)
    for name in namen if isinstance(namen, list) else []:
        pfad = os.path.realpath(os.path.join(ziel, str(name)))
        if pfad.startswith(basis + os.sep) and os.path.isfile(pfad):
            os.remove(pfad)


def _kopieren(quelle: str, ziel: str) -> int:
    """Dateien aus dem Update-Ordner uebernehmen, dann den Ordner loeschen."""
    _entfernen(quelle, ziel)
    anzahl = 0
    for wurzel, ordner, dateien in os.walk(quelle):
        ordner[:] = [o for o in ordner if o in UNTERORDNER]
        rel = os.path.relpath(wurzel, quelle)
        ziel_ordner = os.path.join(ziel, rel) if rel != "." else ziel
        for name in dateien:
            if name == "entfernen.json" or not name.endswith(ENDUNGEN):
                continue
            os.makedirs(ziel_ordner, exist_ok=True)
            von = os.path.join(wurzel, name)
            if name.endswith(".b64"):
                with open(von, encoding="ascii") as datei:
                    inhalt = base64.b64decode("".join(datei.read().split()))
                with open(os.path.join(ziel_ordner, name[:-4]), "wb") as datei:
                    datei.write(inhalt)
            else:
                shutil.copyfile(von, os.path.join(ziel_ordner, name))
            anzahl += 1
    shutil.rmtree(quelle, ignore_errors=True)
    return anzahl


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([SprachUpdate(hass)], update_before_add=True)


class SprachUpdate(UpdateEntity):
    """Zeigt neue Dateien im Update-Ordner an und spielt sie ein."""

    _attr_has_entity_name = True
    _attr_translation_key = "integration"
    _attr_title = NAME
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES
    )
    _attr_should_poll = True
    _attr_release_url = REPO + "/releases"

    def __init__(self, hass: HomeAssistant) -> None:
        self._ordner = [hass.config.path(*o) for o in ORDNER]
        self._quelle = self._ordner[0]
        self._ziel = os.path.dirname(__file__)
        self._attr_unique_id = f"{DOMAIN}_update"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, "sprachmodell")})
    def update(self) -> None:
        installiert = _version(os.path.join(self._ziel, "manifest.json"))
        neu = None
        for ordner in self._ordner:
            if (neu := _version(os.path.join(ordner, "manifest.json"))) is not None:
                self._quelle = ordner
                break
        self._attr_installed_version = installiert
        self._attr_latest_version = neu or installiert
        hinweise = _hinweise(os.path.join(self._quelle, "CHANGELOG.md"), neu) if neu else None
        self._hinweise = hinweise
        erste = next(
            (z.lstrip("-* ").strip() for z in (hinweise or "").splitlines()[1:] if z.strip()),
            "",
        )
        self._attr_release_summary = (erste[:250] or "Neue Version bereit.") if neu else None

    async def async_release_notes(self) -> str | None:
        return getattr(self, "_hinweise", None)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(_kopieren, self._quelle, self._ziel)
        # Neue Dateien gelten erst nach einem Neustart
        await self.hass.services.async_call("homeassistant", "restart")
