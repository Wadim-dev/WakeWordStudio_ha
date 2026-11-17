# Changelog

## Unreleased
- The question before rolling out a version now says correctly that it reaches the devices after a restart of Home Assistant.
- No deprecation warning in the Home Assistant log anymore (word devices are linked to the hub without the deprecated device lookup).

## 1.0.24
- Better models again: your real recordings now count more than synthetic ones, and only a fixed share of synthetic clips of the word goes into training (8,000 Piper, 2,400 other-language voices, 4,000 OmniVoice) however large the stock grows. Before, the growing synthetic stock made new versions trigger more often on other things.
- Night training starts only once enough recordings were newly reviewed since the last run (default 20, *Settings*). A run on almost the same data could not get better.
- *Restart trainer* under *Settings → Trainer*: choose once the Home Assistant button that restarts your trainer (Proxmox, Portainer, app …), then restart it from the studio; it asks first while a training runs.
- README images show speech-like waveforms.

## 1.0.23
- Trim like in a recording studio: large waveform with a time ruler, start and end handles right in the waveform (drag, move the selection, draw a new one, arrow keys), a play head that runs along, tap to play from there, *Automatic* finds start and end at the sound.
- A trimmed recording plays only its trimmed part everywhere (play button, waveform), so reviewing later hears exactly what is trained.
- Recording tiles: small waveform per recording (tap to play from there, trimmed part highlighted), tidier score line and buttons, selected answers easy to read on every theme.
- Feedback when answering: the button lights up, a stamp with the answer covers the recording, then it slides away; short vibration on phones.
- Settings → devices that send their recordings: each device has switches for *Keep wake clips* and the setup page, a *Send to* menu and a *Set up* button that turns both on and opens the page. Turning *Keep wake clips* off asks first.

## 1.0.22
- Full transparency on the *Training* page: new card *Running right now* with a progress bar for everything the trainer is doing at the same time – the step itself, the tools' own progress (downloads, loading models, computing features, training steps) with count, speed and time left, and OmniVoice's word and other-speech stock.
- The log keeps the whole run (up to 500 lines instead of 80), is taller, can be filtered (*Everything*, *Important*, *Tool output*) and copied in one go.
- OmniVoice reports every batch: how many clips were kept and what speech recognition heard in the ones it rejected.

## 1.0.21
- Fix: while a training ran, the *Training* page jumped back to the top every time the trainer reported (about every 20 seconds), so scrolling down to the log was hardly possible. Refreshing a page now keeps its scroll position, also in Home Assistant setups where the page scrolls inside the frame.

## 1.0.20
- Settings → *Devices that send their recordings* is now a step-by-step guide for every TECHO device (Echo Show, Spot, Dot, Echo 2nd gen, TECHO5 Panel …): copy buttons for address and token, and a list of your devices with whether each one is sending, how many clips are waiting, the last problem, a button that switches the device's setup page on and opens it, and one that turns on *Keep wake clips* when it is off.
- Devices that send their recordings: the address to enter is now `http://<home assistant>:8123/api/wake_word_studio`, named like the integration. The older address `…/api/sprachmodell` keeps working, so devices set up with it need no change.

## 1.0.19
- Devices that send their recordings (TECHO firmware 1.6.43, *Send wake clips to* → *Custom*): the device adds `/api/clips` to the address it is given, so the receiver now also answers at `/api/sprachmodell/api/clips` and `/api/sprachmodell/api/clips/ping`. The address to enter is `http://<home assistant>:8123/api/sprachmodell`, the token is the trainer key. Errors are answered as `{"ok": false, "error": "..."}`, which the device shows.
- Settings: new card *Devices that send their recordings* with the values to enter on the device.

## 1.0.18
- Fix: with a theme whose header is see-through (e.g. glass themes) the page content showed through the Wake Word Studio header and tabs while scrolling. The header now always has a solid base.
- Fix: the new training steps showed their internal names ("aehnlich_pruefen"); they are now "Listening to similar words" and "Generating more voices (OmniVoice)".
- Trainer: the speech synthesis no longer fills the log with harmless onnxruntime messages about pinning threads in a container ("pthread_setaffinity_np failed").

## 1.0.17
- Fix: the first time Wake Word Studio was opened after Home Assistant loaded, the page could stay black (opening it again worked). The panel is now ready as soon as its script has run.
- More and better training data: about 50,000 synthetic clips per word instead of 17,000, plus up to 9,000 clips from **OmniVoice**, a modern voice model with many different voices (men, women, children, old, high, low, whispering). Every OmniVoice clip is checked by speech recognition (faster-whisper) before it is used: the word must be heard in a positive clip and must not be heard in a negative one. Without a graphics card the stock grows by at most 90 minutes per run, so the first runs after this update take longer.
- Listening check for sound-alikes: each similar word the trainer uses as a negative example is spoken and heard by the speech recognition first; one that sounds exactly like your word is left out, so the model never learns to ignore its own word.
- Pre-review (new switch "Pre-review new recordings", on by default): while the trainer has nothing else to do, it listens to new device recordings and confirms those in which the word was clearly heard. They are marked *auto* in History (new filter) and can be changed like any other answer. Each recording shows what was heard.
- Trim per recording: *Trim* under a recording opens its waveform with start and end sliders; listen to the selection and save. Training uses only the selected part; *Whole recording* removes the trim.
- Device wake-ups and false wake-ups are trimmed by themselves for training: the word is placed at the end of the clip; a device sound that follows after a short pause is cut off, sound that runs on without a pause counts as part of the word.
- Honest test: from now on new recordings are held back for the test by whole days (about one day in three), so the test contains days the model never heard (other room noise, other mood). Older recordings keep their place.
- Recordings can be sent directly by a device: `POST /api/sprachmodell/clips` (multipart `audio` WAV up to 2 MB and `meta` JSON with `name`, `device`, `kind`, `at`, `model`, `slot`, `score`, `cutoff`), `GET /api/sprachmodell/clips/ping`, both with `Authorization: Bearer <trainer key>`. A clip that is already there (same audio) is kept once, also when the device is asked for its clips later.

## 1.0.16
- The threshold adjusts itself (new switch "Adjust threshold automatically", on by default): when a version is rolled out the devices get the threshold it was tested with; afterwards it follows your answers to recordings of that version once 10 correct and 5 false wake-ups are reviewed, never more than 0.03 below the tested value. The quality page shows the current value and why it was set.
- The threshold suggestion only counts recordings scored by the version that is on the devices now (older recordings were scored by a different model).
- Trainer profile: swap shows what the trainer itself uses (from its control group); inside a container the system file could show the host's swap.

## 1.0.15
- Fix: after an update the browser could keep the old text file and show placeholders like `h_bereit` on the start page. The texts are now loaded with the same version as the panel.
- Fix: tapping a cell or a device button in the quality table did nothing.
- A renamed device is now one device everywhere: older recordings take the device's current name (before, the table and filters could list the same device twice, e.g. under its old and new name).

## 1.0.14
- Quality page: table of your answers (word, missed, not the word, not reviewed) against the device's confidence, for all devices or one. Cells where you and the model strongly disagree are outlined; tap a cell to listen to exactly those recordings in History and decide again.
- Rollout follows Home Assistant's rules: a better version is saved to `custom_wake_words` and a repair message offers a restart with one tap (Home Assistant reads new wake word models when it starts); after the restart the word is selected on its devices by itself. Wake Word Studio no longer touches ESPHome's internal wake word cache or its runtime data.
- Devices are found through the device and entity registries and the device name ESPHome stores in its config entry.
- The start page shows when a new version waits for a restart, with a button to the repair message.

## 1.0.13
- New hub page: a status banner at the top says what matters now (training with progress and finish time, recordings waiting for review, trainer missing, or all set) with one button to the next step. Word cards show recall as a ring, open reviews, version and a 14-day chart of device recordings. Trainer card with processor, memory and disk use; queue with the nightly time; devices with the words on each.
- Training shows the expected finish time ("done around 16:40") next to the time left.
- Settings → Trainer: profile with version, cores, memory, swap and free disk, each rated green/yellow/red with a tip.
- The repository is now `Wadim-dev/WakeWordStudio_ha`; all links point there (old links keep working).
- Repair message when the trainer is mostly waiting for memory or disk for more than 15 minutes; it disappears once the trainer runs smoothly again.

## 1.0.12
- Proxmox setup: the trainer container is always placed on a local disk (most free space), never on network storage – before, the first storage in the list was taken, which could be a NAS and made training very slow. New containers get 100 GB disk (was 40).

## 1.0.11
- Time left: during training (and other long steps) the trainer measures its pace over the last 15 minutes and shows how long the step still takes. Progress now moves with every training step, not only every 500.

## 1.0.10
- The training view also shows waiting for memory and for the processor, so a slow run shows its cause.

## 1.0.9
- The training view shows how much of the time the trainer waits for its disk, with a hint when a faster disk would help.
- Fix: the queue position text showed "Free space" instead of the position.

## 1.0.8
- Training log shows the newest line at the top, so it no longer has to be scrolled down. It stays where you scrolled while new lines arrive.
- Training batches are shown as one updating progress line instead of filling the log, and progress lines no longer overlap the next line.

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
