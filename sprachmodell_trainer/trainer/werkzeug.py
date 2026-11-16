"""Einzelne Arbeitsschritte als eigene Prozesse, damit ein Abbruch sofort greift.

Aufruf: python -m trainer.werkzeug <befehl> <auftrag.json>
Fortschritt: Zeilen "FORTSCHRITT <erledigt> <gesamt>", Ergebnis: letzte Zeile "ERGEBNIS <json>".
"""

from __future__ import annotations

import glob
import json
import os
import random
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
FAKTOR = 0.0390625  # Merkmale wie microWakeWord als uint16
CUTOFFS = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 0.97, 0.98, 0.99]
GLAETTEN = 5  # wie auf dem Geraet: Mittel ueber 5 Schritte


def _fortschritt(i: int, n: int) -> None:
    print(f"FORTSCHRITT {i} {n}", flush=True)


def _dateien(ordner: list[str]) -> list[str]:
    return sorted(f for d in ordner for f in glob.glob(os.path.join(d, "*.wav")))


# --- kuenstliche Aufnahmen ------------------------------------------------

def tts(a: dict) -> dict:
    """a: ziel, anzahl, texte, stimmen, [lautschrift_von]: Stimme, die den Text in Lautschrift umsetzt
    (fuer fremde Stimmen, die das Wort mit Akzent sprechen sollen)."""
    import scipy.signal as ss
    import scipy.io.wavfile as wf
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    ziel = a["ziel"]
    os.makedirs(ziel, exist_ok=True)
    stimmen = [PiperVoice.load(v) for v in a["stimmen"]]
    texte = list(a["texte"])
    if a.get("lautschrift_von"):
        quelle = PiperVoice.load(a["lautschrift_von"])
        texte = ["[[ " + " ".join("".join(s) for s in quelle.phonemize(t)) + " ]]" for t in texte]
    rnd = random.Random(sum(map(ord, ziel)))
    n = int(a["anzahl"])
    fertig = len(glob.glob(os.path.join(ziel, "*.wav")))
    i = fertig
    versuche = 0
    while i < n and versuche < n * 3:
        versuche += 1
        v = rnd.choice(stimmen)
        nsp = getattr(v.config, "num_speakers", 1) or 1
        cfg = SynthesisConfig(
            speaker_id=rnd.randrange(nsp) if nsp > 1 else None,
            length_scale=rnd.uniform(0.75, 1.4), noise_scale=rnd.uniform(0.4, 1.0), noise_w_scale=rnd.uniform(0.5, 1.3),
        )
        try:
            x = np.concatenate([c.audio_float_array for c in v.synthesize(rnd.choice(texte), syn_config=cfg)])
        except Exception:  # noqa: BLE001
            continue
        sr = v.config.sample_rate
        if len(x) < sr * 0.2 or len(x) > sr * 4.5:
            continue
        f = 1.0
        if rnd.random() < 0.6:  # Tonhoehe/Formanten: Kinder und tiefe Stimmen
            f = rnd.choice([rnd.uniform(0.85, 0.97), rnd.uniform(1.03, 1.25)])
        x = ss.resample_poly(x, 16000, int(round(sr * f)))
        x = x / (np.abs(x).max() + 1e-6) * rnd.uniform(0.3, 0.95)
        wf.write(os.path.join(ziel, f"{i:05d}.wav"), 16000, (x * 32767).astype(np.int16))
        i += 1
        if i % max(1, min(200, n // 20)) == 0:
            _fortschritt(i - fertig, n - fertig)
    return {"anzahl": i}


# --- Merkmale ---------------------------------------------------------------

_AUG = None
_OPT: dict = {}


def _init(opt: dict) -> None:
    global _AUG, _OPT  # noqa: PLW0603
    _OPT = opt
    warnings.filterwarnings("ignore")
    s = os.getpid()
    np.random.seed(s)
    random.seed(s)
    if opt.get("wiederholungen"):
        from microwakeword.audio.augmentation import Augmentation

        _AUG = Augmentation(
            augmentation_duration_s=3.2,
            augmentation_probabilities={
                "SevenBandParametricEQ": 0.15, "TanhDistortion": 0.1, "PitchShift": 0.15, "BandStopFilter": 0.1,
                "AddColorNoise": 0.15, "AddBackgroundNoise": 0.75, "Gain": 1.0, "GainTransition": 0.2, "RIR": 0.5,
            },
            impulse_paths=[opt["rir"]], background_paths=opt["bg"],
            background_min_snr_db=opt.get("snr_min", -5), background_max_snr_db=15, min_gain_db=-30,
            min_jitter_s=0.10, max_jitter_s=0.21,
        )


def _merkmal(f: str) -> list[np.ndarray]:
    import soundfile as sf
    from microwakeword.audio.audio_utils import generate_features_for_clip, remove_silence_webrtc

    try:
        if not _OPT.get("wiederholungen"):  # lange Aufnahmen: volle Laenge, unveraendert
            x, _ = sf.read(f, dtype="int16")
            x = x if x.ndim == 1 else x[:, 0]
            s = generate_features_for_clip(x, 10)
            return [np.clip(np.round(s / FAKTOR), 0, 65535).astype(np.uint16)]
        x, _ = sf.read(f, dtype="float32")
        x = x if x.ndim == 1 else x.mean(1)
        if _OPT.get("trim"):
            x = remove_silence_webrtc(x)
        aus = []
        for _ in range(_OPT["wiederholungen"]):
            s = generate_features_for_clip(_AUG.augment_clip(x), 10)[-_OPT.get("frames", 220):]
            aus.append(np.clip(np.round(s / FAKTOR), 0, 65535).astype(np.uint16))
        return aus
    except Exception:  # noqa: BLE001
        return []


def merkmale(a: dict) -> dict:
    """a: ziel (…_mmap), ordner [..] oder dateien [..], wiederholungen (0 = lang/unveraendert), frames, trim,
    bg [..], rir, snr_min, prozesse."""
    from multiprocessing import Pool

    from .grenzen import prozesse

    from mmap_ninja.ragged import RaggedMmap

    dateien = a.get("dateien") or _dateien(a["ordner"])
    n = len(dateien)
    zaehler = {"n": 0}

    def erzeugen():
        with Pool(prozesse(a.get("prozesse")), initializer=_init, initargs=(a,)) as pool:
            for i, r in enumerate(pool.imap_unordered(_merkmal, dateien, chunksize=16)):
                if i % max(1, min(200, n // 20)) == 0:
                    _fortschritt(i, n)
                zaehler["n"] += len(r)
                yield from r

    os.makedirs(os.path.dirname(a["ziel"]), exist_ok=True)
    RaggedMmap.from_generator(out_dir=a["ziel"], sample_generator=erzeugen(), batch_size=500, verbose=False)
    return {"dateien": n, "merkmale": zaehler["n"]}


# --- ehrlicher Test ---------------------------------------------------------

def _laden(f: str) -> np.ndarray:
    import soundfile as sf

    x, _ = sf.read(f, dtype="int16")
    return x if x.ndim == 1 else x[:, 0]


def _verlauf(m, x: np.ndarray) -> np.ndarray:
    p = np.array(m.predict_clip(x, step_ms=10), dtype=np.float32)
    if len(p) < GLAETTEN:
        return p
    return np.convolve(p, np.ones(GLAETTEN) / GLAETTEN, mode="valid")


def pruefen(a: dict) -> dict:
    """a: modell, positiv [{datei, person}], negativ [datei], gerede [datei], bg [datei], max_stunden.
    Ergebnis je Schwelle: Trefferquote ruhig/mit Musik, Gegenbeispiele ausgeloest, Fehlausloeser pro Stunde."""
    from microwakeword.inference import Model

    m = Model(a["modell"], stride=3)
    rnd = random.Random(1)
    pause = np.zeros(16000, np.int16)
    bg = a.get("bg") or []
    gesamt = len(a["positiv"]) * 2 + len(a["negativ"]) + max(1, len(a["gerede"]))
    schritt = [0]

    def weiter() -> None:
        schritt[0] += 1
        if schritt[0] % 25 == 0:
            _fortschritt(schritt[0], gesamt)

    def musik(x: np.ndarray, snr: float) -> np.ndarray:
        if not bg:
            return x
        b = _laden(rnd.choice(bg)).astype(np.float32)
        if len(b) < len(x):
            b = np.tile(b, len(x) // max(1, len(b)) + 1)
        s = rnd.randrange(0, len(b) - len(x) + 1)
        b = b[s:s + len(x)]
        px = np.mean(x.astype(np.float32) ** 2) + 1e-9
        pb = np.mean(b ** 2) + 1e-9
        return np.clip(x + b * np.sqrt(px / pb / 10 ** (snr / 10)), -32768, 32767).astype(np.int16)

    ruhig, laut, personen = [], [], []
    for p in a["positiv"]:
        x = np.concatenate([pause, _laden(p["datei"]), pause])
        ruhig.append(float(_verlauf(m, x).max()))
        weiter()
        laut.append(float(_verlauf(m, musik(x, 5)).max()))
        weiter()
        personen.append(p.get("person") or "")
    gegen = []
    for f in a["negativ"]:
        gegen.append(float(_verlauf(m, np.concatenate([pause, _laden(f), pause])).max()))
        weiter()
    ausloeser = {c: 0 for c in CUTOFFS}
    zuletzt = {c: -1e9 for c in CUTOFFS}
    dauer = 0.0
    t0 = 0.0
    for f in a["gerede"]:
        x = _laden(f)
        p = _verlauf(m, np.concatenate([x, np.zeros(4800, np.int16)]))
        for c in CUTOFFS:
            for i in np.nonzero(p >= c)[0]:
                t = t0 + i * 0.03
                if t - zuletzt[c] > 2.0:
                    ausloeser[c] += 1
                    zuletzt[c] = t
        dauer += len(x) / 16000
        t0 += len(x) / 16000 + 0.3
        weiter()
        if dauer > a.get("max_stunden", 3) * 3600:
            break
    stunden = max(dauer / 3600, 1e-6)
    ruhig_a, laut_a, gegen_a = np.array(ruhig), np.array(laut), np.array(gegen)
    je = {}
    for c in CUTOFFS:
        jp: dict[str, list[float]] = {}
        for wert, person in zip(ruhig, personen):
            if person:
                jp.setdefault(person, []).append(1.0 if wert >= c else 0.0)
        je[str(c)] = {
            "trefferquote": float((ruhig_a >= c).mean()) if len(ruhig) else None,
            "trefferquote_musik": float((laut_a >= c).mean()) if len(laut) else None,
            "gegenbeispiele": float((gegen_a >= c).mean()) if len(gegen) else None,
            "fehlausloeser_pro_stunde": ausloeser[c] / stunden if a["gerede"] else None,
            "je_person": {k: {"trefferquote": round(float(np.mean(v)), 3), "anzahl": len(v)} for k, v in jp.items()},
        }
    return {"stunden": round(stunden, 2), "positiv": len(ruhig), "negativ": len(gegen), "je_schwelle": je}


BEFEHLE = {"tts": tts, "merkmale": merkmale, "pruefen": pruefen}

if __name__ == "__main__":
    with open(sys.argv[2], encoding="utf-8") as datei:
        auftrag = json.load(datei)
    ergebnis = BEFEHLE[sys.argv[1]](auftrag)
    print("ERGEBNIS " + json.dumps(ergebnis), flush=True)
