# Changelog

## 1.0.46
- **Real false wakes count much more:** a recording where a device really woke up and you answered *not said* is now trained as its own set, seen more often and punished harder. Before, a few dozen of them were mixed with thousands of harmless near misses and hardly counted.
- **The verdict looks at them:** each run measures how many held-out real false wakes of your devices would wake the new and the old version again, and how many of your own *not said* recordings wake them. Both now count for the verdict (with the check for chance), so a version that stops waking at home is rolled out. A version that hears worse in daily life or in the hard test is still never rolled out.
- The run report and *Compare versions* show both as bars.
- **Trainer update needed (1.0.42);** restart the trainer under *Settings → Trainer*.

## 1.0.45
- **Far fewer recordings to review:** with *Pre-review* on, a near miss from a device with a score below 0.80, in which speech recognition heard neither the word nor anything that sounds like it, counts as *not said* by itself (marked *auto*, it still teaches the model as a negative, and you can change it in *History → Reviewed*). Near misses above 0.80 and anything that sounds like the word stay for you. Open near misses that were already listened to are sorted out once when Home Assistant starts. No trainer update needed.

## 1.0.44
- **Check your answers again:** *History → Reviewed* now shows how many recordings you marked *said* and *not said* (*All / Said / Not said* filters with counts) and can sort by *Doubtful first*: the answers the device disagreed with most come first (*said* with a low score, *not said* with a high one). Recordings where the device clearly disagreed are marked (*said* with a score below 0.20, *not said* although the device woke up), so possible mistakes are easy to find and change right there. No trainer update needed.

## 1.0.43
- **The fair test has its own live view:** while two versions are tested, the *Training* page no longer shows the path of a training. It shows the stations of the comparison (ingredients → recordings → check data → fetch versions → version A → version B → verdict) and, while they are tested, a live duel: both versions side by side, a balance that leans towards the one ahead so far, the part being tested right now (everyday conditions, similar words, talk, music/noise, quiet room) with its progress, how often each version hears the word in every condition and the hard test, and how often it woke for nothing so far ("3 in 480 min"). The figures are live interim figures at threshold 0.90; the verdict at the end is worked out as before.
- **Large cards fold away:** *Automatic* and *Previous runs* on *Training*, the answer table, *Threshold*, *Versions* and *Compare versions* on *Quality*, the live log, and the detailed figures of the active version (bars, comparison with the version before, per person) are closed by default and show a one-line summary; tap to open. Which ones you opened is remembered in this browser.
- **Trainer update needed (1.0.41)** for the live figures of the fair test; restart the trainer under *Settings → Trainer*. With an older trainer the comparison path still shows, without figures.

## 1.0.42
- **Compare any two versions:** *Quality* has a new card *Compare versions* below the version list. Pick two versions (swap with one tap) and see the same questions as in the run report side by side: hears the word in everyday life and in the hard test, wakes up for nothing in talk, in music/noise and in a quiet room.
- **Honest about where the figures come from:** if both versions were measured in the same run (a new version against the one on the devices), the card shows that run's verdicts. Otherwise it says the figures come from separate runs on different test recordings and are only roughly comparable.
- **Fair test:** *Fair test* lets the trainer test both versions on exactly the same recordings, speech and noise, without training (usually 20 to 40 minutes), with the same check for chance as after a training. The result stays with the word and is shown for that pair from then on; *Test again* repeats it. The Training page shows the fair test while it runs.
- **Trainer update needed (1.0.40)** for the fair test; restart the trainer under *Settings → Trainer*. An older trainer is never handed a fair test (it would train instead).

## 1.0.41
- **Version curve shows the newest versions:** the curve on *Training → Previous runs* and *Quality → Versions* now shows the 12 newest trained versions, including those that were not rolled out (small grey points); older ones drop out. Before, it only showed rolled-out versions from the very first one, so newer runs were missing. No trainer update needed.

## 1.0.40
- **Your own threshold:** *Quality → Threshold* has a field to set the threshold yourself, in addition to the suggestion: steps of 0.01 with − and +, or type a value from 0.50 to 0.99, then *Set*. It applies to all devices of the word. So your value stays, setting it switches the automatic adjustment off for that word (the card says so before you confirm); switch it on again under *Training → Automatic*. The card shows when you set it and to which value. No trainer update needed.

## 1.0.39
- **Fix: thorough runs could hang and restart the trainer over and over at *Downloading chime* (#49).** The trainer read the whole CHiME-Home file into memory at once, which took 6.6 GB; on trainers with less memory the container was killed, restarted, generated voices again and was killed at the same spot all night. It now reads the file a few rows at a time (0.55 GB measured). The music, noise and room sets are read the same way.
- **No more loops on a download:** if the trainer does not come back from the home-noise download, the next run skips it and the gentle recipe goes on with music and noise only (as when it cannot be fetched). After the next trainer update it is tried once more.

## 1.0.38
- **Fix: a model could wake in a quiet room.** The gentle recipe of 1.0.37 let the volume of a quarter of its word clips drop almost to silence (the library default of −45 dB). A model trained on that can take a quiet room for the word: on 20.11. a kitchen Echo sent a near miss every few seconds with such a version. The gentle recipe now keeps the word at least as loud as a voice across the room (at most −20 dB); measured on test clips, the share of clips below −35 dBFS dropped from 12 % to 2 %.
- **Quiet rooms as negatives:** every run (all recipes) learns half an hour of a quiet room as negatives: faint hiss, mains hum, far-away sounds and silence, from about −80 to −35 dBFS. Made once from the noise sets, no download.
- **Quiet-room test:** the honest test also listens to 20 minutes of a quiet room, the candidate check to 10. A threshold that wakes more than once there does not count, so the device threshold goes up or the candidate loses; a new version that wakes more often in a quiet room than the active one is *really worse* and is not rolled out. The comparison shows it as its own row (*wakes up for nothing, per hour in a quiet room*).
- After a thorough run of 1.0.37, the next run starts once from scratch instead of training on from the model before (it may have come from the old gentle recipe). That run takes longer than usual.

## 1.0.37
- **Thorough runs try a gentle recipe:** the third candidate learns from clips roughened the way the Tater trainer prepares them: background noise always 5–10 dB below the voice (instead of up to 5 dB louder), room sound on 70 % of the clips (instead of half), no volume sweeps, and real noise from inside homes instead of speech as the background. The other two candidates keep the usual recipe (and the cut-off words). The check on your real recordings decides which one stays, so the recipe that suits your word and your home wins, and the studio says which recipe it was. Tests by the WakeSmith author suggest that the data preparation, not the trainer, is what makes the difference.
- **Real home noise:** the trainer fetches about two hours of CHiME-Home recordings once (kitchen, living room, TV, children, appliances; 400 MB download, 240 MB on disk) for the gentle recipe. If it cannot be fetched, that candidate uses music and noise only and the run goes on.
- Features of a thorough run take about twice as long (every set is prepared in both recipes); the model itself is built exactly as before and checked for device support like every model.

## 1.0.36
- **Training you can follow:** while a word trains, a path shows every real step of the trainer (ingredients, your recordings, voices, sound image, learning, testing, done). Finished steps tick off, the current one glows and fills with its own progress. Below it a small scene shows what happens right now, driven by the real numbers: your recordings flow in one by one, speech bubbles appear for the synthetic voices, similar words are listened to and the ones too close fly out, sound turns into an image column by column, the network brightens while it learns, the test shields fill as the test runs, and the result flies home.
- **Live learning curve:** the trainer now reports every interim check of microWakeWord (hit rate and false wakes per hour), and the training scene draws it live, one line per candidate in a thorough run.
- **Review tiles redesigned:** each recording is a tile in its colour (woke, near miss, false wake) with a big play button, a taller waveform with a glowing play head, a box with the suggestion, what was heard and the score against the threshold, and two big decision buttons; the suggested one is marked. A ring at the top fills with every decision. On the phone the buttons are full width and the extra actions are icons.
- **Clearer figures everywhere:** the overview, everyday results and quality figures are tiles with an icon, a number that counts up and a ring; people are small cards with a bar instead of tables (quality and upload); past runs are a timeline with a coloured result badge; the upload area glows and moves when a file is dragged over it; the word page shows the word big in its colour and updates live while you type, and devices are tiles that light up when the word is on them.
- **Restart shows the real result:** after *Restart trainer* the studio waits until the trainer reports with the new version. Before, Docker briefly started the old container first and the studio showed the old version as the result.
- **Trainer version separate from the studio:** the studio now knows which trainer version it works with. A release that only changes the studio no longer asks for a trainer restart; a new trainer comes only when the trainer itself changes.

## 1.0.35
- **Fix: averaged models did not wake on TECHO5 devices.** The averaged model divided by the number of candidates with a multiplication (MUL), and the TECHO5 firmware has no MUL. The model loaded, but every step failed, so the word never woke while *Okay Nabu* kept working. The trainer now puts the division into the last layer of each candidate and only adds the parts, which gives the same probabilities with operations every device runs.
- **Only models that run on the devices are built:** the trainer reads the operations of every model it makes and keeps only those that ESPHome and TECHO5 both run. An averaged model that would not run is left out and the best single candidate stays; if a model still had such an operation, the run stops with a clear message instead of sending it. The self-test checks this as well.
- **Second safety net in Home Assistant:** a version that uses an operation the devices cannot run (for example an averaged model from an older trainer) never counts as better, is never rolled out automatically, and *Roll out* refuses it with a message. The run shows *does not run on the devices*.

## 1.0.34
- **Room sound per device:** *Devices → Learn the room* records a few hand claps with your phone next to the device. A short guided dialog (countdown with a signal tone, live wave, each clap lights up) picks out every clap with its echo, measures the reverb time and lets you hear your own word as the device hears it in that room. The trainer mixes these real room impulses into the training (about half of the reverb, next to the general room set); the honest test keeps the general set, so versions stay comparable. Several spots per device can be learned, each word uses the rooms of its devices (switch *Room sound of your devices* under Training → Automatic, on by default, only active once a room is learned). The run report says how many claps it used.
- **Restarting the trainer:** every trainer has its own restart button, chosen in its profile. A press shows *Restarting …* until the trainer reports back, so it is not pressed twice; after 10 minutes without an answer it says where to look. The old single setting keeps working for its trainer.
- **Updates on the start page:** a card on the start page tells when something needs you after an update, with the button right there: a new Wake Word Studio version to install, Home Assistant to restart, or a trainer that is older than the integration (restart it, or it updates itself, or its image is still being built).
- **Livelier and clearer pages:** the automatic settings are tiles with an icon and a switch, the overview shows the way of your word (collect, review, training, on the devices) with the current step glowing, numbers count up and rings fill when a page opens, recording shows a live wave with each take popping in with its own little waveform and a ring towards 50 takes, settings fold into sections (remembered per browser), a new word appears big in its colour as you type and comes to life with a short animation, and a curve shows how each version got better. Everything stays still with *reduce motion*.
- Trainer self-test: fetches room claps, mixes them in and rebuilds the features when they change.

## 1.0.33
- *Thorough* chooses on your real recordings: with 20 or more real test recordings, the candidates are compared on half of them and the test reports on the other half, so the choice is made on what your devices really hear without flattering the result. With fewer it chooses on its own check data as before.
- *Thorough* tries different recipes: the second candidate also learns cut-off copies of the word as negatives (someone starts the word and stops, or says a longer word that begins the same). The check decides which recipe suits the word.
- New switch *Averaged model* (below *Thorough*): one more model averages the three candidates (their log-odds, then one sigmoid, so the device reads it like a single model). It wakes less often by mistake but needs about three times the memory on the device, so it is off by default and only used when it does better than the best single candidate. The model description gets the larger memory size by itself.
- 38 languages instead of 13: every language with Piper voices that espeak speaks and FLEURS speech for the honest test (added: Arabic, Bulgarian, Catalan, Danish, Estonian, Finnish, Georgian, Greek, Hindi, Hungarian, Icelandic, Indonesian, Kazakh, Korean, Latvian, Luxembourgish, Norwegian, Persian, Romanian, Serbian, Slovak, Slovenian, Swahili, Vietnamese, Welsh). The language list is sorted by name.
- The Quality page says what a thorough run chose and on what (real recordings or check data, averaged model, recipe).
- Trainer self-test: also trains with cut-off words, chooses on real halves, builds the averaged model and checks that it reads exactly like a single one on the device.

## 1.0.32
- Proxmox trainers update themselves too: the container set up by the Proxmox script now has access to Docker inside it, so the trainer fetches a new version while idle instead of only on a restart. For an existing Proxmox trainer the profile shows the one line to paste once into the Proxmox shell (`proxmox.sh update`); container, data and key stay.
- The profile no longer tells Proxmox trainers to "set the container up again": it says they update on every restart and offers that one line.

## 1.0.31
- Several trainers: for example the Proxmox container as the main trainer and a PC with a graphics card that is only on now and then. Each trainer gets its own id; all train from the same recordings and data in Home Assistant.
- *Training → Automatic → Next run on*: *Automatic (fastest free one)* or a fixed trainer (if it is off or does not take runs, the others take over). Each trainer shows its status and how long a normal and a thorough run take on it: measured from its own last run, otherwise estimated from a short speed test every trainer runs at start.
- *Settings → Trainer* lists all trainers with their profile, a switch *Takes runs* and *Remove from the list* for one that is off (removed by itself after 30 days). A restart only affects the run on that trainer; cancelling reaches the trainer that runs it. Each run says which trainer ran it.
- *Set up a trainer*: a tab each for the Home Assistant app, Proxmox, Windows PC and Linux / NAS with three steps and one line to copy (works in PowerShell, cmd and Linux shells; the button copies it with the key, the page shows it masked).
- Docker trainers update themselves: started with `-v /var/run/docker.sock:/var/run/docker.sock`, the trainer fetches a new version while idle and swaps its container for one with the same settings; if the new one does not keep running, the old one starts again.
- Graphics cards: tested with an RTX 5080 (Blackwell), it trains on the card with TensorFlow 2.21. The earlier note that RTX 50 is not supported was wrong and is removed.
- Hard test: every test recording is also played far beyond daily life (very far away in another room, a TV louder than you, music louder than you, everything at once). Hardly any version reaches 100 % there, so a version that hears everything at home can still be told apart from a better one. The comparison counts it like everyday detection (at about one false wake per hour, beyond chance); *Thorough* uses it to break ties between candidates. Shown on the Quality page (tile, bars, versions table) and as a bar pair in the version comparison. Versions from before 1.0.31 get their hard-test value in the next run, which tests the active version again.
- Animations: while a word trains, sound flows into a small network that fires layer by layer and the result lights up; the progress bar has a glowing tip; a better version is greeted with a short burst of confetti (once); cards fade in when a page opens. Pure CSS, the loop does not restart when the page refreshes, and everything stays still with *reduce motion* switched on.
- Quality: the active version shows its freshest measurement (from the latest comparison run in everyday conditions) instead of the values from when it was trained.

## 1.0.30
- Graphics card version: TensorFlow could not find one CUDA library (`libcusolver.so.11`) and therefore ignored the card, even on a supported setup. All CUDA libraries are now registered with the system loader, and the image build fails if any of them cannot be loaded.
- If the card is passed in but its libraries cannot be loaded, the Training page now says so (instead of "sees no card") and asks to report it.

## 1.0.29
- Graphics card version of the trainer (NVIDIA, Docker image `:gpu`, start with `--gpus all`; Linux with the NVIDIA Container Toolkit or Windows with Docker Desktop). At start the trainer tries the card once: if it works, training runs on it, otherwise on the processor, so the `:gpu` image never does worse than the normal one. TensorFlow 2.21 supports cards up to the RTX 40 series; RTX 50 (Blackwell) is not supported by it yet and falls back to the processor. Test reports with real cards welcome.
- *Training → Automatic* shows where the trainer computes: with a working card a choice *Graphics card (automatic) / Processor only*, otherwise the reason (card not passed in, card not supported, being tested). Durations are estimated per device.
- Each run in the list says *Graphics card* when it ran there, or *Graphics card failed, processor* if the card failed during the run and the processor finished it.
- Profile: the graphics card row says whether it is used for training.
- Version check: if a Docker or Proxmox trainer is older than the integration, the profile says whether the new trainer image is already published (it is built about 30 minutes after a release), so a restart does not silently fetch the old version.
- *Settings → Trainer* shows the Docker command for the graphics card version.

## 1.0.28
- *Thorough* (Training → Automatic, off by default): each run trains three candidates and keeps the one that hears best in everyday conditions at about one false wake per hour. They are compared on check data of their own (held-out synthetic voice, FLEURS dev speech, other music/noise files), never on the test, so the honest test stays untouched; with *Thorough* the test leaves those check clips out. The winner is the base for the next run. A run takes about two to three times as long.
- Estimate for your trainer right under the switch: processor, cores, memory, graphics card, how long a normal and a thorough run take on it (from the last run) and whether a night run is done by 7 in the morning.
- The trainer reports its processor and graphics cards; *Settings → Trainer → Profile* shows them.
- Version details say which candidate was kept.

## 1.0.27
- Easy to read comparison instead of the curve: the *Active version* card now shows, next to *How well it hears*, the version against the one before with two bars per question – *Hears the word in everyday life* (more is better), *Wakes up for nothing, per hour of talk* and *per hour of music/noise* (fewer is better) – each marked *really better*, *really worse* or *no real difference*. *All figures in the comparison* jumps to the full table.
- Versions tested before 1.0.26 get the same bars from their own test (marked as old test) instead of an empty view.
- Bars grow in when the page is opened, not again with every refresh.

## 1.0.26
- Everyday test: every test recording is now also played soft or far away, in another room (reverb), with music and noise, with a TV talking in the background and all at once. False wakes are counted on up to 8 hours of speech (before 3) and, new, on 1 hour of music and noise.
- Honest comparison: a new version is no longer judged by two numbers. It is compared with the version on the devices on everyday detection at 0.5, 1 and 2 false wakes per hour, false wakes in speech and in music/noise, every condition, similar words and the weakest person – and a difference only counts when it is larger than chance for the size of the test set. Versions that are neither really better nor really worse are shown as *as good*; the version on the devices stays.
- *Quality → Versions*: tap a version to see the whole comparison (✓ better, ✗ worse, ≈ within chance, bold = part of the decision) and a curve of everyday detection against false wakes for both versions. New columns *Quiet* and *Everyday*.
- *Active version* shows everyday detection, false wakes in music/noise and a bar per condition.
- The trainer needs a restart to use the new test (*Settings → Trainer → Restart*).

## 1.0.25
- *Other word* on every recording (key **3**, only with two or more words): when one word caught a recording of another (e.g. *hey casita* landed at *hey jarvis*), pick the word that was really said. The recording goes there as *said*, with its trim and person, and stays here as *not said*, so both words learn from it. *Undo* in the toast and in History. The other model's score does not go along, so each word's statistics stay its own. Thanks to Domino85 for the idea.
- Phones: the recording tiles no longer stick out a few pixels on the right (score line and buttons stay inside the tile).
- Issue forms: *New issue* now offers a bug report form (versions, device, log, diagnostics) and links ideas to Discussions → Ideas and questions to Discussions. The README has a short *Ideas, questions and bugs* section.
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
