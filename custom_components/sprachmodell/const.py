"""Feste Werte der Integration Sprachmodell."""

from __future__ import annotations

DOMAIN = "sprachmodell"
NAME = "Sprachmodell"

# Seitenleiste
PANEL_URL = "sprachmodell"
PANEL_TITEL = "Sprachmodell"
PANEL_ICON = "mdi:waveform"
PANEL_ELEMENT = "sprachmodell-panel"
STATIC_URL = f"/{DOMAIN}_static"

# Urteile
WORT = "wort"            # das Wort wurde gesagt
KEIN_WORT = "kein_wort"  # das Wort wurde nicht gesagt
VERWORFEN = "verworfen"  # unbrauchbar (zu leise, kaputt, unklar)
URTEILE = (WORT, KEIN_WORT, VERWORFEN)

# Arten, die ein Geraet liefert (TECHO-Firmware, Schalter "Keep wake clips")
ARTEN = ("wake", "mistake", "noise", "nearmiss")

# Quellen einer Aufnahme
QUELLE_GERAET = "echo"         # vom Geraet geholt (Name bleibt fuer alte Daten)
QUELLE_HOCHGELADEN = "hochgeladen"
QUELLE_BROWSER = "browser"     # in der App aufgenommen

# Sprachen, fuer die der Trainer Grunddaten (fremde Stimmen, Gerede) mitbringt
SPRACHEN = ("de", "en", "ru", "fr", "es", "it", "nl", "pl", "uk", "tr", "pt", "cs", "sv")

# Einstellungen eines Worts
STANDARD_WORT = {
    "wort": "",
    "anzeige": "",
    "modell_id": "",
    "sprache": "en",
    # Knotenname -> Platz ("1" oder "2"); leer = noch keinem Geraet zugeordnet
    "geraete": {},
    "automatisch_einspielen": True,
    "nachts": True,
    "farbe": "",
}

# Einstellungen der ganzen Zentrale
STANDARD_ZENTRALE = {
    "uhrzeit": "02:00",
    "erinnerung_tage": 7,
    "unbewertet_tage": 60,
    "personen": [],
    "alle_plaetze": False,  # auch Aufnahmen von Plaetzen sammeln, die keinem Wort gehoeren
}

# Signal an Entitaeten und Seite: Daten haben sich geaendert
SIGNAL_NEU = f"{DOMAIN}_neu"

# Trainer gilt als verbunden, wenn er sich in dieser Zeit gemeldet hat
TRAINER_ONLINE_S = 180

# Phasen des Trainings
PHASEN = ["bereit", "wartet", "vorbereiten", "daten", "merkmale", "training", "test", "fertig", "fehler"]
LAEUFT = ("vorbereiten", "daten", "merkmale", "training", "test")
