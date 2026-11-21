"""Constants of Wake Word Studio (domain "sprachmodell")."""

from __future__ import annotations

DOMAIN = "sprachmodell"
NAME = "Wake Word Studio"
REPO = "https://github.com/Wadim-dev/WakeWordStudio_ha"
CONF_ORDNER = "ordner"  # storage folder

# Seitenleiste
PANEL_URL = "wake-word-studio"
PANEL_TITEL = NAME
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
SPRACHEN = (
    "de", "en", "ru", "fr", "es", "it", "nl", "pl", "uk", "tr", "pt", "cs", "sv",
    "ar", "bg", "ca", "cy", "da", "el", "et", "fa", "fi", "hi", "hu", "id", "is", "ka", "kk", "ko", "lb", "lv", "no", "ro", "sk", "sl", "sr", "sw", "vi",
)

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
    # Keep the devices' threshold right by itself: the tested value on rollout, later your answers
    "schwelle_automatisch": True,
    # Speech recognition on the trainer listens to new device recordings and confirms those with the word
    "vorpruefen": True,
    # "Thorough": train three candidates per run and keep the best (a run takes about two to three times as long)
    "gruendlich": False,
    # With "thorough": also one model that averages the candidates (fewer false wakes, but it needs about three
    # times the memory on the device). It is only used if it does better than the best single candidate.
    "mitteln": False,
    # Mix the room sound learned on the devices page (claps next to each device) into the training. Only has an
    # effect once at least one device has its room learned
    "raumklang": True,
    "farbe": "",
}

# Einstellungen der ganzen Zentrale
STANDARD_ZENTRALE = {
    "uhrzeit": "02:00",
    # Train at night only once this many recordings were newly reviewed since the last run: a run on almost the
    # same data cannot get better, it only costs hours
    "nachts_min_neu": 20,
    "erinnerung_tage": 7,
    "unbewertet_tage": 60,
    "personen": [],
    # a button entity that restarts the trainer (Proxmox, Portainer, app ...), empty = none. Since 1.0.34 one per
    # trainer in "neustart_tasten" (trainer id -> button); this older single one still counts for its trainer
    "trainer_neustart": "",
    "neustart_tasten": {},
    "alle_plaetze": False,  # auch Aufnahmen von Plaetzen sammeln, die keinem Wort gehoeren
    # where the trainer computes: "auto" = graphics card if the trainer can use one, "cpu" = processor only
    "geraet": "auto",
    # which trainer gets the next run when several are connected: "auto" = the fastest free one, else a trainer id
    "trainer_wahl": "auto",
}

# Signal an Entitaeten und Seite: Daten haben sich geaendert
SIGNAL_NEU = f"{DOMAIN}_neu"

# Published trainer image (ghcr.io, anonymous pull token) and how often to look again while it is not there yet
BILD_TOKEN = "https://ghcr.io/token?scope=repository:wadim-dev/wake-word-studio-trainer:pull"
BILD_MANIFEST = "https://ghcr.io/v2/wadim-dev/wake-word-studio-trainer/manifests"
BILD_PRUEFEN_S = 300

# Trainer gilt als verbunden, wenn er sich in dieser Zeit gemeldet hat
TRAINER_ONLINE_S = 180
# Trainer that has not reported for this long is removed from the list (it can simply connect again)
TRAINER_VERGESSEN_S = 30 * 24 * 3600
# Id of trainers older than 1.0.31, which do not send one
TRAINER_OHNE_ID = "trainer"

# Repairs: a device of a word missing this long, trainings waiting without trainer this long
GERAET_FEHLT_S = 15 * 60
TRAINER_FEHLT_S = 24 * 3600
ENGPASS_S = 15 * 60  # trainer mostly waits for memory or disk this long: tell the user
ENGPASS_WARTEN = 50  # % of time waiting for memory or disk
ENGPASS_CPU = 50  # % processor use below which the trainer counts as held up

# Phasen des Trainings
PHASEN = ["bereit", "wartet", "vorbereiten", "daten", "merkmale", "training", "test", "fertig", "fehler"]
LAEUFT = ("vorbereiten", "daten", "merkmale", "training", "test")
# Training phase as shown by the sensor (stable English state keys)
PHASE_ZUSTAND = {
    "bereit": "ready",
    "wartet": "waiting",
    "vorbereiten": "preparing",
    "daten": "fetching_data",
    "merkmale": "features",
    "training": "training",
    "test": "testing",
    "fertig": "done",
    "fehler": "error",
}

# Automatic threshold: never more than this below the value the version was tested with, never above the maximum
SCHWELLE_SPIELRAUM = 0.03
SCHWELLE_MAX = 0.99

# Pre-review: at most this many recordings per word and request to the trainer
VORPRUEFEN_JE_MAL = 40

# Version of the trainer this studio works with (sprachmodell_trainer/: config.yaml and trainer/__init__.py). It only
# moves when the trainer itself changes, so a release that only changes the studio does not ask for a trainer restart.
TRAINER_VERSION = "1.0.39"
