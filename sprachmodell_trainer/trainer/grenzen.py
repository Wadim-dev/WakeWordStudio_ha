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
    try:
        nutzung = shutil.disk_usage(platz_pfad)
        aus["platz_frei_gb"] = round(nutzung.free / 1024 ** 3, 1)
        aus["platz_gb"] = round(nutzung.total / 1024 ** 3, 1)
    except OSError:
        pass
    return aus
