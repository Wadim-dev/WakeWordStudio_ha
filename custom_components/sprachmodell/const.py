"""Feste Werte der Integration Sprachmodell."""

from __future__ import annotations

DOMAIN = "sprachmodell"
NAME = "Sprachmodell"

# Alle Daten (Aufnahmen, Versionen, Trainingsverlauf) liegen hier, damit sie
# im HA-Backup sind und der Trainer sie ueber die Schnittstelle holen kann.
ORDNER_STANDARD = "/share/sprachmodell"

# Eigenes Aktivierungswort in /config/custom_wake_words/<MODELL_ID>.tflite/.json
MODELL_ID_STANDARD = "alisa_wadim"
WORT_STANDARD = "Алиса"
ANZEIGE_STANDARD = "Алиса (eigenes)"

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

# Arten, die der Echo liefert
ARTEN = ("wake", "mistake", "noise", "nearmiss")

# Einstellungen (Optionen des Eintrags)
OPT_PERSONEN = "personen"
OPT_NACHTS = "nachts"
OPT_UHRZEIT = "uhrzeit"
OPT_AUTO = "automatisch_einspielen"
OPT_ERINNERUNG = "erinnerung_tage"
OPT_NUR_WORT1 = "nur_wort_1"
OPT_AUFBEWAHREN = "unbewertet_tage"

STANDARD_OPTIONEN = {
    OPT_PERSONEN: [],
    OPT_NACHTS: True,
    OPT_UHRZEIT: "02:00",
    OPT_AUTO: True,
    OPT_ERINNERUNG: 7,
    OPT_NUR_WORT1: True,
    OPT_AUFBEWAHREN: 60,
}

# Signal an Entitaeten und Seite: Daten haben sich geaendert
SIGNAL_NEU = f"{DOMAIN}_neu"

# Trainer gilt als verbunden, wenn er sich in dieser Zeit gemeldet hat
TRAINER_ONLINE_S = 180
