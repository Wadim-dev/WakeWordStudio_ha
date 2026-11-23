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


LIVE_CUTOFF = 0.9  # threshold for the running interim figures of a test (the report uses the tested threshold)


def _live(daten: dict) -> None:
    """Interim figures of a running test for the live view in Home Assistant."""
    print("LIVE " + json.dumps(daten, separators=(",", ":")), flush=True)


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

        if opt.get("rezept") == "sanft":
            # gentle recipe (as the Tater trainer prepares its clips): noise always well below the voice, more
            # room sound, no volume sweeps; a thorough run trains one candidate on it and real recordings decide
            _AUG = Augmentation(
                augmentation_duration_s=3.2,
                augmentation_probabilities={
                    "SevenBandParametricEQ": 0.1, "TanhDistortion": 0.05, "PitchShift": 0.15, "BandStopFilter": 0.1,
                    "AddColorNoise": 0.1, "AddBackgroundNoise": 0.7, "Gain": 0.8, "RIR": 0.7,
                },
                impulse_paths=[opt["rir"]], background_paths=opt["bg"],
                background_min_snr_db=5, background_max_snr_db=10,
                # never fainter than about a normal voice across the room: with the library's default (-45 dB)
                # a quarter of the words became almost silent, and v20 (20.11.) woke on a quiet kitchen
                min_gain_db=-20,
                min_jitter_s=0.10, max_jitter_s=0.21,
            )
            return
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


def _abgebrochen(x: np.ndarray) -> np.ndarray:
    """The word broken off part-way, as when somebody starts it and stops or says a longer word that begins the
    same: from the start of the voice up to a random point between a quarter and 60 % of it."""
    rahmen = 320  # 20 ms
    n = len(x) // rahmen
    if n < 4:
        return x
    energie = np.sqrt((x[: n * rahmen].reshape(n, rahmen) ** 2).mean(axis=1))
    stimme = np.flatnonzero(energie > 0.15 * (energie.max() + 1e-9))
    if len(stimme) < 2:
        return x
    von, bis = int(stimme[0]) * rahmen, (int(stimme[-1]) + 1) * rahmen
    return x[: von + int((bis - von) * random.uniform(0.25, 0.6))]


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
            s = generate_features_for_clip(_AUG.augment_clip(_abgebrochen(x) if _OPT.get("abschneiden") else x), 10)[-_OPT.get("frames", 220):]
            aus.append(np.clip(np.round(s / FAKTOR), 0, 65535).astype(np.uint16))
        return aus
    except Exception as err:  # noqa: BLE001 - one broken file must not stop the step, but it is reported
        print(f"Skipped {os.path.basename(f)}: {type(err).__name__}: {err}"[:240], flush=True)
        return []


def merkmale(a: dict) -> dict:
    """a: ziel (…_mmap), ordner [..] oder dateien [..], wiederholungen (0 = lang/unveraendert), frames, trim,
    bg [..], rir, snr_min, prozesse, abschneiden (the word broken off part-way, as a negative), rezept ("sanft":
    gentle recipe)."""
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


def ruhe(rnd: random.Random, n: int, bg: list[str]) -> np.ndarray:
    """n samples of a quiet room without anybody talking: faint hiss, hum or far-away sounds (about -80 to -35
    dBFS), now and then digital silence. A model must never wake on this (seen 20.11.: a kitchen Echo woke every
    few seconds on a quiet room). Used as negatives in training and as a test of its own."""
    art = rnd.random()
    if art < 0.04:
        return np.zeros(n, np.int16)
    if bg and art < 0.5:
        x = _laden(rnd.choice(bg)).astype(np.float32)
        if len(x) < n:
            x = np.tile(x, n // max(1, len(x)) + 1)
        s = rnd.randrange(0, len(x) - n + 1)
        x = x[s:s + n]
        pegel = rnd.uniform(-65, -35)
    else:
        g = np.random.default_rng(rnd.randrange(1 << 30))
        spek = np.fft.rfft(g.standard_normal(n))
        f = np.fft.rfftfreq(n, 1 / 16000)
        f[0] = f[1] if len(f) > 1 else 1.0
        x = np.fft.irfft(spek / f ** rnd.choice((0.0, 0.5, 1.0)), n).astype(np.float32)  # white, pink, brown
        if rnd.random() < 0.3:  # mains hum of a fridge or a lamp
            t = np.arange(n) / 16000
            netz = rnd.choice((50.0, 60.0))
            brumm = sum(np.sin(2 * np.pi * netz * k * t) / k for k in (1, 2, 3)).astype(np.float32)
            x = x / (np.sqrt(np.mean(x ** 2)) + 1e-9) + 2 * brumm
        pegel = rnd.uniform(-80, -45)
    x = x / (np.sqrt(np.mean(x ** 2)) + 1e-9) * 32768 * 10 ** (pegel / 20)
    return np.clip(np.round(x), -32768, 32767).astype(np.int16)


def _verlauf(m, x: np.ndarray) -> np.ndarray:
    p = np.array(m.predict_clip(x, step_ms=10), dtype=np.float32)
    if len(p) < GLAETTEN:
        return p
    return np.convolve(p, np.ones(GLAETTEN) / GLAETTEN, mode="valid")


# Everyday conditions of the test. Every model of a run hears exactly the same audio (fixed random seed), so
# old and new are compared on identical clips.
BEDINGUNGEN = ("ruhig", "leise", "hall", "musik", "gerede", "alltag")
# Hard test: far harder than daily life, so a good version does not reach 100 % here and two versions that both
# hear everything in daily life can still be told apart (who has more reserve).
SCHWER = ("weit", "laut_tv", "laut_musik", "chaos")


def _ausloesen(m, x: np.ndarray, zuletzt: dict, t0: float, ausloeser: dict) -> None:
    """Count wake-ups in a long recording per threshold (one wake-up at most every 2 s, like the device)."""
    p = _verlauf(m, np.concatenate([x, np.zeros(4800, np.int16)]))
    for c in CUTOFFS:
        for i in np.nonzero(p >= c)[0]:
            t = t0 + i * 0.03
            if t - zuletzt[c] > 2.0:
                ausloeser[c] += 1
                zuletzt[c] = t


def pruefen(a: dict) -> dict:
    """a: modell, positiv [{datei, person}], negativ [datei], gerede [datei], bg [datei], rir (folder, optional),
    max_stunden (speech), max_stunden_bg (music and noise).

    Every real test recording is heard six ways, like at home: quiet room, quietly or from far away (-18 dB), in
    another room (reverb), with music, with a TV talking in the background, and all at once. Per threshold:
    hit rate per condition, similar-sounding words that trigger, false wakes per hour of speech and of music/noise
    and in a quiet room (stille_minuten, default 20) - with the counts, so the comparison can tell chance from a
    real difference."""
    from microwakeword.inference import Model

    m = Model(a["modell"], stride=3)
    rnd = random.Random(1)
    pause = np.zeros(16000, np.int16)
    bg = a.get("bg") or []
    rede_dateien = a.get("gerede") or []
    rir = a.get("rir") or ""
    raeume = sorted(glob.glob(os.path.join(rir, "*.wav")))[:200] if os.path.isdir(rir) else [rir] if rir else []
    gesamt = len(a["positiv"]) * (len(BEDINGUNGEN) + len(SCHWER)) + len(a["negativ"]) + max(1, len(rede_dateien)) + 1
    schritt = [0]

    def weiter() -> None:
        schritt[0] += 1
        if schritt[0] % 25 == 0:
            _fortschritt(schritt[0], gesamt)

    def stueck(dateien: list[str], n: int) -> np.ndarray:
        b = _laden(rnd.choice(dateien)).astype(np.float32)
        if len(b) < n:
            b = np.tile(b, n // max(1, len(b)) + 1)
        s = rnd.randrange(0, len(b) - n + 1)
        return b[s:s + n]

    def mischen(x: np.ndarray, dateien: list[str], snr: float) -> np.ndarray:
        if not dateien:
            return x
        b = stueck(dateien, len(x))
        px = np.mean(x.astype(np.float32) ** 2) + 1e-9
        pb = np.mean(b ** 2) + 1e-9
        return np.clip(x + b * np.sqrt(px / pb / 10 ** (snr / 10)), -32768, 32767).astype(np.int16)

    def leiser(x: np.ndarray, db: float) -> np.ndarray:
        return (x.astype(np.float32) * 10 ** (-db / 20)).astype(np.int16)

    def hall(x: np.ndarray) -> np.ndarray:
        if not raeume:
            return x
        import soundfile as sf

        r, _ = sf.read(rnd.choice(raeume), dtype="float32")
        r = r if r.ndim == 1 else r[:, 0]
        r = r[: 16000 * 2] / (np.max(np.abs(r)) + 1e-9)
        y = np.convolve(x.astype(np.float32), r)[: len(x)]
        # same loudness as before: the room changes the sound, "quiet" is its own condition
        y *= np.sqrt((np.mean(x.astype(np.float32) ** 2) + 1e-9) / (np.mean(y ** 2) + 1e-9))
        return np.clip(y, -32768, 32767).astype(np.int16)

    werte: dict[str, list[float]] = {b: [] for b in BEDINGUNGEN + SCHWER}
    personen = []
    max_min = {"gerede": round(a.get("max_stunden", 3) * 60, 1), "geraeusch": round(a.get("max_stunden_bg", 1) * 60, 1),
               "stille": float(a.get("stille_minuten", 20))}
    live = {"teil": "lagen", "n": 0, "gesamt": len(a["positiv"]), "hoert": {b: 0 for b in BEDINGUNGEN + SCHWER},
            "aehnlich": 0, "aehnlich_n": 0, "aehnlich_gesamt": len(a["negativ"]),
            "fehl": {"gerede": 0, "geraeusch": 0, "stille": 0}, "min": {"gerede": 0.0, "geraeusch": 0.0, "stille": 0.0},
            "max_min": max_min}
    _live(live)
    for p in a["positiv"]:
        x = np.concatenate([pause, _laden(p["datei"]), pause])
        fassungen = {
            "ruhig": x,
            "leise": leiser(x, 18),
            "hall": hall(x),
            "musik": mischen(x, bg, 5),
            "gerede": mischen(x, rede_dateien, 5),
        }
        fassungen["alltag"] = mischen(leiser(hall(x), 8), bg if rnd.random() < 0.5 else rede_dateien, 10)
        # hard test: very far away in another room, a loud TV, loud music, everything at once (fixed seed as above)
        fassungen["weit"] = leiser(hall(x), 30)
        fassungen["laut_tv"] = mischen(x, rede_dateien, -3)
        fassungen["laut_musik"] = mischen(x, bg, -3)
        fassungen["chaos"] = mischen(leiser(hall(x), 18), bg if rnd.random() < 0.5 else rede_dateien, 3)
        for b in BEDINGUNGEN + SCHWER:
            werte[b].append(float(_verlauf(m, fassungen[b]).max()))
            live["hoert"][b] += werte[b][-1] >= LIVE_CUTOFF
            weiter()
        personen.append(p.get("person") or "")
        live["n"] += 1
        _live(live)
    gegen = []
    live["teil"] = "aehnlich"
    for f in a["negativ"]:
        gegen.append(float(_verlauf(m, np.concatenate([pause, _laden(f), pause])).max()))
        live["aehnlich"] += gegen[-1] >= LIVE_CUTOFF
        live["aehnlich_n"] += 1
        if live["aehnlich_n"] % 5 == 0 or live["aehnlich_n"] == len(a["negativ"]):
            _live(live)
        weiter()
    live["teil"] = "gerede"
    _live(live)

    ausloeser = {c: 0 for c in CUTOFFS}
    zuletzt = {c: -1e9 for c in CUTOFFS}
    dauer = t0 = 0.0
    for f in rede_dateien:
        x = _laden(f)
        _ausloesen(m, x, zuletzt, t0, ausloeser)
        dauer += len(x) / 16000
        t0 += len(x) / 16000 + 0.3
        weiter()
        if int(dauer / 60) != int(live["min"]["gerede"]):
            live["min"]["gerede"], live["fehl"]["gerede"] = round(dauer / 60, 1), ausloeser[LIVE_CUTOFF]
            _live(live)
        if dauer > a.get("max_stunden", 3) * 3600:
            break
    live["min"]["gerede"], live["fehl"]["gerede"] = round(dauer / 60, 1), ausloeser[LIVE_CUTOFF]
    live["max_min"]["gerede"] = live["min"]["gerede"]  # less speech than the limit: the test ends here
    live["teil"] = "geraeusch"
    _live(live)
    # music and everyday noise without anybody talking: a wake-up here is just as annoying
    aus_bg = {c: 0 for c in CUTOFFS}
    zuletzt_bg = {c: -1e9 for c in CUTOFFS}
    dauer_bg = t0 = 0.0
    for f in sorted(bg)[: 2000]:
        x = _laden(f)
        _ausloesen(m, x, zuletzt_bg, t0, aus_bg)
        dauer_bg += len(x) / 16000
        t0 += len(x) / 16000 + 0.3
        if int(dauer_bg / 60) != int(live["min"]["geraeusch"]):
            live["min"]["geraeusch"], live["fehl"]["geraeusch"] = round(dauer_bg / 60, 1), aus_bg[LIVE_CUTOFF]
            _live(live)
        if dauer_bg > a.get("max_stunden_bg", 1) * 3600:
            break
    live["min"]["geraeusch"], live["fehl"]["geraeusch"] = round(dauer_bg / 60, 1), aus_bg[LIVE_CUTOFF]
    live["max_min"]["geraeusch"] = live["min"]["geraeusch"]
    live["teil"] = "stille"
    _live(live)
    weiter()
    # a quiet room: faint hiss, hum, far-away sounds - nothing a model may wake on
    aus_st = {c: 0 for c in CUTOFFS}
    zuletzt_st = {c: -1e9 for c in CUTOFFS}
    rnd_st = random.Random(6)
    dauer_st = t0 = 0.0
    while dauer_st < a.get("stille_minuten", 20) * 60:
        x = ruhe(rnd_st, 16000 * 30, bg)
        _ausloesen(m, x, zuletzt_st, t0, aus_st)
        dauer_st += 30
        t0 += 30.3
        live["min"]["stille"], live["fehl"]["stille"] = round(dauer_st / 60, 1), aus_st[LIVE_CUTOFF]
        _live(live)
    stunden, stunden_bg = max(dauer / 3600, 1e-6), max(dauer_bg / 3600, 1e-6)
    arr = {b: np.array(v) for b, v in werte.items()}
    gegen_a = np.array(gegen)
    je = {}
    for c in CUTOFFS:
        jp: dict[str, list[float]] = {}
        for wert, person in zip(werte["ruhig"], personen):
            if person:
                jp.setdefault(person, []).append(1.0 if wert >= c else 0.0)
        bed = {b: float((v >= c).mean()) if len(v) else None for b, v in arr.items() if b in BEDINGUNGEN}
        schwer = {b: float((arr[b] >= c).mean()) if len(arr[b]) else None for b in SCHWER}
        je[str(c)] = {
            "trefferquote": bed["ruhig"],
            "trefferquote_musik": bed["musik"],
            "trefferquote_alltag": float(np.mean([v for v in bed.values()])) if len(werte["ruhig"]) else None,
            "bedingungen": bed,
            "schwer": schwer,
            "trefferquote_schwer": float(np.mean([v for v in schwer.values()])) if len(werte["ruhig"]) else None,
            "gegenbeispiele": float((gegen_a >= c).mean()) if len(gegen) else None,
            "gegenbeispiele_anzahl": int((gegen_a >= c).sum()),
            "fehlausloeser_pro_stunde": ausloeser[c] / stunden if rede_dateien else None,
            "fehlausloeser_anzahl": ausloeser[c],
            "fehlausloeser_geraeusch_pro_stunde": aus_bg[c] / stunden_bg if dauer_bg else None,
            "fehlausloeser_geraeusch_anzahl": aus_bg[c],
            "fehlausloeser_stille_pro_stunde": aus_st[c] / (dauer_st / 3600) if dauer_st else None,
            "fehlausloeser_stille_anzahl": aus_st[c] if dauer_st else None,
            "je_person": {k: {"trefferquote": round(float(np.mean(v)), 3), "anzahl": len(v)} for k, v in jp.items()},
        }
    return {"stunden": round(stunden, 2), "stunden_geraeusch": round(dauer_bg / 3600, 2),
            "stunden_stille": round(dauer_st / 3600, 2), "positiv": len(werte["ruhig"]),
            "negativ": len(gegen), "je_schwelle": je}


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


def mitteln(a: dict) -> dict:
    """One streaming model that averages several trained candidates (their log-odds, then one sigmoid).

    a: config (training.yaml of the run, for the model shape and the calibration audio of the int8 conversion),
    gewichte [best_weights.weights.h5 of each candidate], modell_args (the mixednet flags they were trained with),
    ziel (folder; the model lands in ziel/<MODELL_DATEI>). Candidates trained from different random starts make
    different mistakes while the word scores high in all of them, so their mean wakes less often by mistake. The
    file needs about as many times the device memory as it has candidates."""
    import argparse

    import tensorflow as tf

    from microwakeword import mixednet, model_train_eval, utils
    from microwakeword import data as input_data
    from microwakeword.layers import modes

    from .bausteine import fehlende_bausteine

    parser = argparse.ArgumentParser()
    parser.add_argument("--training_config")
    mixednet.model_parameters(parser)
    flags = parser.parse_args([f"--training_config={a['config']}", *a["modell_args"]])
    config = model_train_eval.load_config(flags, mixednet)
    config["train_dir"] = a["ziel"]
    os.makedirs(a["ziel"], exist_ok=True)
    teile = []
    for i, w in enumerate(a["gewichte"]):
        m = mixednet.model(flags, shape=config["training_input_shape"], batch_size=1)
        m.load_weights(w)
        # the last layer without its sigmoid: the candidates' log-odds are averaged and one sigmoid follows, so
        # the output keeps the 1/256 steps the device expects (a plain mean of probabilities would be
        # quantized with another scale, and the device would read it twice as high)
        kopf = [lay for lay in m.layers if isinstance(lay, tf.keras.layers.Dense)][-1]
        kopf.activation = tf.keras.activations.linear
        # the 1/n of the mean goes into this layer's weights, so the parts are only added afterwards: a division
        # or multiplication would become a MUL, which the TECHO5 firmware cannot run (the model never wakes there)
        kopf.set_weights([w / len(a["gewichte"]) for w in kopf.get_weights()])
        s = utils.to_streaming_inference(m, config, modes.Modes.STREAM_INTERNAL_STATE_INFERENCE)
        teile.append(s)
        _fortschritt(i + 1, len(a["gewichte"]) + 2)
    eingang = tf.keras.layers.Input(shape=teile[0].input.shape[1:], batch_size=1, dtype=tf.float32,
                                    name="input_audio")
    ausgang = tf.keras.layers.Activation("sigmoid", name="wahrscheinlichkeit")(
        tf.keras.layers.Add(name="mittel")([t(eingang) for t in teile]))
    gesamt = tf.keras.Model(eingang, ausgang, name="gemittelt")
    pfad = os.path.join(a["ziel"], "stream_state_internal")
    archiv = tf.keras.export.ExportArchive()
    archiv.track(gesamt)
    archiv.add_endpoint(name="serve", fn=gesamt.call,
                        input_signature=[tf.TensorSpec(shape=gesamt.input.shape, dtype=tf.float32)])
    archiv.write_out(pfad)
    _fortschritt(len(a["gewichte"]) + 1, len(a["gewichte"]) + 2)
    utils.convert_saved_model_to_tflite(config, input_data.FeatureHandler(config), pfad,
                                        os.path.join(a["ziel"], "tflite_stream_state_internal_quant"),
                                        "stream_state_internal_quant.tflite", quantize=True)
    datei = os.path.join(a["ziel"], "tflite_stream_state_internal_quant", "stream_state_internal_quant.tflite")
    with open(datei, "rb") as f:
        fehlt = fehlende_bausteine(f.read())
    if fehlt:
        raise RuntimeError("averaged model uses operations the devices cannot run: " + ", ".join(fehlt))
    return {"datei": datei, "groesse": os.path.getsize(datei), "teile": len(teile)}


BEFEHLE = {"tts": tts, "merkmale": merkmale, "pruefen": pruefen, "schlank": schlank, "hoeren": hoeren, "omni": omni, "proben": proben, "mitteln": mitteln}

if __name__ == "__main__":
    with open(sys.argv[2], encoding="utf-8") as datei:
        auftrag = json.load(datei)
    ergebnis = BEFEHLE[sys.argv[1]](auftrag)
    print("ERGEBNIS " + json.dumps(ergebnis), flush=True)
