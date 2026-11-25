"""Is the new version really better than the one on the devices?

Both versions are tested on exactly the same audio in the same run. Instead of two numbers at one point the
comparison looks at the whole picture: everyday hit rate at the same number of false wakes (the usual way to
compare wake words), a hard test far beyond daily life (so two versions that both hear everything at home can still
be told apart), every listening condition, false wakes in speech, in music/noise and in a quiet room, similar-sounding words
and the weakest person. Small test sets make small differences look big, so a difference only counts when it is
larger than chance; otherwise both are "as good" and the version on the devices stays.

Pure Python on purpose (no numpy): Home Assistant's tests and the trainer share it.
"""

from __future__ import annotations

import math
from typing import Any

# false wakes per hour of speech at which the everyday hit rates are compared
FA_PUNKTE = (0.5, 1.0, 2.0)
MIN_SCHWELLE = 0.8  # lower thresholds are too risky in unknown rooms (as when choosing the threshold)
BEDINGUNGEN = ("ruhig", "leise", "hall", "musik", "gerede")
SCHWER_LAGEN = 4  # conditions of the hard test (far away, loud TV, loud music, everything at once)
# wake-ups allowed in the quiet-room test (20 minutes of faint hiss, hum, far-away sounds): a threshold with more
# does not count, however well it hears (seen 20.11.: a version woke every few seconds in a quiet kitchen)
STILLE_ERLAUBT = 1


def ruhig_genug(v: dict[str, Any]) -> bool:
    """The version stays quiet in a quiet room at this threshold (tests before 1.0.38 have no such test: True)."""
    n = v.get("fehlausloeser_stille_anzahl")
    return n is None or n <= STILLE_ERLAUBT


def _je(je: dict[str, Any]) -> list[tuple[float, dict[str, Any]]]:
    return sorted(((float(k), v) for k, v in je.items()), key=lambda kv: kv[0])


def alltag_bei(je: dict[str, Any], fa_max: float, stunden: float | None = None,
               feld: str = "trefferquote_alltag") -> float | None:
    """Best everyday hit rate (or, with feld="trefferquote_schwer", hard-test hit rate) of a version while it stays
    at about fa_max false wakes per hour of speech.

    With the hours of speech the limit allows for chance (Poisson: a few hours hold only a handful of false
    wakes, 2 or 4 is often luck). Thresholds that wake in a quiet room do not count. None if the version never
    gets that quiet, or was tested before everyday conditions existed - then the false-wake rows decide."""
    punkte = [(c, v) for c, v in _je(je) if c >= MIN_SCHWELLE and v.get(feld) is not None and ruhig_genug(v)]
    if not punkte:
        return None
    if stunden:
        erlaubt = fa_max * stunden + 2 * math.sqrt(max(1.0, fa_max * stunden))
        werte = [v[feld] for _, v in punkte
                 if v.get("fehlausloeser_anzahl") is not None and v["fehlausloeser_anzahl"] <= erlaubt]
    else:
        werte = [v[feld] for _, v in punkte
                 if v.get("fehlausloeser_pro_stunde") is not None and v["fehlausloeser_pro_stunde"] <= fa_max]
    return max(werte) if werte else None


def _quote_unterschied(neu: float | None, alt: float | None, n: int) -> str:
    """Two hit rates measured on n clips each: different only if at least 2 clips and beyond 2 standard errors."""
    if neu is None or alt is None or n <= 0:
        return "gleich"
    d = neu - alt
    if abs(d) * n < 1.999:
        return "gleich"
    p = (neu + alt) / 2
    se = math.sqrt(max(p * (1 - p), 0.25 / n) * 2 / n)
    if abs(d) <= 2 * se:
        return "gleich"
    return "besser" if d > 0 else "schlechter"


def _anzahl_unterschied(neu: int | None, alt: int | None, kleiner_besser: bool = True) -> str:
    """Two counts of rare events (false wakes) over the same material: Poisson, at least 2 apart."""
    if neu is None or alt is None:
        return "gleich"
    d = neu - alt
    if abs(d) < 2 or abs(d) <= 2 * math.sqrt(neu + alt):
        return "gleich"
    weniger = d < 0
    return "besser" if weniger == kleiner_besser else "schlechter"


def vergleichen(neu: dict[str, Any], alt: dict[str, Any], cut_neu: float, cut_alt: float) -> dict[str, Any]:
    """neu/alt: test results (je_schwelle, positiv, negativ, stunden). cut_*: threshold each version would run at.

    Returns rows (kennzahl, neu, alt, urteil besser/schlechter/gleich, wichtig) and the overall verdict:
    better only if at least one important row is really better and none is really worse."""
    jn, ja = neu["je_schwelle"], alt["je_schwelle"]
    pn, pa = jn[str(cut_neu)], ja[str(cut_alt)]
    n_pos = int(neu.get("positiv") or 0)
    n_alltag = n_pos * (len(BEDINGUNGEN) + 1)
    zeilen: list[dict[str, Any]] = []

    def zeile(kennzahl: str, wn: Any, wa: Any, urteil: str, wichtig: bool, **mehr: Any) -> None:
        zeilen.append({"kennzahl": kennzahl, "neu": wn, "alt": wa, "urteil": urteil, "wichtig": wichtig, **mehr})

    for fa in FA_PUNKTE:
        wn, wa = alltag_bei(jn, fa, neu.get("stunden")), alltag_bei(ja, fa, alt.get("stunden"))
        zeile("alltag_bei_fa", wn, wa, _quote_unterschied(wn, wa, n_alltag), True, fa=fa)
    # hard test at about one false wake per hour: tells two versions apart that both hear everything in daily life
    wn = alltag_bei(jn, 1.0, neu.get("stunden"), "trefferquote_schwer")
    wa = alltag_bei(ja, 1.0, alt.get("stunden"), "trefferquote_schwer")
    if wn is not None or wa is not None:
        zeile("schwer_bei_fa", wn, wa, _quote_unterschied(wn, wa, n_pos * SCHWER_LAGEN), True, fa=1.0)
    zeile("fehlausloeser_rede", pn.get("fehlausloeser_pro_stunde"), pa.get("fehlausloeser_pro_stunde"),
          _anzahl_unterschied(pn.get("fehlausloeser_anzahl"), pa.get("fehlausloeser_anzahl")), True)
    if pn.get("fehlausloeser_geraeusch_pro_stunde") is not None:
        zeile("fehlausloeser_geraeusch", pn.get("fehlausloeser_geraeusch_pro_stunde"),
              pa.get("fehlausloeser_geraeusch_pro_stunde"),
              _anzahl_unterschied(pn.get("fehlausloeser_geraeusch_anzahl"), pa.get("fehlausloeser_geraeusch_anzahl")),
              True)
    if pn.get("fehlausloeser_stille_anzahl") is not None and pa.get("fehlausloeser_stille_anzahl") is not None:
        n_st, a_st = pn["fehlausloeser_stille_anzahl"], pa["fehlausloeser_stille_anzahl"]
        u = _anzahl_unterschied(n_st, a_st)
        if n_st > STILLE_ERLAUBT and n_st > a_st:
            u = "schlechter"  # waking in a quiet room is never chance
        zeile("fehlausloeser_stille", pn.get("fehlausloeser_stille_pro_stunde"),
              pa.get("fehlausloeser_stille_pro_stunde"), u, True)
    for b in BEDINGUNGEN:
        wn, wa = (pn.get("bedingungen") or {}).get(b), (pa.get("bedingungen") or {}).get(b)
        if wn is None and b == "ruhig":
            wn, wa = pn.get("trefferquote"), pa.get("trefferquote")
        if wn is not None or wa is not None:
            zeile("erkannt_" + b, wn, wa, _quote_unterschied(wn, wa, n_pos), False)
    if pn.get("gegenbeispiele") is not None:
        n_neg = int(neu.get("negativ") or 0)
        # fewer similar words that wake the device is better, so the hit-rate test runs the other way round
        u = _quote_unterschied(pa.get("gegenbeispiele"), pn.get("gegenbeispiele"), n_neg)
        # your own "not said" recordings (held out) count for the verdict: they are what wakes the devices at home
        zeile("aehnliche_woerter", pn.get("gegenbeispiele"), pa.get("gegenbeispiele"), u, True)
    if pn.get("echte_fehlausloeser") is not None and pa.get("echte_fehlausloeser") is not None:
        n_f = int(neu.get("fehl_negativ") or 0)
        u = _quote_unterschied(pa.get("echte_fehlausloeser"), pn.get("echte_fehlausloeser"), n_f)
        zeile("echte_fehlausloeser", pn.get("echte_fehlausloeser"), pa.get("echte_fehlausloeser"), u, True)
    schwach_n = _schwaechste(pn.get("je_person") or {})
    schwach_a = _schwaechste(pa.get("je_person") or {})
    if schwach_n and schwach_a:
        zeile("schwaechste_person", schwach_n[1], schwach_a[1],
              _quote_unterschied(schwach_n[1], schwach_a[1], min(schwach_n[2], schwach_a[2])), False,
              person=schwach_n[0])

    wichtig = [z for z in zeilen if z["wichtig"]]
    schlechter = [z["kennzahl"] for z in wichtig if z["urteil"] == "schlechter"]
    besser_in = [z["kennzahl"] for z in wichtig if z["urteil"] == "besser"]
    if schlechter:
        urteil, grund = "schlechter", "schlechter_in"
    elif besser_in:
        urteil, grund = "besser", "besser_in"
    else:
        urteil, grund = "gleich", "gleich"
    return {"urteil": urteil, "grund": grund, "besser_in": besser_in, "schlechter_in": schlechter,
            "zeilen": zeilen, "testaufnahmen": n_pos, "stunden_rede": neu.get("stunden"),
            "stunden_geraeusch": neu.get("stunden_geraeusch")}


def _schwaechste(je_person: dict[str, Any]) -> tuple[str, float, int] | None:
    """The person the version hears worst (only people with at least 3 test recordings)."""
    kandidaten = [(name, float(v["trefferquote"]), int(v["anzahl"])) for name, v in je_person.items()
                  if isinstance(v, dict) and int(v.get("anzahl") or 0) >= 3 and v.get("trefferquote") is not None]
    return min(kandidaten, key=lambda k: k[1]) if kandidaten else None


def kandidat_wahl(werte: list[dict[str, Any]]) -> int:
    """Index of the candidate a thorough run keeps. werte: per candidate alltag and schwer (hit rates at about one
    false wake per hour), aehnlich (share of similar words that wake it), fehlausloeser_min, rezept.

    Best everyday hit rate first; a tie goes to the hard test, then to fewer similar words that wake it, then to
    fewer false wakes. The averaged model needs several times the device memory, so it only wins when it is
    really ahead; on a full tie a single candidate stays."""
    def schluessel(i: int) -> tuple[float, float, float, float, int]:
        w = werte[i]
        return (w.get("alltag") or 0.0, w.get("schwer") or 0.0, -(w.get("aehnlich") or 0.0),
                -float(w.get("fehlausloeser_min") or 0), 0 if w.get("rezept") == "gemittelt" else 1)

    return max(range(len(werte)), key=schluessel)
