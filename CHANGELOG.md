# Changelog

## 0.2.1
- Trainer adapts to its machine: CPU quota, memory limit and currently free memory decide how many worker processes run (less memory = slower, but it finishes).
- A trainer restart (crash, out of memory, update) now ends a lost run immediately instead of after 20 minutes.
- Proxmox script: `update` mode pulls the newest trainer image and keeps settings and data.

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
