# Changelog

## 1.0.7
- Fix: on machines with little memory (about 5 GB) training was killed at its first evaluation (step 500), because microWakeWord loads the complete validation sets of the base data into memory. Evaluation now uses evenly chosen samples that fit the memory (about 800 per GB per set, ambient audio about 8 minutes per GB); training still uses all data.
- If memory runs out anyway, the system stops the computing step first, not the trainer service.
- A run lost because the trainer restarted is no longer an error: Home Assistant queues it again and the trainer starts it with less memory (up to 2 times).
- The self-test also covers choosing the evaluation data.
- Interrupted downloads of the base data continue where they stopped (up to 6 attempts with growing pauses); a damaged archive is downloaded once more instead of failing.
- If Home Assistant is away for more than 30 minutes when a run finishes, the trainer keeps the model and delivers it as soon as Home Assistant is back.
- If the trainer's disk is almost full (below 0.5 GB), the step stops with a clear message instead of writing broken files.
- A queued run is never handed to two trainers at the same time; evaluation data of an older memory size is removed.

## 1.0.6
- Fix: training stopped at its first evaluation because TensorBoard was missing in the trainer image.
- Every trainer image now runs a complete tiny training before it is published (features with worker pool and augmentation, training with evaluation, model conversion, model test).
- Short runs evaluate too; feature files that cannot be read are listed in the log, and a step without any features fails clearly.

## 1.0.5
- **Fix: training could never get past "Fetching recordings".** The trainer image installed microWakeWord without its `audio` and `layers` folders (they have no `__init__.py`), so computing features failed at once; with the old worker pool that looked like a hang at 8 %. microWakeWord is now installed completely, and the image is only published if every module the trainer uses can be imported.
- Trainer never hangs: every step runs in its own process group under a watchdog.
  - No output and no computing for 10 minutes: the step is stopped.
  - Less than 0.25 GB memory left for 30 seconds: the step is stopped before the system's out-of-memory killer picks a process.
  - Killed by the system: recognised as out of memory.
- A stopped step runs again, slower but safer: features with half the processes and then one, training with smaller batches and fewer threads (continuing from its last checkpoint), voices and tests simply again. Only after three attempts the run ends with a clear error.
- Fewer parallel processes from the start (2 GB memory per process instead of 1.5).
- Cancelling stops all workers of a step, none are left behind.

## 1.0.4
- Trainer: if a worker process is stopped while computing features (usually out of memory), the step no longer hangs forever. It reports a clear error and runs again with a single process.
- Training page shows the run in detail: every step with start time and duration, the trainer's processor, memory and free space, and a live log of the last 80 messages (kept after an error).
- Progress shows every step change right away, and the trainer log lists each step.
- History: the chosen answer (word / not the word / unusable) is highlighted and changes at once when tapped; trainer reports no longer reload the list you are working in.
- `last_contact` of the trainer sensor is no longer written to the history (it changes every 20 seconds).
- No more deprecation warning about `via_device` on Home Assistant 2026.11 (the link from word devices to the hub is set in the device registry).

## 1.0.3
- Trainer: a recording deleted while a run fetches the data is skipped instead of stopping the run (it used to wait for Home Assistant for up to 30 minutes and then fail).
- "Recording not found" and "version not found" answers are JSON with a translated message.
- Integration quality scale Platinum: strict typing, mypy runs in the checks.
- Social preview image for GitHub.

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
