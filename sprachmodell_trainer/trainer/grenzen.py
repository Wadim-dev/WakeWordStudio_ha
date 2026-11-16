"""Was der Trainer wirklich nutzen darf (Container-Grenzen statt Werte des ganzen Rechners)."""

from __future__ import annotations

import os

GB_JE_PROZESS = 1.5


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


def prozesse(gewuenscht: int | None = None) -> int:
    """Parallele Arbeitsprozesse: nicht mehr als Kerne und nicht mehr, als in den Speicher passen."""
    n = gewuenscht or kerne()
    ram = ram_gb()
    if ram:
        n = min(n, max(1, int(ram / GB_JE_PROZESS)))
    return max(1, n)
