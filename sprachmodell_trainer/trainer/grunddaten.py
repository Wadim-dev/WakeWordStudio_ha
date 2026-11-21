"""Grunddaten aus oeffentlichen Quellen holen (einmal, dann im Datenordner zwischengespeichert).

- Gegenbeispiele als fertige Merkmale (microWakeWord: Sprache, Partygeraeusch, Umgebung)
- Hintergrundgeraeusche (FMA-Musik, AudioSet) und Raumklang (MIT-Impulsantworten) zum Verfremden
- Gerede in der Sprache des Worts (FLEURS): Training als schwere Gegenbeispiele, Test fuer Fehlausloeser
- Stimmen (Piper) fuer kuenstliche Aufnahmen des Worts
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import shutil
import subprocess
import tarfile
import time
import zipfile
import zlib
from pathlib import Path
from typing import Callable

from . import __version__

import numpy as np
import requests
import soundfile as sf

_LOG = logging.getLogger("trainer.grunddaten")
HF = "https://huggingface.co"
NEG = ("speech", "dinner_party", "no_speech", "dinner_party_eval")
FLEURS = {
    "de": "de_de", "en": "en_us", "ru": "ru_ru", "fr": "fr_fr", "es": "es_419", "it": "it_it", "nl": "nl_nl",
    "pl": "pl_pl", "uk": "uk_ua", "tr": "tr_tr", "pt": "pt_br", "cs": "cs_cz", "sv": "sv_se",
    # more languages: every one with Piper voices that espeak speaks and FLEURS speech for the honest test
    "ar": "ar_eg", "bg": "bg_bg", "ca": "ca_es", "cy": "cy_gb", "da": "da_dk", "el": "el_gr", "et": "et_ee",
    "fa": "fa_ir", "fi": "fi_fi", "hi": "hi_in", "hu": "hu_hu", "id": "id_id", "is": "is_is", "ka": "ka_ge",
    "kk": "kk_kz", "ko": "ko_kr", "lb": "lb_lu", "lv": "lv_lv", "no": "nb_no", "ro": "ro_ro", "sk": "sk_sk",
    "sl": "sl_si", "sr": "sr_rs", "sw": "sw_ke", "vi": "vi_vn",
}
# Fremde Akzente: das Wort auch von Stimmen anderer Sprachen sprechen lassen
FREMD = ("en", "de", "ru", "es", "fr")


LADEN_VERSUCHE = 6
STILLE_ANZAHL = 600  # quiet-room negatives of 3 s (half an hour)


def _laden(url: str, ziel: Path) -> Path:
    """Download with resume: a broken connection (internet gone, server busy) continues where it stopped, up to
    LADEN_VERSUCHE times with growing pauses; an incomplete file is never used."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(ziel.suffix + ".tmp")
    for versuch in range(1, LADEN_VERSUCHE + 1):
        try:
            schon = tmp.stat().st_size if tmp.exists() else 0
            kopf = {"Range": f"bytes={schon}-"} if schon else {}
            with requests.get(url, stream=True, timeout=120, headers=kopf) as r:
                if r.status_code == 416:  # already complete
                    break
                r.raise_for_status()
                if schon and r.status_code != 206:  # server ignores Range: start again
                    schon = 0
                gesamt = schon + int(r.headers.get("Content-Length") or 0)
                with open(tmp, "ab" if schon else "wb") as datei:
                    for stueck in r.iter_content(1 << 20):
                        datei.write(stueck)
            if r.headers.get("Content-Length") and tmp.stat().st_size < gesamt:
                raise OSError(f"incomplete: {tmp.stat().st_size} of {gesamt} bytes")
            break
        except (requests.RequestException, OSError) as err:
            if versuch == LADEN_VERSUCHE:
                raise RuntimeError(f"Download failed after {versuch} attempts: {url.rsplit('/', 1)[-1]}: {err}") from err
            pause = min(300, 10 * 2 ** versuch)
            _LOG.warning("Download of %s interrupted (%s), continuing in %s s", url.rsplit("/", 1)[-1], err, pause)
            time.sleep(pause)
    tmp.replace(ziel)
    return ziel


def _geladen(url: str, datei: Path, arbeit: Callable[[Path], None]) -> None:
    """Download and process a file; a damaged download (broken archive) is deleted and fetched once more."""
    for versuch in (1, 2):
        _laden(url, datei)
        try:
            arbeit(datei)
            return
        except (zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile, EOFError, zlib.error) as err:
            if versuch == 2:
                raise RuntimeError(f"Downloaded file {datei.name} is damaged: {err}") from err
            _LOG.warning("File %s is damaged (%s), downloading it again", datei.name, err)
        finally:
            datei.unlink(missing_ok=True)


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
                shutil.rmtree(ziel, ignore_errors=True)

                def auspacken(z: Path) -> None:
                    with zipfile.ZipFile(z) as archiv:
                        archiv.extractall(self.o / "neg")

                _geladen(f"{HF}/datasets/kahrendt/microwakeword/resolve/main/{name}.zip", self.o / "tmp" / f"{name}.zip",
                         auspacken)
                (ziel / "fertig").touch()
            aus[name] = ziel
        return aus

    def hintergrund(self) -> list[Path]:
        ziele = []
        fma = self.o / "bg" / "fma"
        if not (fma / "fertig").exists():
            self.melden("laden:music")
            fma.mkdir(parents=True, exist_ok=True)

            def musik(z: Path) -> None:
                with zipfile.ZipFile(z) as archiv:
                    for i, info in enumerate(n for n in archiv.infolist() if n.filename.lower().endswith((".mp3", ".wav"))):
                        try:
                            _wav16(archiv.read(info), fma / f"fma{i:05d}.wav")
                        except (zipfile.BadZipFile, zlib.error, EOFError):
                            raise
                        except Exception:  # noqa: BLE001 - one bad song is skipped
                            continue

            _geladen(f"{HF}/datasets/mchl914/fma_xsmall/resolve/main/fma_xs.zip", self.o / "tmp" / "fma.zip", musik)
            (fma / "fertig").touch()
        ziele.append(fma)
        aset = self.o / "bg" / "audioset"
        if not (aset / "fertig").exists():
            self.melden("laden:audioset")
            aset.mkdir(parents=True, exist_ok=True)
            p = _laden(f"{HF}/datasets/agkphysics/AudioSet/resolve/main/data/bal_train/00.parquet", self.o / "tmp" / "as.parquet")
            for i, r in enumerate(_zeilen(p, ["audio"])):
                try:
                    _wav16(r["audio"]["bytes"], aset / f"as{i:05d}.wav")
                except Exception:  # noqa: BLE001
                    continue
            p.unlink()
            (aset / "fertig").touch()
        ziele.append(aset)
        return ziele

    def hausgeraeusche(self) -> Path | None:
        """Real noise from inside homes (CHiME-Home: kitchen, living room, TV, children, appliances, about two hours),
        for the gentle recipe of a thorough run. Optional: if it cannot be fetched, that recipe uses music and
        AudioSet only and the run goes on."""
        haus = self.o / "bg" / "chime"
        if (haus / "fertig").exists():
            return haus
        versuch = self.o / "bg" / "chime_versuch"
        if versuch.exists() and versuch.read_text().strip() == __version__:
            # this version already started it once and the trainer did not come back (killed, out of memory ...):
            # never again in a loop, the gentle recipe goes on with music and noise only
            _LOG.warning("Home noise (CHiME-Home) skipped: the last attempt did not finish")
            return None
        try:
            self.melden("laden:chime")
            versuch.parent.mkdir(parents=True, exist_ok=True)
            versuch.write_text(__version__)
            haus.mkdir(parents=True, exist_ok=True)
            p = _laden(f"{HF}/datasets/InnaBoby/chime_home/resolve/main/data/train-00000-of-00005.parquet",
                       self.o / "tmp" / "chime.parquet")
            n = 0
            # a few rows at a time: the whole file as Python lists needed 6.6 GB and killed small trainers (#49)
            for i, r in enumerate(x["audio"] for x in _zeilen(p, ["audio"])):
                x = np.asarray(r.get("array") or [], dtype=np.float32)
                if r.get("sampling_rate") != 16000 or x.size < 16000:
                    continue
                sf.write(haus / f"chime{i:05d}.wav", np.clip(x, -1, 1), 16000, subtype="PCM_16")
                n += 1
            p.unlink(missing_ok=True)
            if n < 100:
                raise RuntimeError(f"only {n} clips")
            (haus / "fertig").touch()
            versuch.unlink(missing_ok=True)
            return haus
        except Exception as err:  # noqa: BLE001 - optional data, the run goes on without it
            _LOG.warning("Home noise (CHiME-Home) not available, gentle recipe uses music and noise only: %s", err)
            shutil.rmtree(haus, ignore_errors=True)
            versuch.unlink(missing_ok=True)  # a plain error (network ...) may be tried again next run
            return None

    def stille(self, bg: list[Path]) -> Path | None:
        """A quiet room as negatives (werkzeug.ruhe: faint hiss, hum, far-away sounds from the noise sets), made once.
        Optional: if it fails, the run goes on without it."""
        ziel = self.o / "bg" / "stille"
        if (ziel / "fertig").exists():
            return ziel
        try:
            import random

            from .werkzeug import ruhe

            shutil.rmtree(ziel, ignore_errors=True)
            ziel.mkdir(parents=True, exist_ok=True)
            dateien = sorted(str(p) for o in bg for p in Path(o).glob("*.wav"))
            rnd = random.Random(7)
            quellen = rnd.sample(dateien, min(len(dateien), 2000))
            for i in range(STILLE_ANZAHL):
                sf.write(ziel / f"stille{i:04d}.wav", ruhe(rnd, 16000 * 3, quellen), 16000, subtype="PCM_16")
            (ziel / "fertig").touch()
            return ziel
        except Exception as err:  # noqa: BLE001 - optional data, the run goes on without it
            _LOG.warning("Quiet-room negatives could not be made: %s", err)
            shutil.rmtree(ziel, ignore_errors=True)
            return None

    def raumklang(self) -> Path:
        rir = self.o / "bg" / "rir"
        if not (rir / "fertig").exists():
            self.melden("laden:rir")
            rir.mkdir(parents=True, exist_ok=True)
            p = _laden(f"{HF}/api/datasets/davidscripka/MIT_environmental_impulse_responses/parquet/default/train/0.parquet",
                       self.o / "tmp" / "rir.parquet")
            for i, r in enumerate(_zeilen(p)):
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

                def saetze_audio(t: Path, ziel: Path = ziel) -> None:
                    with tarfile.open(t) as archiv:
                        for m in archiv:
                            datei = archiv.extractfile(m) if m.isfile() and m.name.endswith(".wav") else None
                            if datei is None:
                                continue
                            daten = datei.read()
                            try:
                                _wav16(daten, ziel / Path(m.name).name)
                            except Exception:  # noqa: BLE001 - one bad recording is skipped
                                continue

                _geladen(f"{HF}/datasets/google/fleurs/resolve/main/data/{code}/audio/{teil}.tar.gz",
                         self.o / "tmp" / f"{code}_{teil}.tar.gz", saetze_audio)
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


def _zeilen(p: Path, spalten: list[str] | None = None):
    """Rows of a parquet file a few at a time (audio sets are far bigger in memory than on disk)."""
    import pyarrow.parquet as pq

    for b in pq.ParquetFile(p).iter_batches(batch_size=16, columns=spalten):
        yield from b.to_pylist()


def platz_frei(ordner: str) -> float:
    return shutil.disk_usage(ordner).free / 1e9


def befehl(args: list[str], **kw) -> subprocess.Popen:
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, **kw)
