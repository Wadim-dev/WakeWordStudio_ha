"""Sensors: review queue and trainer (hub); review queue, training, version and quality (per word)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LAEUFT, PHASE_ZUSTAND
from .entity import SprachEntitaet, plattform_anmelden

if TYPE_CHECKING:
    from . import SprachConfigEntry
    from .zentrale import Wort, Zentrale

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: SprachConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    z = entry.runtime_data
    plattform_anmelden(
        z, "sensor", [Pruefliste(z), Trainer(z)],
        lambda w: [WortPruefliste(z, w), Training(z, w), Version(z, w), Trefferquote(z, w), Fehlausloeser(z, w)],
        async_add_entities,
    )


class Pruefliste(SprachEntitaet, SensorEntity):
    """How many recordings of all words wait for review."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z: Zentrale) -> None:
        super().__init__(z, "pruefliste")

    @property
    def native_value(self) -> int:
        return self.z.offen_gesamt()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"per_word": {w.wort: len(w.speicher.offen()) for w in self.z.woerter.values()}}


class Trainer(SprachEntitaet, SensorEntity):
    """Is a trainer connected, and what is it doing?"""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["disconnected", "ready", "training"]  # noqa: RUF012 - HA attribute
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, z: Zentrale) -> None:
        super().__init__(z, "trainer")

    @property
    def native_value(self) -> str:
        if not self.z.trainer_online:
            return "disconnected"
        laeuft = any(w.speicher.daten["training"].get("phase") in LAEUFT for w in self.z.woerter.values())
        return "training" if laeuft else "ready"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self.z.trainer_info or {}
        return {
            "last_contact": self.z.trainer_kontakt.isoformat() if self.z.trainer_kontakt else None,
            "queue": [self.z.woerter[w].wort for w in self.z.reihe()],
            **{k: info[k] for k in ("name", "version", "cpu", "ram_gb", "gpu") if k in info},
        }


class WortPruefliste(SprachEntitaet, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, z: Zentrale, w: Wort) -> None:
        super().__init__(z, "pruefliste", w)

    @property
    def native_value(self) -> int:
        return len(self.wort.speicher.offen())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stat = self.wort.speicher.statistik()
        return {
            "per_device": stat["offen_je_echo"],
            "oldest_waiting_since": stat["aeltestes_offen"],
            "reviewed": stat["bewertet"],
        }


class Training(SprachEntitaet, SensorEntity):
    """What the trainer is doing for this word, with progress."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(PHASE_ZUSTAND.values())  # noqa: RUF012 - HA attribute

    def __init__(self, z: Zentrale, w: Wort) -> None:
        super().__init__(z, "training", w)

    @property
    def native_value(self) -> str:
        return PHASE_ZUSTAND.get(self.wort.speicher.daten["training"].get("phase") or "bereit", "ready")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self.wort.speicher.daten["training"]
        return {
            "progress": t.get("prozent"),
            "step": t.get("schritt"),
            "minutes_left": t.get("restzeit_min"),
            "since": t.get("seit"),
            "new_reviews": self.wort.neue_seit_letztem_lauf(),
        }


class Version(SprachEntitaet, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, z: Zentrale, w: Wort) -> None:
        super().__init__(z, "version", w)

    @property
    def native_value(self) -> str | None:
        v = self.wort.aktive_version()
        return f"v{v['nr']}" if v else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.wort.aktive_version() or {}
        return {"rolled_out": v.get("eingespielt"), "sha256": v.get("sha256")}


def _neu(w: Wort) -> dict[str, Any]:
    return ((w.aktive_version() or {}).get("bericht") or {}).get("neu") or {}


class Trefferquote(SprachEntitaet, SensorEntity):
    """Recognised in the honest test (held-back recordings)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, z: Zentrale, w: Wort) -> None:
        super().__init__(z, "trefferquote", w)

    @property
    def native_value(self) -> float | None:
        wert = _neu(self.wort).get("trefferquote")
        return round(wert * 100, 1) if isinstance(wert, int | float) else None


class Fehlausloeser(SprachEntitaet, SensorEntity):
    """False wakes per hour of speech in the word's language (trainer test)."""

    _attr_native_unit_of_measurement = "/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, z: Zentrale, w: Wort) -> None:
        super().__init__(z, "fehlausloeser", w)

    @property
    def native_value(self) -> float | None:
        wert = _neu(self.wort).get("fehlausloeser_pro_stunde")
        return round(wert, 2) if isinstance(wert, int | float) else None
