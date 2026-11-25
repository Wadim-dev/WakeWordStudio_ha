"""Self-test of the trainer image: one tiny run through every step that needs the installed libraries.

Synthetic audio -> features (worker pool, augmentation) -> microWakeWord training with evaluation and
TFLite conversion -> test of the model. Runs in CI on every image before it is published:
    python -m trainer.selbsttest
"""

from __future__ import annotations

import logging
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from .grenzen import beschleuniger
from .lauf import MIXEDNET, Lauf

RATE = 16000


class _HA:
    """Stands in for Home Assistant."""

    def __init__(self) -> None:
        self.klatscher: dict[str, bytes] = {}
        self.modelle: dict[int, bytes] = {}
        self.vergleiche: list[dict] = []

    def status(self, daten: dict) -> None:
        pass

    def raum(self, knoten: str, rid: str) -> bytes | None:
        return self.klatscher.get(rid)

    def modell(self, wort: str, nr: int | None = None) -> bytes | None:
        return self.modelle.get(nr or 0)

    def vergleich(self, wort: str, bericht: dict) -> dict:
        self.vergleiche.append(bericht)
        return {"ok": True}


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
        neg_wavs = [_wav(o / "neg" / f"{i}.wav", _ton(rnd, 0.8, False)) for i in range(24)]
        lang = [_wav(o / "lang" / f"{i}.wav", rnd.normal(0, 0.05, RATE * 30)) for i in range(3)]

        lauf = Lauf(_HA(), {"wort_id": "selbsttest", "wort": "Test"}, str(o / "daten"), {"schritte": 40})
        # graphics card version: the probe must answer (with a card: gpu, without: processor), never hang
        b = beschleuniger()
        if b.get("bild") == "gpu" and not b.get("gpu") and lauf.geraet != "cpu":
            raise RuntimeError("no usable card, but the run does not use the processor")
        print(f"SELBSTTEST device {lauf.geraet} ({b})", flush=True)
        lauf.ordner.mkdir(parents=True, exist_ok=True)
        m = o / "merkmale"
        for name, dateien in (("pos", pos), ("neg", neg_wavs)):
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

        # room sound of the user's devices: fetched, mixed to about half with the general set, usable by the
        # augmentation, and the features are rebuilt when the claps change
        ha = lauf.ha
        for i in range(2):
            klatsch = np.concatenate([[0.9], rnd.normal(0, 0.2, 3000) * np.exp(-np.arange(3000) / 900)])
            sf.write(o / "k.wav", np.clip(klatsch, -1, 1), RATE, subtype="PCM_16")
            ha.klatscher[f"k{i}"] = (o / "k.wav").read_bytes()
        rir_dir = Path(rir).parent
        for i in range(5):
            _wav(rir_dir / f"r{i}.wav", np.concatenate([[1.0], rnd.normal(0, 0.05, 800) * np.exp(-np.arange(800) / 150)]))
        lauf.auftrag["raeume"] = [{"knoten": "kueche", "id": "k0"}, {"knoten": "kueche", "id": "k1"},
                                  {"knoten": "bad", "id": "weg"}]
        mix = lauf._raumklang(rir_dir)
        eigen = sorted(mix.glob("eigen_*.wav"))
        assert lauf.raum_n == 2 and len(eigen) == 6 and len(list(mix.glob("r*.wav"))) == 6, (lauf.raum_n, len(eigen))
        ergebnis = lauf._merkmale_werkzeug({
            "ziel": str(o / "raum_test" / "pos_mmap"), "dateien": pos[:4], "wiederholungen": 3, "frames": 150,
            "trim": True, "bg": bg, "rir": str(mix), "snr_min": 5, "prozesse": 1,
        }, 0, 1, "merkmale")
        assert ergebnis.get("merkmale", 0) > 0, f"no features with the room mix: {ergebnis}"
        sig = lauf.raum_sig
        lauf.auftrag["raeume"] = lauf.auftrag["raeume"][:1]
        lauf._raumklang(rir_dir)
        assert lauf.raum_sig and lauf.raum_sig != sig, "room change must rebuild the features"
        lauf.auftrag["raeume"], lauf.raum_n, lauf.raum_sig = [], 0, ""
        print("SELBSTTEST room sound ok", flush=True)

        # gentle recipe of thorough runs (third candidate): its own augmentation works, and each candidate gets
        # exactly its sets
        ergebnis = lauf._merkmale_werkzeug({
            "ziel": str(o / "sanft_test" / "pos_mmap"), "dateien": pos[:4], "wiederholungen": 2, "frames": 150,
            "trim": True, "bg": bg, "rir": rir, "prozesse": 1, "rezept": "sanft",
        }, 0, 1, "merkmale")
        assert ergebnis.get("merkmale", 0) > 0, f"no features with the gentle recipe: {ergebnis}"
        satz = {n: {"dir": n} for n in ("pos", "abgebrochen", "sanft_pos", "gerede")}
        assert set(lauf._rezept(satz, "standard")) == {"pos", "gerede"}
        assert set(lauf._rezept(satz, "abgebrochen")) == {"pos", "abgebrochen", "gerede"}
        assert lauf._rezept(satz, "sanft") == {"pos": {"dir": "sanft_pos"}, "gerede": {"dir": "gerede"}}
        print("SELBSTTEST gentle recipe ok", flush=True)

        # a quiet room as negatives: faint, never the level of a voice, and its features are built untrimmed
        import random

        from .werkzeug import ruhe

        r = random.Random(1)
        stille = []
        for i in range(12):
            x = ruhe(r, RATE * 3, bg)
            pegel = 20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) / 32768 + 1e-12)
            assert pegel < -30, f"quiet room too loud: {pegel:.0f} dBFS"
            stille.append(_wav(o / "stille" / f"{i}.wav", x.astype(np.float64) / 32768))
        ergebnis = lauf._merkmale_werkzeug({
            "ziel": str(o / "stille_test" / "stille_mmap"), "dateien": stille, "wiederholungen": 1, "frames": 150,
            "trim": False, "bg": bg, "rir": rir, "prozesse": 1,
        }, 0, 1, "merkmale")
        assert ergebnis.get("merkmale", 0) == len(stille), f"quiet-room features missing: {ergebnis}"
        print("SELBSTTEST quiet room ok", flush=True)

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
        assert (lauf.ordner / "train" / "stand").exists(), "base model without its marker"
        # the live learning curve for the studio: one point per evaluation of microWakeWord
        kurve = next(iter(lauf.live()["kurven"].values()), [])
        assert kurve and all(len(p) == 3 and 0 <= p[1] <= 100 for p in kurve), f"no learning curve: {lauf.kurven}"
        print(f"SELBSTTEST training ok ({time.time() - t0:.0f} s, model {tflite.stat().st_size} bytes)", flush=True)

        ergebnis = lauf._werkzeug_sicher("pruefen", {
            "modell": str(tflite), "positiv": [{"datei": f, "person": "A"} for f in pos[20:]], "negativ": neg_wavs[20:],
            "gerede": lang, "bg": bg, "rir": rir, "max_stunden": 1, "max_stunden_bg": 0.05, "stille_minuten": 2,
            "fehl": neg_wavs[20:23],
        }, "test", 0, 1, "test_neu")
        assert ergebnis["fehl_negativ"] == 3 and ergebnis["je_schwelle"]["0.97"]["echte_fehlausloeser"] is not None, ergebnis
        assert ergebnis["positiv"] == 4 and ergebnis["je_schwelle"], f"test result incomplete: {ergebnis}"
        punkt = ergebnis["je_schwelle"]["0.97"]
        assert set(punkt["bedingungen"]) == {"ruhig", "leise", "hall", "musik", "gerede", "alltag"}, punkt
        assert set(punkt["schwer"]) == {"weit", "laut_tv", "laut_musik", "chaos"} and punkt["trefferquote_schwer"] is not None, punkt
        assert punkt["fehlausloeser_geraeusch_pro_stunde"] is not None, punkt
        assert punkt["fehlausloeser_stille_anzahl"] is not None and ergebnis["stunden_stille"] > 0, punkt
        from .vergleich import vergleichen

        v = vergleichen(ergebnis, ergebnis, 0.97, 0.97)  # the same model against itself: as good
        assert v["urteil"] == "gleich", v
        print(f"SELBSTTEST test ok ({time.time() - t0:.0f} s)", flush=True)

        # "thorough": two candidates, compared on their own check data, the winner becomes the base model
        tts = {"test_pos": o / "pos", "test_neg": o / "neg"}
        bester, wahl = lauf._kandidaten(2, merkmale, neg, tts, [o / "bg"], {"dev": o / "lang"}, Path(rir))
        assert bester.exists() and wahl["gewaehlt"] in (1, 2) and len(wahl["werte"]) == 2, wahl
        assert wahl["grundlage"] == "kuenstlich" and wahl["teile"] == 1, wahl
        assert not (lauf.ordner / "train_1").exists() and not (lauf.ordner / "train_2").exists()
        print(f"SELBSTTEST candidates ok ({time.time() - t0:.0f} s, kept {wahl['gewaehlt']})", flush=True)

        # thorough with the new parts: cut-off words for the second candidate, the choice on half of the real
        # test recordings, and the averaged model (built, loadable, tested like the others)
        ab = m / "abgebrochen"
        for teil, auswahl in (("training", pos[:16]), ("validation", pos[16:20])):
            ergebnis = lauf._merkmale_werkzeug({
                "ziel": str(ab / teil / "abgebrochen_mmap"), "dateien": auswahl, "wiederholungen": 2, "frames": 150,
                "trim": True, "bg": bg, "rir": rir, "snr_min": 5, "prozesse": 2, "abschneiden": True,
            }, 0, 1, "merkmale")
            assert ergebnis.get("merkmale", 0) > 0, f"no cut-off features: {ergebnis}"
        merkmale["abgebrochen"] = {"dir": str(ab), "wort": False, "gewicht": 1.0, "strafe": 1.0}
        echt = {"wort_test": [{"datei": f, "person": "AB"[i % 2]} for i, f in enumerate(pos[16:])],
                "kein_test": [{"datei": f, "person": "", "fehl": i < 3} for i, f in enumerate(neg_wavs[16:])],
                "wort_train": [], "kein_train": []}
        wahl_echt, bericht_echt = lauf._haelften(echt)
        assert len(wahl_echt["positiv"]) == 4 and len(bericht_echt["wort_test"]) == 4, (wahl_echt, bericht_echt)
        assert not {a["datei"] for a in wahl_echt["positiv"]} & {a["datei"] for a in bericht_echt["wort_test"]}
        assert {a["person"] for a in wahl_echt["positiv"]} == {"A", "B"}, wahl_echt
        bester, wahl = lauf._kandidaten(2, merkmale, neg, tts, [o / "bg"], {"dev": o / "lang"}, Path(rir),
                                        wahl_echt, mitteln=True)
        rezepte = [w["rezept"] for w in wahl["werte"]]
        assert rezepte == ["standard", "abgebrochen", "gemittelt"], wahl
        assert wahl["grundlage"] == "echt" and wahl["wahl_aufnahmen"] == 4, wahl
        gemittelt = lauf.ordner / "gemittelt" / "tflite_stream_state_internal_quant" / "stream_state_internal_quant.tflite"
        einzel = lauf.ordner / "train" / "tflite_stream_state_internal_quant" / "stream_state_internal_quant.tflite"
        assert gemittelt.exists() and einzel.exists(), "averaged or single model missing"
        assert gemittelt.stat().st_size > 1.5 * einzel.stat().st_size, (gemittelt.stat().st_size, einzel.stat().st_size)
        from .bausteine import fehlende_bausteine
        for f in (gemittelt, einzel):
            assert not fehlende_bausteine(f.read_bytes()), f"{f.name}: {fehlende_bausteine(f.read_bytes())}"
        assert bester.exists() and (wahl["teile"] == 2) == (bester == gemittelt), wahl
        print(f"SELBSTTEST thorough+averaged ok ({time.time() - t0:.0f} s, kept {wahl['gewaehlt']}, "
              f"averaged {gemittelt.stat().st_size} bytes)", flush=True)

        # the averaged model must read like a single one on the device: one candidate averaged with itself gives
        # the same probabilities, and the output keeps the 1/256 steps the device expects
        from ai_edge_litert.interpreter import Interpreter
        from microwakeword.inference import Model

        gewicht = str(lauf.ordner / "train" / "best_weights.weights.h5")
        e = lauf._werkzeug("mitteln", {"config": str(lauf.ordner / "training.yaml"), "gewichte": [gewicht, gewicht],
                                       "modell_args": MIXEDNET[1:], "ziel": str(o / "doppelt")}, "training", 0, 1, "mitteln")
        i = Interpreter(e["datei"])
        i.allocate_tensors()
        skala = i.get_output_details()[0]["quantization"]
        assert abs(skala[0] - 1 / 256) < 1e-9 and skala[1] == 0, f"averaged model output scale {skala}"
        x = np.concatenate([np.zeros(RATE, np.int16), (sf.read(pos[20], dtype="int16")[0])])
        p1 = np.array(Model(str(einzel), stride=3).predict_clip(x, step_ms=10))
        p2 = np.array(Model(e["datei"], stride=3).predict_clip(x, step_ms=10))
        assert len(p1) == len(p2) and float(np.abs(p1 - p2).max()) <= 0.02, (p1[:10], p2[:10])
        print("SELBSTTEST averaged model reads like a single one", flush=True)

        # fair comparison of two stored versions: no training, both tested on the same audio, result to HA
        lauf.ha.modelle = {1: einzel.read_bytes(), 2: gemittelt.read_bytes()}
        lauf._vergleichen({"a": 2, "b": 1}, echt, tts, [o / "bg"], {"test": o / "lang", "dev": o / "lang"}, Path(rir))
        v = lauf.ha.vergleiche[-1]
        assert (v["a"], v["b"]) == (2, 1) and v["neu"] and v["alt"] and v["vergleich"]["urteil"] in (
            "besser", "schlechter", "gleich"), v
        assert "je_schwelle" not in v and not list(lauf.ordner.glob("vergleich_v*.tflite")), v.keys()
        # real false wakes of the devices are measured for both versions and count for the verdict
        assert v["neu"]["echte_fehlausloeser_n"] == v["alt"]["echte_fehlausloeser_n"] == 3, v["neu"]
        assert any(z["kennzahl"] == "echte_fehlausloeser" and z["wichtig"] for z in v["vergleich"]["zeilen"]), v["vergleich"]
        # live interim figures of both tests: every part of the test reached, counts within their totals
        for k in ("vgl_a", "vgl_b"):
            lv = lauf.live()["pruefen"].get(k) or {}
            assert lv.get("teil") == "stille" and lv["n"] == lv["gesamt"] > 0, lv
            assert all(0 <= x <= lv["n"] for x in lv["hoert"].values()) and lv["min"]["stille"] > 0, lv
        print(f"SELBSTTEST fair comparison ok ({time.time() - t0:.0f} s, {v['vergleich']['urteil']})", flush=True)
    print("SELBSTTEST OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # noqa: BLE001
        logging.exception("Self-test failed")
        print(f"SELBSTTEST FAILED: {err}", flush=True)
        sys.exit(1)
