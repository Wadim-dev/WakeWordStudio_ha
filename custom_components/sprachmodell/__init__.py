"""Sprachmodell: eigenes Aktivierungswort pruefen, trainieren und einspielen.

Wie VisionState, nur fuer Sprache:

- Die Echos (TECHO5) heben bei jedem Aufwachen und jedem knappen Fast-Aufwachen
  ein paar Sekunden Ton auf. Die Integration holt sie ab.
- In der Seitenleiste "Sprachmodell" hoert man sie nach und sagt, ob das Wort
  gesagt wurde. Zips von der Setup-Seite der Echos laedt man dort auch hoch.
- Ein Trainer (eigener Container im Heimnetz) holt die bewerteten Aufnahmen,
  trainiert nachts eine neue Version, testet sie ehrlich gegen
  zurueckgehaltene Aufnahmen und schickt sie zurueck. Ist sie besser, spielt
  die Integration sie an allen Echos ein; sonst bleibt die alte.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components import frontend, panel_custom, persistent_notification
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.loader import async_get_integration
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)

from .const import (
    ANZEIGE_STANDARD,
    DOMAIN,
    MODELL_ID_STANDARD,
    OPT_AUFBEWAHREN,
    OPT_AUTO,
    OPT_ERINNERUNG,
    OPT_NACHTS,
    OPT_NUR_WORT1,
    OPT_PERSONEN,
    OPT_UHRZEIT,
    ORDNER_STANDARD,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_TITEL,
    PANEL_URL,
    SIGNAL_NEU,
    STANDARD_OPTIONEN,
    STATIC_URL,
    TRAINER_ONLINE_S,
)
from .sammler import LISTE, Sammler, echos_finden
from .speicher import Speicher, jetzt

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH, Platform.UPDATE]
SAMMELN_TAKT = timedelta(minutes=2)
HINWEIS_ID = f"{DOMAIN}_pruefen"
# Cache der ESPHome-Integration fuer eigene Aktivierungswoerter (sonst erst nach Neustart neu)
WAKE_WORD_CACHE = "wake_word_cache"

type SprachConfigEntry = ConfigEntry["Zentrale"]


class Zentrale:
    """Alles, was die Integration zur Laufzeit braucht."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.speicher = Speicher(entry.data.get("ordner") or ORDNER_STANDARD)
        self.sammler = Sammler(hass, self.speicher, self.opt(OPT_NUR_WORT1))
        self.modell_id: str = entry.data.get("modell_id") or MODELL_ID_STANDARD
        self.anzeige: str = entry.data.get("anzeige") or ANZEIGE_STANDARD
        self.trainer_kontakt: datetime | None = None
        self.trainer_info: dict[str, Any] = {}
        self.version = "0"
        self._weg: list[Any] = []
        self._sammeln_spaeter = None

    # --- Einstellungen ---------------------------------------------------

    def opt(self, name: str) -> Any:
        return self.entry.options.get(name, STANDARD_OPTIONEN[name])

    @property
    def schluessel(self) -> str:
        return self.entry.data["schluessel"]

    def personen(self) -> list[str]:
        eigene = [p for p in self.opt(OPT_PERSONEN) if p]
        if eigene:
            return eigene
        namen = [
            s.attributes.get("friendly_name") or s.entity_id
            for s in self.hass.states.async_all("person")
        ]
        return sorted(namen)

    @property
    def trainer_online(self) -> bool:
        return bool(
            self.trainer_kontakt
            and (datetime.now(timezone.utc) - self.trainer_kontakt).total_seconds() < TRAINER_ONLINE_S
        )

    # --- Aenderungen melden ---------------------------------------------

    @callback
    def geaendert(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_NEU)

    # --- Start / Stop ----------------------------------------------------

    async def starten(self) -> None:
        await self.hass.async_add_executor_job(self.speicher.laden)
        datei = self.hass.config.path("custom_wake_words", self.modell_id + ".tflite")
        await self.hass.async_add_executor_job(self.speicher.vorhandenes_uebernehmen, datei)
        # Ein Training, das bei einem Neustart lief, ist verloren
        if self.speicher.daten["training"].get("phase") not in ("bereit", "fertig", "fehler"):
            self.speicher.daten["training"] = {"phase": "bereit", "hinweis": "Neustart während des Trainings"}

        self._weg.append(async_track_time_interval(self.hass, self._takt, SAMMELN_TAKT))
        self._weg.append(async_track_time_interval(self.hass, self._stuendlich, timedelta(hours=1)))
        stunde, minute = (int(x) for x in str(self.opt(OPT_UHRZEIT)).split(":")[:2])
        self._weg.append(async_track_time_change(self.hass, self._nachts, hour=stunde, minute=minute, second=0))
        self._zaehler_beobachten()
        async_call_later(self.hass, 20, self._takt)
        async_call_later(self.hass, 60, self._stuendlich)

    def _zaehler_beobachten(self) -> None:
        sensoren = [
            s.entity_id for s in self.hass.states.async_all("sensor")
            if s.entity_id.endswith("_wake_clips")
        ]
        if sensoren:
            self._weg.append(async_track_state_change_event(self.hass, sensoren, self._zaehler))

    @callback
    def _zaehler(self, _event: Event) -> None:
        # Kurz warten: der Echo schreibt die Aufnahme erst fertig
        if self._sammeln_spaeter:
            self._sammeln_spaeter()
        self._sammeln_spaeter = async_call_later(self.hass, 5, self._takt)

    async def stoppen(self) -> None:
        for weg in self._weg:
            weg()
        self._weg.clear()
        await self.hass.async_add_executor_job(self.speicher.speichern)

    # --- Regelmaessiges -------------------------------------------------

    async def _takt(self, _now: Any = None) -> None:
        self._sammeln_spaeter = None
        try:
            neu = await self.sammler.holen()
        except Exception:  # noqa: BLE001 - Sammeln darf nie die Integration stoppen
            _LOGGER.exception("Aufnahmen holen fehlgeschlagen")
            return
        if neu:
            self.geaendert()

    async def _stuendlich(self, _now: Any = None) -> None:
        weg = await self.hass.async_add_executor_job(
            self.speicher.aufraeumen, int(self.opt(OPT_AUFBEWAHREN))
        )
        if weg:
            self.geaendert()
        self.erinnern()

    @callback
    def erinnern(self) -> None:
        """Hinweis in HA (Glocke), wenn Aufnahmen schon lange warten – wie bei VisionState."""
        tage = int(self.opt(OPT_ERINNERUNG))
        stat = self.speicher.statistik()
        aeltestes = stat["aeltestes_offen"]
        if tage <= 0 or not aeltestes:
            persistent_notification.async_dismiss(self.hass, HINWEIS_ID)
            return
        alter = datetime.now(timezone.utc) - datetime.fromisoformat(aeltestes)
        if alter.days >= tage:
            persistent_notification.async_create(
                self.hass,
                f"{stat['offen']} Aufnahmen warten auf Prüfung, die älteste seit {alter.days} Tagen. "
                f"[Jetzt prüfen](/{PANEL_URL}/pruefen)",
                title="Sprachmodell",
                notification_id=HINWEIS_ID,
            )
        else:
            persistent_notification.async_dismiss(self.hass, HINWEIS_ID)

    async def _nachts(self, _now: Any = None) -> None:
        if not self.opt(OPT_NACHTS):
            return
        if self.neue_seit_letztem_lauf() > 0:
            self.auftrag("nachts")

    def neue_seit_letztem_lauf(self) -> int:
        stat = self.speicher.statistik()
        letzte = next((l for l in reversed(self.speicher.daten["laeufe"]) if l.get("bewertet") is not None), None)
        return stat["bewertet"] - (letzte["bewertet"] if letzte else 0)

    # --- Training --------------------------------------------------------

    @callback
    def auftrag(self, grund: str) -> None:
        self.speicher.daten["auftrag"] = {"grund": grund, "zeit": jetzt()}
        phase = self.speicher.daten["training"].get("phase")
        if phase in ("bereit", "fertig", "fehler", None):
            self.speicher.daten["training"] = {"phase": "wartet", "grund": grund, "seit": jetzt()}
        self.hass.async_add_executor_job(self.speicher.speichern)
        self.geaendert()

    @callback
    def abbrechen(self) -> None:
        self.speicher.daten["auftrag"] = None
        self.speicher.daten["abbrechen"] = True
        if self.speicher.daten["training"].get("phase") == "wartet":
            self.speicher.daten["training"] = {"phase": "bereit"}
        self.hass.async_add_executor_job(self.speicher.speichern)
        self.geaendert()

    @callback
    def trainer_meldet(self, status: dict[str, Any]) -> None:
        self.trainer_kontakt = datetime.now(timezone.utc)
        alt = self.speicher.daten["training"]
        neu = {**{k: v for k, v in status.items() if k != "info"}, "aktualisiert": jetzt()}
        if "info" in status and isinstance(status["info"], dict):
            self.trainer_info = status["info"]
        if neu.get("phase") and neu.get("phase") != alt.get("phase"):
            neu.setdefault("seit", jetzt())
            if neu["phase"] == "fehler":
                self.speicher.daten["laeufe"].append({
                    "start": alt.get("start"), "ende": jetzt(), "ergebnis": "fehler",
                    "hinweis": neu.get("schritt") or neu.get("hinweis"),
                })
            self.speicher.daten["training"] = {**alt, **neu}
            self.hass.async_add_executor_job(self.speicher.speichern)
        else:
            self.speicher.daten["training"] = {**alt, **neu}
            self.speicher.stand += 1
        self.geaendert()

    async def ergebnis(self, tflite: bytes, bericht: dict[str, Any]) -> dict[str, Any]:
        """Neue Version vom Trainer: ablegen, Lauf merken, wenn besser einspielen."""
        eintrag = await self.hass.async_add_executor_job(self.speicher.version_neu, tflite, bericht)
        besser = bool(bericht.get("besser"))
        lauf = {
            "start": self.speicher.daten["training"].get("start") or bericht.get("start"),
            "ende": jetzt(),
            "version": eintrag["nr"],
            "ergebnis": "besser" if besser else "nicht besser",
            "bewertet": bericht.get("bewertet_genutzt", self.speicher.statistik()["bewertet"]),
            "neu": bericht.get("neu"),
            "alt": bericht.get("alt"),
            "dauer_min": bericht.get("dauer_min"),
        }
        eintrag["status"] = "geprueft" if besser else "verworfen"
        self.speicher.daten["laeufe"].append(lauf)
        self.speicher.daten["training"] = {"phase": "fertig", "seit": jetzt(), "version": eintrag["nr"],
                                           "besser": besser}
        self.speicher.daten["auftrag"] = None
        await self.hass.async_add_executor_job(self.speicher.speichern)
        if besser and self.opt(OPT_AUTO):
            await self.einspielen(eintrag["nr"])
            lauf["ergebnis"] = "eingespielt"
            await self.hass.async_add_executor_job(self.speicher.speichern)
        self.geaendert()
        return eintrag

    async def einspielen(self, nr: int, cutoff: float | None = None) -> None:
        """Version an allen Echos einspielen, ohne HA neu zu starten."""
        version = self.speicher.version(nr)
        if version is None:
            raise ValueError(f"Version {nr} gibt es nicht")
        if cutoff is None:
            cutoff = float((version.get("bericht") or {}).get("cutoff") or 0.97)
        ziel = self.hass.config.path("custom_wake_words")
        await self.hass.async_add_executor_job(
            self.speicher.einspielen_dateien, nr, ziel, self.modell_id, self.anzeige, cutoff
        )
        # ESPHome merkt sich die Liste eigener Woerter samt Pruefsumme bis zum Neustart.
        # Ohne den Zwischenspeicher liest es sie neu; nach dem Neuladen holen die Echos
        # das Modell mit der neuen Pruefsumme selbst.
        self.hass.data.pop(WAKE_WORD_CACHE, None)
        knoten = set(echos_finden(self.hass))
        for eintrag in self.hass.config_entries.async_entries("esphome"):
            info = getattr(getattr(eintrag, "runtime_data", None), "device_info", None)
            name = str(getattr(info, "name", "")).replace("-", "_")
            if name in knoten:
                self.hass.async_create_task(self.hass.config_entries.async_reload(eintrag.entry_id))
        self.geaendert()

    # --- Schwelle --------------------------------------------------------

    async def schwelle_setzen(self, wert: float) -> list[str]:
        ziele = [
            s.entity_id for s in self.hass.states.async_all("number")
            if s.entity_id.endswith("_assistant_1_wake_word_threshold")
        ]
        if ziele:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": ziele, "value": round(wert, 2)}, blocking=True
            )
        return ziele

    def schwellen_jetzt(self) -> dict[str, float]:
        werte = {}
        for s in self.hass.states.async_all("number"):
            if s.entity_id.endswith("_assistant_1_wake_word_threshold"):
                try:
                    werte[s.attributes.get("friendly_name") or s.entity_id] = float(s.state)
                except ValueError:
                    pass
        return werte


async def async_setup_entry(hass: HomeAssistant, entry: SprachConfigEntry) -> bool:
    """Integration starten."""
    if "schluessel" not in entry.data:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "schluessel": secrets.token_urlsafe(24)}
        )
    zentrale = Zentrale(hass, entry)
    zentrale.version = str((await async_get_integration(hass, DOMAIN)).version or "0")
    entry.runtime_data = zentrale
    await zentrale.starten()

    from .api import ansichten_anmelden  # noqa: PLC0415 - braucht die Zentrale

    ansichten_anmelden(hass)

    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, os.path.join(os.path.dirname(__file__), "frontend"), cache_headers=False)]
    )
    if PANEL_URL not in hass.data.get(frontend.DATA_PANELS, {}):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title=PANEL_TITEL,
            sidebar_icon=PANEL_ICON,
            module_url=f"{STATIC_URL}/sprachmodell-panel.js?v={zentrale.version}",
            require_admin=False,
            config={},
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_optionen_neu))
    return True


async def _optionen_neu(hass: HomeAssistant, entry: SprachConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SprachConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.stoppen()
        frontend.async_remove_panel(hass, PANEL_URL)
    return ok


def zentrale_holen(hass: HomeAssistant) -> Zentrale | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if isinstance(getattr(entry, "runtime_data", None), Zentrale):
            return entry.runtime_data
    return None


__all__ = ["DOMAIN", "LISTE", "Zentrale", "zentrale_holen"]
