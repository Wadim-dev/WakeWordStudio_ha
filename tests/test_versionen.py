"""Version numbers: the trainer files and the image tag move together and match the trainer version the studio
expects (const.TRAINER_VERSION); the studio itself may be newer when a release only changed the studio."""

import json
from pathlib import Path
import re

from custom_components.sprachmodell.const import TRAINER_VERSION

WURZEL = Path(__file__).parent.parent


def _zahl(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def test_versionen_passen() -> None:
    manifest = json.loads((WURZEL / "custom_components/sprachmodell/manifest.json").read_text())["version"]
    trainer = re.search(r'__version__ = "([^"]+)"', (WURZEL / "sprachmodell_trainer/trainer/__init__.py").read_text())
    bild = re.search(r'^version: "([^"]+)"', (WURZEL / "sprachmodell_trainer/config.yaml").read_text(), re.M)
    panel = re.search(r"^const VERSION = '([^']+)'", (WURZEL / "custom_components/sprachmodell/frontend/sprachmodell-panel.js").read_text(), re.M)
    assert trainer and bild and panel
    assert trainer.group(1) == bild.group(1) == TRAINER_VERSION
    assert panel.group(1) == manifest
    assert _zahl(manifest) >= _zahl(TRAINER_VERSION)
