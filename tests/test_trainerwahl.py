"""Several trainers: who gets a run, pausing, forgetting, per-trainer restarts, durations and self-update."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant

from custom_components.sprachmodell.const import TRAINER_VERSION
from custom_components.sprachmodell.dauer import schaetzen, ziel_geraet
from custom_components.sprachmodell.zentrale import trainer_name

PROXMOX = {"art": "docker", "version": "1.0.31", "prozessor": "Intel(R) Core(TM) i3-10100T CPU @ 3.00GHz",
           "grafik": [], "tempo": {"vorbereiten_s": 8.0, "rechnen_cpu_s": 6.0}}
PC = {"art": "docker", "version": "1.0.31", "prozessor": "11th Gen Intel(R) Core(TM) i7-11700K @ 3.60GHz",
      "grafik": [{"art": "nvidia", "name": "NVIDIA GeForce RTX 5080, 16303 MiB"}],
      "beschleuniger": {"bild": "gpu", "gpu": True}, "tempo": {"vorbereiten_s": 4.0, "rechnen_cpu_s": 3.0,
                                                               "rechnen_gpu_s": 0.5}}


def test_namen() -> None:
    assert trainer_name(PROXMOX) == "i3-10100T"
    assert trainer_name(PC) == "i7-11700K + RTX 5080"
    assert trainer_name({"art": "app"}) == "Home Assistant App"
    assert trainer_name({"name": "Keller", "name_eigen": True, "prozessor": "x"}) == "Keller"
    assert trainer_name({"name": "164c3b80751d"}) == "164c3b80751d"
    assert trainer_name({}) == "Trainer"


def test_dauer_gemessen_und_geschaetzt() -> None:
    laeufe = [
        {"dauer_min": 100, "training_min": 40, "kandidaten": 1, "geraet": "cpu", "trainer": "proxmox"},
        {"dauer_min": 0},  # broken record: ignored
    ]
    d = schaetzen(laeufe, {"proxmox": PROXMOX, "pc": PC, "neu": {}}, "auto", None)
    assert d["proxmox"] == {"einfach": 100.0, "gruendlich": 180.0, "quelle": "gemessen", "geraet": "cpu"}
    # PC: preparation 60 min x 4/8, training 40 min x 0.5/6 on the card
    assert d["pc"] == {"einfach": round(30 + 40 / 12, 1), "gruendlich": round(30 + 3 * 40 / 12, 1),
                       "quelle": "geschaetzt", "geraet": "gpu"}
    assert d["neu"] is None  # no speed test yet
    # processor only chosen: the PC is scaled with its processor training speed
    assert schaetzen(laeufe, {"proxmox": PROXMOX, "pc": PC}, "cpu", None)["pc"]["einfach"] == 30 + 20
    # runs from before trainer ids belong to the first trainer with an id; an old run without training_min
    alt = [{"dauer_min": 50, "kandidaten": 2, "geraet": "cpu"}]
    assert schaetzen(alt, {"proxmox": PROXMOX}, "auto", "proxmox")["proxmox"]["quelle"] == "gemessen"
    assert ziel_geraet(PC, "auto") == "gpu" and ziel_geraet(PC, "cpu") == "cpu" and ziel_geraet({}, "auto") == "cpu"


async def test_mehrere_trainer(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    w = await z.wort_neu({"wort": "Hey Lumi"})
    w.speicher.daten["laeufe"] = [{"dauer_min": 100, "training_min": 40, "geraet": "cpu", "trainer": "proxmox"}]
    z.trainer_meldet({"info": PROXMOX}, "proxmox")
    z.trainer_meldet({"info": PC}, "pc")
    assert z.daten["trainer_alt"] == "proxmox"  # first trainer with an id: owns the old runs
    z.auftrag(w.id, "von_hand")
    # automatic: the fastest free trainer gets it, the other one is not offered it
    assert z.ziel_trainer(w) == "pc" and z.naechster_auftrag("proxmox") is None
    assert z.naechster_auftrag("pc") is w
    # the PC is busy (speed test, update): the Proxmox takes it
    z.trainer_sehen("pc", frei=False)
    assert z.ziel_trainer(w) == "proxmox"
    z.trainer_sehen("pc", frei=True)
    # fixed choice: always that trainer while it is on, even if busy (the run waits for it)
    await z.einstellungen_setzen({"trainer_wahl": "proxmox"})
    assert z.ziel_trainer(w) == "proxmox"
    z.trainer_sehen("proxmox", frei=False)
    assert z.ziel_trainer(w) is None
    z.trainer_sehen("proxmox", frei=True)
    # paused: never chosen, the other one takes it
    await z.trainer_einstellen("proxmox", pause=True)
    assert z.trainer_pausiert("proxmox") and z.ziel_trainer(w) == "pc"
    await z.trainer_einstellen("proxmox", pause=False)
    assert not z.trainer_pausiert("proxmox")
    # off: the other one takes it
    z.trainer["proxmox"]["kontakt"] = datetime.now(UTC) - timedelta(hours=1)
    assert z.ziel_trainer(w) == "pc"
    z.trainer_sehen("proxmox")
    # a run on the PC: a restart of the Proxmox does not lose it, a restart of the PC does
    await z.einstellungen_setzen({"trainer_wahl": "auto"})
    z.trainer_meldet({"wort_id": w.id, "phase": "training", "prozent": 10}, "pc")
    assert w.speicher.daten["training"]["trainer"] == "pc" and z.laeuft_bei("pc") == [w]
    assert z.haupt_trainer() == "pc" and z.trainer_info["prozessor"] == PC["prozessor"]
    assert z.ziel_trainer(w) == "proxmox"  # the PC is busy with it
    z.trainer_meldet({"neustart": True}, "proxmox")
    assert w.speicher.daten["training"]["phase"] == "training"
    z.trainer_meldet({"neustart": True}, "pc")
    assert w.speicher.daten["training"]["phase"] == "wartet" and w.id in z.reihe()  # queued again
    # the result remembers where it ran, with the speed test to scale it for others
    z.trainer_meldet({"wort_id": w.id, "phase": "training"}, "pc")
    await z.ergebnis(w, b"TFL3x", {"besser": False, "dauer_min": 20, "training_min": 2, "geraet": "gpu"}, "pc")
    lauf = w.speicher.daten["laeufe"][-1]
    assert lauf["trainer"] == "pc" and lauf["trainer_name"] == "i7-11700K + RTX 5080" and lauf["tempo"] == PC["tempo"]
    assert z.dauer(w)["pc"]["quelle"] == "gemessen"
    # forgetting a chosen trainer resets the choice
    await z.einstellungen_setzen({"trainer_wahl": "pc"})
    await z.trainer_einstellen("pc", vergessen=True)
    assert "pc" not in z.trainer and z.opt("trainer_wahl") == "auto"
    await hass.async_block_till_done()


async def test_alter_trainer_und_speichern(hass: HomeAssistant, geladen) -> None:
    """A trainer from before 1.0.31 (no id) is replaced by itself once it sends one; the list survives a reload."""
    z = geladen.runtime_data
    z.trainer_meldet({"info": PROXMOX})
    assert list(z.trainer) == ["trainer"]
    z.trainer["trainer"]["kontakt"] = datetime.now(UTC) - timedelta(hours=1)
    z.trainer_meldet({"info": {**PROXMOX, "swap_belegt_gb": 1}}, "neu1")
    assert list(z.trainer) == ["neu1"]
    await z.trainer_einstellen("neu1", pause=True)
    await hass.async_block_till_done(wait_background_tasks=True)  # every pending save is on disk before the list is cleared
    assert z.daten["trainer"]["neu1"]["info"].get("swap_belegt_gb") is None  # changing values are not stored
    z.trainer.clear()
    await hass.async_add_executor_job(z._laden)
    assert "neu1" in z.trainer and z.trainer_pausiert("neu1") and not z.trainer["neu1"]["frei"]
    # not heard of for a month: removed
    z.trainer["neu1"]["kontakt"] = datetime.now(UTC) - timedelta(days=31)
    await z._stuendlich()
    assert "neu1" not in z.trainer


async def test_selbst_aktualisieren(hass: HomeAssistant, geladen) -> None:
    z = geladen.runtime_data
    z.trainer_meldet({"info": {"art": "docker", "version": "0.1", "selbst_update": True}}, "pc")
    z.trainer_meldet({"info": {"art": "docker", "version": "0.1"}}, "proxmox")
    z._bild[TRAINER_VERSION] = (True, 1e18)
    assert z.aktualisieren_fuer("pc") == TRAINER_VERSION
    assert z.aktualisieren_fuer("proxmox") is None  # no access to Docker: updated by its restart
    z._bild[TRAINER_VERSION] = (False, 1e18)
    assert z.aktualisieren_fuer("pc") is None  # image not published yet
    assert z.aktualisieren_fuer("gibtsnicht") is None
