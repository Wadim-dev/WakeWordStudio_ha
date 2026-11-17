"""Einzelne Arbeitsschritte als eigene Prozesse, damit ein Abbruch sofort greift.

Aufruf: python -m trainer.werkzeug <befehl> <auftrag.json>
Fortschritt: Zeilen "FORTSCHRITT <erledigt> <gesamt>", Ergebnis: letzte Zeile "ERGEBNIS <json>".
"""

from __future__ import annotations

import glob
import json
import os
import random
import re
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
FAKTOR = 0.0390625  # Merkmale wie microWakeWord als uint16
CUTOFFS = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 0.97, 0.98, 0.99]
GLAETTEN = 5  # wie auf dem Geraet: Mittel ueber 5 Schritte


def _fortschritt(i: int, n: int) -> None:
    print(f"FORTSCHRITT {i} {n}", flush=True)


def _balken(name: str, i: int, n: int) -> None:
    """An extra progress bar of its own in Home Assistant (next to the step's bar)."""
    print(f"BALKEN {name}|{i}|{n}", flush=True)


def _dateien(ordner: list[str]) -> list[str]:
    return sorted(f for d in ordner for f in glob.glob(os.path.join(d, "*.wav")))


# --- kuenstliche Aufnahmen ------------------------------------------------

_TTS: dict = {}


def _tts_init(a: dict) -> None:
    import onnxruntime
    from piper import PiperVoice

    warnings.filterwarnings("ignore")
    # in a container limited to some cores onnxruntime cannot pin its threads and reports it as an error for every
    # voice ("pthread_setaffinity_np failed"); harmless, it only hid the real log lines. Real errors still raise.
    onnxruntime.set_default_logger_severity(4)
    _TTS["a"] = a
    _TTS["stimmen"] = [PiperVoice.load(v) for v in a["stimmen"]]
    texte = list(a["texte"])
    if a.get("lautschrift_von"):
        quelle = PiperVoice.load(a["lautschrift_von"])
        texte = ["[[ " + " ".join("".join(s) for s in quelle.phonemize(t)) + " ]]" for t in texte]
    _TTS["texte"] = texte


def _tts_eine(i: int) -> bool:
    """Clip number i. Each number has its own random settings, so a resumed or parallel run makes the same set."""
    import scipy.signal as ss
    import scipy.io.wavfile as wf
    from piper.config import SynthesisConfig

    a, stimmen, texte = _TTS["a"], _TTS["stimmen"], _TTS["texte"]
    datei = os.path.join(a["ziel"], f"{i:05d}.wav")
    if os.path.exists(datei):
        return True
    rnd = random.Random(f"{a['ziel']}/{i}")
    for _ in range(3):
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
        tmp = datei[:-4] + ".tmp"
        wf.write(tmp, 16000, (x * 32767).astype(np.int16))
        os.replace(tmp, datei)
        return True
    return False


def tts(a: dict) -> dict:
    """a: ziel, anzahl, texte, stimmen, [lautschrift_von], [prozesse]. lautschrift_von: voice that turns the text into
    phonemes (for foreign voices that should say the word with an accent). Resumes where it stopped; with several
    processes each one makes its own numbers."""
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool

    from .grenzen import prozesse

    os.makedirs(a["ziel"], exist_ok=True)
    n = int(a["anzahl"])
    offen = [i for i in range(n) if not os.path.exists(os.path.join(a["ziel"], f"{i:05d}.wav"))]
    p = max(1, min(prozesse(a.get("prozesse")), len(offen) // 50 or 1))
    erledigt = 0
    if p == 1:
        _tts_init(a)
        for k, i in enumerate(offen):
            erledigt += _tts_eine(i)
            if k % max(1, min(200, len(offen) // 20)) == 0:
                _fortschritt(k, len(offen))
    else:
        with ProcessPoolExecutor(p, initializer=_tts_init, initargs=(a,)) as pool:
            try:
                for k, ok in enumerate(pool.map(_tts_eine, offen, chunksize=8)):
                    erledigt += ok
                    if k % max(1, min(200, len(offen) // 20)) == 0:
                        _fortschritt(k, len(offen))
            except BrokenProcessPool:
                print("SPEICHER A worker process was stopped, probably out of memory", flush=True)
                raise SystemExit(3) from None
    return {"anzahl": len(glob.glob(os.path.join(a["ziel"], "*.wav"))), "neu": erledigt}


def proben(a: dict) -> dict:
    """A few clips of each text for the listening check: a: ziel, texte, stimmen, je. Files <text no>_<k>.wav."""
    os.makedirs(a["ziel"], exist_ok=True)
    texte = list(a["texte"])
    _tts_init({**a, "texte": texte[:1] or [""]})
    for i, text in enumerate(texte):
        _TTS["texte"] = [text]
        for k in range(int(a.get("je", 3))):
            nr = i * 100 + k  # own number per clip: own voice and settings
            datei = os.path.join(a["ziel"], f"{i:04d}_{k}.wav")
            if not os.path.exists(datei) and _tts_eine(nr):
                os.replace(os.path.join(a["ziel"], f"{nr:05d}.wav"), datei)
        _fortschritt(i + 1, len(texte))
    return {"texte": len(texte)}


# --- modern voices and listening (run in the separate "stimmen" environment) --------------------------

# Voice descriptions for OmniVoice: who speaks, how. Mixed at random for every clip.
OMNI_WER = ["female", "male"]
OMNI_ALTER = ["child", "teenager", "young adult", "middle-aged", "elderly"]
OMNI_HOEHE = ["", "", "very low pitch", "low pitch", "moderate pitch", "high pitch", "very high pitch"]


def _omni_stimme(rnd: random.Random) -> str:
    teile = [rnd.choice(OMNI_WER), rnd.choice(OMNI_ALTER), rnd.choice(OMNI_HOEHE)]
    if rnd.random() < 0.08:
        teile.append("whisper")
    return ", ".join(t for t in teile if t)


def _normal(text: str) -> str:
    """Lower case, ё as е, only letters and digits (for comparing what was heard with the word)."""
    t = text.lower().replace("ё", "е")
    return "".join(c for c in t if c.isalnum())


def enthaelt_wort(gehoert: str, wort: str) -> bool:
    w = _normal(wort)
    return bool(w) and w in _normal(gehoert)


def _threads() -> int:
    from .grenzen import kerne

    return int(os.environ.get("THREADS") or 0) or kerne()


def _whisper(sprache: str):
    from faster_whisper import WhisperModel

    return WhisperModel(os.environ.get("WHISPER_MODELL", "small"), device="cpu", compute_type="int8",
                        cpu_threads=_threads())


def _hoeren(m, x: np.ndarray, sprache: str) -> str:
    """What the speech recognition hears in a 16 kHz clip (empty for silence)."""
    teile, _ = m.transcribe(x.astype(np.float32), language=sprache or None, beam_size=1, vad_filter=False,
                            condition_on_previous_text=False)
    text = " ".join(t.text for t in teile).strip()
    # Whisper's known filler for silence and noise ("subtitles by ...", "thanks for watching")
    if re.search(r"субтитр|subtit|amara|продолжение следует|thanks? for watching|untertitel", text, re.IGNORECASE):
        return ""
    return text


def hoeren(a: dict) -> dict:
    """a: sprache, dateien [{id, datei}]. Result: {id: what was heard}."""
    import soundfile as sf
    from scipy.signal import resample_poly

    m = _whisper(a.get("sprache") or "")
    aus = {}
    for k, d in enumerate(a["dateien"]):
        try:
            x, sr = sf.read(d["datei"], dtype="float32")
            x = x if x.ndim == 1 else x.mean(1)
            if sr != 16000:
                x = resample_poly(x, 16000, sr)
            aus[d["id"]] = _hoeren(m, x, a.get("sprache") or "")
        except Exception as err:  # noqa: BLE001
            print(f"Could not listen to {d['id']}: {type(err).__name__}: {err}"[:240], flush=True)
        _fortschritt(k + 1, len(a["dateien"]))
    return aus


def omni(a: dict) -> dict:
    """More voices with OmniVoice: a: sprache, wort, ziel_pos, ziel_neg, anzahl_pos, anzahl_neg, texte_pos, texte_neg,
    minuten. Every clip is checked by the speech recognition: the word must be heard in a positive and must not be
    heard in a negative, so broken or wrong clips never reach the training. Stops after `minuten` and continues on
    the next run."""
    import time

    import soundfile as sf
    import torch
    from omnivoice import OmniVoice
    from omnivoice.models.omnivoice import OmniVoiceGenerationConfig
    from scipy.signal import resample_poly

    start = time.monotonic()
    dauer = float(a.get("minuten", 90)) * 60
    ende = start + dauer
    torch.set_num_threads(_threads())
    modell = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cpu", dtype=torch.float32)
    ohr = _whisper(a["sprache"])
    cfg = OmniVoiceGenerationConfig(num_step=8)
    rnd = random.Random()
    paket = 8
    stand = {}
    for art in ("pos", "neg"):
        ziel = a[f"ziel_{art}"]
        os.makedirs(ziel, exist_ok=True)
        da = sorted(glob.glob(os.path.join(ziel, "*.wav")))
        stand[art] = {"ziel": ziel, "n": int(a[f"anzahl_{art}"]), "da": len(da), "verworfen": 0,
                      "nr": max([int(os.path.basename(f)[:6]) for f in da] + [-1]) + 1, "texte": list(a[f"texte_{art}"])}
    gesamt = sum(s["n"] for s in stand.values())
    while time.monotonic() < ende:
        # always fill the set that is furthest behind, so both grow together over the runs
        offen = [k for k, s in stand.items() if s["da"] < s["n"] and s["texte"]]
        if not offen:
            break
        art = min(offen, key=lambda k: stand[k]["da"] / stand[k]["n"])
        s = stand[art]
        satz = [rnd.choice(s["texte"]) for _ in range(paket)]
        stimme = [_omni_stimme(rnd) for _ in range(paket)]
        try:
            audio = modell.generate(text=satz, language=[a["sprache"]] * paket, instruct=stimme,
                                    speed=[rnd.uniform(0.8, 1.25) for _ in range(paket)], generation_config=cfg)
        except Exception as err:  # noqa: BLE001
            print(f"OmniVoice: {type(err).__name__}: {err}"[:240], flush=True)
            break
        behalten, weg = 0, []
        for x in audio:
            x = resample_poly(np.asarray(x, dtype=np.float32), 16000, 24000)
            if len(x) < 3200 or len(x) > 16000 * 4 or np.abs(x).max() < 1e-3:
                s["verworfen"] += 1
                weg.append("(too short/long or silent)")
                continue
            gehoert = _hoeren(ohr, x, a["sprache"])
            if enthaelt_wort(gehoert, a["wort"]) != (art == "pos"):
                s["verworfen"] += 1
                weg.append(repr(gehoert[:40]))
                continue
            behalten += 1
            x = x / (np.abs(x).max() + 1e-6) * rnd.uniform(0.3, 0.95)
            datei = os.path.join(s["ziel"], f"{s['nr']:06d}.wav")
            sf.write(datei + ".tmp", (x * 32767).astype(np.int16), 16000, format="WAV")
            os.replace(datei + ".tmp", datei)
            s["nr"] += 1
            s["da"] += 1
        name = "OmniVoice: word" if art == "pos" else "OmniVoice: other speech"
        print(f"{name}: {behalten} of {len(audio)} kept" + (f", rejected after listening: {', '.join(weg[:4])}" if weg else "")
              + f" - {s['da']}/{s['n']}", flush=True)
        _balken("omni_wort" if art == "pos" else "omni_gerede", min(s["da"], s["n"]), s["n"])
        # progress by time budget or stock, whichever is further: the step ends at the first of both
        voll = sum(min(s["da"], s["n"]) for s in stand.values()) / max(1, gesamt)
        _fortschritt(round(1000 * max(voll, (time.monotonic() - start) / dauer)), 1000)
    ergebnis = {}
    for art, s in stand.items():
        ergebnis[art] = {"anzahl": s["da"], "verworfen": s["verworfen"]}
        print(f"OmniVoice {art}: {s['da']} of {s['n']} clips, {s['verworfen']} rejected by the check", flush=True)
    return ergebnis


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
    except Exception as err:  # noqa: BLE001 - one broken file must not stop the step, but it is reported
        print(f"Skipped {os.path.basename(f)}: {type(err).__name__}: {err}"[:240], flush=True)
        return []


def merkmale(a: dict) -> dict:
    """a: ziel (…_mmap), ordner [..] oder dateien [..], wiederholungen (0 = lang/unveraendert), frames, trim,
    bg [..], rir, snr_min, prozesse."""
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool

    from .grenzen import prozesse

    from mmap_ninja.ragged import RaggedMmap

    # import here first: a broken installation then fails with its real error, not as a broken worker pool
    from microwakeword.audio.audio_utils import generate_features_for_clip  # noqa: F401
    from microwakeword.audio.augmentation import Augmentation  # noqa: F401

    dateien = a.get("dateien") or _dateien(a["ordner"])
    n = len(dateien)
    zaehler = {"n": 0}

    def erzeugen():
        # ProcessPoolExecutor instead of multiprocessing.Pool: if a worker is killed (out of memory),
        # Pool waits forever, the executor raises BrokenProcessPool and the step ends with a clear error.
        with ProcessPoolExecutor(prozesse(a.get("prozesse")), initializer=_init, initargs=(a,)) as pool:
            try:
                for i, r in enumerate(pool.map(_merkmal, dateien, chunksize=16)):
                    if i % max(1, min(200, n // 20)) == 0:
                        _fortschritt(i, n)
                    zaehler["n"] += len(r)
                    yield from r
            except BrokenProcessPool:
                print("SPEICHER A worker process was stopped, probably out of memory", flush=True)
                raise SystemExit(3) from None

    os.makedirs(os.path.dirname(a["ziel"]), exist_ok=True)
    RaggedMmap.from_generator(out_dir=a["ziel"], sample_generator=erzeugen(), batch_size=500, verbose=False)
    if n and not zaehler["n"]:
        raise SystemExit(f"No features could be computed from any of the {n} files")
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


def schlank(a: dict) -> dict:
    """Small copy of a feature set for evaluation during training (microWakeWord loads validation and test sets
    completely into memory). a: quelle, ziel, max_proben (per validation/testing set), max_frames (per *_ambient set).
    training/ stays a link to the original (it is read lazily)."""
    from pathlib import Path

    from mmap_ninja.ragged import RaggedMmap

    quelle, ziel = Path(a["quelle"]), Path(a["ziel"])
    ziel.mkdir(parents=True, exist_ok=True)
    aus: dict[str, int] = {}
    for teil in sorted(p for p in quelle.iterdir() if p.is_dir()):
        neu = ziel / teil.name
        if teil.name == "training":
            if not neu.exists():
                neu.symlink_to(teil.resolve(), target_is_directory=True)
            continue
        for m in sorted(teil.glob("**/*_mmap")):
            alt = RaggedMmap(str(m))
            n = len(alt)
            if teil.name.endswith("ambient"):
                frames, k = 0, 0
                while k < n and frames < a["max_frames"]:
                    frames += len(alt[k])
                    k += 1
                auswahl = list(range(k))
            else:
                k = min(n, int(a["max_proben"]))
                auswahl = sorted({int(i) for i in np.linspace(0, n - 1, k)}) if n else []
            out = neu / m.relative_to(teil)
            out.parent.mkdir(parents=True, exist_ok=True)
            RaggedMmap.from_generator(out_dir=str(out), sample_generator=(alt[i] for i in auswahl),
                                      batch_size=500, verbose=False)
            aus[f"{teil.name}/{m.name}"] = len(auswahl)
            print(f"{quelle.name}/{teil.name}/{m.name}: {len(auswahl)} of {n}", flush=True)
    return aus


BEFEHLE = {"tts": tts, "merkmale": merkmale, "pruefen": pruefen, "schlank": schlank, "hoeren": hoeren, "omni": omni, "proben": proben}

if __name__ == "__main__":
    with open(sys.argv[2], encoding="utf-8") as datei:
        auftrag = json.load(datei)
    ergebnis = BEFEHLE[sys.argv[1]](auftrag)
    print("ERGEBNIS " + json.dumps(ergebnis), flush=True)
