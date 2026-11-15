"""Grunddaten aus oeffentlichen Quellen holen (einmal, dann im Datenordner zwischengespeichert).

- Gegenbeispiele als fertige Merkmale (microWakeWord: Sprache, Partygeraeusch, Umgebung)
- Hintergrundgeraeusche (FMA-Musik, AudioSet) und Raumklang (MIT-Impulsantworten) zum Verfremden
- Gerede in der Sprache des Worts (FLEURS): Training als schwere Gegenbeispiele, Test fuer Fehlausloeser
- Stimmen (Piper) fuer kuenstliche Aufnahmen des Worts
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

import numpy as np
import requests
import soundfile as sf

_LOG = logging.getLogger("trainer.grunddaten")
HF = "https://huggingface.co"
NEG = ("speech", "dinner_party", "no_speech", "dinner_party_eval")
FLEURS = {
    "de": "de_de", "en": "en_us", "ru": "ru_ru", "fr": "fr_fr", "es": "es_419", "it": "it_it", "nl": "nl_nl",
    "pl": "pl_pl", "uk": "uk_ua", "tr": "tr_tr", "pt": "pt_br", "cs": "cs_cz", "sv": "sv_se",
}
# Fremde Akzente: das Wort auch von Stimmen anderer Sprachen sprechen lassen
FREMD = ("en", "de", "ru", "es", "fr")


def _laden(url: str, ziel: Path) -> Path:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(ziel.suffix + ".tmp")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as datei:
            for stueck in r.iter_content(1 << 20):
                datei.write(stueck)
    tmp.replace(ziel)
    return ziel


def _wav16(daten: bytes | str, ziel: Path) -> None:
    import scipy.signal as ss

    x, sr = sf.read(io.BytesIO(daten) if isinstance(daten, bytes) else daten, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if sr != 16000:
        x = ss.resample_poly(x, 16000, sr)
    sf.write(str(ziel), np.clip(x, -1, 1), 16000, subtype="PCM_16")


class Grunddaten:
    def __init__(self, ordner: str, melden: Callable[[str], None]) -> None:
        self.o = Path(ordner) / "grund"
        self.melden = melden

    # --- allgemein --------------------------------------------------------

    def negative(self) -> dict[str, Path]:
        aus = {}
        for name in NEG:
            ziel = self.o / "neg" / name
            if not (ziel / "fertig").exists():
                self.melden(f"laden:{name}")
                z = _laden(f"{HF}/datasets/kahrendt/microwakeword/resolve/main/{name}.zip", self.o / "tmp" / f"{name}.zip")
                shutil.rmtree(ziel, ignore_errors=True)
                with zipfile.ZipFile(z) as archiv:
                    archiv.extractall(self.o / "neg")
                z.unlink()
                (ziel / "fertig").touch()
            aus[name] = ziel
        return aus

    def hintergrund(self) -> list[Path]:
        ziele = []
        fma = self.o / "bg" / "fma"
        if not (fma / "fertig").exists():
            self.melden("laden:music")
            fma.mkdir(parents=True, exist_ok=True)
            z = _laden(f"{HF}/datasets/mchl914/fma_xsmall/resolve/main/fma_xs.zip", self.o / "tmp" / "fma.zip")
            with zipfile.ZipFile(z) as archiv:
                for i, info in enumerate(n for n in archiv.infolist() if n.filename.lower().endswith((".mp3", ".wav"))):
                    try:
                        _wav16(archiv.read(info), fma / f"fma{i:05d}.wav")
                    except Exception:  # noqa: BLE001
                        continue
            z.unlink()
            (fma / "fertig").touch()
        ziele.append(fma)
        aset = self.o / "bg" / "audioset"
        if not (aset / "fertig").exists():
            self.melden("laden:audioset")
            aset.mkdir(parents=True, exist_ok=True)
            import pyarrow.parquet as pq

            p = _laden(f"{HF}/datasets/agkphysics/AudioSet/resolve/main/data/bal_train/00.parquet", self.o / "tmp" / "as.parquet")
            for i, r in enumerate(pq.read_table(p, columns=["audio"]).to_pylist()):
                try:
                    _wav16(r["audio"]["bytes"], aset / f"as{i:05d}.wav")
                except Exception:  # noqa: BLE001
                    continue
            p.unlink()
            (aset / "fertig").touch()
        ziele.append(aset)
        return ziele

    def raumklang(self) -> Path:
        rir = self.o / "bg" / "rir"
        if not (rir / "fertig").exists():
            self.melden("laden:rir")
            rir.mkdir(parents=True, exist_ok=True)
            import pyarrow.parquet as pq

            p = _laden(f"{HF}/api/datasets/davidscripka/MIT_environmental_impulse_responses/parquet/default/train/0.parquet",
                       self.o / "tmp" / "rir.parquet")
            for i, r in enumerate(pq.read_table(p).to_pylist()):
                _wav16(r["audio"]["bytes"], rir / f"rir{i:03d}.wav")
            p.unlink()
            (rir / "fertig").touch()
        return rir

    # --- je Sprache -------------------------------------------------------

    def gerede(self, sprache: str) -> dict[str, Path]:
        """FLEURS: train (schwere Gegenbeispiele + Saetze), test+dev (ehrlicher Test)."""
        code = FLEURS.get(sprache, "en_us")
        aus = {}
        for teil in ("train", "test", "dev"):
            ziel = self.o / "gerede" / sprache / teil
            if not (ziel / "fertig").exists():
                self.melden(f"laden:fleurs {sprache} {teil}")
                ziel.mkdir(parents=True, exist_ok=True)
                t = _laden(f"{HF}/datasets/google/fleurs/resolve/main/data/{code}/audio/{teil}.tar.gz", self.o / "tmp" / f"{code}_{teil}.tar.gz")
                with tarfile.open(t) as archiv:
                    for m in archiv:
                        if m.isfile() and m.name.endswith(".wav"):
                            daten = archiv.extractfile(m).read()
                            try:
                                _wav16(daten, ziel / Path(m.name).name)
                            except Exception:  # noqa: BLE001
                                continue
                t.unlink()
                try:
                    tsv = requests.get(f"{HF}/datasets/google/fleurs/resolve/main/data/{code}/{teil}.tsv", timeout=60).text
                    saetze = sorted({z.split("\t")[2] for z in tsv.splitlines() if z.count("\t") >= 3})
                    (ziel / "saetze.txt").write_text("\n".join(saetze), encoding="utf-8")
                except requests.RequestException:
                    pass
                (ziel / "fertig").touch()
            aus[teil] = ziel
        return aus

    def stimmen(self, sprache: str, je_sprache: int = 6) -> dict[str, list[Path]]:
        """Piper-Stimmen: eigene Sprache (mehrere) und ein paar fremde fuer Akzente."""
        liste = self.o / "stimmen" / "voices.json"
        if not liste.exists():
            _laden(f"{HF}/rhasspy/piper-voices/resolve/main/voices.json", liste)
        alle = json.loads(liste.read_text(encoding="utf-8"))
        aus: dict[str, list[Path]] = {}
        for s in (sprache, *[f for f in FREMD if f != sprache][:3]):
            passend = [v for v in alle.values() if v["language"]["family"] == s]
            passend.sort(key=lambda v: ({"medium": 0, "high": 1, "low": 2, "x_low": 3}.get(v["quality"], 4), v["key"]))
            gesehen, gewaehlt = set(), []
            for v in passend:
                if v["name"] in gesehen:
                    continue
                gesehen.add(v["name"])
                gewaehlt.append(v)
                if len(gewaehlt) >= (je_sprache if s == sprache else 1):
                    break
            for v in gewaehlt:
                for pfad in v["files"]:
                    if pfad.endswith((".onnx", ".onnx.json")):
                        ziel = self.o / "stimmen" / Path(pfad).name
                        if not ziel.exists():
                            self.melden(f"laden:{v['key']}")
                            _laden(f"{HF}/rhasspy/piper-voices/resolve/main/{pfad}", ziel)
                aus.setdefault(s, []).append(self.o / "stimmen" / (v["key"] + ".onnx"))
        return aus

    def aufraeumen(self) -> None:
        shutil.rmtree(self.o / "tmp", ignore_errors=True)


def platz_frei(ordner: str) -> float:
    return shutil.disk_usage(ordner).free / 1e9


def befehl(args: list[str], **kw) -> subprocess.Popen:
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, **kw)
