"""Schnittstellen fuer die Seite in der Seitenleiste und fuer den Trainer.

Seite (HA-Anmeldung noetig):
    GET  /api/sprachmodell/daten            Uebersicht, Statistik, Training, Versionen
    GET  /api/sprachmodell/liste            Aufnahmen (filter, echo, art, seite)
    GET  /api/sprachmodell/audio/<id>       WAV einer Aufnahme
    POST /api/sprachmodell/urteil           {ids, urteil, person}
    POST /api/sprachmodell/hochladen        Zip (multipart: datei, person)
    POST /api/sprachmodell/aktion           {aktion, ...}

Trainer (Schluessel im Kopf "X-Sprachmodell-Schluessel"):
    GET  /api/sprachmodell/trainer/auftrag
    GET  /api/sprachmodell/trainer/liste
    GET  /api/sprachmodell/trainer/audio/<id>
    GET  /api/sprachmodell/trainer/modell   aktive Version (Ausgangspunkt fuers Feintuning)
    POST /api/sprachmodell/trainer/status
    POST /api/sprachmodell/trainer/ergebnis multipart: modell (tflite), bericht (json)
"""

from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.network import NoURLAvailableError, get_url

from . import zentrale_holen
from .const import DOMAIN, OPT_AUTO, OPT_NACHTS, OPT_UHRZEIT
from .sammler import echos_finden
from .speicher import sichere_id

GROESSTE_ZIP = 200 * 1024 * 1024
GROESSTES_MODELL = 2 * 1024 * 1024
_ANGEMELDET = f"{DOMAIN}_ansichten"


def _zentrale(request: web.Request):
    hass: HomeAssistant = request.app[KEY_HASS]
    zentrale = zentrale_holen(hass)
    if zentrale is None:
        raise web.HTTPServiceUnavailable(text="Sprachmodell ist nicht eingerichtet")
    return zentrale


def _wav(zentrale, aid: str) -> web.StreamResponse:
    aid = sichere_id(aid)
    pfad = zentrale.speicher.pfad("aufnahmen", aid + ".wav")
    if aid not in zentrale.speicher.daten["aufnahmen"] or not os.path.isfile(pfad):
        raise web.HTTPNotFound()
    return web.FileResponse(pfad, headers={"Content-Type": "audio/wav", "Cache-Control": "private, max-age=86400"})


def _interne_adresse(hass: HomeAssistant) -> str | None:
    try:
        return get_url(hass, prefer_external=False, allow_cloud=False, allow_external=False)
    except NoURLAvailableError:
        return None


def _uebersicht(zentrale) -> dict[str, Any]:
    sp = zentrale.speicher
    stat = sp.statistik()
    versionen = sorted(sp.daten["versionen"], key=lambda v: v["nr"], reverse=True)
    return {
        "stand": sp.stand,
        "version_integration": zentrale.version,
        "statistik": stat,
        "training": sp.daten["training"],
        "auftrag": sp.daten["auftrag"],
        "laeufe": list(reversed(sp.daten["laeufe"][-50:])),
        "versionen": versionen,
        "aktiv": sp.daten["aktiv"],
        "echos": echos_finden(zentrale.hass),
        "echo_fehler": zentrale.sammler.fehler,
        "personen": zentrale.personen(),
        "schwellen": zentrale.schwellen_jetzt(),
        "trainer": {
            "online": zentrale.trainer_online,
            "kontakt": zentrale.trainer_kontakt.isoformat() if zentrale.trainer_kontakt else None,
            "info": zentrale.trainer_info,
            "schluessel": zentrale.schluessel,
            "adresse": _interne_adresse(zentrale.hass),
        },
        "einstellungen": {
            "nachts": zentrale.opt(OPT_NACHTS),
            "uhrzeit": zentrale.opt(OPT_UHRZEIT),
            "automatisch_einspielen": zentrale.opt(OPT_AUTO),
            "modell_id": zentrale.modell_id,
            "anzeige": zentrale.anzeige,
            "ordner": sp.ordner,
        },
        "neu_seit_lauf": zentrale.neue_seit_letztem_lauf(),
    }


class DatenAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/daten"
    name = "api:sprachmodell:daten"

    async def get(self, request: web.Request) -> web.Response:
        return self.json(_uebersicht(_zentrale(request)))


class ListeAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/liste"
    name = "api:sprachmodell:liste"

    async def get(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        q = request.query
        return self.json(z.speicher.liste(
            q.get("filter", "offen"), q.get("echo") or None, q.get("art") or None,
            max(0, int(q.get("seite", 0) or 0)),
        ))


class AudioAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/audio/{aid}"
    name = "api:sprachmodell:audio"

    async def get(self, request: web.Request, aid: str) -> web.StreamResponse:
        return _wav(_zentrale(request), aid)


class UrteilAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/urteil"
    name = "api:sprachmodell:urteil"

    async def post(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        daten = await request.json()
        ids = [str(i) for i in daten.get("ids") or []]
        hass = request.app[KEY_HASS]
        if daten.get("loeschen"):
            n = await hass.async_add_executor_job(z.speicher.loeschen, ids)
        elif "urteil" in daten:
            try:
                n = await hass.async_add_executor_job(
                    z.speicher.urteilen, ids, daten.get("urteil"), daten.get("person")
                )
            except ValueError as err:
                return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        else:
            n = await hass.async_add_executor_job(z.speicher.person_setzen, ids, daten.get("person"))
        z.geaendert()
        z.erinnern()
        return self.json({"geaendert": n, "stand": z.speicher.stand})


class HochladenAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/hochladen"
    name = "api:sprachmodell:hochladen"

    async def post(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        hass = request.app[KEY_HASS]
        leser = await request.multipart()
        person, inhalt = None, b""
        async for teil in leser:
            if teil.name == "person":
                person = (await teil.text()).strip() or None
            elif teil.name == "datei":
                stuecke, groesse = [], 0
                while stueck := await teil.read_chunk(1 << 20):
                    groesse += len(stueck)
                    if groesse > GROESSTE_ZIP:
                        return self.json_message("Datei zu groß (höchstens 200 MB)", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    stuecke.append(stueck)
                inhalt = b"".join(stuecke)
        if not inhalt:
            return self.json_message("Keine Datei", HTTPStatus.BAD_REQUEST)
        try:
            ergebnis = await hass.async_add_executor_job(z.speicher.zip_einlesen, inhalt, person)
        except ValueError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        z.geaendert()
        return self.json(ergebnis)


class AktionAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/aktion"
    name = "api:sprachmodell:aktion"

    async def post(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        hass = request.app[KEY_HASS]
        daten = await request.json()
        aktion = daten.get("aktion")
        if aktion == "training_starten":
            z.auftrag("von Hand")
        elif aktion == "training_abbrechen":
            z.abbrechen()
        elif aktion == "jetzt_holen":
            await z._takt()  # noqa: SLF001
        elif aktion == "einspielen":
            try:
                await z.einspielen(int(daten["nr"]))
            except (KeyError, ValueError) as err:
                return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        elif aktion == "schwelle":
            ziele = await z.schwelle_setzen(float(daten["wert"]))
            return self.json({"gesetzt": ziele})
        elif aktion == "vorschlaege_uebernehmen":
            offen = [a for a in z.speicher.offen() if a.get("vorschlag")]
            if daten.get("ids"):
                gewollt = set(daten["ids"])
                offen = [a for a in offen if a["id"] in gewollt]
            for urteil in ("wort", "kein_wort"):
                ids = [a["id"] for a in offen if a["vorschlag"] == urteil]
                if ids:
                    await hass.async_add_executor_job(z.speicher.urteilen, ids, urteil, daten.get("person"))
            z.erinnern()
        elif aktion == "einstellungen":
            optionen = dict(z.entry.options)
            for schluessel in (OPT_NACHTS, OPT_AUTO, OPT_UHRZEIT):
                if schluessel in daten:
                    optionen[schluessel] = daten[schluessel]
            hass.config_entries.async_update_entry(z.entry, options=optionen)
            return self.json({"ok": True})
        else:
            return self.json_message("Unbekannte Aktion", HTTPStatus.BAD_REQUEST)
        z.geaendert()
        return self.json({"ok": True, "stand": z.speicher.stand})


# --- Trainer ------------------------------------------------------------


class _TrainerAnsicht(HomeAssistantView):
    requires_auth = False

    def _pruefen(self, request: web.Request):
        z = _zentrale(request)
        geschickt = request.headers.get("X-Sprachmodell-Schluessel", "")
        if not hmac.compare_digest(geschickt.encode(), z.schluessel.encode()):
            raise web.HTTPUnauthorized(text="Falscher Schlüssel")
        z.trainer_kontakt = datetime.now(timezone.utc)
        return z


class TrainerAuftrag(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/auftrag"
    name = "api:sprachmodell:trainer:auftrag"

    async def get(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        abbrechen = bool(z.speicher.daten.pop("abbrechen", False))
        return self.json({
            "auftrag": z.speicher.daten["auftrag"],
            "abbrechen": abbrechen,
            "aktiv": z.speicher.daten["aktiv"],
            "modell_id": z.modell_id,
            "wort": z.entry.data.get("wort") or "Алиса",
        })


class TrainerListe(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/liste"
    name = "api:sprachmodell:trainer:liste"

    async def get(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        return self.json({"aufnahmen": z.speicher.trainer_liste()})


class TrainerAudio(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/audio/{aid}"
    name = "api:sprachmodell:trainer:audio"

    async def get(self, request: web.Request, aid: str) -> web.StreamResponse:
        return _wav(self._pruefen(request), aid)


class TrainerModell(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/modell"
    name = "api:sprachmodell:trainer:modell"

    async def get(self, request: web.Request) -> web.StreamResponse:
        z = self._pruefen(request)
        nr = request.query.get("nr") or z.speicher.daten["aktiv"]
        if not nr:
            raise web.HTTPNotFound()
        pfad = z.speicher.modell_datei(int(nr))
        if not os.path.isfile(pfad):
            raise web.HTTPNotFound()
        return web.FileResponse(pfad, headers={"Content-Type": "application/octet-stream", "X-Version": str(nr)})


class TrainerStatus(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/status"
    name = "api:sprachmodell:trainer:status"

    async def post(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        daten = await request.json()
        if not isinstance(daten, dict):
            return self.json_message("JSON-Objekt erwartet", HTTPStatus.BAD_REQUEST)
        if daten.get("phase") in ("vorbereiten", "daten", "merkmale", "training", "test"):
            # Auftrag ist angenommen
            if z.speicher.daten["training"].get("phase") in ("wartet", "bereit", "fertig", "fehler"):
                daten.setdefault("start", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            z.speicher.daten["auftrag"] = None
        z.trainer_meldet(daten)
        return self.json({"ok": True})


class TrainerErgebnis(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/ergebnis"
    name = "api:sprachmodell:trainer:ergebnis"

    async def post(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        leser = await request.multipart()
        modell, bericht = b"", {}
        async for teil in leser:
            if teil.name == "modell":
                modell = await teil.read()
                if len(modell) > GROESSTES_MODELL:
                    return self.json_message("Modell zu groß", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            elif teil.name == "bericht":
                bericht = json.loads(await teil.text())
        if b"TFL3" not in modell[:16]:
            return self.json_message("Kein TFLite-Modell", HTTPStatus.BAD_REQUEST)
        eintrag = await z.ergebnis(modell, bericht if isinstance(bericht, dict) else {})
        return self.json({"version": eintrag["nr"], "status": eintrag["status"]})


@callback
def ansichten_anmelden(hass: HomeAssistant) -> None:
    if hass.data.get(_ANGEMELDET):
        return
    hass.data[_ANGEMELDET] = True
    for ansicht in (
        DatenAnsicht, ListeAnsicht, AudioAnsicht, UrteilAnsicht, HochladenAnsicht, AktionAnsicht,
        TrainerAuftrag, TrainerListe, TrainerAudio, TrainerModell, TrainerStatus, TrainerErgebnis,
    ):
        hass.http.register_view(ansicht())
