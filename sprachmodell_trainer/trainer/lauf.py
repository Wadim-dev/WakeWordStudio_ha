"""Ein Trainingslauf fuer ein Aktivierungswort.

Ablauf: Grunddaten -> eigene Aufnahmen aus HA -> kuenstliche Stimmen -> Merkmale -> microWakeWord-Training
-> ehrlicher Test neu gegen alt -> Ergebnis an HA. Fortschritt geht laufend an HA (App: Training).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import yaml

from .grunddaten import Grunddaten, platz_frei
from .ha import HA

_LOG = logging.getLogger("trainer.lauf")

# Mengen kuenstlicher Aufnahmen (MENGE nur zum Ausprobieren verkleinern)
_M = float(os.environ.get("MENGE", "1"))
POS_EIGEN = int(8000 * _M)
POS_FREMD = int(600 * _M)  # je fremder Stimme
NEG_AEHNLICH = int(6000 * _M)
NEG_SAETZE = int(3000 * _M)
HALTE_TEST = max(10, int(200 * _M))  # von einer zurueckgehaltenen Stimme, nur zum Testen
FRAMES = 220
MIN_ECHT_TEST = 5
PLATZ_GB = float(os.environ.get("PLATZ_GB", "8"))  # erster Lauf (Grunddaten), danach reichen 3 GB

VOKALE_LATEIN = "aeiouyäöü"
VOKALE_KYRILL = "аеиоуыэюя"
VOKALE = VOKALE_LATEIN + VOKALE_KYRILL + "áéíóúàèìòùâêîôûёїє"

MIXEDNET = [
    "mixednet", "--pointwise_filters", "64,64,64,64", "--repeat_in_block", "1, 1, 1, 1",
    "--mixconv_kernel_sizes", "[5], [7,11], [9,15], [23]", "--residual_connection", "0,0,0,0",
    "--first_conv_filters", "32", "--first_conv_kernel_size", "5", "--stride", "3",
]
MODELL_DATEI = "tflite_stream_state_internal_quant/stream_state_internal_quant.tflite"

# Anteil am Gesamtfortschritt je Abschnitt
ANTEILE = {"vorbereiten": (0, 8), "daten": (8, 12), "stimmen": (12, 35), "merkmale": (35, 50),
           "training": (50, 92), "test": (92, 100)}


class Abgebrochen(Exception):
    """Training wurde in der App abgebrochen."""


def aehnliche_woerter(wort: str) -> list[str]:
    """Verwechslungsgefahr: Woerter, die fast so klingen (fuer jede Sprache, ohne Woerterbuch)."""
    w = wort.strip()
    klein = w.lower()
    aus: set[str] = set()
    teile = w.split()
    if len(teile) > 1:
        aus.update(teile)
        aus.add(" ".join(teile[:-1]))
        aus.add(" ".join(teile[1:]))
    if len(klein) > 3:
        for i in range(len(klein)):
            aus.add(klein[:i] + klein[i + 1:])  # Laut weg
        for i in range(len(klein) - 1):
            aus.add(klein[:i] + klein[i + 1] + klein[i] + klein[i + 2:])  # Laute vertauscht
    rnd = random.Random(klein)
    for i, c in enumerate(klein):
        if c in VOKALE:
            vokale = VOKALE_KYRILL if "\u0400" <= c <= "\u04ff" else VOKALE_LATEIN
            for v in rnd.sample(vokale, 4):
                if v != c:
                    aus.add(klein[:i] + v + klein[i + 1:])
    h = max(2, len(klein) // 2)
    aus.update({klein[:h], klein[h:], klein[:h + 1]})
    aus = {a.strip(" ,") for a in aus if len(a.strip()) >= 2}
    aus.discard(klein)
    aus = {a for a in aus if a.lower() != klein and a.lower().replace(" ", "") != klein.replace(" ", "")}
    return sorted(aus)


class Lauf:
    def __init__(self, ha: HA, auftrag: dict[str, Any], daten: str, optionen: dict[str, Any]) -> None:
        self.ha = ha
        self.auftrag = auftrag
        self.wort_id = str(auftrag["wort_id"])
        self.wort = str(auftrag["wort"]).strip()
        self.sprache = str(auftrag.get("sprache") or "en")
        self.daten = daten
        self.o = optionen
        self.ordner = Path(daten) / "woerter" / self.wort_id
        self._stopp = threading.Event()
        self._prozess: subprocess.Popen | None = None
        self._zuletzt = 0.0
        self.start = time.time()
        self.phase = "vorbereiten"
        self.letzter: dict[str, Any] = {"wort_id": self.wort_id}  # last reported state, repeated as heartbeat

    # --- Steuerung --------------------------------------------------------

    def abbrechen(self) -> None:
        self._stopp.set()
        if self._prozess and self._prozess.poll() is None:
            self._prozess.kill()

    def _pruefen(self) -> None:
        if self._stopp.is_set():
            raise Abgebrochen

    def melden(self, phase: str, prozent: float | None, schritt: str, sofort: bool = True, **mehr: Any) -> None:
        from .dienst import info

        if not sofort and time.time() - self._zuletzt < 10:
            return
        self._zuletzt = time.time()
        self.letzter = {"wort_id": self.wort_id, "phase": phase,
                        "prozent": None if prozent is None else round(prozent, 1), "schritt": schritt, **mehr}
        self.ha.status({**self.letzter, "info": info()})

    def _abschnitt(self, name: str, anteil: float, schritt: str, sofort: bool = False, **mehr: Any) -> None:
        phase = {"stimmen": "daten"}.get(name, name)
        self.phase = phase
        von, bis = ANTEILE[name]
        self.melden(phase, von + (bis - von) * max(0.0, min(1.0, anteil)), schritt, sofort, **mehr)

    def _werkzeug(self, befehl: str, auftrag: dict, abschnitt: str, von: float, bis: float, schritt: str) -> dict:
        """Arbeitsschritt als eigenen Prozess starten, Fortschritt weitergeben, abbrechbar."""
        datei = self.ordner / f"auftrag_{befehl}.json"
        datei.write_text(json.dumps(auftrag), encoding="utf-8")
        return self._ausfuehren([sys.executable, "-m", "trainer.werkzeug", befehl, str(datei)],
                                abschnitt, von, bis, schritt)

    def _ausfuehren(self, args: list[str], abschnitt: str, von: float, bis: float, schritt: str,
                    cwd: str | None = None, schritte_gesamt: int | None = None) -> dict:
        self._pruefen()
        umgebung = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent), "TF_CPP_MIN_LOG_LEVEL": "2"}
        if self.o.get("threads"):
            umgebung["TF_NUM_INTRAOP_THREADS"] = umgebung["OMP_NUM_THREADS"] = str(self.o["threads"])
        self._prozess = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                         bufsize=1, cwd=cwd, env=umgebung)
        letzte: deque[str] = deque(maxlen=40)
        ergebnis: dict = {}
        for zeile in self._prozess.stdout:  # type: ignore[union-attr]
            zeile = zeile.rstrip()
            letzte.append(zeile)
            if self._stopp.is_set():
                self._prozess.kill()
                break
            anteil = None
            if zeile.startswith("FORTSCHRITT "):
                _, a, b = zeile.split()
                anteil = int(a) / max(1, int(b))
            elif zeile.startswith("ERGEBNIS "):
                ergebnis = json.loads(zeile[9:])
            elif schritte_gesamt and (m := re.search(r"Step #?(\d+)", zeile)):
                anteil = int(m.group(1)) / schritte_gesamt
                if "Validation" in zeile:
                    _LOG.info(zeile)
            if anteil is not None:
                self._abschnitt(abschnitt, von + (bis - von) * anteil, schritt)
        code = self._prozess.wait()
        self._prozess = None
        self._pruefen()
        if code != 0:
            _LOG.error("Step failed:\n%s", "\n".join(letzte))
            raise RuntimeError(next((z for z in reversed(letzte) if z.strip()), f"exit {code}")[:300])
        return ergebnis

    # --- Ablauf -----------------------------------------------------------

    def ausfuehren(self) -> None:
        self.ordner.mkdir(parents=True, exist_ok=True)
        self._abschnitt("vorbereiten", 0, "grunddaten", True)
        g = Grunddaten(self.daten, lambda s: (self._pruefen(), self._abschnitt("vorbereiten", 0.3, s, True)))
        noetig = PLATZ_GB if not (g.o / "neg" / "speech" / "fertig").exists() else min(PLATZ_GB, 3)
        if platz_frei(self.daten) < noetig:
            raise RuntimeError(f"Not enough disk space: at least {noetig:g} GB free needed")
        neg = g.negative()
        bg = g.hintergrund()
        rir = g.raumklang()
        gerede = g.gerede(self.sprache)
        stimmen = g.stimmen(self.sprache)
        g.aufraeumen()
        self._pruefen()
        if not stimmen.get(self.sprache):
            raise RuntimeError(f"No voice for language {self.sprache}")

        echt = self._echte_aufnahmen()
        tts = self._stimmen(stimmen, gerede)
        merkmale = self._merkmale(echt, tts, bg, rir, gerede, g)
        tflite = self._training(merkmale, neg)
        bericht = self._test(tflite, echt, tts, bg, gerede)
        self._abschnitt("test", 1, "senden", True)
        self.ha.ergebnis(self.wort_id, tflite.read_bytes(), bericht)
        self.letzter = {"wort_id": self.wort_id}  # HA now shows the result; the heartbeat must not report "testing" again
        _LOG.info("Done: %s", json.dumps(bericht, ensure_ascii=False))

    # --- eigene Aufnahmen ---------------------------------------------------

    def _echte_aufnahmen(self) -> dict[str, list[dict]]:
        self._abschnitt("daten", 0, "aufnahmen", True)
        liste = self.ha.liste(self.wort_id)
        basis = self.ordner / "echt"
        aus: dict[str, list[dict]] = {k: [] for k in ("wort_train", "wort_test", "kein_train", "kein_test")}
        behalten = set()
        for i, a in enumerate(liste):
            self._pruefen()
            art = ("wort" if a["urteil"] == "wort" else "kein") + ("_test" if a.get("test") else "_train")
            ziel = basis / art / f"{a['id']}.wav"
            behalten.add(ziel)
            if not ziel.exists():
                inhalt = self.ha.audio(self.wort_id, a["id"])
                if inhalt is None:  # deleted in the meantime
                    _LOG.info("Recording %s no longer exists, skipped", a["id"])
                    behalten.discard(ziel)
                    continue
                ziel.parent.mkdir(parents=True, exist_ok=True)
                tmp = ziel.with_suffix(".tmp")
                tmp.write_bytes(inhalt)
                tmp.replace(ziel)
            aus[art].append({"datei": str(ziel), "person": a.get("person") or ""})
            if i % 20 == 0:
                self._abschnitt("daten", i / max(1, len(liste)), f"aufnahmen:{i}/{len(liste)}")
        if basis.exists():  # umbewertete oder geloeschte Aufnahmen entfernen
            for f in basis.glob("*/*.wav"):
                if f not in behalten:
                    f.unlink()
        self.bewertet = len(liste)
        return aus

    # --- kuenstliche Stimmen ------------------------------------------------

    def _stimmen(self, stimmen: dict[str, list[Path]], gerede: dict[str, Path]) -> dict[str, Path]:
        eigen = [str(p) for p in stimmen[self.sprache]]
        halte = eigen[-1]
        lernen = eigen[:-1] or eigen
        fremd = [str(p[0]) for s, p in stimmen.items() if s != self.sprache and p]
        marke = hashlib.sha1(json.dumps([self.wort.lower(), self.sprache, eigen, fremd]).encode()).hexdigest()
        basis = self.ordner / "tts"
        if (basis / "marke").exists() and (basis / "marke").read_text() != marke:
            shutil.rmtree(basis, ignore_errors=True)  # Wort geaendert: alles neu
            shutil.rmtree(self.ordner / "merkmale", ignore_errors=True)
            shutil.rmtree(self.ordner / "train", ignore_errors=True)
        basis.mkdir(parents=True, exist_ok=True)
        (basis / "marke").write_text(marke)

        w = self.wort
        pos_texte = sorted({w, w + "!", w + "?", w + ".", w.lower(), w.capitalize(), w + ", "})
        aehnlich = aehnliche_woerter(w)
        saetze = self._saetze(gerede)
        aufgaben = [
            ("pos_eigen", POS_EIGEN, pos_texte, lernen, None),
            *[(f"pos_fremd_{i}", POS_FREMD, pos_texte, [v], eigen[0]) for i, v in enumerate(fremd)],
            ("neg_aehnlich", NEG_AEHNLICH, aehnlich, lernen, None),
            ("neg_saetze", NEG_SAETZE, saetze, lernen, None),
            ("test_pos", HALTE_TEST, pos_texte, [halte], None),
            ("test_neg", HALTE_TEST, aehnlich, [halte], None),
        ]
        gesamt = sum(a[1] for a in aufgaben)
        erledigt = 0
        aus = {}
        for name, anzahl, texte, voices, lautschrift in aufgaben:
            ziel = basis / name
            aus[name] = ziel
            if not (ziel / "fertig").exists():
                von, bis = erledigt / gesamt, (erledigt + anzahl) / gesamt
                self._werkzeug("tts", {"ziel": str(ziel), "anzahl": anzahl, "texte": texte, "stimmen": voices,
                                       "lautschrift_von": lautschrift},
                               "stimmen", von, bis, "stimmen")
                (ziel / "fertig").touch()
            erledigt += anzahl
        (basis / "aehnlich.txt").write_text("\n".join(aehnlich), encoding="utf-8")
        return aus

    def _saetze(self, gerede: dict[str, Path]) -> list[str]:
        """Kurze Stuecke echter Saetze der Sprache: Alltagsgerede, das nicht ausloesen darf."""
        datei = gerede["train"] / "saetze.txt"
        saetze = datei.read_text(encoding="utf-8").splitlines() if datei.exists() else []
        rnd = random.Random(1)
        aus = set()
        wl = self.wort.lower()
        for s in rnd.sample(saetze, min(len(saetze), 1500)):
            teile = s.split()
            if not teile:
                continue
            n = rnd.randint(1, min(4, len(teile)))
            i = rnd.randrange(0, len(teile) - n + 1)
            stueck = " ".join(teile[i:i + n]).strip(" ,.;:!?\"'")
            if len(stueck) >= 2 and wl not in stueck.lower():
                aus.add(stueck)
        return sorted(aus) or aehnliche_woerter(self.wort)

    # --- Merkmale -----------------------------------------------------------

    def _merkmale(self, echt: dict, tts: dict, bg: list[Path], rir: Path, gerede: dict[str, Path],
                  g: Grunddaten) -> dict[str, dict]:
        basis = self.ordner / "merkmale"
        bgs = [str(p) for p in bg] + [str(gerede["train"])]
        wdh_echt = lambda n: max(3, min(40, 3000 // max(1, n)))  # noqa: E731
        sets: list[tuple[str, list[str], int, bool, bool, float, float]] = [
            # name, dateien, Wiederholungen, wort?, neu bauen?, Gewicht, Strafe
            ("pos_eigen", self._wavs(tts["pos_eigen"]), 2, True, False, 2.0, 1.0),
            ("pos_fremd", [f for k, p in tts.items() if k.startswith("pos_fremd") for f in self._wavs(p)],
             1, True, False, 1.0, 1.0),
            ("neg_aehnlich", self._wavs(tts["neg_aehnlich"]), 1, False, False, 3.0, 2.0),
            ("neg_saetze", self._wavs(tts["neg_saetze"]), 1, False, False, 1.0, 1.5),
        ]
        if echt["wort_train"]:
            d = [a["datei"] for a in echt["wort_train"]]
            sets.append(("echt_wort", d, wdh_echt(len(d)), True, True, 2.0, 1.0))
        if echt["kein_train"]:
            d = [a["datei"] for a in echt["kein_train"]]
            sets.append(("echt_kein", d, wdh_echt(len(d)), False, True, 1.5, 3.0))
        gesamt = sum(len(s[1]) * s[2] for s in sets) or 1
        erledigt = 0
        aus: dict[str, dict] = {}
        for name, dateien, wdh, ist_wort, neu, gewicht, strafe in sets:
            ziel = basis / name
            menge = len(dateien) * wdh
            if neu or not (ziel / "fertig").exists():
                shutil.rmtree(ziel, ignore_errors=True)
                rnd = random.Random(name)
                dateien = sorted(dateien)
                rnd.shuffle(dateien)
                n_val = max(1, len(dateien) // 10) if len(dateien) >= 10 else 0
                for teil, auswahl in (("validation", dateien[:n_val]), ("training", dateien[n_val:])):
                    if not auswahl:
                        continue
                    anteil = len(auswahl) * wdh / gesamt
                    self._werkzeug("merkmale", {
                        "ziel": str(ziel / teil / f"{name}_mmap"), "dateien": auswahl, "wiederholungen": wdh,
                        "frames": FRAMES, "trim": True, "bg": bgs, "rir": str(rir), "snr_min": -5,
                        "prozesse": self.o.get("threads") or None,
                    }, "merkmale", erledigt / gesamt, erledigt / gesamt + anteil, "merkmale")
                    erledigt += len(auswahl) * wdh
                if (ziel / "validation").exists():
                    shutil.copytree(ziel / "validation", ziel / "testing", dirs_exist_ok=True)
                (ziel / "fertig").touch()
            else:
                erledigt += menge
            aus[name] = {"dir": str(ziel), "wort": ist_wort, "gewicht": gewicht, "strafe": strafe}
        # Gerede der Sprache in voller Laenge: einmal je Sprache, fuer alle Woerter
        lang = g.o / "merkmale" / f"gerede_{self.sprache}"
        if not (lang / "fertig").exists():
            shutil.rmtree(lang, ignore_errors=True)
            self._werkzeug("merkmale", {"ziel": str(lang / "training" / "gerede_mmap"), "ordner": [str(gerede["train"])],
                                        "wiederholungen": 0, "prozesse": self.o.get("threads") or None},
                           "merkmale", 0.95, 1.0, "merkmale_gerede")
            (lang / "fertig").touch()
        aus["gerede"] = {"dir": str(lang), "wort": False, "gewicht": 8.0, "strafe": 1.0, "lang": True}
        return aus

    @staticmethod
    def _wavs(ordner: Path) -> list[str]:
        return sorted(str(p) for p in Path(ordner).glob("*.wav"))

    # --- Training -----------------------------------------------------------

    def _training(self, merkmale: dict[str, dict], neg: dict[str, Path]) -> Path:
        train = self.ordner / "train"
        weiter = (train / "restore").exists() and not self.o.get("schritte")
        self.weiter = weiter
        if weiter:
            schritte, lr = [3000, 3000], [0.0002, 0.0001]
        else:
            shutil.rmtree(train, ignore_errors=True)
            gesamt = int(self.o.get("schritte") or 15000)
            schritte, lr = [gesamt * 2 // 3, gesamt - gesamt * 2 // 3], [0.0005, 0.0001]

        def satz(d: str, gewicht: float, strafe: float, wahr: bool, art: str) -> dict:
            return {"features_dir": d, "sampling_weight": gewicht, "penalty_weight": strafe, "truth": wahr,
                    "truncation_strategy": art, "type": "mmap"}

        features = [satz(m["dir"], m["gewicht"], m["strafe"], m["wort"],
                         "random" if m.get("lang") else "truncate_start") for m in merkmale.values()]
        features += [
            satz(str(neg["speech"]), 10.0, 1.0, False, "random"),
            satz(str(neg["dinner_party"]), 10.0, 1.0, False, "random"),
            satz(str(neg["no_speech"]), 5.0, 1.0, False, "random"),
            satz(str(neg["dinner_party_eval"]), 0.0, 1.0, False, "split"),
        ]
        cfg = {
            "window_step_ms": 10, "train_dir": str(train), "features": features,
            "training_steps": schritte, "positive_class_weight": [1, 1], "negative_class_weight": [20, 20],
            "learning_rates": lr, "batch_size": 128,
            "time_mask_max_size": [5, 5], "time_mask_count": [2, 2], "freq_mask_max_size": [5, 5], "freq_mask_count": [2, 2],
            "eval_step_interval": 500, "clip_duration_ms": 1500,
            "target_minimization": 0.9, "minimization_metric": None, "maximization_metric": "average_viable_recall",
        }
        datei = self.ordner / "training.yaml"
        datei.write_text(yaml.dump(cfg), encoding="utf-8")
        text = "weitertrainieren" if weiter else "training"
        self._abschnitt("training", 0, text, True, schritte=sum(schritte))
        args = [sys.executable, "-m", "microwakeword.model_train_eval", f"--training_config={datei}",
                "--train", "1", "--restore_checkpoint", "1",
                "--test_tf_nonstreaming", "0", "--test_tflite_nonstreaming", "0",
                "--test_tflite_nonstreaming_quantized", "0", "--test_tflite_streaming", "0",
                "--test_tflite_streaming_quantized", "1", "--use_weights", "best_weights", *MIXEDNET]
        self._ausfuehren(args, "training", 0, 1, text, cwd=str(self.ordner), schritte_gesamt=sum(schritte))
        modell = train / MODELL_DATEI
        if not modell.exists():
            raise RuntimeError("Training produced no model")
        return modell

    # --- ehrlicher Test -----------------------------------------------------

    def _test(self, tflite: Path, echt: dict, tts: dict, bg: list[Path], gerede: dict[str, Path]) -> dict:
        positiv = echt["wort_test"]
        quelle = "echt"
        if len(positiv) < MIN_ECHT_TEST:
            quelle = "kuenstlich"
            positiv = positiv + [{"datei": f, "person": ""} for f in self._wavs(tts["test_pos"])[:150]]
        negativ = [a["datei"] for a in echt["kein_test"]] + self._wavs(tts["test_neg"])[:150]
        rede = self._wavs(gerede["test"]) + self._wavs(gerede["dev"])
        random.Random(3).shuffle(rede)
        musik = sorted(str(p) for p in Path(bg[0]).glob("*.wav"))
        random.Random(4).shuffle(musik)
        auftrag = {"positiv": positiv, "negativ": negativ, "gerede": rede, "bg": musik[:300], "max_stunden": 3}

        neu = self._werkzeug("pruefen", {**auftrag, "modell": str(tflite)}, "test", 0, 0.5, "test_neu")
        alt = None
        alt_bytes = self.ha.modell(self.wort_id) if self.auftrag.get("aktiv") else None
        if alt_bytes:
            alt_datei = self.ordner / "alt.tflite"
            alt_datei.write_bytes(alt_bytes)
            alt = self._werkzeug("pruefen", {**auftrag, "modell": str(alt_datei)}, "test", 0.5, 1.0,
                                 "test_alt")
        ziel = float(self.o.get("ziel_fehlausloeser") or 1.0)
        cut_neu, werte_neu = self._schwelle(neu, ziel)
        bericht: dict[str, Any] = {
            "neu": werte_neu, "cutoff": cut_neu, "ziel_fehlausloeser": ziel, "test_quelle": quelle,
            "test_positiv": neu["positiv"], "test_negativ": neu["negativ"], "test_stunden": neu["stunden"],
            "je_schwelle": neu["je_schwelle"], "bewertet_genutzt": getattr(self, "bewertet", 0),
            "start": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.start)),
            "dauer_min": round((time.time() - self.start) / 60, 1),
            "weitertrainiert": getattr(self, "weiter", False),
        }
        if alt:
            cut_alt, werte_alt = self._schwelle(alt, ziel)
            bericht["alt"] = {**werte_alt, "cutoff": cut_alt}
            bericht["besser"] = self._besser(werte_neu, werte_alt, ziel)
        else:
            bericht["alt"] = None
            bericht["besser"] = True
        return bericht

    @staticmethod
    def _schwelle(ergebnis: dict, ziel: float) -> tuple[float, dict]:
        """Niedrigste Schwelle, bei der die Fehlausloeser unter dem Ziel bleiben (sonst die strengste)."""
        je = {float(k): v for k, v in ergebnis["je_schwelle"].items()}
        passend = [c for c, v in sorted(je.items())
                   if v["fehlausloeser_pro_stunde"] is None or v["fehlausloeser_pro_stunde"] <= ziel]
        cut = passend[0] if passend else max(je)
        cut = max(cut, 0.8)  # darunter zu riskant fuer unbekannte Raeume
        if cut not in je:
            cut = min((c for c in je if c >= cut), default=max(je))
        w = je[cut]
        return cut, {
            "trefferquote": w["trefferquote"], "trefferquote_musik": w["trefferquote_musik"],
            "fehlausloeser_pro_stunde": None if w["fehlausloeser_pro_stunde"] is None else round(w["fehlausloeser_pro_stunde"], 2),
            "gegenbeispiele": w["gegenbeispiele"], "je_person": w["je_person"],
        }

    @staticmethod
    def _besser(neu: dict, alt: dict, ziel: float) -> bool:
        tn, ta = neu["trefferquote"] or 0, alt["trefferquote"] or 0
        fn, fa = neu["fehlausloeser_pro_stunde"] or 0, alt["fehlausloeser_pro_stunde"] or 0
        if tn >= ta + 0.01 and fn <= max(fa, ziel) * 1.1:
            return True
        if tn >= ta - 0.005 and fn < fa * 0.8:
            return True
        return False
