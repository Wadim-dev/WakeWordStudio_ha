"""Diagnostics: words, devices, training state and trainer, without the trainer key or names of people."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import STANDARD_ZENTRALE

if TYPE_CHECKING:
    from . import SprachConfigEntry

# The key lets a trainer read all recordings; people are personal data
VERDECKT = {"schluessel", "personen", "person", "je_person"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SprachConfigEntry) -> dict[str, Any]:
    z = entry.runtime_data
    woerter = {}
    for wort in z.woerter.values():
        stat = wort.speicher.statistik()
        woerter[wort.id] = {
            "settings": dict(wort.cfg),
            "statistics": {k: stat[k] for k in ("aufnahmen", "bewertet", "offen", "wort", "kein_wort", "test", "alltag")},
            "training": wort.speicher.daten["training"],
            "active_version": wort.speicher.daten["aktiv"],
            "versions": [
                {k: v.get(k) for k in ("nr", "zeit", "status", "groesse", "eingespielt")}
                | {"result": (v.get("bericht") or {}).get("neu")}
                for v in wort.speicher.daten["versionen"]
            ],
            "runs": wort.speicher.daten["laeufe"][-10:],
        }
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "version": entry.version},
            "integration_version": z.version,
            "storage": z.ablage,
            "settings": {k: z.opt(k) for k in STANDARD_ZENTRALE},
            "queue": z.reihe(),
            "trainer": {
                "online": z.trainer_online,
                "last_contact": z.trainer_kontakt.isoformat() if z.trainer_kontakt else None,
                "info": z.trainer_info,
                "all": {tid: {"online": z.ist_online(tid), "paused": z.trainer_pausiert(tid), "info": t["info"]}
                        for tid, t in z.trainer.items()},
                "next": z.ziel_trainer(),
            },
            "devices": z.geraete_zustand(),
            "words": woerter,
            "schluessel": z.schluessel,
        },
        VERDECKT,
    )
