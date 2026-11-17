"""Was der Trainer wirklich nutzen darf (Container-Grenzen statt Werte des ganzen Rechners)."""

from __future__ import annotations

import os

GB_JE_PROZESS = 2.0  # rather fewer processes than running out of memory


def kerne() -> int:
    n = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    try:  # cgroup v2: "max 100000" oder "400000 100000"
        quote, periode = open("/sys/fs/cgroup/cpu.max", encoding="utf-8").read().split()
        if quote != "max":
            n = min(n, max(1, int(int(quote) / int(periode))))
    except (OSError, ValueError):
        pass
    return max(1, n)


def ram_gb() -> float | None:
    gesamt = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as datei:
            for zeile in datei:
                if zeile.startswith("MemTotal:"):
                    gesamt = int(zeile.split()[1]) / 1024 / 1024
    except OSError:
        pass
    for pfad in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            wert = open(pfad, encoding="utf-8").read().strip()
            if wert != "max" and int(wert) < (1 << 60):
                grenze = int(wert) / 1024 ** 3
                gesamt = grenze if gesamt is None else min(gesamt, grenze)
                break
        except (OSError, ValueError):
            continue
    return round(gesamt, 1) if gesamt else None


def frei_gb() -> float | None:
    """Jetzt wirklich freier Speicher: MemAvailable, im Container hoechstens Grenze minus Belegung."""
    frei = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as datei:
            for zeile in datei:
                if zeile.startswith("MemAvailable:"):
                    frei = int(zeile.split()[1]) / 1024 / 1024
    except OSError:
        pass
    try:
        grenze = open("/sys/fs/cgroup/memory.max", encoding="utf-8").read().strip()
        if grenze != "max":
            belegt = int(open("/sys/fs/cgroup/memory.current", encoding="utf-8").read())
            cache = 0
            for zeile in open("/sys/fs/cgroup/memory.stat", encoding="utf-8"):
                if zeile.startswith("inactive_file "):
                    cache = int(zeile.split()[1])
            rest = (int(grenze) - belegt + cache) / 1024 ** 3
            frei = rest if frei is None else min(frei, rest)
    except (OSError, ValueError):
        pass
    return frei


def prozesse(gewuenscht: int | None = None) -> int:
    """Parallele Arbeitsprozesse: nicht mehr als Kerne und nicht mehr, als jetzt in den freien Speicher passen.
    Wenig Speicher = weniger Prozesse = langsamer, aber es laeuft durch."""
    n = gewuenscht or kerne()
    for gb in (ram_gb(), frei_gb()):
        if gb:
            n = min(n, int(gb / GB_JE_PROZESS))
    return max(1, n)


_CPU_VORHER: tuple[float, float] | None = None


def _cpu_sekunden() -> float | None:
    """CPU-Zeit des Containers (cgroup v2), sonst des ganzen Rechners."""
    try:
        for zeile in open("/sys/fs/cgroup/cpu.stat", encoding="utf-8"):
            if zeile.startswith("usage_usec "):
                return int(zeile.split()[1]) / 1e6
    except (OSError, ValueError):
        pass
    try:
        werte = [int(x) for x in open("/proc/stat", encoding="utf-8").readline().split()[1:]]
        return (sum(werte) - werte[3] - (werte[4] if len(werte) > 4 else 0)) / (os.sysconf("SC_CLK_TCK") or 100)
    except (OSError, ValueError, IndexError):
        return None


def auslastung(platz_pfad: str | None = None) -> dict:
    """Jetzt: CPU in % aller erlaubten Kerne (seit dem letzten Aufruf), Speicher belegt/gesamt, freier Plattenplatz."""
    global _CPU_VORHER  # noqa: PLW0603
    import shutil
    import time

    aus: dict = {"kerne": kerne()}
    jetzt, cpu = time.monotonic(), _cpu_sekunden()
    if cpu is not None:
        if _CPU_VORHER and jetzt - _CPU_VORHER[0] > 0.5:
            aus["cpu"] = round(max(0.0, min(100.0, (cpu - _CPU_VORHER[1]) / (jetzt - _CPU_VORHER[0]) / aus["kerne"] * 100)))
        _CPU_VORHER = (jetzt, cpu)
    gesamt, frei = ram_gb(), frei_gb()
    if gesamt:
        aus["ram_gb"] = gesamt
        if frei is not None:
            aus["ram_belegt_gb"] = round(max(0.0, gesamt - frei), 1)
    # share of the last 10 s in which work had to wait (Linux pressure stall information): for the disk, for
    # memory (pages read again because memory is short) and for the processor (limit of the container reached)
    for datei, schluessel in (("io", "platte_warten"), ("memory", "speicher_warten"), ("cpu", "cpu_warten")):
        try:
            for zeile in open(f"/sys/fs/cgroup/{datei}.pressure", encoding="utf-8"):
                if zeile.startswith("some "):
                    aus[schluessel] = round(float(zeile.split("avg10=")[1].split()[0]))
        except (OSError, ValueError, IndexError):
            pass
    if platz_pfad:
        try:
            aus["platz_frei_gb"] = round(shutil.disk_usage(platz_pfad).free / 1024 ** 3, 1)
        except OSError:
            pass
    return aus


def _cgroup_zahl(name: str, ordner: str = "/sys/fs/cgroup") -> int | None:
    """A number from the trainer's control group (None when missing or unlimited)."""
    try:
        with open(os.path.join(ordner, name), encoding="utf-8") as datei:
            text = datei.read().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def steckbrief(platz_pfad: str) -> dict:
    """Swap and free disk space for the trainer profile in Home Assistant (shown with a green/yellow/red rating)."""
    import shutil

    aus: dict = {}
    werte: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as datei:
            for zeile in datei:
                name, _, rest = zeile.partition(":")
                if name in ("SwapTotal", "SwapFree"):
                    werte[name] = int(rest.split()[0])
    except (OSError, ValueError, IndexError):
        pass
    if "SwapTotal" in werte:
        aus["swap_gb"] = round(werte["SwapTotal"] / 1024 ** 2, 1)
        aus["swap_belegt_gb"] = round((werte["SwapTotal"] - werte.get("SwapFree", werte["SwapTotal"])) / 1024 ** 2, 1)
    # In a container /proc/meminfo can show the host's swap. The trainer's own control group knows
    # how much swap the trainer itself uses, so that value wins when it is there.
    eigen = _cgroup_zahl("memory.swap.current")
    if eigen is not None:
        aus["swap_belegt_gb"] = round(eigen / 1024 ** 3, 1)
        grenze = _cgroup_zahl("memory.swap.max")
        if grenze is not None:
            aus["swap_gb"] = round(grenze / 1024 ** 3, 1) if "swap_gb" not in aus else min(aus["swap_gb"], round(grenze / 1024 ** 3, 1))
    try:
        nutzung = shutil.disk_usage(platz_pfad)
        aus["platz_frei_gb"] = round(nutzung.free / 1024 ** 3, 1)
        aus["platz_gb"] = round(nutzung.total / 1024 ** 3, 1)
    except OSError:
        pass
    return aus


def hardware() -> dict:
    """Processor name and graphics cards the trainer can see, for the advice on the Training page.

    NVIDIA: /dev/nvidia0 (passed into the container) and the name from nvidia-smi or /proc/driver. Intel/AMD:
    render devices under /sys/class/drm with their vendor; they cannot speed up this training."""
    import glob
    import shutil
    import subprocess

    aus: dict = {}
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as datei:
            for zeile in datei:
                if zeile.startswith("model name"):
                    aus["prozessor"] = " ".join(zeile.split(":", 1)[1].split())[:80]
                    break
    except OSError:
        pass
    karten: list[dict] = []
    # /dev/nvidia0: Linux with the NVIDIA container toolkit; /dev/dxg: Docker Desktop on Windows (WSL2)
    if os.path.exists("/dev/nvidia0") or (os.path.exists("/dev/dxg") and shutil.which("nvidia-smi")):
        name = "NVIDIA"
        try:
            ausgabe = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                     capture_output=True, text=True, timeout=10, check=False).stdout.strip()
            if ausgabe:
                name = ausgabe.splitlines()[0][:80]
        except (OSError, subprocess.SubprocessError):
            for info in glob.glob("/proc/driver/nvidia/gpus/*/information"):
                try:
                    for zeile in open(info, encoding="utf-8"):
                        if zeile.startswith("Model:"):
                            name = zeile.split(":", 1)[1].strip()[:80]
                except OSError:
                    pass
        karten.append({"art": "nvidia", "name": name})
    hersteller = {"0x8086": "intel", "0x1002": "amd", "0x10de": "nvidia"}
    for karte in sorted(glob.glob("/sys/class/drm/renderD*/device/vendor")):
        try:
            art = hersteller.get(open(karte, encoding="utf-8").read().strip())
        except OSError:
            continue
        if art and art != "nvidia" and not any(k["art"] == art for k in karten):
            karten.append({"art": art, "name": "AMD graphics" if art == "amd" else "Intel graphics"})
    aus["grafik"] = karten
    return aus



# The GPU image sets TRAINER_BILD=gpu. Whether TensorFlow can really train on the card is only known after trying:
# a card can be found but not usable (missing CUDA libraries, a card too old for the GPU code TensorFlow ships).
_PROBE = r"""
import json, os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
try:
    import tensorflow as tf
    karten = tf.config.list_physical_devices("GPU")
    if not karten:
        print(json.dumps({"gpu": False, "grund": "keine_karte"}))
    else:
        d = tf.config.experimental.get_device_details(karten[0])
        with tf.device("/GPU:0"):
            x = tf.random.normal((8, 49, 40, 1))
            y = tf.keras.layers.Conv2D(8, 3)(x)
            z = float(tf.reduce_sum(tf.matmul(tf.reshape(y, (8, -1)), tf.reshape(y, (8, -1)), transpose_b=True)))
        cc = d.get("compute_capability")
        print(json.dumps({"gpu": z == z, "name": d.get("device_name", ""),
                          "cc": ".".join(map(str, cc)) if cc else ""}))
except Exception as err:  # noqa: BLE001
    print(json.dumps({"gpu": False, "grund": "nicht_unterstuetzt", "fehler": str(err)[-300:]}))
"""
_beschleuniger: dict | None = None


def beschleuniger(warten: bool = True) -> dict:
    """{"bild": "gpu"|"cpu", "gpu": bool, "name", "cc", "grund"}; the probe runs once per trainer start.
    warten=False: do not block, answer {"bild": "gpu", "pruefe": True} while the probe has not finished."""
    global _beschleuniger  # noqa: PLW0603
    if _beschleuniger is not None:
        return _beschleuniger
    if not warten:
        return {"bild": os.environ.get("TRAINER_BILD") or "cpu", "gpu": False, "pruefe": True}
    if os.environ.get("TRAINER_BILD") != "gpu":
        _beschleuniger = {"bild": "cpu", "gpu": False}
        return _beschleuniger
    import json
    import subprocess
    import sys

    aus = {"gpu": False, "grund": "nicht_unterstuetzt"}
    try:
        lauf = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, timeout=300,
                              check=False)
        zeilen = [z for z in lauf.stdout.splitlines() if z.startswith("{")]
        if zeilen:
            aus = json.loads(zeilen[-1])
        else:
            aus["fehler"] = (lauf.stderr or "")[-300:]
    except (OSError, subprocess.SubprocessError, ValueError) as err:
        aus["fehler"] = str(err)[-300:]
    if aus.get("grund") == "keine_karte" and any(k["art"] == "nvidia" for k in hardware()["grafik"]):
        # the card is passed in, but TensorFlow could not load its libraries: a fault of the image, not of the setup
        aus["grund"] = "nicht_geladen"
    _beschleuniger = {"bild": "gpu", **aus}
    return _beschleuniger


# Short speed test (about a minute): how fast this trainer prepares data (all processes, the processor's share of a
# run) and trains (a small model shaped like the wake word models, on the processor and on the graphics card).
# Home Assistant scales the durations of real runs with these numbers to estimate other trainers.
_TEMPO_VORBEREITEN = r"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np

def stueck(k):
    rnd = np.random.default_rng(k)
    x = rnd.standard_normal(16000 * 3).astype(np.float32)
    for _ in range(6):
        f = np.abs(np.fft.rfft(x.reshape(-1, 480) * np.hanning(480), axis=1))
        x = (x + np.convolve(x, np.ones(9) / 9, "same")).astype(np.float32)
    return float(f.sum())

if __name__ == "__main__":
    n = int(sys.argv[1])
    with ProcessPoolExecutor(n) as pool:
        list(pool.map(stueck, range(n)))
        t = time.monotonic()
        list(pool.map(stueck, range(2400)))
        print(json.dumps({"s": time.monotonic() - t}))
"""
_TEMPO_RECHNEN = r"""
import json, os, time
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
import numpy as np
import tensorflow as tf
x = np.random.default_rng(1).standard_normal((2048, 98, 40)).astype("float32")
y = (np.random.default_rng(2).random(2048) > 0.5).astype("float32")
m = tf.keras.Sequential([tf.keras.Input((98, 40)), tf.keras.layers.Reshape((98, 1, 40)),
    tf.keras.layers.Conv2D(32, (5, 1), activation="relu"), tf.keras.layers.DepthwiseConv2D((9, 1), activation="relu"),
    tf.keras.layers.Conv2D(64, 1, activation="relu"), tf.keras.layers.DepthwiseConv2D((11, 1), activation="relu"),
    tf.keras.layers.Conv2D(64, 1, activation="relu"), tf.keras.layers.GlobalAveragePooling2D(),
    tf.keras.layers.Dense(1, activation="sigmoid")])
m.compile("adam", "binary_crossentropy")
m.fit(x[:256], y[:256], batch_size=128, epochs=1, verbose=0)
t = time.monotonic()
m.fit(x, y, batch_size=128, epochs=8, verbose=0)
print(json.dumps({"s": time.monotonic() - t}))
"""
_tempo: dict | None = None


def _tempo_lauf(skript: str, args: list[str], umgebung: dict[str, str] | None = None) -> float | None:
    import json
    import subprocess
    import sys

    try:
        lauf = subprocess.run([sys.executable, "-c", skript, *args], capture_output=True, text=True, timeout=300,
                              check=False, env={**os.environ, **(umgebung or {})})
        zeilen = [z for z in lauf.stdout.splitlines() if z.startswith("{")]
        if zeilen:
            wert = json.loads(zeilen[-1])
            return round(float(wert["s"]), 2)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        pass
    return None


def tempo(daten: str | None = None, warten: bool = True) -> dict:
    """{"vorbereiten_s", "rechnen_cpu_s", "rechnen_gpu_s"} (seconds, smaller is faster), measured once per trainer
    version and hardware and kept in the data folder. warten=False: what is known now ({} while it is measured)."""
    global _tempo  # noqa: PLW0603
    import json

    if _tempo is not None or not warten:
        return dict(_tempo or {})
    from . import __version__

    b = beschleuniger()
    schluessel = "|".join([__version__, b.get("bild", "cpu"), str(b.get("name") or ""), str(prozesse()),
                           os.environ.get("TF_NUM_INTRAOP_THREADS", "")])
    pfad = os.path.join(daten or os.environ.get("DATEN", "/data"), "tempo.json")
    try:
        with open(pfad, encoding="utf-8") as datei:
            gespeichert = json.load(datei)
        if gespeichert.get("schluessel") == schluessel:
            _tempo = gespeichert["werte"]
            return dict(_tempo)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    werte: dict = {}
    if (s := _tempo_lauf(_TEMPO_VORBEREITEN, [str(prozesse())])) is not None:
        werte["vorbereiten_s"] = s
    if (s := _tempo_lauf(_TEMPO_RECHNEN, [], {"CUDA_VISIBLE_DEVICES": "-1"})) is not None:
        werte["rechnen_cpu_s"] = s
    if b.get("gpu") and (s := _tempo_lauf(_TEMPO_RECHNEN, [], {"TF_FORCE_GPU_ALLOW_GROWTH": "true"})) is not None:
        werte["rechnen_gpu_s"] = s
    try:
        with open(pfad, "w", encoding="utf-8") as datei:
            json.dump({"schluessel": schluessel, "werte": werte}, datei)
    except OSError:
        pass
    _tempo = werte
    return dict(werte)
