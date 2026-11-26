"""Check what the panel and the trainer send before anything is stored.

Settings are stored and later shown in the browser, used for timers and for cleaning up recordings, so every value
is checked against its type and range first; a request with one wrong value changes nothing.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .const import SPRACHEN, STANDARD_WORT, STANDARD_ZENTRALE

UHRZEIT = re.compile(r"([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?")
FARBE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
KENNUNG = re.compile(r"[A-Za-z0-9_-]{1,40}")
TASTE = re.compile(r"button\.[a-z0-9_]{1,200}")
KNOTEN = re.compile(r"[A-Za-z0-9_.-]{1,120}")
STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f]")

# whole numbers of the hub settings: smallest and largest value, as the panel's fields show them
GANZE = {"nachts_min_neu": (1, 500), "erinnerung_tage": (0, 60), "unbewertet_tage": (7, 365)}
GERAETE = ("auto", "cpu")
PERSONEN_MAX = 30
SCHALTER_WORT = tuple(k for k, v in STANDARD_WORT.items() if isinstance(v, bool))


class Ungueltig(ValueError):
    """A value is not allowed; the text is a code the panel translates."""

    def __init__(self) -> None:
        super().__init__("einstellung_ungueltig")


def _ganz(wert: Any, von: int, bis: int) -> int:
    if isinstance(wert, bool) or not isinstance(wert, int | float) or not math.isfinite(wert) or wert != int(wert):
        raise Ungueltig
    zahl = int(wert)
    if not von <= zahl <= bis:
        raise Ungueltig
    return zahl


def _text(wert: Any, laenge: int, leer: bool = True) -> str:
    if not isinstance(wert, str):
        raise Ungueltig
    text = wert.strip()
    if len(text) > laenge or STEUERZEICHEN.search(text) or (not text and not leer):
        raise Ungueltig
    return text


def _schalter(wert: Any) -> bool:
    if not isinstance(wert, bool):
        raise Ungueltig
    return wert


def _taste(wert: Any) -> str:
    text = _text(wert, 210)
    if text and not TASTE.fullmatch(text):
        raise Ungueltig
    return text


def uhrzeit(wert: Any) -> str:
    """HH:MM (a browser may add seconds); anything else is refused."""
    treffer = UHRZEIT.fullmatch(wert) if isinstance(wert, str) else None
    if not treffer:
        raise Ungueltig
    return f"{treffer.group(1)}:{treffer.group(2)}"


def farbe(wert: Any) -> str:
    """A hex colour like #03a9f4, or empty for the default."""
    if wert in ("", None):
        return ""
    if not isinstance(wert, str) or not FARBE.fullmatch(wert):
        raise Ungueltig
    kurz = wert.lower()
    return kurz if len(kurz) == 7 else "#" + "".join(z * 2 for z in kurz[1:])


def zentrale(neu: dict[str, Any]) -> dict[str, Any]:
    """Hub settings of a request: only known keys, each checked. Raises before anything is stored."""
    if not isinstance(neu, dict):
        raise Ungueltig
    aus: dict[str, Any] = {}
    for k, v in neu.items():
        if k not in STANDARD_ZENTRALE:
            continue
        if k == "uhrzeit":
            aus[k] = uhrzeit(v)
        elif k in GANZE:
            aus[k] = _ganz(v, *GANZE[k])
        elif k == "personen":
            if not isinstance(v, list) or len(v) > PERSONEN_MAX:
                raise Ungueltig
            namen = [_text(x, 40, leer=False) for x in v]
            aus[k] = list(dict.fromkeys(namen))
        elif k == "trainer_neustart":
            aus[k] = _taste(v)
        elif k == "neustart_tasten":
            if not isinstance(v, dict) or len(v) > 50:
                raise Ungueltig
            for tid in v:
                if not isinstance(tid, str) or not KENNUNG.fullmatch(tid):
                    raise Ungueltig
            aus[k] = {tid: _taste(taste) for tid, taste in v.items()}
        elif k == "alle_plaetze":
            aus[k] = _schalter(v)
        elif k == "geraet":
            if v not in GERAETE:
                raise Ungueltig
            aus[k] = v
        elif k == "trainer_wahl":
            if not isinstance(v, str) or not KENNUNG.fullmatch(v):
                raise Ungueltig
            aus[k] = v
    return aus


def wort(neu: dict[str, Any]) -> dict[str, Any]:
    """Settings of a word from a request: only known keys, each checked."""
    if not isinstance(neu, dict):
        raise Ungueltig
    aus: dict[str, Any] = {}
    for k, v in neu.items():
        if k not in STANDARD_WORT:
            continue
        if k == "wort":
            aus[k] = _text(v, 60)  # empty is answered with its own message by the caller
        elif k == "anzeige":
            aus[k] = _text(v, 80)
        elif k == "modell_id":
            aus[k] = _text(v, 80)
        elif k == "sprache":
            if v not in SPRACHEN:
                raise Ungueltig
            aus[k] = v
        elif k == "geraete":
            if not isinstance(v, dict) or len(v) > 200:
                raise Ungueltig
            for knoten, platz in v.items():
                if not isinstance(knoten, str) or not KNOTEN.fullmatch(knoten) or platz not in ("1", "2"):
                    raise Ungueltig
            aus[k] = dict(v)
        elif k == "farbe":
            aus[k] = farbe(v)
        elif k in SCHALTER_WORT:
            aus[k] = _schalter(v)
    return aus


def gespeichert_zentrale(alt: Any) -> dict[str, Any]:
    """Stored hub settings when Home Assistant starts: a value an older version let through falls back to the
    default instead of stopping the integration."""
    aus: dict[str, Any] = {}
    for k, v in (alt.items() if isinstance(alt, dict) else ()):
        try:
            aus.update(zentrale({k: v}))
        except ValueError:
            # lists are kept entry by entry, so one odd entry does not cost the people or the restart buttons
            if k == "personen" and isinstance(v, list):
                namen = [STEUERZEICHEN.sub("", x).strip()[:40] for x in v if isinstance(x, str)]
                aus[k] = list(dict.fromkeys(n for n in namen if n))[:PERSONEN_MAX]
            elif k == "neustart_tasten" and isinstance(v, dict):
                aus[k] = {
                    tid: taste for tid, taste in v.items()
                    if isinstance(tid, str) and KENNUNG.fullmatch(tid) and isinstance(taste, str) and TASTE.fullmatch(taste)
                }
    return aus


def gespeichert_wort(alt: Any) -> dict[str, Any]:
    """Stored settings of a word at start. Colour, switches and devices that do not pass fall back to the default;
    texts stay as they are (they are escaped wherever they are shown), so no word loses its name."""
    aus: dict[str, Any] = {}
    for k, v in (alt.items() if isinstance(alt, dict) else ()):
        if k not in STANDARD_WORT:
            continue
        try:
            aus.update(wort({k: v}))
        except ValueError:
            if isinstance(STANDARD_WORT[k], str) and k != "farbe" and isinstance(v, str):
                aus[k] = STEUERZEICHEN.sub("", v)
    return aus


# --- what a trainer sends ---------------------------------------------------

PHASE = re.compile(r"[a-z_]{1,24}")


def sauber(wert: Any, tiefe: int = 8, text: int = 500, liste: int = 5000) -> Any:
    """A JSON value from a trainer, limited: numbers and switches as they are, texts cut, containers not deeper
    or longer than the reports need, keys short texts. Everything else becomes None."""
    if wert is None or isinstance(wert, bool | int):
        return wert
    if isinstance(wert, float):
        return wert if wert == wert and wert not in (float("inf"), float("-inf")) else None
    if isinstance(wert, str):
        return STEUERZEICHEN.sub(" ", wert[:text])
    if tiefe <= 0:
        return None
    if isinstance(wert, list):
        return [sauber(x, tiefe - 1, text, liste) for x in wert[:liste]]
    if isinstance(wert, dict):
        return {str(k)[:80]: sauber(v, tiefe - 1, text, liste) for k, v in list(wert.items())[:liste]}
    return None


def _zahl(wert: Any, von: float, bis: float) -> float | None:
    if isinstance(wert, bool) or not isinstance(wert, int | float) or wert != wert:
        return None
    return max(von, min(bis, wert))


def status(roh: Any) -> dict[str, Any]:
    """The status a trainer posts: only the keys the studio knows, each with its type. Unknown keys are dropped,
    so nothing a trainer sends reaches the stored state or the browser unchecked."""
    if not isinstance(roh, dict):
        return {}
    aus: dict[str, Any] = {}
    if isinstance(roh.get("info"), dict):
        aus["info"] = sauber(roh["info"], tiefe=4, text=300, liste=64)
    if roh.get("neustart") is True:
        aus["neustart"] = True
    if isinstance(roh.get("wort_id"), str):
        aus["wort_id"] = roh["wort_id"][:80]
    if isinstance(roh.get("live"), dict):
        aus["live"] = roh["live"]  # checked on its own (zentrale._live_pruefen)
    if isinstance(roh.get("phase"), str) and PHASE.fullmatch(roh["phase"]):
        aus["phase"] = roh["phase"]
    if "prozent" in roh:
        aus["prozent"] = _zahl(roh["prozent"], 0, 100)
    for k in ("schritt", "hinweis"):
        if isinstance(roh.get(k), str):
            aus[k] = STEUERZEICHEN.sub(" ", roh[k][:300])
    if (rest := _zahl(roh.get("restzeit_min"), 0, 100000)) is not None:
        aus["restzeit_min"] = round(rest)
    return aus
