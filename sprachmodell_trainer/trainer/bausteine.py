"""Which operations a model uses, and whether the devices can run them (same file as the integration's bausteine.py).

A wake word model is a TFLite flatbuffer. The voice devices do not run full TensorFlow Lite: ESPHome registers
20 operations (micro_wake_word, streaming_model.cpp) and the TECHO5 firmware has its own small interpreter with
16 of them (no MUL, MEAN, PAD or PACK). A model with any other operation loads, but every step fails, so it never
wakes. Home Assistant checks the operation codes here before it puts a version on the devices.

The reader only follows the flatbuffer tables it needs (Model.operator_codes), without TensorFlow.
"""

from __future__ import annotations

import struct

# Builtin operator codes (TFLite schema) that every supported device runs
LAUFEN_UEBERALL: dict[int, str] = {
    0: "ADD",
    1: "AVERAGE_POOL_2D",
    2: "CONCATENATION",
    3: "CONV_2D",
    4: "DEPTHWISE_CONV_2D",
    9: "FULLY_CONNECTED",
    14: "LOGISTIC",
    17: "MAX_POOL_2D",
    22: "RESHAPE",
    45: "STRIDED_SLICE",
    102: "SPLIT_V",
    114: "QUANTIZE",
    129: "CALL_ONCE",
    142: "VAR_HANDLE",
    143: "READ_VARIABLE",
    144: "ASSIGN_VARIABLE",
}

_NAMEN = {18: "MUL", 25: "MEAN", 34: "PAD", 41: "SUB", 42: "DIV", 83: "PACK"}


class KeinModell(ValueError):
    """The bytes are no readable TFLite model."""


def _u32(daten: bytes, pos: int) -> int:
    if pos < 0 or pos + 4 > len(daten):
        raise KeinModell("ausserhalb")
    return int(struct.unpack_from("<I", daten, pos)[0])


def _feld(daten: bytes, tabelle: int, nr: int) -> int | None:
    """Absolute position of field nr of the table at position tabelle, or None if the field is absent."""
    vtabelle = tabelle - struct.unpack_from("<i", daten, tabelle)[0]
    if vtabelle < 0 or vtabelle + 4 > len(daten):
        raise KeinModell("vtabelle")
    groesse = struct.unpack_from("<H", daten, vtabelle)[0]
    eintrag = 4 + 2 * nr
    if eintrag + 2 > groesse:
        return None
    versatz = struct.unpack_from("<H", daten, vtabelle + eintrag)[0]
    return tabelle + versatz if versatz else None


def bausteine(daten: bytes) -> set[int]:
    """Builtin operator codes the model declares (schema: Model field 1 = operator_codes)."""
    if len(daten) < 8 or daten[4:8] != b"TFL3":
        raise KeinModell("kein_tflite")
    try:
        wurzel = _u32(daten, 0)
        feld = _feld(daten, wurzel, 1)
        if feld is None:
            return set()
        vektor = feld + _u32(daten, feld)
        anzahl = _u32(daten, vektor)
        codes: set[int] = set()
        for i in range(anzahl):
            pos = vektor + 4 + 4 * i
            tabelle = pos + _u32(daten, pos)
            alt_feld = _feld(daten, tabelle, 0)  # deprecated_builtin_code (int8)
            neu_feld = _feld(daten, tabelle, 3)  # builtin_code (int32)
            alt = struct.unpack_from("<b", daten, alt_feld)[0] if alt_feld is not None else 0
            neu = struct.unpack_from("<i", daten, neu_feld)[0] if neu_feld is not None else 0
            codes.add(max(alt, neu))
    except struct.error as err:
        raise KeinModell("kaputt") from err
    return codes


def fehlende_bausteine(daten: bytes) -> list[str]:
    """Names of the operations the devices cannot run; empty when the model runs everywhere."""
    return sorted(_NAMEN.get(c, f"OP_{c}") for c in bausteine(daten) if c not in LAUFEN_UEBERALL)
