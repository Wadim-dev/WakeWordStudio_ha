"""The trainer's comparison of a new version with the one on the devices (pure Python, shared module)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "vergleich", Path(__file__).parent.parent / "sprachmodell_trainer" / "trainer" / "vergleich.py")
assert _spec and _spec.loader
vergleich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vergleich)

SCHWELLEN = (0.8, 0.85, 0.9, 0.92, 0.95, 0.97, 0.98, 0.99)


def _ergebnis(alltag: dict[float, float], fa: dict[float, int], stunden: float = 6.0, n: int = 40,
              leise: float = 0.9, geraeusch: int = 1) -> dict:
    je = {}
    for c in SCHWELLEN:
        q = alltag[c]
        je[str(c)] = {
            "trefferquote": 1.0, "trefferquote_musik": q, "trefferquote_alltag": q,
            "bedingungen": {"ruhig": 1.0, "leise": leise, "hall": q, "musik": q, "gerede": q, "alltag": q},
            "gegenbeispiele": 0.1, "gegenbeispiele_anzahl": 18,
            "fehlausloeser_pro_stunde": fa[c] / stunden, "fehlausloeser_anzahl": fa[c],
            "fehlausloeser_geraeusch_pro_stunde": geraeusch, "fehlausloeser_geraeusch_anzahl": geraeusch,
            "je_person": {"Anna": {"trefferquote": 1.0, "anzahl": 10}},
        }
    return {"je_schwelle": je, "positiv": n, "negativ": 180, "stunden": stunden, "stunden_geraeusch": 1.0}


FA_ALT = {0.8: 40, 0.85: 30, 0.9: 20, 0.92: 14, 0.95: 10, 0.97: 6, 0.98: 4, 0.99: 2}
QUOTE = {0.8: 0.97, 0.85: 0.96, 0.9: 0.95, 0.92: 0.93, 0.95: 0.9, 0.97: 0.86, 0.98: 0.82, 0.99: 0.75}


def test_gleiches_modell_ist_gleich_gut() -> None:
    e = _ergebnis(QUOTE, FA_ALT)
    v = vergleich.vergleichen(e, e, 0.99, 0.99)
    assert v["urteil"] == "gleich" and not v["besser_in"] and not v["schlechter_in"]
    assert {z["kennzahl"] for z in v["zeilen"]} >= {"alltag_bei_fa", "fehlausloeser_rede", "fehlausloeser_geraeusch",
                                                    "erkannt_leise", "aehnliche_woerter", "schwaechste_person"}


def test_zwei_gegen_vier_fehlausloeser_ist_zufall() -> None:
    """Like v10 against v11: 2 against 4 false wakes in 3 hours is chance, not a worse model."""
    neu = _ergebnis(QUOTE, {**FA_ALT, 0.99: 4}, stunden=3)
    alt = _ergebnis(QUOTE, FA_ALT, stunden=3)
    v = vergleich.vergleichen(neu, alt, 0.99, 0.99)
    assert v["urteil"] == "gleich"


def test_hoert_im_alltag_besser_bei_gleichen_fehlausloesern() -> None:
    besser = {c: min(1.0, q + 0.08) for c, q in QUOTE.items()}
    v = vergleich.vergleichen(_ergebnis(besser, FA_ALT), _ergebnis(QUOTE, FA_ALT), 0.99, 0.99)
    assert v["urteil"] == "besser" and "alltag_bei_fa" in v["besser_in"]


def test_viel_mehr_fehlausloeser_ist_schlechter() -> None:
    mehr = {c: n * 3 + 6 for c, n in FA_ALT.items()}
    besser = {c: min(1.0, q + 0.08) for c, q in QUOTE.items()}
    v = vergleich.vergleichen(_ergebnis(besser, mehr), _ergebnis(QUOTE, FA_ALT), 0.99, 0.99)
    assert v["urteil"] == "schlechter" and "fehlausloeser_rede" in v["schlechter_in"]


def test_leise_schlechter_ist_nur_hinweis() -> None:
    v = vergleich.vergleichen(_ergebnis(QUOTE, FA_ALT, leise=0.5), _ergebnis(QUOTE, FA_ALT), 0.99, 0.99)
    zeile = next(z for z in v["zeilen"] if z["kennzahl"] == "erkannt_leise")
    assert zeile["urteil"] == "schlechter" and not zeile["wichtig"]


def test_alte_berichte_ohne_alltag() -> None:
    je = {str(c): {"trefferquote": 1.0, "fehlausloeser_pro_stunde": 1.0} for c in SCHWELLEN}
    assert vergleich.alltag_bei(je, 1.0) is None
    assert vergleich.alltag_bei(_ergebnis(QUOTE, FA_ALT)["je_schwelle"], 0.1) is None  # never that quiet
    assert vergleich.alltag_bei(_ergebnis(QUOTE, FA_ALT)["je_schwelle"], 1.0) == 0.86
    assert vergleich.alltag_bei(_ergebnis(QUOTE, FA_ALT)["je_schwelle"], 1.0, 6.0) == 0.9  # allows for chance
