"""Sensoren: Pruefliste (wie sensor.visionstate_review_queue), Training, Version."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SprachEntitaet

PHASEN = ["bereit", "wartet", "vorbereiten", "daten", "merkmale", "training", "test", "fertig", "fehler"]


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    z = entry.runtime_data
    async_add_entities([Pruefliste(z), Training(z), Version(z), Trefferquote(z), Fehlausloeser(z)])


class Pruefliste(SprachEntitaet, SensorEntity):
    """Wie viele Aufnahmen auf Pruefung warten."""

    _attr_icon = "mdi:playlist-check"
    _attr_native_unit_of_measurement = "Aufnahmen"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z) -> None:
        super().__init__(z, "pruefliste")

    @property
    def native_value(self) -> int:
        return len(self.z.speicher.offen())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stat = self.z.speicher.statistik()
        return {
            "je_echo": stat["offen_je_echo"],
            "oldest_waiting_since": stat["aeltestes_offen"],
            "bewertet": stat["bewertet"],
            "stand": self.z.speicher.stand,
        }


class Training(SprachEntitaet, SensorEntity):
    """Was der Trainer gerade macht, mit Fortschritt."""

    _attr_icon = "mdi:school-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PHASEN

    def __init__(self, z) -> None:
        super().__init__(z, "training")

    @property
    def native_value(self) -> str:
        phase = self.z.speicher.daten["training"].get("phase") or "bereit"
        return phase if phase in PHASEN else "bereit"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self.z.speicher.daten["training"]
        return {
            "prozent": t.get("prozent"),
            "schritt": t.get("schritt"),
            "restzeit_min": t.get("restzeit_min"),
            "seit": t.get("seit"),
            "trainer_verbunden": self.z.trainer_online,
            "neue_bewertungen": self.z.neue_seit_letztem_lauf(),
        }


def _aktiv(z) -> dict[str, Any] | None:
    nr = z.speicher.daten.get("aktiv")
    return z.speicher.version(nr) if nr else None


class Version(SprachEntitaet, SensorEntity):
    _attr_icon = "mdi:tag-outline"

    def __init__(self, z) -> None:
        super().__init__(z, "version")

    @property
    def native_value(self) -> str | None:
        v = _aktiv(self.z)
        return f"v{v['nr']}" if v else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = _aktiv(self.z) or {}
        return {"eingespielt": v.get("eingespielt"), "sha256": v.get("sha256")}


class Trefferquote(SprachEntitaet, SensorEntity):
    """Erkannt im ehrlichen Test (zurueckgehaltene Aufnahmen)."""

    _attr_icon = "mdi:bullseye-arrow"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z) -> None:
        super().__init__(z, "trefferquote")

    @property
    def native_value(self) -> float | None:
        b = ((_aktiv(self.z) or {}).get("bericht") or {}).get("neu") or {}
        wert = b.get("trefferquote")
        return round(wert * 100, 1) if isinstance(wert, int | float) else None


class Fehlausloeser(SprachEntitaet, SensorEntity):
    """Fehlausloeser pro Stunde russisches Gerede (Test des Trainers)."""

    _attr_icon = "mdi:alarm-light-outline"
    _attr_native_unit_of_measurement = "pro Stunde"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z) -> None:
        super().__init__(z, "fehlausloeser")

    @property
    def native_value(self) -> float | None:
        b = ((_aktiv(self.z) or {}).get("bericht") or {}).get("neu") or {}
        wert = b.get("fehlausloeser_pro_stunde")
        return round(wert, 2) if isinstance(wert, int | float) else None
