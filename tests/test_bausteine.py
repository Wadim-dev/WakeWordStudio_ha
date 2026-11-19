"""Reading the operations of a TFLite model without TensorFlow."""

from __future__ import annotations

import os

import pytest

from custom_components.sprachmodell.bausteine import KeinModell, bausteine, fehlende_bausteine

MODELLE = os.path.join(os.path.dirname(__file__), "modelle")


def _lesen(name: str) -> bytes:
    with open(os.path.join(MODELLE, name + ".tflite"), "rb") as datei:
        return datei.read()


def test_bausteine_lesen() -> None:
    assert bausteine(_lesen("laeuft")) == {0, 14, 114}  # ADD, LOGISTIC, QUANTIZE
    assert fehlende_bausteine(_lesen("laeuft")) == []
    assert fehlende_bausteine(_lesen("mul")) == ["MUL"]


@pytest.mark.parametrize("daten", [b"", b"TFL3", b"\x00\x00\x00\x00XXXX" + bytes(40), b"\xff\xff\xff\x00TFL3" + bytes(8)])
def test_kein_modell(daten: bytes) -> None:
    with pytest.raises(KeinModell):
        bausteine(daten)


def test_trainer_hat_dieselbe_datei() -> None:
    """The trainer checks with its own copy of the file (it cannot import the integration); apart from the first
    line both must be the same."""
    pfade = [os.path.join(os.path.dirname(__file__), "..", *teile, "bausteine.py")
             for teile in (("custom_components", "sprachmodell"), ("sprachmodell_trainer", "trainer"))]
    inhalte = []
    for pfad in pfade:
        with open(pfad, encoding="utf-8") as datei:
            inhalte.append(datei.read().split("\n")[1:])
    assert inhalte[0] == inhalte[1]
