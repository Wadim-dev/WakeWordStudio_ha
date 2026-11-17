"""How long a run would take on each trainer.

Measured: the newest run of that trainer on the same device (graphics card or processor). Estimated: a run of another
trainer, its data preparation scaled by the two trainers' preparation speed test and its training by their
training speed test (both measured by the trainers themselves at start, seconds for a fixed piece of work).
"""

from __future__ import annotations

from typing import Any

ANTEIL_TRAINING = 0.42  # share of a run spent training when an old run did not record it


def ziel_geraet(info: dict[str, Any], wunsch: str) -> str:
    """Where this trainer would compute: "gpu" if its card works and the user did not choose processor only."""
    return "gpu" if wunsch != "cpu" and (info.get("beschleuniger") or {}).get("gpu") else "cpu"


def _teile(lauf: dict[str, Any]) -> tuple[float, float] | None:
    """(preparation, training of one candidate) in minutes of a finished run."""
    dauer = lauf.get("dauer_min")
    if not isinstance(dauer, (int, float)) or dauer <= 0:
        return None
    n = max(1, int(lauf.get("kandidaten") or 1))
    training = lauf.get("training_min")
    je = training / n if isinstance(training, (int, float)) and training > 0 else dauer * ANTEIL_TRAINING / n
    vorbereiten = max(0.0, dauer - n * je)
    return vorbereiten, je


def _ergebnis(vorbereiten: float, je: float, quelle: str, geraet: str) -> dict[str, Any]:
    einfach = vorbereiten + je
    return {"einfach": round(einfach, 1), "gruendlich": round(einfach + 2 * je, 1), "quelle": quelle, "geraet": geraet}


def schaetzen(
    laeufe: list[dict[str, Any]], trainer: dict[str, dict[str, Any]], wunsch: str, alt: str | None,
) -> dict[str, dict[str, Any] | None]:
    """{trainer id: {"einfach", "gruendlich" (minutes), "quelle": "gemessen"|"geschaetzt", "geraet"} or None}.

    laeufe: runs of a word, oldest first. trainer: id -> info as the trainer reported it. alt: the trainer that
    ran the runs from before trainers had an id."""
    neueste = [lauf for lauf in reversed(laeufe) if _teile(lauf)]
    aus: dict[str, dict[str, Any] | None] = {}
    for tid, info in trainer.items():
        geraet = ziel_geraet(info, wunsch)
        eigen = next((lauf for lauf in neueste if (lauf.get("trainer") or alt) == tid
                      and (lauf.get("geraet") or "cpu") == geraet), None)
        if eigen:
            vorbereiten, je = _teile(eigen)  # type: ignore[misc]
            aus[tid] = _ergebnis(vorbereiten, je, "gemessen", geraet)
            continue
        tempo = info.get("tempo") or {}
        aus[tid] = None
        for lauf in neueste:
            von = lauf.get("trainer") or alt
            t_ref = lauf.get("tempo") or (trainer.get(von or "") or {}).get("tempo") or {}
            g_ref = lauf.get("geraet") or "cpu"
            try:
                v = tempo["vorbereiten_s"] / t_ref["vorbereiten_s"]
                r = tempo[f"rechnen_{geraet}_s"] / t_ref[f"rechnen_{g_ref}_s"]
            except (KeyError, TypeError, ZeroDivisionError):
                continue
            vorbereiten, je = _teile(lauf)  # type: ignore[misc]
            aus[tid] = _ergebnis(vorbereiten * v, je * r, "geschaetzt", geraet)
            break
    return aus
