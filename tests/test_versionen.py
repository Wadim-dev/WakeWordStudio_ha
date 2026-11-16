"""All version numbers move together: integration, trainer and the trainer image tag."""

import json
from pathlib import Path
import re

WURZEL = Path(__file__).parent.parent


def test_versionen_gleich() -> None:
    manifest = json.loads((WURZEL / "custom_components/sprachmodell/manifest.json").read_text())["version"]
    trainer = re.search(r'__version__ = "([^"]+)"', (WURZEL / "sprachmodell_trainer/trainer/__init__.py").read_text())
    bild = re.search(r'^version: "([^"]+)"', (WURZEL / "sprachmodell_trainer/config.yaml").read_text(), re.M)
    assert trainer and bild
    assert manifest == trainer.group(1) == bild.group(1)
