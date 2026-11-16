"""Repair flow: restart Home Assistant so ESPHome reads the new wake word models."""

from __future__ import annotations

from typing import Any

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .zentrale import NEUSTART_MELDUNG


class NeustartFlow(RepairsFlow):
    """Confirm, then restart Home Assistant."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            await self.hass.services.async_call("homeassistant", "restart", blocking=False)
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm")


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    if issue_id != NEUSTART_MELDUNG:
        raise ValueError(issue_id)
    return NeustartFlow()
