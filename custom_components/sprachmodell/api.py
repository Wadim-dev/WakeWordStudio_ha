"""HTTP API for the panel and for the trainer.

Panel (Home Assistant login; changing words, settings, the trainer key, rolling out and
deleting need an administrator). "wort" = id of the word:
    GET  /api/sprachmodell/daten?wort=           Zentrale + Einzelheiten eines Worts
    GET  /api/sprachmodell/liste?wort=           Aufnahmen (filter, echo, art, seite, sort=zweifel)
    GET  /api/sprachmodell/audio/<wort>/<id>     WAV einer Aufnahme
    POST /api/sprachmodell/urteil                {wort, ids, urteil | person | loeschen}
    POST /api/sprachmodell/hochladen             multipart: wort, person, datei (Zip)
    POST /api/sprachmodell/aufnahme              multipart: wort, urteil, person, notiz, datei (WAV)
    POST /api/sprachmodell/aktion                {aktion, wort?, ...}; anderes_wort {wort, id, ziel, person}
                                                 hands a recording to another word (anderes_wort_zurueck undoes)

Trainer (header "X-Sprachmodell-Schluessel" with the trainer key, or the Home Assistant
token of an administrator, e.g. the one a Home Assistant app gets from the Supervisor):
    GET  /api/sprachmodell/trainer/auftrag       naechster Auftrag, Abbruch, Woerter
    GET  /api/sprachmodell/trainer/liste?wort=
    GET  /api/sprachmodell/trainer/audio/<wort>/<id>
    GET  /api/sprachmodell/trainer/modell?wort=  aktive Version (Ausgangspunkt fuers Feintuning)
    POST /api/sprachmodell/trainer/status        {wort_id, phase, prozent, schritt, ...}
    POST /api/sprachmodell/trainer/ergebnis?wort= multipart: modell (tflite), bericht (json)
    POST /api/sprachmodell/trainer/gehoert       {wort_id, ergebnisse: {id: heard text}} (pre-review)
    POST /api/sprachmodell/trainer/vergleich     {wort_id, bericht} (fair comparison of two stored versions)

Devices (header "Authorization: Bearer <trainer key>"), the clip upload format of TECHO5's "Send wake clips to":
    POST /api/sprachmodell/clips                 multipart: audio (16 kHz mono WAV, max 2 MB), meta (JSON: name,
                                                 device, kind, at, model, slot, score, cutoff)
    GET  /api/sprachmodell/clips/ping            checks the key
    Devices add /api/clips to the base address: http://<home assistant>/api/wake_word_studio (also /api/sprachmodell).
"""

from __future__ import annotations

import hmac
from http import HTTPStatus
import json
import os
import re
import secrets
from typing import Any

from aiohttp import BodyPartReader, web
from homeassistant.components.http.const import KEY_HASS_USER
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.http import KEY_AUTHENTICATED, KEY_HASS, HomeAssistantView
from homeassistant.helpers.network import NoURLAvailableError, get_url

from . import zentrale_holen
from .const import DOMAIN, KEIN_WORT, SPRACHEN, STANDARD_WORT, STANDARD_ZENTRALE, TRAINER_OHNE_ID, TRAINER_VERSION, VORPRUEFEN_JE_MAL, WORT
from .speicher import sichere_id
from .zentrale import Wort, Zentrale, trainer_name

GROESSTE_ZIP = 200 * 1024 * 1024
GROESSTE_AUFNAHME = 10 * 1024 * 1024
GROESSTES_MODELL = 2 * 1024 * 1024
_ANGEMELDET = f"{DOMAIN}_ansichten"
# Actions that change the setup or reach the devices: administrators only
NUR_ADMIN = {
    "einstellungen", "schluessel_neu", "reihe", "wort_neu", "wort_aendern", "wort_loeschen",
    "einspielen", "auswaehlen", "schwelle", "trainer", "vergleich_starten",
}


def _fehler(art: type[web.HTTPException], code: str) -> web.HTTPException:
    """HTTP error with a JSON body {"message": code}; the panel translates the code."""
    return art(text=json.dumps({"message": code}), content_type="application/json")


def _admin(request: web.Request) -> bool:
    benutzer = request.get(KEY_HASS_USER)
    return benutzer is not None and benutzer.is_admin


def _zentrale(request: web.Request) -> Zentrale:
    hass: HomeAssistant = request.app[KEY_HASS]
    zentrale = zentrale_holen(hass)
    if zentrale is None:
        raise _fehler(web.HTTPServiceUnavailable, "nicht_eingerichtet")
    return zentrale


def _wort(z: Zentrale, wid: str | None) -> Wort:
    wort = z.woerter.get(str(wid or ""))
    if wort is None:
        raise _fehler(web.HTTPNotFound, "wort_nicht_gefunden")
    return wort


def _wav(wort: Wort, aid: str) -> web.StreamResponse:
    aid = sichere_id(aid)
    pfad = wort.speicher.pfad("aufnahmen", aid + ".wav")
    if aid not in wort.speicher.daten["aufnahmen"] or not os.path.isfile(pfad):
        raise _fehler(web.HTTPNotFound, "aufnahme_nicht_gefunden")
    return web.FileResponse(pfad, headers={"Content-Type": "audio/wav", "Cache-Control": "private, max-age=86400"})


def _interne_adresse(hass: HomeAssistant) -> str | None:
    try:
        return get_url(hass, prefer_external=False, allow_cloud=False, allow_external=False)
    except NoURLAvailableError:
        return None


def _vorhandene_modelle(ordner: str) -> list[dict[str, Any]]:
    """Eigene Woerter in /config/custom_wake_words (zum Uebernehmen beim Anlegen)."""
    aus: list[dict[str, Any]] = []
    try:
        namen = sorted(os.listdir(ordner))
    except OSError:
        return aus
    for name in namen:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(ordner, name), encoding="utf-8") as datei:
                info = json.load(datei)
        except (OSError, ValueError):
            continue
        modell = str(info.get("model") or "")
        if modell.endswith(".tflite") and os.path.isfile(os.path.join(ordner, modell)):
            aus.append({
                "modell_id": modell[: -len(".tflite")],
                "anzeige": info.get("wake_word"),
                "sprache": (info.get("trained_languages") or [None])[0],
            })
    return aus


def _trainer_liste(z: Zentrale) -> list[dict[str, Any]]:
    """Every known trainer for the studio: state, hardware, what it runs and how long a run takes there."""
    dauer = z.dauer(z.woerter[z.reihe()[0]] if z.reihe() else None)
    return sorted(({
        "id": tid,
        "name": trainer_name(t["info"]),
        "info": t["info"],
        "online": z.ist_online(tid),
        "kontakt": t["kontakt"].isoformat(),
        "pause": z.trainer_pausiert(tid),
        "laeuft": [w.wort for w in z.laeuft_bei(tid)] if tid in z.trainer else [],
        "dauer": dauer.get(tid),
        "bild_bereit": z.bild_bereit(t["info"]),
        "alt": tid == TRAINER_OHNE_ID,
        "neustart_taste": z.neustart_taste(tid),
        "neustart": z.neustart_zustand(tid),
    } for tid, t in z.trainer.items()), key=lambda x: (not x["online"], x["name"]))


def _zentrale_daten(z: Zentrale, admin: bool) -> dict[str, Any]:
    return {
        "admin": admin,
        "version_integration": z.version,
        "version_trainer": TRAINER_VERSION,
        "woerter": [w.kurz() for w in z.woerter.values()],
        "geraete": z.geraete_zustand(),
        "offen": z.offen_gesamt(),
        "personen": z.personen(),
        "sprachen": list(SPRACHEN),
        "einstellungen": {k: z.opt(k) for k in STANDARD_ZENTRALE},
        "ablage": z.ablage,
        "reihe": z.reihe(),
        "nach_neustart": [w for w in z.daten.get("nach_neustart", []) if w in z.woerter],
        "trainer": {
            "online": z.trainer_online,
            "kontakt": z.trainer_kontakt.isoformat() if z.trainer_kontakt else None,
            "info": z.trainer_info,
            "liste": _trainer_liste(z),
            "ziel": z.ziel_trainer(),
            "last": z.trainer_last(),
            "engpass": z.engpass(),
            "bild_bereit": z.bild_bereit(),
            "schluessel": z.schluessel if admin else None,
            "adresse": _interne_adresse(z.hass),
        },
    }


def _wort_daten(z: Zentrale, wort: Wort) -> dict[str, Any]:
    sp = wort.speicher
    return {
        "id": wort.id,
        "stand": sp.stand,
        "einstellungen": {**wort.cfg, "anzeige": wort.anzeige, "modell_id": wort.modell_id},
        "statistik": sp.statistik(),
        "training": sp.daten["training"],
        "live": wort.live,
        "auftrag": sp.daten["auftrag"],
        "laeufe": list(reversed(sp.daten["laeufe"][-50:])),
        "versionen": sorted(sp.daten["versionen"], key=lambda v: v["nr"], reverse=True),
        "vergleiche": list(reversed(sp.daten.get("vergleiche") or [])),
        "kann_vergleichen": z.kann_vergleichen(),
        "aktiv": sp.daten["aktiv"],
        "schwellen": z.schwellen_jetzt(wort),
        "dauer": z.dauer(wort),
        "neu_seit_lauf": wort.neue_seit_letztem_lauf(),
        "ordner": sp.ordner,
    }


class DatenAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/daten"
    name = "api:sprachmodell:daten"

    async def get(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        hass = request.app[KEY_HASS]
        aus = _zentrale_daten(z, _admin(request))
        wid = request.query.get("wort")
        if wid and wid in z.woerter:
            aus["wort"] = _wort_daten(z, z.woerter[wid])
        if request.query.get("modelle"):
            aus["vorhandene_modelle"] = await hass.async_add_executor_job(
                _vorhandene_modelle, hass.config.path("custom_wake_words")
            )
        return self.json(aus)


class ListeAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/liste"
    name = "api:sprachmodell:liste"

    async def get(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        q = request.query
        wort = _wort(z, q.get("wort"))
        zelle = None
        if q.get("zeile"):
            try:
                zelle = (str(q["zeile"]), float(q.get("von", 0)), float(q.get("bis", 2)))
            except ValueError:
                return self.json_message("ungueltig", HTTPStatus.BAD_REQUEST)
        return self.json(wort.speicher.liste(
            q.get("filter", "offen"), q.get("echo") or None, q.get("art") or None,
            max(0, int(q.get("seite", 0) or 0)), zelle=zelle, sortierung=q.get("sort") or None,
        ))


class AudioAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/audio/{wid}/{aid}"
    name = "api:sprachmodell:audio"

    async def get(self, request: web.Request, wid: str, aid: str) -> web.StreamResponse:
        return _wav(_wort(_zentrale(request), wid), aid)


class UrteilAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/urteil"
    name = "api:sprachmodell:urteil"

    async def post(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        daten = await _json(request)
        wort = _wort(z, daten.get("wort"))
        sp = wort.speicher
        ids = [str(i) for i in daten.get("ids") or []]
        hass = request.app[KEY_HASS]
        if daten.get("loeschen"):
            if not _admin(request):
                return self.json_message("nur_admin", HTTPStatus.FORBIDDEN)
            n = await hass.async_add_executor_job(sp.loeschen, ids)
        elif "urteil" in daten:
            try:
                n = await hass.async_add_executor_job(sp.urteilen, ids, daten.get("urteil"), daten.get("person"))
            except ValueError as err:
                return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        else:
            n = await hass.async_add_executor_job(sp.person_setzen, ids, daten.get("person"))
        z.geaendert()
        z.erinnern()
        return self.json({"geaendert": n, "stand": sp.stand})


async def _json(request: web.Request) -> dict[str, Any]:
    try:
        daten = await request.json()
    except ValueError as err:
        raise _fehler(web.HTTPBadRequest, "json_erwartet") from err
    if not isinstance(daten, dict):
        raise _fehler(web.HTTPBadRequest, "json_erwartet")
    return daten


async def _multipart(request: web.Request, grenze: int, feld: str = "datei") -> tuple[dict[str, str], bytes]:
    felder: dict[str, str] = {}
    inhalt = b""
    if not request.content_type.startswith("multipart/"):
        raise _fehler(web.HTTPBadRequest, "keine_datei")
    async for teil in await request.multipart():
        if not isinstance(teil, BodyPartReader):
            continue
        if teil.name == feld:
            stuecke, groesse = [], 0
            while stueck := await teil.read_chunk(1 << 20):
                groesse += len(stueck)
                if groesse > grenze:
                    raise web.HTTPRequestEntityTooLarge(max_size=grenze, actual_size=groesse)
                stuecke.append(stueck)
            inhalt = b"".join(stuecke)
        elif teil.name:
            felder[teil.name] = (await teil.text()).strip()
    return felder, inhalt


class HochladenAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/hochladen"
    name = "api:sprachmodell:hochladen"

    async def post(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        hass = request.app[KEY_HASS]
        felder, inhalt = await _multipart(request, GROESSTE_ZIP)
        wort = _wort(z, felder.get("wort"))
        if not inhalt:
            return self.json_message("keine_datei", HTTPStatus.BAD_REQUEST)
        try:
            ergebnis = await hass.async_add_executor_job(
                wort.speicher.zip_einlesen, inhalt, felder.get("person") or None
            )
        except ValueError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        z.geaendert()
        return self.json(ergebnis)


class AufnahmeAnsicht(HomeAssistantView):
    """Eine im Browser aufgenommene Aufnahme (WAV, schon bewertet)."""

    url = "/api/sprachmodell/aufnahme"
    name = "api:sprachmodell:aufnahme"

    async def post(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        hass = request.app[KEY_HASS]
        felder, inhalt = await _multipart(request, GROESSTE_AUFNAHME)
        wort = _wort(z, felder.get("wort"))
        try:
            eintrag = await hass.async_add_executor_job(
                wort.speicher.browser_aufnahme, inhalt, felder.get("urteil") or WORT,
                felder.get("person") or None, felder.get("notiz") or None,
            )
        except (ValueError, EOFError) as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        z.geaendert()
        return self.json({"id": eintrag.get("id"), "stand": wort.speicher.stand})


class RaumAnsicht(HomeAssistantView):
    """Room sound of a device: POST one clap (WAV, cut in the browser), DELETE all of the device."""

    url = "/api/sprachmodell/raum"
    name = "api:sprachmodell:raum"

    async def post(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        if not _admin(request):
            return self.json_message("nur_admin", HTTPStatus.FORBIDDEN)
        hass = request.app[KEY_HASS]
        felder, inhalt = await _multipart(request, GROESSTE_AUFNAHME)
        knoten = felder.get("knoten") or ""
        if knoten not in {g["knoten"] for g in z.geraete_zustand()}:
            return self.json_message("geraet_unbekannt", HTTPStatus.BAD_REQUEST)
        try:
            hall = float(felder["hall"]) if felder.get("hall") else None
            rid = await hass.async_add_executor_job(z.raeume.hinzufuegen, knoten, inhalt, hall, felder.get("stelle"))
        except (ValueError, EOFError) as err:
            return self.json_message(str(err) if str(err).isidentifier() else "ungueltig", HTTPStatus.BAD_REQUEST)
        return self.json({"id": rid, "raum": z.raeume.zustand(knoten)})

    async def delete(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        if not _admin(request):
            return self.json_message("nur_admin", HTTPStatus.FORBIDDEN)
        await request.app[KEY_HASS].async_add_executor_job(z.raeume.loeschen, request.query.get("knoten") or "")
        return self.json({"ok": True})


def _raum_wav(z: Zentrale, knoten: str, rid: str) -> web.StreamResponse:
    pfad = z.raeume.datei(knoten, rid)
    if not pfad:
        raise _fehler(web.HTTPNotFound, "aufnahme_nicht_gefunden")
    return web.FileResponse(pfad, headers={"Content-Type": "audio/wav", "Cache-Control": "private, max-age=86400"})


class RaumAudio(HomeAssistantView):
    url = "/api/sprachmodell/raum/{knoten}/{rid}"
    name = "api:sprachmodell:raum:audio"

    async def get(self, request: web.Request, knoten: str, rid: str) -> web.StreamResponse:
        return _raum_wav(_zentrale(request), knoten, rid)


class AktionAnsicht(HomeAssistantView):
    url = "/api/sprachmodell/aktion"
    name = "api:sprachmodell:aktion"

    async def post(self, request: web.Request) -> web.Response:
        z = _zentrale(request)
        hass = request.app[KEY_HASS]
        daten = await _json(request)
        aktion = str(daten.get("aktion"))
        if aktion in NUR_ADMIN and not _admin(request):
            return self.json_message("nur_admin", HTTPStatus.FORBIDDEN)
        try:
            antwort = await self._ausfuehren(z, hass, aktion, daten)
        except (KeyError, TypeError, ValueError) as err:
            code = str(err) if isinstance(err, ValueError) and str(err).isidentifier() else "ungueltig"
            return self.json_message(code, HTTPStatus.BAD_REQUEST)
        z.geaendert()
        return self.json(antwort or {"ok": True})

    async def _ausfuehren(self, z: Zentrale, hass: HomeAssistant, aktion: str, daten: dict[str, Any]) -> dict[str, Any] | None:
        # --- ohne Wort ---
        if aktion == "wort_neu":
            cfg = {k: v for k, v in (daten.get("einstellungen") or {}).items() if k in STANDARD_WORT}
            wort = await z.wort_neu(cfg)
            return {"id": wort.id}
        if aktion == "jetzt_holen":
            await z.jetzt_holen()
            return None
        if aktion == "einstellungen":
            await z.einstellungen_setzen(daten.get("einstellungen") or {})
            return None
        if aktion == "schluessel_neu":
            z.daten["schluessel"] = secrets.token_urlsafe(24)
            await hass.async_add_executor_job(z.speichern)
            return None
        if aktion == "trainer":
            tid = str(daten["trainer"])
            if tid not in z.trainer:
                raise ValueError("trainer_unbekannt")
            if "taste" in daten:
                taste = str(daten.get("taste") or "")
                if taste and not taste.startswith("button."):
                    raise ValueError("ungueltig")
                await z.neustart_taste_setzen(tid, taste)
            elif daten.get("neustarten"):
                await z.trainer_neustarten(tid)
            else:
                await z.trainer_einstellen(tid, pause=bool(daten.get("pause")), vergessen=bool(daten.get("vergessen")))
            return None
        if aktion == "reihe":
            reihe = [w for w in daten.get("reihe") or [] if w in z.woerter]
            z.daten["reihe"] = reihe + [w for w in z.reihe() if w not in reihe]
            await hass.async_add_executor_job(z.speichern)
            return None
        # --- mit Wort ---
        wort = _wort(z, daten.get("wort"))
        if aktion == "wort_aendern":
            await z.wort_aendern(wort.id, daten.get("einstellungen") or {})
        elif aktion == "wort_loeschen":
            await z.wort_loeschen(wort.id, bool(daten.get("dateien")))
        elif aktion == "training_starten":
            z.auftrag(wort.id, "von_hand")
        elif aktion == "vergleich_starten":
            z.vergleich_starten(wort, int(daten["a"]), int(daten["b"]))
        elif aktion == "training_abbrechen":
            z.abbrechen(wort.id)
        elif aktion == "einspielen":
            await z.einspielen(wort, int(daten["nr"]))
        elif aktion == "auswaehlen":
            return {"gesetzt": await z.auswaehlen(wort)}
        elif aktion == "schwelle":
            if daten.get("hand"):
                return {"gesetzt": await z.schwelle_von_hand(wort, float(daten["wert"]))}
            return {"gesetzt": await z.schwelle_setzen(wort, float(daten["wert"]))}
        elif aktion == "schnitt":
            von, bis = daten.get("von"), daten.get("bis")
            await hass.async_add_executor_job(
                wort.speicher.schnitt_setzen, sichere_id(str(daten["id"])),
                None if von is None else float(von), None if bis is None else float(bis))
        elif aktion in ("anderes_wort", "anderes_wort_zurueck"):
            ziel = _wort(z, daten.get("ziel"))
            aid = sichere_id(str(daten["id"]))
            if aktion == "anderes_wort":
                await hass.async_add_executor_job(
                    wort.speicher.an_wort_geben, aid, ziel.speicher, {"id": wort.id, "wort": wort.wort},
                    {"id": ziel.id, "wort": ziel.wort}, daten.get("person"))
            else:
                await hass.async_add_executor_job(wort.speicher.zurueckholen, aid, ziel.speicher)
            z.erinnern()
            return {"ziel": ziel.id, "stand": wort.speicher.stand}
        elif aktion == "vorschlaege_uebernehmen":
            offen = [a for a in wort.speicher.offen() if a.get("vorschlag")]
            if daten.get("ids"):
                gewollt = set(daten["ids"])
                offen = [a for a in offen if a["id"] in gewollt]
            for urteil in (WORT, KEIN_WORT):
                ids = [a["id"] for a in offen if a["vorschlag"] == urteil]
                if ids:
                    await hass.async_add_executor_job(wort.speicher.urteilen, ids, urteil, daten.get("person"))
            z.erinnern()
        else:
            raise ValueError("unbekannte_aktion")
        return None


# --- Trainer ------------------------------------------------------------


def _kennung(request: web.Request) -> str:
    """Id the trainer sends (since 1.0.31); older trainers send none and share one."""
    wert = request.headers.get("X-Sprachmodell-Trainer", "")
    return wert if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", wert) else TRAINER_OHNE_ID


class _TrainerAnsicht(HomeAssistantView):
    requires_auth = False

    def _pruefen(self, request: web.Request) -> Zentrale:
        z = _zentrale(request)
        geschickt = request.headers.get("X-Sprachmodell-Schluessel", "")
        mit_schluessel = bool(geschickt) and hmac.compare_digest(geschickt.encode(), z.schluessel.encode())
        benutzer = request.get(KEY_HASS_USER)
        mit_ha = bool(request.get(KEY_AUTHENTICATED)) and benutzer is not None and benutzer.is_admin
        if not (mit_schluessel or mit_ha):
            raise _fehler(web.HTTPUnauthorized, "falscher_schluessel")
        z.trainer_sehen(_kennung(request))
        return z


def _auftrag(z: Zentrale, wort: Wort) -> dict[str, Any]:
    """What a trainer needs for one run of a word."""
    return {
        **(wort.speicher.daten["auftrag"] or {}),
        "wort_id": wort.id,
        "wort": wort.wort,
        "sprache": wort.sprache,
        "modell_id": wort.modell_id,
        "anzeige": wort.anzeige,
        "aktiv": wort.speicher.daten["aktiv"],
        "kandidaten": 3 if wort.cfg.get("gruendlich") else 1,
        "mitteln": bool(wort.cfg.get("gruendlich") and wort.cfg.get("mitteln")),
        "geraet": z.opt("geraet"),
        "raeume": z.raeume.fuer_training(list(wort.geraete)) if wort.cfg.get("raumklang", True) else [],
    }


class TrainerAuftrag(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/auftrag"
    name = "api:sprachmodell:trainer:auftrag"

    async def get(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        tid = _kennung(request)
        frei = request.query.get("frei") != "0"
        z.trainer_sehen(tid, frei)
        abbrechen = z.abbruch_fuer(tid)
        wort = z.naechster_auftrag(tid) if frei else None
        auftrag = None
        # an older trainer would train instead of comparing: a comparison waits for a newer one
        if wort is not None and (not (wort.speicher.daten["auftrag"] or {}).get("vergleich") or z.kann_vergleichen(tid)):
            auftrag = _auftrag(z, wort)
        vorpruefen = []
        # nothing to train: the trainer may listen to new recordings meanwhile (only one trainer, the one that would
        # get the next run, so two never listen to the same recordings)
        if auftrag is None and frei and not z.laeuft_bei(tid) and z.ziel_trainer() == tid:
            for w in z.woerter.values():
                if w.cfg.get("vorpruefen") and (ids := w.speicher.zum_hoeren(VORPRUEFEN_JE_MAL)):
                    vorpruefen.append({"wort_id": w.id, "wort": w.wort, "sprache": w.sprache, "ids": ids})
        return self.json({
            "auftrag": auftrag,
            "vorpruefen": vorpruefen,
            "aktualisieren": z.aktualisieren_fuer(tid) if frei and auftrag is None else None,
            "abbrechen": abbrechen,
            "woerter": [{"id": w.id, "wort": w.wort, "sprache": w.sprache} for w in z.woerter.values()],
        })


class TrainerListe(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/liste"
    name = "api:sprachmodell:trainer:liste"

    async def get(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        return self.json({"aufnahmen": _wort(z, request.query.get("wort")).speicher.trainer_liste()})


class TrainerAudio(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/audio/{wid}/{aid}"
    name = "api:sprachmodell:trainer:audio"

    async def get(self, request: web.Request, wid: str, aid: str) -> web.StreamResponse:
        return _wav(_wort(self._pruefen(request), wid), aid)


class TrainerRaum(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/raum/{knoten}/{rid}"
    name = "api:sprachmodell:trainer:raum"

    async def get(self, request: web.Request, knoten: str, rid: str) -> web.StreamResponse:
        return _raum_wav(self._pruefen(request), knoten, rid)


class TrainerModell(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/modell"
    name = "api:sprachmodell:trainer:modell"

    async def get(self, request: web.Request) -> web.StreamResponse:
        z = self._pruefen(request)
        wort = _wort(z, request.query.get("wort"))
        nr = request.query.get("nr") or wort.speicher.daten["aktiv"]
        if not nr:
            raise _fehler(web.HTTPNotFound, "modell_nicht_gefunden")
        pfad = wort.speicher.modell_datei(int(nr))
        if not os.path.isfile(pfad):
            raise _fehler(web.HTTPNotFound, "modell_nicht_gefunden")
        return web.FileResponse(pfad, headers={"Content-Type": "application/octet-stream", "X-Version": str(nr)})


class TrainerStatus(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/status"
    name = "api:sprachmodell:trainer:status"

    async def post(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        z.trainer_meldet(await _json(request), _kennung(request))
        return self.json({"ok": True})


class TrainerErgebnis(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/ergebnis"
    name = "api:sprachmodell:trainer:ergebnis"

    async def post(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        wort = _wort(z, request.query.get("wort"))
        modell, bericht = b"", {}
        async for teil in await request.multipart():
            if not isinstance(teil, BodyPartReader):
                continue
            if teil.name == "modell":
                modell = await teil.read()
                if len(modell) > GROESSTES_MODELL:
                    return self.json_message("modell_zu_gross", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            elif teil.name == "bericht":
                try:
                    bericht = json.loads(await teil.text())
                except ValueError:
                    bericht = {}
        if b"TFL3" not in modell[:16]:
            return self.json_message("kein_tflite", HTTPStatus.BAD_REQUEST)
        eintrag = await z.ergebnis(wort, modell, bericht if isinstance(bericht, dict) else {}, _kennung(request))
        return self.json({"version": eintrag["nr"], "status": eintrag["status"]})


class TrainerVergleich(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/vergleich"
    name = "api:sprachmodell:trainer:vergleich"

    async def post(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        daten = await _json(request)
        wort = _wort(z, daten.get("wort_id"))
        bericht = daten.get("bericht")
        if not isinstance(bericht, dict) or "a" not in bericht or "b" not in bericht:
            return self.json_message("ungueltig", HTTPStatus.BAD_REQUEST)
        await z.vergleich_ergebnis(wort, bericht)
        return self.json({"ok": True})


class TrainerGehoert(_TrainerAnsicht):
    url = "/api/sprachmodell/trainer/gehoert"
    name = "api:sprachmodell:trainer:gehoert"

    async def post(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        daten = await _json(request)
        wort = _wort(z, daten.get("wort_id"))
        ergebnisse = daten.get("ergebnisse")
        if not isinstance(ergebnisse, dict):
            return self.json_message("ungueltig", HTTPStatus.BAD_REQUEST)
        hass = request.app[KEY_HASS]
        n = await hass.async_add_executor_job(
            wort.speicher.gehoert_setzen, {str(k): str(v) for k, v in ergebnisse.items()}, wort.wort,
            bool(wort.cfg.get("vorpruefen")))
        z.geaendert()
        z.erinnern()
        return self.json({"bestaetigt": n})


GROESSTER_CLIP = 2 * 1024 * 1024


class _GeraetAnsicht(HomeAssistantView):
    """Receiver for devices that send their clips themselves. The device is given a base address and adds
    /api/clips and /api/clips/ping to it (TECHO firmware), so the base is http://<home assistant>/api/wake_word_studio
    (or the older /api/sprachmodell, named after the domain); the shorter /api/sprachmodell/clips works as well. Errors answer {"ok": false, "error": ...}: the device shows
    the text."""

    requires_auth = False

    @staticmethod
    def _antwort(code: str, status: HTTPStatus) -> web.Response:
        return web.json_response({"ok": False, "error": code, "message": code}, status=status)

    def _pruefen(self, request: web.Request) -> Zentrale:
        z = _zentrale(request)
        art, _, schluessel = request.headers.get("Authorization", "").partition(" ")
        if art.lower() != "bearer" or not schluessel or not hmac.compare_digest(schluessel.encode(), z.schluessel.encode()):
            # 403, not 401: a device with an old key must not get Home Assistant to ban its address
            raise web.HTTPForbidden(text=json.dumps({"ok": False, "error": "falscher_schluessel",
                                                     "message": "falscher_schluessel"}),
                                    content_type="application/json")
        return z


class ClipsPing(_GeraetAnsicht):
    url = "/api/sprachmodell/clips/ping"
    extra_urls = ["/api/wake_word_studio/api/clips/ping", "/api/sprachmodell/api/clips/ping"]  # noqa: RUF012 - as in HomeAssistantView
    name = "api:sprachmodell:clips:ping"

    async def get(self, request: web.Request) -> web.Response:
        self._pruefen(request)
        return self.json({"ok": True})


class ClipsAnsicht(_GeraetAnsicht):
    url = "/api/sprachmodell/clips"
    extra_urls = ["/api/wake_word_studio/api/clips", "/api/sprachmodell/api/clips"]  # noqa: RUF012 - as in HomeAssistantView
    name = "api:sprachmodell:clips"

    async def post(self, request: web.Request) -> web.Response:
        z = self._pruefen(request)
        try:
            felder, audio = await _multipart(request, GROESSTER_CLIP, "audio")
        except web.HTTPRequestEntityTooLarge:
            return self._antwort("audio_zu_gross", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            meta = json.loads(felder.get("meta") or "")
        except ValueError:
            return self._antwort("meta_kein_json", HTTPStatus.BAD_REQUEST)
        if not isinstance(meta, dict) or not audio:
            return self._antwort("meta_unvollstaendig" if audio else "keine_datei", HTTPStatus.BAD_REQUEST)
        try:
            ergebnis = await z.sammler.annehmen(meta, audio)
        except ValueError as err:
            return self._antwort(str(err), HTTPStatus.BAD_REQUEST)
        return self.json({"ok": True, "stored": ergebnis, **({"duplicate": True} if ergebnis == "doppelt" else {})})


@callback
def ansichten_anmelden(hass: HomeAssistant) -> None:
    if hass.data.get(_ANGEMELDET):
        return
    hass.data[_ANGEMELDET] = True
    for ansicht in (
        DatenAnsicht, ListeAnsicht, AudioAnsicht, UrteilAnsicht, HochladenAnsicht, AufnahmeAnsicht,
        AktionAnsicht, RaumAnsicht, RaumAudio, TrainerAuftrag, TrainerListe, TrainerAudio, TrainerRaum, TrainerModell,
        TrainerStatus,
        TrainerErgebnis, TrainerGehoert, TrainerVergleich, ClipsAnsicht, ClipsPing,
    ):
        hass.http.register_view(ansicht())
