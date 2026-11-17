"""The hub of Wake Word Studio: any number of own wake words.

Jedes Wort hat eigene Einstellungen (Sprache, Name am Geraet, welche Geraete
auf welchem Platz), eigene Aufnahmen, eigene Versionen und eigene Trainings.
Die Zentrale selbst kennt die Geraete, die gemeinsamen Einstellungen und die
Warteschlange fuer den Trainer. Alles wird in der App eingestellt.

Storage (chosen when setting up; default /share/sprachmodell, without /share /config/sprachmodell):

    zentrale.json                Woerter, gemeinsame Einstellungen, Warteschlange
    woerter/<id>/daten.json      Aufnahmen, Versionen, Laeufe eines Worts
    woerter/<id>/aufnahmen/      WAVs
    woerter/<id>/modelle/v<n>/   Versionen
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
import os
import secrets
import shutil
import threading
import time
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, CoreState, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_change, async_track_time_interval
from homeassistant.util import slugify

from .const import (
    CONF_ORDNER,
    DOMAIN,
    ENGPASS_CPU,
    ENGPASS_S,
    ENGPASS_WARTEN,
    GERAET_FEHLT_S,
    LAEUFT,
    NAME,
    PANEL_URL,
    SCHWELLE_MAX,
    SCHWELLE_SPIELRAUM,
    SIGNAL_NEU,
    SPRACHEN,
    STANDARD_WORT,
    STANDARD_ZENTRALE,
    TRAINER_FEHLT_S,
    TRAINER_ONLINE_S,
)
from .sammler import WAHL_ENDUNGEN, Sammler, alle_geraete, esphome_eintraege, geraete_info
from .speicher import Speicher, jetzt, sichere_id

_LOGGER = logging.getLogger(__name__)
MAX_NEUSTARTS = 2  # a run lost by a trainer restart is started again this often (with less memory)
ABGEHOLT_SPERRE_S = 120  # a handed-out run is not given to a second trainer within this time

SAMMELN_TAKT = timedelta(minutes=2)
HINWEIS_ID = f"{DOMAIN}_pruefen"
# Cache der ESPHome-Integration fuer eigene Aktivierungswoerter (sonst erst nach Neustart neu)
NEUSTART_MELDUNG = "restart_to_roll_out"
DATEI = "zentrale.json"


def ablage_standard(hass: HomeAssistant) -> str:
    """/share ist im HA-Backup und fuer Apps lesbar; ohne /share (Container) /config."""
    return "/share/sprachmodell" if os.path.isdir("/share") else hass.config.path("sprachmodell")


def sprache_aus(hass: HomeAssistant) -> str:
    sprache = str(hass.config.language or "en").split("-")[0].lower()
    return sprache if sprache in SPRACHEN else "en"


PROTOKOLL_MAX = 500  # log lines of a run kept for the panel (all the trainer sends)
BALKEN_FELDER = ("name", "prozent", "n", "gesamt", "lief", "rest", "rest_min", "tempo", "zeit")


def _live_pruefen(live: dict[str, Any]) -> dict[str, Any]:
    """Keep only what the panel shows, with limits (the trainer is trusted, but the data ends up in the browser)."""
    zeilen = [
        [z[0], str(z[1])[:16], str(z[2])[:300]]
        for z in (live.get("protokoll") or [])[-PROTOKOLL_MAX:]
        if isinstance(z, list) and len(z) == 3 and isinstance(z[0], int | float)
    ]
    schritte = [
        {k: x[k] for k in ("phase", "schritt", "detail", "start", "ende") if k in x and isinstance(x[k], str | int | float)}
        for x in (live.get("schritte") or [])[-50:]
        if isinstance(x, dict)
    ]
    system = {k: v for k, v in (live.get("system") or {}).items() if isinstance(v, int | float) and isinstance(k, str)}
    balken = [
        {k: (x[k] if isinstance(x[k], int | float) else str(x[k])[:80]) for k in BALKEN_FELDER
         if k in x and isinstance(x[k], str | int | float)}
        for x in (live.get("balken") or [])[:8]
        if isinstance(x, dict) and isinstance(x.get("prozent"), int | float)
    ]
    start = live.get("start")
    return {"protokoll": zeilen, "schritte": schritte, "system": system, "balken": balken,
            "start": start if isinstance(start, int | float) else None, "zeit": jetzt()}


class Wort:
    """Ein eigenes Aktivierungswort mit eigenen Aufnahmen und Versionen."""

    def __init__(self, zentrale: Zentrale, wid: str, cfg: dict[str, Any]) -> None:
        self.z = zentrale
        self.id = wid
        self.cfg = {**STANDARD_WORT, **cfg}
        self.speicher = Speicher(os.path.join(zentrale.ablage, "woerter", wid))
        # Details of the current or last run (live log, steps, trainer load); only in memory, the trainer resends them
        self.live: dict[str, Any] | None = None

    # --- Eigenschaften ----------------------------------------------------

    @property
    def wort(self) -> str:
        return self.cfg["wort"] or self.id

    @property
    def anzeige(self) -> str:
        if self.cfg["anzeige"]:
            return str(self.cfg["anzeige"])
        de = str(self.z.hass.config.language or "").startswith("de")
        return f"{self.wort} ({'eigenes' if de else 'custom'})"

    @property
    def modell_id(self) -> str:
        return self.cfg["modell_id"] or self.id

    @property
    def sprache(self) -> str:
        return self.cfg["sprache"] or "en"

    @property
    def geraete(self) -> dict[str, str]:
        """Knoten -> Platz ("1"/"2")."""
        return {str(k): str(v) for k, v in (self.cfg.get("geraete") or {}).items() if str(v) in ("1", "2")}

    def aktive_version(self) -> dict[str, Any] | None:
        nr = self.speicher.daten.get("aktiv")
        return self.speicher.version(nr) if nr else None

    def neue_seit_letztem_lauf(self) -> int:
        stat = self.speicher.statistik()
        letzte = next((lauf for lauf in reversed(self.speicher.daten["laeufe"]) if lauf.get("bewertet") is not None), None)
        return int(stat["bewertet"]) - int(letzte["bewertet"] if letzte else 0)

    def kurz(self) -> dict[str, Any]:
        """Fuer Listen in der App und fuer die Entitaeten."""
        stat = self.speicher.statistik()
        v = self.aktive_version() or {}
        neu = ((v.get("bericht") or {}).get("neu") or {})
        return {
            "id": self.id,
            **self.cfg,
            "anzeige": self.anzeige,
            "modell_id": self.modell_id,
            "offen": stat["offen"],
            "bewertet": stat["bewertet"],
            "aufnahmen": stat["aufnahmen"],
            "aktiv": v.get("nr"),
            "trefferquote": neu.get("trefferquote"),
            "fehlausloeser": neu.get("fehlausloeser_pro_stunde"),
            "training": self.speicher.daten["training"],
            "in_reihe": self.id in self.z.reihe(),
            "eingespielt": v.get("eingespielt"),
            "tage": self.speicher.tage(),
        }


class Zentrale:
    """Alles, was die Integration zur Laufzeit braucht."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.ablage: str = entry.data.get(CONF_ORDNER) or ablage_standard(hass)
        self.daten: dict[str, Any] = {}
        self.woerter: dict[str, Wort] = {}
        self.sammler = Sammler(hass, self)
        self.trainer_kontakt: datetime | None = None
        self.trainer_info: dict[str, Any] = {}
        self._abgeholt: dict[str, float] = {}
        self.version = "0"
        self._sperre = threading.RLock()
        self._weg: list[Any] = []
        self._sammeln_spaeter: CALLBACK_TYPE | None = None
        self._zaehler_weg: CALLBACK_TYPE | None = None
        self._zaehler_ids: list[str] = []
        self._nachts_weg: CALLBACK_TYPE | None = None
        # Plattform -> Funktion, die die Entitaeten eines neuen Worts anlegt
        self.anleger: dict[str, Any] = {}
        # Repairs: (word, node) -> first time the device was missing; issue ids raised now
        self._fehlt_seit: dict[tuple[str, str], datetime] = {}
        self._engpass_seit: datetime | None = None
        self._meldungen: set[str] = set()

    # --- Ablage -----------------------------------------------------------

    def _laden(self) -> None:
        os.makedirs(os.path.join(self.ablage, "woerter"), exist_ok=True)
        try:
            with open(os.path.join(self.ablage, DATEI), encoding="utf-8") as datei:
                daten = json.load(datei)
        except (OSError, ValueError):
            daten = {}
        daten.setdefault("woerter", {})
        daten.setdefault("einstellungen", {})
        daten.setdefault("gesehen", [])
        daten.setdefault("reihe", [])
        neu = "schluessel" not in daten
        daten.setdefault("schluessel", secrets.token_urlsafe(24))
        self.daten = daten
        for wid, cfg in daten["woerter"].items():
            wort = Wort(self, wid, cfg)
            wort.speicher.laden()
            wort.speicher.vorschlaege()
            self.woerter[wid] = wort
        if neu:  # first start: keep the trainer key from now on
            self.speichern()

    def speichern(self) -> None:
        with self._sperre:
            self.daten["woerter"] = {wid: w.cfg for wid, w in self.woerter.items()}
            self.daten["gesehen"] = self.daten["gesehen"][-5000:]
            pfad = os.path.join(self.ablage, DATEI)
            with open(pfad + ".tmp", "w", encoding="utf-8") as datei:
                json.dump(self.daten, datei, ensure_ascii=False, indent=1)
            os.replace(pfad + ".tmp", pfad)

    @callback
    def speichern_spaeter(self) -> None:
        self.hass.async_add_executor_job(self.speichern)

    def opt(self, name: str) -> Any:
        return self.daten.get("einstellungen", {}).get(name, STANDARD_ZENTRALE[name])

    @property
    def schluessel(self) -> str:
        return str(self.daten["schluessel"])

    def personen(self) -> list[str]:
        eigene = [p for p in self.opt("personen") if p]
        if eigene:
            return eigene
        return sorted(
            s.attributes.get("friendly_name") or s.entity_id for s in self.hass.states.async_all("person")
        )

    @property
    def trainer_online(self) -> bool:
        return bool(
            self.trainer_kontakt
            and (datetime.now(UTC) - self.trainer_kontakt).total_seconds() < TRAINER_ONLINE_S
        )

    @callback
    def geaendert(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_NEU)

    # --- Geraete ----------------------------------------------------------

    def geraete(self) -> dict[str, str]:
        """Alle Geraete mit Aufwach-Aufnahmen: Knoten -> Name."""
        return alle_geraete(self.hass)

    def wort_fuer(self, knoten: str, platz: str | None, modell: str | None) -> Wort | None:
        """Zu welchem Wort gehoert eine Aufnahme dieses Geraets?"""
        for w in self.woerter.values():
            if w.geraete.get(knoten) == str(platz or "1"):
                return w
        if modell:
            klein = str(modell).lower()
            for w in self.woerter.values():
                if klein in (w.modell_id.lower(), w.anzeige.lower(), w.wort.lower()):
                    return w
        return None

    def benutzte_geraete(self) -> set[str]:
        return {k for w in self.woerter.values() for k in w.geraete}

    def _entitaeten(self, knoten: str, domain: str, endung: str) -> list[er.RegistryEntry]:
        eintrag = esphome_eintraege(self.hass).get(knoten)
        if eintrag is None:
            return []
        reg = er.async_get(self.hass)
        return [
            e for e in er.async_entries_for_config_entry(reg, eintrag.entry_id)
            if e.domain == domain and not e.disabled_by
            and (e.entity_id.endswith(endung) or str(e.unique_id).endswith(endung))
        ]

    def schwelle_entitaet(self, knoten: str, platz: str) -> str | None:
        treffer = self._entitaeten(knoten, "number", f"_assistant_{platz}_wake_word_threshold")
        return treffer[0].entity_id if treffer else None

    def wortwahl_entitaet(self, knoten: str, platz: str) -> str | None:
        """Auswahl "Aktivierungswort" (Platz 1) bzw. "Aktivierungswort 2" am Geraet."""
        treffer = self._entitaeten(knoten, "select", WAHL_ENDUNGEN.get(platz, f"-wake_word_{platz}"))
        return treffer[0].entity_id if treffer else None

    def geraete_zustand(self) -> list[dict[str, Any]]:
        """Fuer die App: jedes Geraet mit Plaetzen, Wort darauf und Schwelle."""
        aus: list[dict[str, Any]] = []
        for knoten, info in geraete_info(self.hass).items():
            name = info["name"]
            plaetze = {}
            for platz in info["plaetze"]:
                wahl = self.wortwahl_entitaet(knoten, platz)
                schwelle = self.schwelle_entitaet(knoten, platz)
                sw = self.hass.states.get(wahl) if wahl else None
                ss = self.hass.states.get(schwelle) if schwelle else None
                wort = next((w.id for w in self.woerter.values() if w.geraete.get(knoten) == platz), None)
                try:
                    schwellwert = float(ss.state) if ss else None
                except ValueError:
                    schwellwert = None
                plaetze[platz] = {
                    "wort": wort,
                    "auswahl": sw.state if sw else None,
                    "optionen": list(sw.attributes.get("options") or []) if sw else [],
                    "schwelle": schwellwert,
                    "auswahl_entitaet": wahl,
                    "schwelle_entitaet": schwelle,
                }
            aus.append({
                "knoten": knoten, "name": name, "plaetze": plaetze, "clips": info["clips"],
                "fehler": self.sammler.fehler.get(knoten),
                "zaehler": self._zaehlerstand(knoten),
                "senden": self._senden_zustand(knoten),
            })
        return aus

    def _zustand_von(self, knoten: str, domain: str, endung: str) -> tuple[str | None, str | None]:
        """(entity_id, state) of the first entity of the device with this ending."""
        eintrag = esphome_eintraege(self.hass).get(knoten)
        if eintrag is None:
            return None, None
        kern = endung.lstrip("_")
        for e in er.async_entries_for_config_entry(er.async_get(self.hass), eintrag.entry_id):
            if e.domain != domain or e.disabled_by:
                continue
            # entity ids can be renamed; the ESPHome unique id ends in "-<object id>"
            if not (e.entity_id.endswith(endung) or str(e.unique_id).endswith(("-" + kern, endung))):
                continue
            s = self.hass.states.get(e.entity_id)
            return e.entity_id, (s.state if s else None)
        return None, None

    def _senden_zustand(self, knoten: str) -> dict[str, Any] | None:
        """Firmware that sends its clips itself (TECHO "Send wake clips to"): what the guide in Settings needs.

        None when the device has no such select. The address and token can only be set on the device's own
        setup page, so the app offers to switch that page on and open it.
        """
        ziel_id, ziel = self._zustand_von(knoten, "select", "_send_wake_clips_to")
        if ziel_id is None:
            return None
        seite_id, seite = self._zustand_von(knoten, "switch", "_setup_page")
        behalten_id, behalten = self._zustand_von(knoten, "switch", "_keep_wake_clips")
        _, ip = self._zustand_von(knoten, "sensor", "_ip_address")
        status_id, status = self._zustand_von(knoten, "sensor", "_wake_clip_sending")
        offen_id, offen = self._zustand_von(knoten, "sensor", "_wake_clips_unsent")
        ipv4 = next((t.strip() for t in str(ip or "").split(",") if t.strip().count(".") == 3), None)
        z = self.hass.states.get(ziel_id)
        optionen = [str(o) for o in (z.attributes.get("options") or [])] if z else []
        return {
            "ziel": ziel, "ziel_entitaet": ziel_id, "ziel_optionen": optionen,
            "seite": seite, "seite_entitaet": seite_id,
            "behalten": behalten, "behalten_entitaet": behalten_id,
            "ip": ipv4, "status": status, "status_entitaet": status_id, "offen": offen, "offen_entitaet": offen_id,
        }

    def _zaehlerstand(self, knoten: str) -> int | None:
        for e in self._entitaeten(knoten, "sensor", "_wake_clips"):
            s = self.hass.states.get(e.entity_id)
            try:
                return int(float(s.state)) if s else None
            except ValueError:
                return None
        return None

    # --- Woerter ----------------------------------------------------------

    async def wort_neu(self, cfg: dict[str, Any]) -> Wort:
        text = str(cfg.get("wort") or "").strip()
        if not text:
            raise ValueError("wort_fehlt")
        basis = sichere_id(slugify(text) or "wort").lower() or "wort"
        wid, n = basis, 2
        while wid in self.woerter:
            wid, n = f"{basis}_{n}", n + 1
        neu = {**STANDARD_WORT, "sprache": sprache_aus(self.hass)}
        neu.update({k: v for k, v in cfg.items() if k in STANDARD_WORT})
        neu["wort"] = text
        neu["modell_id"] = sichere_id(str(neu.get("modell_id") or wid)).lower()
        wort = Wort(self, wid, neu)
        await self.hass.async_add_executor_job(wort.speicher.laden)
        # Gibt es das Modell schon in custom_wake_words (z. B. von Hand trainiert)? Dann als v1 nehmen
        datei = self.hass.config.path("custom_wake_words", wort.modell_id + ".tflite")
        await self.hass.async_add_executor_job(wort.speicher.vorhandenes_uebernehmen, datei)
        self.woerter[wid] = wort
        self._geraete_freiraeumen(wort)
        await self.hass.async_add_executor_job(self.speichern)
        await self._nach_wortaenderung(neu=wort)
        return wort

    def _geraete_freiraeumen(self, wort: Wort) -> None:
        """Ein Platz an einem Geraet gehoert immer nur einem Wort."""
        for anderes in self.woerter.values():
            if anderes is wort:
                continue
            for knoten, platz in wort.geraete.items():
                if anderes.geraete.get(knoten) == platz:
                    anderes.cfg["geraete"] = {k: v for k, v in anderes.geraete.items() if k != knoten}

    async def wort_aendern(self, wid: str, cfg: dict[str, Any]) -> Wort:
        wort = self.woerter[wid]
        if "wort" in cfg and not str(cfg["wort"]).strip():
            raise ValueError("wort_fehlt")
        for k, v in cfg.items():
            if k in STANDARD_WORT and k != "modell_id":
                wort.cfg[k] = v
        self._geraete_freiraeumen(wort)
        await self.hass.async_add_executor_job(self.speichern)
        await self._nach_wortaenderung()
        return wort

    async def wort_loeschen(self, wid: str, dateien_auch: bool) -> None:
        wort = self.woerter.pop(wid)
        if wid in self.daten["reihe"]:
            self.daten["reihe"].remove(wid)
        await self.hass.async_add_executor_job(self.speichern)
        if dateien_auch:
            await self.hass.async_add_executor_job(shutil.rmtree, wort.speicher.ordner, True)
        await self._nach_wortaenderung(weg=wid)

    async def _nach_wortaenderung(self, neu: Wort | None = None, weg: str | None = None) -> None:
        self._zaehler_beobachten()
        if neu is not None:
            for anlegen in self.anleger.values():
                anlegen(neu)
        if weg is not None:
            # Entitaeten des Worts entfernen
            reg = er.async_get(self.hass)
            for e in er.async_entries_for_config_entry(reg, self.entry.entry_id):
                if str(e.unique_id).startswith(f"{DOMAIN}_{weg}_"):
                    reg.async_remove(e.entity_id)
            dr_reg = dr.async_get(self.hass)
            if geraet := dr_reg.async_get_device(identifiers={(DOMAIN, f"wort_{weg}")}):
                dr_reg.async_remove_device(geraet.id)
        self.geaendert()

    # --- Start / Stop -----------------------------------------------------

    async def starten(self) -> None:
        await self.hass.async_add_executor_job(self._laden)
        self._alte_geraete_entfernen()
        for wort in self.woerter.values():
            t = wort.speicher.daten["training"]
            if t.get("phase") in LAEUFT:
                # Home Assistant restarted during a run: the trainer keeps working and reports again.
                # Only if it stays silent for 20 minutes is the run treated as lost (_verlorene_laeufe).
                t["aktualisiert"] = jetzt()
        self._weg.append(async_track_time_interval(self.hass, self._takt, SAMMELN_TAKT))
        self._weg.append(async_track_time_interval(self.hass, self._stuendlich, timedelta(hours=1)))
        self.nachts_planen()
        self._weg.append(async_call_later(self.hass, 20, self._takt))
        self._weg.append(async_call_later(self.hass, 60, self._stuendlich))
        if self.daten.get("nach_neustart"):
            if self.hass.state is CoreState.running:
                self.neustart_meldung()  # only the integration was reloaded: ESPHome still has the old list
            else:
                # Home Assistant is starting and reads the new models now; select them once the devices are back
                self._weg.append(async_call_later(self.hass, 90, self.nach_neustart))

    @callback
    def nachts_planen(self) -> None:
        if self._nachts_weg:
            self._nachts_weg()
        stunde, minute = (int(x) for x in str(self.opt("uhrzeit")).split(":")[:2])
        self._nachts_weg = async_track_time_change(self.hass, self._nachts, hour=stunde, minute=minute, second=0)

    @callback
    def _alte_geraete_entfernen(self) -> None:
        """Devices of words that no longer exist (deleted while Home Assistant was off)."""
        reg = dr.async_get(self.hass)
        for geraet in dr.async_entries_for_config_entry(reg, self.entry.entry_id):
            if not self.geraet_gehoert(geraet):
                reg.async_update_device(geraet.id, remove_config_entry_id=self.entry.entry_id)

    def geraet_gehoert(self, geraet: dr.DeviceEntry) -> bool:
        """Is this device the hub itself or one of the current words?"""
        for domain, ident in geraet.identifiers:
            if domain != DOMAIN:
                continue
            if ident == DOMAIN or (ident.startswith("wort_") and ident[5:] in self.woerter):
                return True
        return False

    async def stoppen(self) -> None:
        for issue in self._meldungen:
            ir.async_delete_issue(self.hass, DOMAIN, issue)
        self._meldungen.clear()
        ir.async_delete_issue(self.hass, DOMAIN, NEUSTART_MELDUNG)
        for weg in self._weg:
            weg()
        self._weg.clear()
        for weg in (self._zaehler_weg, self._nachts_weg, self._sammeln_spaeter):
            if weg:
                weg()
        self._zaehler_weg = self._nachts_weg = self._sammeln_spaeter = None
        await self.hass.async_add_executor_job(self.speichern)
        for wort in self.woerter.values():
            await self.hass.async_add_executor_job(wort.speicher.speichern)

    @callback
    def _zaehler_beobachten(self) -> None:
        """Zaehler "Wake clips" der Geraete beobachten (neu, wenn Geraete dazukommen)."""
        sensoren = sorted(
            e.entity_id for k in self.geraete() for e in self._entitaeten(k, "sensor", "_wake_clips")
        )
        if sensoren == self._zaehler_ids:
            return
        if self._zaehler_weg:
            self._zaehler_weg()
            self._zaehler_weg = None
        self._zaehler_ids = sensoren
        if sensoren:
            self._zaehler_weg = async_track_state_change_event(self.hass, sensoren, self._zaehler)

    @callback
    def _zaehler(self, _event: Event[EventStateChangedData]) -> None:
        # Kurz warten: das Geraet schreibt die Aufnahme erst fertig
        if self._sammeln_spaeter:
            self._sammeln_spaeter()
        self._sammeln_spaeter = async_call_later(self.hass, 5, self._takt)

    # --- Regelmaessiges ---------------------------------------------------

    async def _takt(self, _now: Any = None) -> None:
        self._sammeln_spaeter = None
        self._zaehler_beobachten()
        self._verlorene_laeufe()
        self.reparaturen_pruefen()
        await self.jetzt_holen()

    async def jetzt_holen(self) -> bool:
        """Ask the devices for new recordings. False if that failed."""
        try:
            neu = await self.sammler.holen()
        except Exception:
            _LOGGER.exception("Fetching recordings failed")
            return False
        if neu:
            self.geaendert()
        return True

    async def _stuendlich(self, _now: Any = None) -> None:
        weg = 0
        for wort in self.woerter.values():
            weg += await self.hass.async_add_executor_job(
                wort.speicher.aufraeumen, int(self.opt("unbewertet_tage"))
            )
        if weg:
            self.geaendert()
        self.erinnern()
        await self.schwelle_pruefen()

    @callback
    def _verlorene_laeufe(self) -> None:
        """Trainer meldet sich bei laufendem Training nicht mehr (Neustart, Absturz): Lauf als Fehler beenden."""
        for wort in self.woerter.values():
            t = wort.speicher.daten["training"]
            if t.get("phase") not in LAEUFT or not t.get("aktualisiert"):
                continue
            alter = datetime.now(UTC) - datetime.fromisoformat(t["aktualisiert"])
            if alter.total_seconds() > 20 * 60:
                self._lauf_verloren(wort)

    def _lauf_verloren(self, wort: Wort) -> None:
        """The trainer restarted or went silent during a run (usually memory): queue the run again, the trainer then
        needs less memory. Only after MAX_NEUSTARTS such restarts the run ends with an error."""
        n = int(wort.speicher.daten["training"].get("neustarts") or 0) + 1
        if n > MAX_NEUSTARTS:
            self.trainer_meldet({"wort_id": wort.id, "phase": "fehler", "schritt": "trainer_getrennt"})
            return
        _LOGGER.warning("Trainer lost the run for %s, starting it again with less memory (%s/%s)",
                        wort.wort, n, MAX_NEUSTARTS)
        wort.speicher.daten["training"] = {"phase": "bereit"}
        self.auftrag(wort.id, "fortsetzen", sparsam=n)

    @callback
    def reparaturen_pruefen(self) -> None:
        """Raise a repair issue for things only the user can fix, remove it once fixed."""
        jetzt_ = datetime.now(UTC)
        vorhanden = set(geraete_info(self.hass))
        gewollt: dict[str, tuple[str, dict[str, str]]] = {}
        for wort in self.woerter.values():
            for knoten in wort.geraete:
                schluessel = (wort.id, knoten)
                if knoten in vorhanden:
                    self._fehlt_seit.pop(schluessel, None)
                    continue
                seit = self._fehlt_seit.setdefault(schluessel, jetzt_)
                if (jetzt_ - seit).total_seconds() >= GERAET_FEHLT_S:
                    gewollt[f"device_missing_{wort.id}_{knoten}"] = (
                        "device_missing", {"word": wort.wort, "device": knoten},
                    )
        wartet_seit = [
            datetime.fromisoformat(w.speicher.daten["training"]["seit"])
            for w in self.woerter.values()
            if w.speicher.daten["training"].get("phase") == "wartet" and w.speicher.daten["training"].get("seit")
        ]
        if not self.trainer_online and wartet_seit and (jetzt_ - min(wartet_seit)).total_seconds() >= TRAINER_FEHLT_S:
            gewollt["trainer_missing"] = ("trainer_missing", {"panel": f"/{PANEL_URL}/einstellungen"})
        engpass = self.engpass()
        if engpass is None:
            self._engpass_seit = None
        else:
            self._engpass_seit = self._engpass_seit or jetzt_
            if (jetzt_ - self._engpass_seit).total_seconds() >= ENGPASS_S:
                gewollt["trainer_slow"] = (f"trainer_slow_{engpass}", {"panel": f"/{PANEL_URL}/einstellungen"})
        for issue_id, (schluessel_, platzhalter) in gewollt.items():
            ir.async_create_issue(
                self.hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key=schluessel_, translation_placeholders=platzhalter,
            )
        for issue_id in self._meldungen - set(gewollt):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._meldungen = set(gewollt)

    def trainer_last(self) -> dict[str, Any]:
        """Current load of the trainer from the running word's live data (empty if nothing runs or it is stale)."""
        for w in self.woerter.values():
            if w.speicher.daten["training"].get("phase") in LAEUFT and w.live and w.live.get("system"):
                try:
                    alter = (datetime.now(UTC) - datetime.fromisoformat(w.live["zeit"])).total_seconds()
                except (TypeError, ValueError):
                    continue
                if alter < 300:
                    return dict(w.live["system"])
        return {}

    def engpass(self) -> str | None:
        """'memory' or 'disk' if the trainer is held up (mostly waiting, processor hardly used), else None."""
        last = self.trainer_last()
        if not last or last.get("cpu", 100) >= ENGPASS_CPU:
            return None
        if last.get("speicher_warten", 0) >= ENGPASS_WARTEN:
            return "memory"
        if last.get("platte_warten", 0) >= ENGPASS_WARTEN:
            return "disk"
        return None

    def offen_gesamt(self) -> int:
        return sum(len(w.speicher.offen()) for w in self.woerter.values())

    @callback
    def erinnern(self) -> None:
        """Hinweis in HA (Glocke), wenn Aufnahmen schon lange warten."""
        tage = int(self.opt("erinnerung_tage"))
        aeltestes = min(
            (w.speicher.statistik()["aeltestes_offen"] for w in self.woerter.values()
             if w.speicher.statistik()["aeltestes_offen"]),
            default=None,
        )
        if tage <= 0 or not aeltestes:
            persistent_notification.async_dismiss(self.hass, HINWEIS_ID)
            return
        alter = datetime.now(UTC) - datetime.fromisoformat(aeltestes)
        if alter.days < tage:
            persistent_notification.async_dismiss(self.hass, HINWEIS_ID)
            return
        de = str(self.hass.config.language or "").startswith("de")
        n = self.offen_gesamt()
        text = (
            f"{n} Aufnahmen warten auf Prüfung, die älteste seit {alter.days} Tagen. [Jetzt prüfen](/{PANEL_URL}/pruefen)"
            if de else
            f"{n} recordings are waiting for review, the oldest for {alter.days} days. [Review now](/{PANEL_URL}/pruefen)"
        )
        persistent_notification.async_create(self.hass, text, title=NAME, notification_id=HINWEIS_ID)

    async def _nachts(self, _now: Any = None) -> None:
        try:
            mindestens = max(1, int(self.opt("nachts_min_neu")))
        except (TypeError, ValueError):
            mindestens = int(str(STANDARD_ZENTRALE["nachts_min_neu"]))
        for wort in self.woerter.values():
            if wort.cfg.get("nachts") and wort.neue_seit_letztem_lauf() >= mindestens:
                self.auftrag(wort.id, "nachts")

    # --- Training ---------------------------------------------------------

    def reihe(self) -> list[str]:
        return [wid for wid in self.daten.get("reihe", []) if wid in self.woerter]

    @callback
    def auftrag(self, wid: str, grund: str, sparsam: int = 0) -> None:
        """Queue a run. sparsam > 0: resumed after the trainer restarted mid-run, the trainer uses less memory."""
        wort = self.woerter[wid]
        self._abgeholt.pop(wid, None)  # a new request may be taken at once
        wort.speicher.daten["auftrag"] = {"grund": grund, "zeit": jetzt(), **({"sparsam": sparsam} if sparsam else {})}
        if wort.speicher.daten["training"].get("phase") in ("bereit", "fertig", "fehler", None):
            wort.speicher.daten["training"] = {"phase": "wartet", "grund": grund, "seit": jetzt(),
                                               **({"neustarts": sparsam} if sparsam else {})}
        if wid not in self.daten["reihe"]:
            self.daten["reihe"].append(wid)
        self.hass.async_add_executor_job(wort.speicher.speichern)
        self.speichern_spaeter()
        self.geaendert()

    @callback
    def abbrechen(self, wid: str) -> None:
        wort = self.woerter[wid]
        wort.speicher.daten["auftrag"] = None
        if wid in self.daten["reihe"]:
            self.daten["reihe"].remove(wid)
        if wort.speicher.daten["training"].get("phase") in LAEUFT:
            self.daten["abbrechen"] = wid
        wort.speicher.daten["training"] = {"phase": "bereit"}
        self.hass.async_add_executor_job(wort.speicher.speichern)
        self.speichern_spaeter()
        self.geaendert()

    def naechster_auftrag(self) -> Wort | None:
        """Next queued run. A run just handed out is held back briefly, so a second trainer never takes it too."""
        frist = time.monotonic() - ABGEHOLT_SPERRE_S
        for wid in self.reihe():
            if wid not in self._abgeholt or self._abgeholt[wid] < frist:
                self._abgeholt[wid] = time.monotonic()
                return self.woerter[wid]
        return None

    @callback
    def trainer_meldet(self, status: dict[str, Any]) -> None:
        self.trainer_kontakt = datetime.now(UTC)
        if isinstance(status.get("info"), dict):
            self.trainer_info = status["info"]
        if status.get("neustart"):
            # Trainer ist neu gestartet (Absturz, Speicher voll, Update): Laeufe, die noch als aktiv gelten, sind verloren
            for anderes in self.woerter.values():
                if anderes.speicher.daten["training"].get("phase") in LAEUFT:
                    self._lauf_verloren(anderes)
        wid = status.get("wort_id")
        wort = self.woerter.get(str(wid)) if wid else None
        if wort is None:
            self.geaendert()
            return
        if isinstance(status.get("live"), dict):
            wort.live = _live_pruefen(status["live"])
            if "phase" not in status:  # only details (end of a run): no change of the stored state
                self.geaendert()
                return
        alt = wort.speicher.daten["training"]
        neu = {**{k: v for k, v in status.items() if k not in ("info", "wort_id", "live")}, "aktualisiert": jetzt()}
        if neu.get("phase") in LAEUFT:
            # Auftrag ist angenommen: aus der Reihe nehmen
            if alt.get("phase") not in LAEUFT:
                neu.setdefault("start", jetzt())
            wort.speicher.daten["auftrag"] = None
            if wort.id in self.daten["reihe"]:
                self.daten["reihe"].remove(wort.id)
                self.speichern_spaeter()
        if neu.get("phase") and neu.get("phase") != alt.get("phase"):
            neu.setdefault("seit", jetzt())
            if neu["phase"] == "fehler":
                wort.speicher.daten["laeufe"].append({
                    "start": alt.get("start"), "ende": jetzt(), "ergebnis": "fehler",
                    "hinweis": neu.get("schritt") or neu.get("hinweis"),
                })
            wort.speicher.daten["training"] = {**alt, **neu}
            self.hass.async_add_executor_job(wort.speicher.speichern)
        else:
            wort.speicher.daten["training"] = {**alt, **neu}
            wort.speicher.stand += 1
        self.geaendert()

    async def ergebnis(self, wort: Wort, tflite: bytes, bericht: dict[str, Any]) -> dict[str, Any]:
        """Neue Version vom Trainer: ablegen, Lauf merken, wenn besser einspielen."""
        sp = wort.speicher
        if bericht.get("alt") and sp.daten.get("aktiv"):
            bericht["alt_nr"] = sp.daten["aktiv"]  # the trainer compared with the version on the devices
        eintrag = await self.hass.async_add_executor_job(sp.version_neu, tflite, bericht)
        besser = bool(bericht.get("besser"))
        gleich = not besser and (bericht.get("vergleich") or {}).get("urteil") == "gleich"
        lauf = {
            "start": sp.daten["training"].get("start") or bericht.get("start"),
            "ende": jetzt(),
            "version": eintrag["nr"],
            "ergebnis": "besser" if besser else "gleich" if gleich else "nicht_besser",
            "bewertet": bericht.get("bewertet_genutzt", sp.statistik()["bewertet"]),
            "neu": bericht.get("neu"),
            "alt": bericht.get("alt"),
            "dauer_min": bericht.get("dauer_min"),
        }
        eintrag["status"] = "geprueft" if besser else "verworfen"
        sp.daten["laeufe"].append(lauf)
        sp.daten["training"] = {"phase": "fertig", "seit": jetzt(), "version": eintrag["nr"], "besser": besser,
                                "gleich": gleich}
        sp.daten["auftrag"] = None
        await self.hass.async_add_executor_job(sp.speichern)
        if besser and wort.cfg.get("automatisch_einspielen"):
            await self.einspielen(wort, eintrag["nr"])
            lauf["ergebnis"] = "eingespielt"
            await self.hass.async_add_executor_job(sp.speichern)
        self.geaendert()
        return eintrag

    # --- Einspielen -------------------------------------------------------

    async def einspielen(self, wort: Wort, nr: int, cutoff: float | None = None) -> None:
        """Version an den Geraeten des Worts einspielen, ohne HA neu zu starten."""
        version = wort.speicher.version(nr)
        if version is None:
            raise ValueError("version_fehlt")
        if cutoff is None:
            cutoff = float((version.get("bericht") or {}).get("cutoff") or 0.97)
        ziel = self.hass.config.path("custom_wake_words")
        await self.hass.async_add_executor_job(
            wort.speicher.einspielen_dateien, nr, ziel, wort.modell_id, wort.anzeige, cutoff, wort.sprache
        )
        # ESPHome reads the folder custom_wake_words when Home Assistant starts. A new version reaches the
        # devices after the next restart; a repair message offers it with one tap, afterwards the word is
        # selected on its slots by itself.
        warten = self.daten.setdefault("nach_neustart", [])
        if wort.id not in warten:
            warten.append(wort.id)
        await self.hass.async_add_executor_job(self.speichern)
        self.neustart_meldung()
        self.geaendert()

    @callback
    def neustart_meldung(self) -> None:
        """Repair message 'restart to roll out' while versions are waiting for a restart."""
        namen = [self.woerter[w].wort for w in self.daten.get("nach_neustart", []) if w in self.woerter]
        if namen:
            ir.async_create_issue(
                self.hass, DOMAIN, NEUSTART_MELDUNG, is_fixable=True, severity=ir.IssueSeverity.WARNING,
                translation_key=NEUSTART_MELDUNG, translation_placeholders={"words": ", ".join(namen)},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, NEUSTART_MELDUNG)

    async def nach_neustart(self, _now: Any = None) -> None:
        """After a restart of Home Assistant: select the rolled out words on their devices."""
        for wid in list(self.daten.get("nach_neustart", [])):
            if wid in self.woerter:
                wort = self.woerter[wid]
                await self.auswaehlen(wort)
                wort.speicher.daten["aktiv_seit"] = jetzt()
                schwelle = wort.speicher.aktive_schwelle()
                if wort.cfg.get("schwelle_automatisch") and schwelle is not None:
                    await self._schwelle_auto(wort, schwelle, "test")
                await self.hass.async_add_executor_job(wort.speicher.speichern)
        self.daten["nach_neustart"] = []
        await self.hass.async_add_executor_job(self.speichern)
        self.neustart_meldung()
        self.geaendert()

    async def auswaehlen(self, wort: Wort) -> list[str]:
        """Das Wort an seinen Plaetzen in der Auswahl "Aktivierungswort" setzen."""
        gesetzt = []
        for knoten, platz in wort.geraete.items():
            ent = self.wortwahl_entitaet(knoten, platz)
            s = self.hass.states.get(ent) if ent else None
            if ent is None or s is None or wort.anzeige not in (s.attributes.get("options") or []):
                continue
            if s.state != wort.anzeige:
                await self.hass.services.async_call(
                    "select", "select_option", {"entity_id": ent, "option": wort.anzeige}, blocking=True
                )
            gesetzt.append(ent)
        return gesetzt

    async def schwelle_setzen(self, wort: Wort, wert: float) -> list[str]:
        ziele = [e for k, p in wort.geraete.items() if (e := self.schwelle_entitaet(k, p))]
        if ziele:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": ziele, "value": round(wert, 2)}, blocking=True
            )
        return ziele

    async def _schwelle_auto(self, wort: Wort, wert: float, quelle: str) -> None:
        """Set the threshold on the word's devices by itself and remember why (shown on the quality page)."""
        wert = round(min(SCHWELLE_MAX, wert), 2)
        if await self.schwelle_setzen(wort, wert):
            wort.speicher.daten["schwelle_auto"] = {"wert": wert, "zeit": jetzt(), "quelle": quelle}

    async def schwelle_pruefen(self) -> None:
        """Follow your answers: once enough device recordings of the active version are reviewed,
        move the threshold to the value that fits them best (never far below the tested value)."""
        for wort in list(self.woerter.values()):
            if not wort.cfg.get("schwelle_automatisch") or not wort.geraete:
                continue
            statistik = await self.hass.async_add_executor_job(wort.speicher.statistik)
            vorschlag, getestet = statistik.get("schwelle_vorschlag"), wort.speicher.aktive_schwelle()
            if vorschlag is None:
                continue
            ziel = round(min(SCHWELLE_MAX, max(vorschlag, (getestet or 0) - SCHWELLE_SPIELRAUM)), 2)
            jetzt_werte = self.schwellen_jetzt(wort).values()
            if jetzt_werte and all(abs(x - ziel) < 0.005 for x in jetzt_werte):
                continue
            await self._schwelle_auto(wort, ziel, "antworten")
            await self.hass.async_add_executor_job(wort.speicher.speichern)
            self.geaendert()

    def schwellen_jetzt(self, wort: Wort) -> dict[str, float]:
        namen = self.geraete()
        werte: dict[str, float] = {}
        for knoten, platz in wort.geraete.items():
            ent = self.schwelle_entitaet(knoten, platz)
            s = self.hass.states.get(ent) if ent else None
            try:
                if s:
                    werte[namen.get(knoten, knoten)] = float(s.state)
            except ValueError:
                pass
        return werte

    async def einstellungen_setzen(self, neu: dict[str, Any]) -> None:
        e = self.daten.setdefault("einstellungen", {})
        for k, v in neu.items():
            if k in STANDARD_ZENTRALE:
                e[k] = v
        if "uhrzeit" in neu:
            self.nachts_planen()
        await self.hass.async_add_executor_job(self.speichern)
        self.erinnern()
        self.geaendert()
