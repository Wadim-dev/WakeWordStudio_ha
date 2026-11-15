"""Die Sprachmodell-Zentrale: beliebig viele eigene Aktivierungswoerter.

Jedes Wort hat eigene Einstellungen (Sprache, Name am Geraet, welche Geraete
auf welchem Platz), eigene Aufnahmen, eigene Versionen und eigene Trainings.
Die Zentrale selbst kennt die Geraete, die gemeinsamen Einstellungen und die
Warteschlange fuer den Trainer. Alles wird in der App eingestellt.

Ablage (Standard /share/sprachmodell, sonst /config/sprachmodell):

    zentrale.json                Woerter, gemeinsame Einstellungen, Warteschlange
    woerter/<id>/daten.json      Aufnahmen, Versionen, Laeufe eines Worts
    woerter/<id>/aufnahmen/      WAVs
    woerter/<id>/modelle/v<n>/   Versionen
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    LAEUFT,
    PANEL_URL,
    SIGNAL_NEU,
    SPRACHEN,
    STANDARD_WORT,
    STANDARD_ZENTRALE,
    TRAINER_ONLINE_S,
)
from .sammler import Sammler, alle_geraete, esphome_eintraege
from .speicher import Speicher, jetzt, sichere_id

_LOGGER = logging.getLogger(__name__)

SAMMELN_TAKT = timedelta(minutes=2)
HINWEIS_ID = f"{DOMAIN}_pruefen"
# Cache der ESPHome-Integration fuer eigene Aktivierungswoerter (sonst erst nach Neustart neu)
WAKE_WORD_CACHE = "wake_word_cache"
DATEI = "zentrale.json"


def ablage_standard(hass: HomeAssistant) -> str:
    """/share ist im HA-Backup und fuer Apps lesbar; ohne /share (Container) /config."""
    return "/share/sprachmodell" if os.path.isdir("/share") else hass.config.path("sprachmodell")


def sprache_aus(hass: HomeAssistant) -> str:
    sprache = str(hass.config.language or "en").split("-")[0].lower()
    return sprache if sprache in SPRACHEN else "en"


class Wort:
    """Ein eigenes Aktivierungswort mit eigenen Aufnahmen und Versionen."""

    def __init__(self, zentrale: Zentrale, wid: str, cfg: dict[str, Any]) -> None:
        self.z = zentrale
        self.id = wid
        self.cfg = {**STANDARD_WORT, **cfg}
        self.speicher = Speicher(os.path.join(zentrale.ablage, "woerter", wid))

    # --- Eigenschaften ----------------------------------------------------

    @property
    def wort(self) -> str:
        return self.cfg["wort"] or self.id

    @property
    def anzeige(self) -> str:
        if self.cfg["anzeige"]:
            return self.cfg["anzeige"]
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
        letzte = next((l for l in reversed(self.speicher.daten["laeufe"]) if l.get("bewertet") is not None), None)
        return stat["bewertet"] - (letzte["bewertet"] if letzte else 0)

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
        }


class Zentrale:
    """Alles, was die Integration zur Laufzeit braucht."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.ablage: str = entry.data.get("ordner") or ablage_standard(hass)
        self.daten: dict[str, Any] = {}
        self.woerter: dict[str, Wort] = {}
        self.sammler = Sammler(hass, self)
        self.trainer_kontakt: datetime | None = None
        self.trainer_info: dict[str, Any] = {}
        self.version = "0"
        self._sperre = threading.RLock()
        self._weg: list[Any] = []
        self._sammeln_spaeter = None
        self._zaehler_weg: Any = None
        self._zaehler_ids: list[str] = []
        self._nachts_weg: Any = None
        # Plattform -> Funktion, die die Entitaeten eines neuen Worts anlegt
        self.anleger: dict[str, Any] = {}

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
        daten.setdefault("schluessel", secrets.token_urlsafe(24))
        self.daten = daten
        for wid, cfg in daten["woerter"].items():
            wort = Wort(self, wid, cfg)
            wort.speicher.laden()
            wort.speicher.vorschlaege()
            self.woerter[wid] = wort

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
        return self.daten["schluessel"]

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
            and (datetime.now(timezone.utc) - self.trainer_kontakt).total_seconds() < TRAINER_ONLINE_S
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
        endung = "-wake_word" if platz == "1" else f"-wake_word_{platz}"
        treffer = self._entitaeten(knoten, "select", endung)
        return treffer[0].entity_id if treffer else None

    def geraete_zustand(self) -> list[dict[str, Any]]:
        """Fuer die App: jedes Geraet mit Plaetzen, Wort darauf und Schwelle."""
        aus: list[dict[str, Any]] = []
        for knoten, name in self.geraete().items():
            plaetze = {}
            for platz in ("1", "2"):
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
                "knoten": knoten, "name": name, "plaetze": plaetze,
                "fehler": self.sammler.fehler.get(knoten),
                "zaehler": self._zaehlerstand(knoten),
            })
        return aus

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
        for k, v in cfg.items():
            if k in STANDARD_WORT and k != "modell_id":
                wort.cfg[k] = v
        if "wort" in cfg and not str(cfg["wort"]).strip():
            raise ValueError("wort_fehlt")
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
        for wort in self.woerter.values():
            t = wort.speicher.daten["training"]
            if t.get("phase") in LAEUFT:
                wort.speicher.daten["training"] = {"phase": "bereit", "hinweis": "neustart"}
        self._weg.append(async_track_time_interval(self.hass, self._takt, SAMMELN_TAKT))
        self._weg.append(async_track_time_interval(self.hass, self._stuendlich, timedelta(hours=1)))
        self.nachts_planen()
        async_call_later(self.hass, 20, self._takt)
        async_call_later(self.hass, 60, self._stuendlich)

    @callback
    def nachts_planen(self) -> None:
        if self._nachts_weg:
            self._nachts_weg()
        stunde, minute = (int(x) for x in str(self.opt("uhrzeit")).split(":")[:2])
        self._nachts_weg = async_track_time_change(self.hass, self._nachts, hour=stunde, minute=minute, second=0)

    async def stoppen(self) -> None:
        for weg in self._weg:
            weg()
        self._weg.clear()
        for weg in (self._zaehler_weg, self._nachts_weg):
            if weg:
                weg()
        self._zaehler_weg = self._nachts_weg = None
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
    def _zaehler(self, _event: Event) -> None:
        # Kurz warten: das Geraet schreibt die Aufnahme erst fertig
        if self._sammeln_spaeter:
            self._sammeln_spaeter()
        self._sammeln_spaeter = async_call_later(self.hass, 5, self._takt)

    # --- Regelmaessiges ---------------------------------------------------

    async def _takt(self, _now: Any = None) -> None:
        self._sammeln_spaeter = None
        self._zaehler_beobachten()
        try:
            neu = await self.sammler.holen()
        except Exception:  # noqa: BLE001 - Sammeln darf nie die Integration stoppen
            _LOGGER.exception("Aufnahmen holen fehlgeschlagen")
            return
        if neu:
            self.geaendert()

    async def jetzt_holen(self) -> None:
        await self._takt()

    async def _stuendlich(self, _now: Any = None) -> None:
        weg = 0
        for wort in self.woerter.values():
            weg += await self.hass.async_add_executor_job(
                wort.speicher.aufraeumen, int(self.opt("unbewertet_tage"))
            )
        if weg:
            self.geaendert()
        self.erinnern()

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
        alter = datetime.now(timezone.utc) - datetime.fromisoformat(aeltestes)
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
        persistent_notification.async_create(self.hass, text, title="Sprachmodell", notification_id=HINWEIS_ID)

    async def _nachts(self, _now: Any = None) -> None:
        for wort in self.woerter.values():
            if wort.cfg.get("nachts") and wort.neue_seit_letztem_lauf() > 0:
                self.auftrag(wort.id, "nachts")

    # --- Training ---------------------------------------------------------

    def reihe(self) -> list[str]:
        return [wid for wid in self.daten.get("reihe", []) if wid in self.woerter]

    @callback
    def auftrag(self, wid: str, grund: str) -> None:
        wort = self.woerter[wid]
        wort.speicher.daten["auftrag"] = {"grund": grund, "zeit": jetzt()}
        if wort.speicher.daten["training"].get("phase") in ("bereit", "fertig", "fehler", None):
            wort.speicher.daten["training"] = {"phase": "wartet", "grund": grund, "seit": jetzt()}
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
        reihe = self.reihe()
        return self.woerter[reihe[0]] if reihe else None

    @callback
    def trainer_meldet(self, status: dict[str, Any]) -> None:
        self.trainer_kontakt = datetime.now(timezone.utc)
        if isinstance(status.get("info"), dict):
            self.trainer_info = status["info"]
        wid = status.get("wort_id")
        wort = self.woerter.get(str(wid)) if wid else None
        if wort is None:
            self.geaendert()
            return
        alt = wort.speicher.daten["training"]
        neu = {**{k: v for k, v in status.items() if k not in ("info", "wort_id")}, "aktualisiert": jetzt()}
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
        eintrag = await self.hass.async_add_executor_job(sp.version_neu, tflite, bericht)
        besser = bool(bericht.get("besser"))
        lauf = {
            "start": sp.daten["training"].get("start") or bericht.get("start"),
            "ende": jetzt(),
            "version": eintrag["nr"],
            "ergebnis": "besser" if besser else "nicht_besser",
            "bewertet": bericht.get("bewertet_genutzt", sp.statistik()["bewertet"]),
            "neu": bericht.get("neu"),
            "alt": bericht.get("alt"),
            "dauer_min": bericht.get("dauer_min"),
        }
        eintrag["status"] = "geprueft" if besser else "verworfen"
        sp.daten["laeufe"].append(lauf)
        sp.daten["training"] = {"phase": "fertig", "seit": jetzt(), "version": eintrag["nr"], "besser": besser}
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
        # ESPHome merkt sich die Liste eigener Woerter samt Pruefsumme bis zum Neustart.
        # Ohne den Zwischenspeicher liest es sie neu; nach dem Neuladen holen die Geraete
        # das Modell mit der neuen Pruefsumme selbst.
        self.hass.data.pop(WAKE_WORD_CACHE, None)
        eintraege = esphome_eintraege(self.hass)
        for knoten in wort.geraete:
            if (eintrag := eintraege.get(knoten)) is not None:
                self.hass.async_create_task(self.hass.config_entries.async_reload(eintrag.entry_id))
        # Nach dem Neuladen das Wort an den Plaetzen auswaehlen
        async_call_later(self.hass, 30, lambda _n: self.hass.async_create_task(self.auswaehlen(wort)))
        self.geaendert()

    async def auswaehlen(self, wort: Wort) -> list[str]:
        """Das Wort an seinen Plaetzen in der Auswahl "Aktivierungswort" setzen."""
        gesetzt = []
        for knoten, platz in wort.geraete.items():
            ent = self.wortwahl_entitaet(knoten, platz)
            s = self.hass.states.get(ent) if ent else None
            if s is None or wort.anzeige not in (s.attributes.get("options") or []):
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
