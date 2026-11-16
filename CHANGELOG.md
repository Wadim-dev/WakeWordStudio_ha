# Changelog

## 1.0.2
- Logo with "for Home Assistant" (integration, trainer app, README and title image).

## 1.0.1
- Training keeps running when Home Assistant restarts or updates: the trainer waits up to 30 minutes for Home Assistant (all requests, including sending the result) and repeats its full progress every 20 seconds, so the panel shows the run again right after the restart. Home Assistant gives the trainer 20 minutes to report back before a run counts as lost.

## 1.0.0
- New name: **Wake Word Studio** (repository `Wadim-dev/wake-word-studio_ha`, panel `/wake-word-studio`). Entity IDs of existing installations stay the same.
- Any ESPHome voice device with a *Wake word* select is found by itself and shown with the name you gave it; firmware with wake clips also delivers recordings.
- Storage folder chosen at setup and changeable via *Reconfigure* (data moves along, copied first, old folder deleted only after a complete copy).
- Integration quality scale Gold: diagnostics (key and people redacted), repairs for missing devices and missing trainer, translated entities, states, attributes and errors, icons, stale device removal.
- Settings, words, rollout and deleting only for administrators.
- Updates now come through the Marketplace; the own update entity is removed.
- Trainer image `ghcr.io/wadim-dev/wake-word-studio-trainer` (the old name keeps receiving updates), variable `KEY` (`SCHLUESSEL` still works), messages in English; Proxmox script with the new name, switches old containers over with `update`.
- Logo, screenshots and README in English and German.

## 0.2.1
- Trainer adapts to its machine: CPU quota, memory limit and currently free memory decide how many worker processes run (less memory = slower, but it finishes).
- A trainer restart (crash, out of memory, update) now ends a lost run immediately instead of after 20 minutes.
- Proxmox script: the trainer updates itself every time its container starts (restart = update, also from the Proxmox integration in Home Assistant). `update` switches an existing container over.

## 0.2.0
- Wake word hub: any number of words, any language, devices and wake word slot freely selectable per word.
- New pages: all words, devices, settings, new word wizard (can take over an existing model), word settings.
- Record the word or counter examples directly in the browser.
- One device and entity set per word, created and removed automatically.
- Trainer as Home Assistant app or Docker container (microWakeWord): base data, synthetic voices in the word's
  language and foreign accents, similar-sounding words as negatives, fine-tuning, honest test new vs. current
  with automatic threshold, progress and cancel in the app.
- Interface in English and German.

## 0.1.0
- Erste Version: Aufnahmen der Echos abholen, in der Seitenleiste prüfen (mit Vorschlägen und Tastenkürzeln), Zips hochladen, Trainingsfortschritt, Qualität mit Schwelle aus deinen Antworten, Versionen einspielen ohne Neustart, Schnittstelle für den Trainer.
