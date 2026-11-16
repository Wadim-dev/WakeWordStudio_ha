# Wake Word Studio Trainer

Trains your own wake words for the **Wake Word Studio** integration. It runs on its own: every 20 seconds it asks Home
Assistant whether a word should be trained (button *Train now*, or at night when there are new ratings), does the
whole job and sends the result back. The app in the sidebar shows progress, and if the new model is better in an
honest test it is put on your voice satellites automatically.

## What a run does

1. **Base data** (first run only, about 8 GB, cached in the app's data folder):
   negative features from the microWakeWord project, background music and noise, room impulse responses,
   speech in the word's language (FLEURS) and Piper voices.
2. **Your clips**: everything you rated in the app (word said / not said). Clips marked as *test* are never trained on.
3. **Synthetic voices**: thousands of versions of your word spoken by several voices of the word's language,
   with other languages' accents, plus similar-sounding words and everyday phrases as negatives.
4. **Features** with random background noise, room echo, volume and pitch changes.
5. **Training** (microWakeWord, mixednet). The next run fine-tunes the previous one, which is much faster.
6. **Honest test** of the new model and the active one on the same test set: recognised in quiet and with music,
   negatives triggered, false triggers per hour on real speech. The detection threshold is chosen so that the false
   triggers stay below your target. Only a better model is installed.

## Options

| Option | Meaning |
|---|---|
| `threads` | CPU threads to use, `0` = all |
| `ziel_fehlausloeser` | Target false triggers per hour of speech (default 1.0). Lower = stricter threshold |
| `schritte` | Training steps for a full run, `0` = automatic (15 000, fine-tuning 6 000) |

## Requirements

- 64-bit system (amd64 or aarch64), at least 4 GB free RAM (it adapts: less memory = slower), 10 GB free disk.
- A full first run takes a few hours on a small PC, later runs are shorter.

## Running it on another computer (Docker)

A faster computer in your network can do the training instead. Take the key from
**Wake Word Studio → Settings → Trainer** and start:

```bash
docker run -d --name wake-word-studio-trainer --restart unless-stopped \
  -e HA_URL=http://homeassistant.local:8123 \
  -e KEY=<key from the panel> \
  -v wake-word-studio-trainer:/data \
  ghcr.io/wadim-dev/wake-word-studio-trainer:latest
```

On **Proxmox VE** one line in the Proxmox shell creates its own container that updates itself on every restart:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Wadim-dev/wake-word-studio_ha/main/sprachmodell_trainer/proxmox.sh)" -- http://homeassistant.local:8123 <key>
```

Optional variables: `THREADS`, `ZIEL_FEHLAUSLOESER`, `SCHRITTE`, `TRAINER_NAME`. Only one trainer should run at a time.

---

# Deutsch

Der Trainer holt alle 20 Sekunden in Home Assistant ab, ob ein Wort trainiert werden soll (Knopf **Jetzt
trainieren** oder nachts bei neuen Bewertungen), erledigt alles selbst und schickt das Ergebnis zurück. Ist das neue
Modell im ehrlichen Test besser, landet es von selbst auf den Geräten.

Der erste Lauf lädt einmal etwa 8 GB Grunddaten (Gegenbeispiele, Musik, Raumklang, Gerede in der Sprache des Worts,
Stimmen). Danach trainiert er auf den bewerteten Aufnahmen plus künstlichen Stimmen, testet neu gegen alt auf
denselben Testaufnahmen und wählt die Schwelle so, dass die Fehlauslöser unter dem Ziel bleiben.

Einstellungen: `threads` (0 = alle), `ziel_fehlausloeser` (pro Stunde Gerede, Standard 1,0),
`schritte` (0 = automatisch). Für einen anderen Rechner den Docker- oder Proxmox-Befehl oben nehmen, Schlüssel aus
**Wake Word Studio → Einstellungen → Trainer**.
