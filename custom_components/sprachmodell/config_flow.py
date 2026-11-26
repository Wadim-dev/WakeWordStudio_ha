"""Set up and reconfigure: only the storage folder. Words, devices and everything else live in the panel."""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import TextSelector
import voluptuous as vol

from .const import CONF_ORDNER, DOMAIN, NAME
from .zentrale import DATEI, ablage_standard

_LOGGER = logging.getLogger(__name__)
_PROBE = ".wake_word_studio_probe"


def ordner_pruefen(pfad: str, config_dir: str, alt: str | None = None) -> str | None:
    """Error key if the folder cannot hold the data, otherwise None (creates the folder)."""
    if not os.path.isabs(pfad):
        return "not_absolute"
    verboten = [os.path.join(config_dir, unter) for unter in ("custom_components", ".storage", "www")]
    if pfad in ("/", config_dir) or any(pfad == v or pfad.startswith(v + os.sep) for v in verboten):
        return "not_allowed"
    if alt and (pfad.startswith(alt + os.sep) or alt.startswith(pfad + os.sep)):
        return "nested"
    try:
        os.makedirs(pfad, exist_ok=True)
        probe = os.path.join(pfad, _PROBE)
        with open(probe, "w", encoding="utf-8") as datei:
            datei.write("ok")
        os.remove(probe)
    except OSError:
        return "not_writable"
    if os.listdir(pfad) and not os.path.isfile(os.path.join(pfad, DATEI)):
        return "not_empty"
    return None


def umziehen(alt: str, neu: str) -> bool:
    """Move the data from alt to neu. A folder that already holds data is taken as it is.

    Copies everything first and deletes the old folder only when the copy is complete,
    so a failure never loses data. Returns True if data was moved.
    """
    if os.path.isfile(os.path.join(neu, DATEI)) or not os.path.isdir(alt):
        return False
    kopiert: list[str] = []
    try:
        for name in os.listdir(alt):
            quelle, ziel = os.path.join(alt, name), os.path.join(neu, name)
            if os.path.isdir(quelle):
                shutil.copytree(quelle, ziel)
            else:
                shutil.copy2(quelle, ziel)
            kopiert.append(ziel)
    except OSError:
        for ziel in kopiert:
            if os.path.isdir(ziel):
                shutil.rmtree(ziel, ignore_errors=True)
            else:
                os.remove(ziel)
        raise
    shutil.rmtree(alt, ignore_errors=True)
    return True


def _schema(vorschlag: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_ORDNER, default=vorschlag): TextSelector()})


class SprachmodellConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        fehler: dict[str, str] = {}
        if user_input is not None:
            ordner = os.path.normpath(str(user_input[CONF_ORDNER]).strip())
            if not (problem := await self.hass.async_add_executor_job(ordner_pruefen, ordner, self.hass.config.config_dir)):
                return self.async_create_entry(title=NAME, data={CONF_ORDNER: ordner})
            fehler[CONF_ORDNER] = problem
        vorschlag = str((user_input or {}).get(CONF_ORDNER) or await self.hass.async_add_executor_job(
            ablage_standard, self.hass))
        return self.async_show_form(step_id="user", data_schema=_schema(vorschlag), errors=fehler)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose another storage folder; the data moves along."""
        entry = self._get_reconfigure_entry()
        alt = os.path.normpath(str(
            entry.data.get(CONF_ORDNER) or await self.hass.async_add_executor_job(ablage_standard, self.hass)))
        fehler: dict[str, str] = {}
        if user_input is not None:
            neu = os.path.normpath(str(user_input[CONF_ORDNER]).strip())
            if neu == alt:
                return self.async_abort(reason="unchanged")
            problem = await self.hass.async_add_executor_job(ordner_pruefen, neu, self.hass.config.config_dir, alt)
            if problem is None:
                await self.hass.config_entries.async_unload(entry.entry_id)
                try:
                    await self.hass.async_add_executor_job(umziehen, alt, neu)
                except OSError:
                    _LOGGER.exception("Moving the data from %s to %s failed", alt, neu)
                    problem = "move_failed"
                    await self.hass.config_entries.async_setup(entry.entry_id)
                else:
                    return self.async_update_reload_and_abort(entry, data_updates={CONF_ORDNER: neu})
            fehler[CONF_ORDNER] = problem
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema((user_input or {}).get(CONF_ORDNER) or alt),
            errors=fehler,
            description_placeholders={"current": alt},
        )
