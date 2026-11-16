"""Self-test of the trainer image: one tiny run through every step that needs the installed libraries.

Synthetic audio -> features (worker pool, augmentation) -> microWakeWord training with evaluation and
TFLite conversion -> test of the model. Runs in CI on every image before it is published:
    python -m trainer.selbsttest
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from .lauf import Lauf

RATE = 16000


class _HA:
    """Stands in for Home Assistant."""

    def status(self, daten: dict) -> None:
        pass


def _wav(pfad: Path, x: np.ndarray) -> str:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    sf.write(pfad, np.clip(x, -1, 1), RATE, subtype="PCM_16")
    return str(pfad)


def _ton(rnd: np.random.Generator, sek: float, hoch: bool) -> np.ndarray:
    t = np.arange(int(RATE * sek)) / RATE
    f0 = rnd.uniform(500, 900) if hoch else rnd.uniform(150, 300)
    x = 0.4 * np.sin(2 * np.pi * (f0 + 300 * t) * t) * np.hanning(len(t))
    pause = np.zeros(RATE // 4)
    return np.concatenate([pause, x + rnd.normal(0, 0.01, len(t)), pause])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    t0 = time.time()
    rnd = np.random.default_rng(1)
    with tempfile.TemporaryDirectory() as tmp:
        o = Path(tmp)
        bg = [_wav(o / "bg" / f"{i}.wav", rnd.normal(0, 0.05, RATE * 5)) for i in range(3)]
        rir = _wav(o / "rir" / "r.wav", np.concatenate([[1.0], rnd.normal(0, 0.05, 800) * np.exp(-np.arange(800) / 150)]))
        pos = [_wav(o / "pos" / f"{i}.wav", _ton(rnd, 0.8, True)) for i in range(24)]
        neg = [_wav(o / "neg" / f"{i}.wav", _ton(rnd, 0.8, False)) for i in range(24)]
        lang = [_wav(o / "lang" / f"{i}.wav", rnd.normal(0, 0.05, RATE * 30)) for i in range(3)]

        lauf = Lauf(_HA(), {"wort_id": "selbsttest", "wort": "Test"}, str(o / "daten"), {"schritte": 40})
        lauf.ordner.mkdir(parents=True, exist_ok=True)
        m = o / "merkmale"
        for name, dateien in (("pos", pos), ("neg", neg)):
            for teil, auswahl in (("training", dateien[:16]), ("validation", dateien[16:20]), ("testing", dateien[20:])):
                ergebnis = lauf._merkmale_werkzeug({
                    "ziel": str(m / name / teil / f"{name}_mmap"), "dateien": auswahl, "wiederholungen": 2,
                    "frames": 150, "trim": True, "bg": bg, "rir": rir, "snr_min": 5, "prozesse": 2,
                }, 0, 1, "merkmale")
                assert ergebnis.get("merkmale", 0) > 0, f"no features for {name}/{teil}: {ergebnis}"
        for teil in ("training", "validation_ambient", "testing_ambient"):
            ergebnis = lauf._merkmale_werkzeug({"ziel": str(m / "lang" / teil / "lang_mmap"), "dateien": lang,
                                                "wiederholungen": 0, "prozesse": 1}, 0, 1, "merkmale")
            assert ergebnis.get("merkmale", 0) > 0, f"no long features: {ergebnis}"
        print(f"SELBSTTEST features ok ({time.time() - t0:.0f} s)", flush=True)

        merkmale = {"pos": {"dir": str(m / "pos"), "wort": True, "gewicht": 1.0, "strafe": 1.0},
                    "neg": {"dir": str(m / "neg"), "wort": False, "gewicht": 1.0, "strafe": 1.0}}
        lang_dir = m / "lang"
        # evaluation sets are cut down to fit the memory, like in a real run
        neg = lauf._schlanke_negative({"speech": lang_dir, "dinner_party": lang_dir, "no_speech": lang_dir,
                                       "dinner_party_eval": lang_dir})
        assert (neg["speech"] / "training").is_symlink() and (neg["speech"] / "validation_ambient").is_dir()
        print(f"SELBSTTEST evaluation data ok ({time.time() - t0:.0f} s)", flush=True)
        tflite = lauf._training(merkmale, neg)
        assert tflite.exists() and tflite.stat().st_size > 1000, "no model"
        print(f"SELBSTTEST training ok ({time.time() - t0:.0f} s, model {tflite.stat().st_size} bytes)", flush=True)

        ergebnis = lauf._werkzeug_sicher("pruefen", {
            "modell": str(tflite), "positiv": [{"datei": f, "person": "A"} for f in pos[20:]], "negativ": neg[20:],
            "gerede": lang, "bg": bg, "max_stunden": 1,
        }, "test", 0, 1, "test_neu")
        assert ergebnis["positiv"] == 4 and ergebnis["je_schwelle"], f"test result incomplete: {ergebnis}"
        print(f"SELBSTTEST test ok ({time.time() - t0:.0f} s)", flush=True)
    print("SELBSTTEST OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # noqa: BLE001
        logging.exception("Self-test failed")
        print(f"SELBSTTEST FAILED: {err}", flush=True)
        sys.exit(1)
