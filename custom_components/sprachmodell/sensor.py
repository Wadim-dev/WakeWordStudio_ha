"""Sensoren: Pruefliste und Trainer (Zentrale); Training, Version, Qualitaet (je Wort)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PHASEN
from .entity import SprachEntitaet, plattform_anmelden


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    z = entry.runtime_data
    plattform_anmelden(
        z, "sensor", [Pruefliste(z), Trainer(z)],
        lambda w: [WortPruefliste(z, w), Training(z, w), Version(z, w), Trefferquote(z, w), Fehlausloeser(z, w)],
        async_add_entities,
    )


class Pruefliste(SprachEntitaet, SensorEntity):
    """Wie viele Aufnahmen aller Woerter auf Pruefung warten."""

    _attr_icon = "mdi:playlist-check"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z) -> None:
        super().__init__(z, "pruefliste")

    @property
    def native_value(self) -> int:
        return self.z.offen_gesamt()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"je_wort": {w.wort: len(w.speicher.offen()) for w in self.z.woerter.values()}}


class Trainer(SprachEntitaet, SensorEntity):
    """Ist ein Trainer verbunden, und was macht er?"""

    _attr_icon = "mdi:school-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["getrennt", "bereit", "trainiert"]

    def __init__(self, z) -> None:
        super().__init__(z, "trainer")

    @property
    def native_value(self) -> str:
        if not self.z.trainer_online:
            return "getrennt"
        laeuft = any(w.speicher.daten["training"].get("phase") in PHASEN[2:7] for w in self.z.woerter.values())
        return "trainiert" if laeuft else "bereit"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "kontakt": self.z.trainer_kontakt.isoformat() if self.z.trainer_kontakt else None,
            "warteschlange": [self.z.woerter[w].wort for w in self.z.reihe()],
            **{k: v for k, v in (self.z.trainer_info or {}).items() if k in ("version", "cpu", "ram_gb", "gpu", "name")},
        }


class WortPruefliste(SprachEntitaet, SensorEntity):
    _attr_icon = "mdi:playlist-check"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z, w) -> None:
        super().__init__(z, "pruefliste", w)

    @property
    def native_value(self) -> int:
        return len(self.w.speicher.offen())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stat = self.w.speicher.statistik()
        return {
            "je_geraet": stat["offen_je_echo"],
            "oldest_waiting_since": stat["aeltestes_offen"],
            "bewertet": stat["bewertet"],
        }


class Training(SprachEntitaet, SensorEntity):
    """Was der Trainer fuer dieses Wort gerade macht, mit Fortschritt."""

    _attr_icon = "mdi:school-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PHASEN

    def __init__(self, z, w) -> None:
        super().__init__(z, "training", w)

    @property
    def native_value(self) -> str:
        phase = self.w.speicher.daten["training"].get("phase") or "bereit"
        return phase if phase in PHASEN else "bereit"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self.w.speicher.daten["training"]
        return {
            "prozent": t.get("prozent"),
            "schritt": t.get("schritt"),
            "restzeit_min": t.get("restzeit_min"),
            "seit": t.get("seit"),
            "neue_bewertungen": self.w.neue_seit_letztem_lauf(),
        }


class Version(SprachEntitaet, SensorEntity):
    _attr_icon = "mdi:tag-outline"

    def __init__(self, z, w) -> None:
        super().__init__(z, "version", w)

    @property
    def native_value(self) -> str | None:
        v = self.w.aktive_version()
        return f"v{v['nr']}" if v else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.w.aktive_version() or {}
        return {"eingespielt": v.get("eingespielt"), "sha256": v.get("sha256")}


def _neu(w) -> dict[str, Any]:
    return ((w.aktive_version() or {}).get("bericht") or {}).get("neu") or {}


class Trefferquote(SprachEntitaet, SensorEntity):
    """Erkannt im ehrlichen Test (zurueckgehaltene Aufnahmen)."""

    _attr_icon = "mdi:bullseye-arrow"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z, w) -> None:
        super().__init__(z, "trefferquote", w)

    @property
    def native_value(self) -> float | None:
        wert = _neu(self.w).get("trefferquote")
        return round(wert * 100, 1) if isinstance(wert, int | float) else None


class Fehlausloeser(SprachEntitaet, SensorEntity):
    """Fehlausloeser pro Stunde Gerede in der Sprache des Worts (Test des Trainers)."""

    _attr_icon = "mdi:alarm-light-outline"
    _attr_native_unit_of_measurement = "/h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z, w) -> None:
        super().__init__(z, "fehlausloeser", w)

    @property
    def native_value(self) -> float | None:
        wert = _neu(self.w).get("fehlausloeser_pro_stunde")
        return round(wert, 2) if isinstance(wert, int | float) else None
