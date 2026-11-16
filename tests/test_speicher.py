"""Storage of one word: recordings, verdicts, statistics, versions."""

from __future__ import annotations

import io
import json
import os
import time
import wave
import zipfile

import pytest

from custom_components.sprachmodell import speicher as sp
from custom_components.sprachmodell.speicher import Speicher, ist_test, wav_16k, wav_dauer

from .conftest import wav


@pytest.fixture
def s(tmp_path) -> Speicher:
    sp_ = Speicher(str(tmp_path / "wort"))
    sp_.laden()
    return sp_


def _zip(dateien: dict[str, bytes]) -> bytes:
    aus = io.BytesIO()
    with zipfile.ZipFile(aus, "w") as z:
        for name, inhalt in dateien.items():
            z.writestr(name, inhalt)
    return aus.getvalue()


def test_wav_umwandeln() -> None:
    gut = wav()
    assert wav_16k(gut) is gut
    for roh in (wav(kanaele=2), wav(breite=1), wav(breite=4, ton=1 << 20), wav(rate=44100)):
        neu = wav_16k(roh)
        with wave.open(io.BytesIO(neu)) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        assert abs(wav_dauer(neu) - 1.0) < 0.01
    with pytest.raises(ValueError, match="wav_format"):
        wav_16k(wav(breite=3))
    assert wav_dauer(b"kein wav") == 0.0


def test_laden_kaputt_und_speichern(s: Speicher) -> None:
    with open(s.pfad("daten.json"), "w", encoding="utf-8") as datei:
        datei.write("{kaputt")
    s.laden()
    assert s.daten["aufnahmen"] == {} and s.daten["training"] == {"phase": "bereit"}
    s.speichern()
    assert json.load(open(s.pfad("daten.json"), encoding="utf-8"))["version"] == sp.VERSION


def test_zip_einlesen(s: Speicher) -> None:
    with pytest.raises(ValueError, match="keine_zip"):
        s.zip_einlesen(b"nope", None)
    inhalt = _zip({
        "word/a.wav": wav(),
        "word/b.wav": wav(kanaele=2),
        "not_word/c.wav": wav(sekunden=0.8),
        "word/kaputt.wav": b"RIFFxxxx",
        "__MACOSX/word/a.wav": wav(),
        "readme.txt": b"hi",
    })
    erg = s.zip_einlesen(inhalt, "Anna")
    assert erg == {"wort": 2, "kein_wort": 1, "doppelt": 0, "kaputt": 1}
    assert s.zip_einlesen(inhalt, None)["doppelt"] == 3
    personen = {a["person"] for a in s.daten["aufnahmen"].values()}
    assert personen == {"Anna"}


def test_browser_aufnahme(s: Speicher) -> None:
    with pytest.raises(ValueError, match="urteil_unbekannt"):
        s.browser_aufnahme(wav(), "verworfen", None, None)
    with pytest.raises(ValueError, match="zu_kurz"):
        s.browser_aufnahme(wav(sekunden=0.1), "wort", None, None)
    with pytest.raises(ValueError, match="wav_format"):
        s.browser_aufnahme(b"RIFF" + b"\0" * 40, "wort", None, None)
    e = s.browser_aufnahme(wav(), "wort", "Max", "Kitchen")
    assert e["quelle"] == "browser" and e["urteil"] == "wort" and e["notiz"] == "Kitchen"
    assert s.browser_aufnahme(wav(), "wort", None, None)["id"] == e["id"]


def _geraete_aufnahmen(s: Speicher) -> None:
    for i, (art, zeit, score) in enumerate([
        ("nearmiss", "2026-11-16T06:00:00+00:00", 0.95),
        ("wake", "2026-11-16T06:00:10+00:00", 0.99),
        ("nearmiss", "2026-11-16T07:00:00+00:00", 0.90),
        ("mistake", "2026-11-16T08:00:00+00:00", 0.98),
        ("noise", "2026-11-16T09:00:00+00:00", 0.5),
        ("wake", "2026-11-16T10:00:00+00:00", 0.985),
    ]):
        s.aufnahme_neu({"id": f"k-{i}", "quelle": "echo", "echo": "Kitchen", "art": art, "zeit": zeit, "score": score, "cutoff": 0.97}, wav())


def test_vorschlaege_und_urteile(s: Speicher) -> None:
    _geraete_aufnahmen(s)
    s.vorschlaege()
    a = s.daten["aufnahmen"]
    assert (a["k-0"]["vorschlag"], a["k-0"]["grund"]) == ("wort", "verpasst")
    assert (a["k-1"]["vorschlag"], a["k-1"]["grund"]) == ("wort", "aufgewacht")
    assert (a["k-2"]["vorschlag"], a["k-2"]["grund"]) == ("kein_wort", "knapp")
    assert (a["k-3"]["vorschlag"], a["k-3"]["grund"]) == ("kein_wort", "abgebrochen")
    assert (a["k-4"]["vorschlag"], a["k-4"]["grund"]) == ("kein_wort", "geraeusch")
    assert len(s.offen()) == 6
    with pytest.raises(ValueError, match="urteil_unbekannt"):
        s.urteilen(["k-0"], "vielleicht", None)
    assert s.urteilen(["k-0", "k-1", "fehlt"], "wort", "Anna") == 2
    assert s.urteilen(["k-3"], "kein_wort", None) == 1
    assert s.person_setzen(["k-3", "fehlt"], "Max") == 1
    assert s.urteilen(["k-3"], None, "") == 1 and s.daten["aufnahmen"]["k-3"]["person"] is None
    s.vorschlaege()  # bereits bewertete bleiben
    assert s.liste("offen", None, None, 0)["gesamt"] == 4
    assert s.liste("bewertet", "Kitchen", "wort", 0)["gesamt"] == 2
    assert s.liste("hochgeladen", None, None, 0)["gesamt"] == 0
    assert s.liste("test", None, None, 0)["gesamt"] == sum(ist_test(i) for i in ("k-0", "k-1"))
    assert s.liste("alle", None, None, 0, je_seite=4)["seiten"] == 2
    assert s.bekannt("k-0") and not s.bekannt("x")


def test_statistik_mit_schwelle(s: Speicher) -> None:
    for i in range(12):
        s.aufnahme_neu({"id": f"w{i}", "quelle": "echo", "echo": "Kitchen", "art": "wake", "score": 0.97 + i * 0.002, "urteil": "wort"}, wav())
    for i in range(6):
        s.aufnahme_neu({"id": f"f{i}", "quelle": "echo", "echo": "Kitchen", "art": "mistake", "score": 0.975, "urteil": "kein_wort"}, wav())
    s.aufnahme_neu({"id": "v", "quelle": "echo", "echo": "Kitchen", "art": "nearmiss", "score": 0.9, "urteil": "wort", "person": "Anna"}, wav())
    st = s.statistik()
    assert st["bewertet"] == 19 and st["wort"] == 13 and st["kein_wort"] == 6
    assert st["alltag"] == {"aufgewacht": 18, "richtig": 12, "falsch": 6, "verpasst": 1}
    assert st["schwelle_vorschlag"] == pytest.approx(0.98)
    assert st["personen"]["Anna"] == {"wort": 1, "kein_wort": 0}
    assert st["aeltestes_offen"] is None
    assert len(s.trainer_liste()) == 19


def test_loeschen_und_aufraeumen(s: Speicher) -> None:
    s.aufnahme_neu({"id": "alt", "quelle": "echo", "zeit": "2020-01-01T00:00:00+00:00"}, wav())
    s.aufnahme_neu({"id": "neu", "quelle": "echo"}, wav())
    s.aufnahme_neu({"id": "weg", "quelle": "echo", "urteil": "verworfen"}, wav())
    os.remove(s.pfad("aufnahmen", "neu.wav"))
    assert s.loeschen(["neu", "fehlt"]) == 1
    assert s.aufraeumen(60) == 2
    assert s.daten["aufnahmen"] == {} and s.bekannt("alt")
    assert s.aufraeumen(60) == 0


def test_versionen(s: Speicher, tmp_path) -> None:
    eintrag = s.version_neu(b"TFL3modell", {"neu": {"trefferquote": 0.9}})
    assert eintrag["nr"] == 1 and os.path.isfile(s.modell_datei(1)) and s.version(1) is eintrag
    s.version_neu(b"TFL3zwei", {})
    ziel = str(tmp_path / "custom_wake_words")
    s.einspielen_dateien(1, ziel, "hey_lumi", "Hey Lumi (custom)", 0.95, "en")
    s.einspielen_dateien(2, ziel, "hey_lumi", "Hey Lumi (custom)", 0.95, "en")
    beschreibung = json.load(open(os.path.join(ziel, "hey_lumi.json"), encoding="utf-8"))
    assert beschreibung["wake_word"] == "Hey Lumi (custom)" and beschreibung["micro"]["probability_cutoff"] == 0.95
    assert beschreibung["author"] == "Wake Word Studio v2"
    assert s.daten["aktiv"] == 2 and s.version(1)["status"] == "frueher"
    assert s.version(9) is None


def test_vorhandenes_uebernehmen(s: Speicher, tmp_path) -> None:
    datei = tmp_path / "alt.tflite"
    assert s.vorhandenes_uebernehmen(str(datei)) is None
    datei.write_bytes(b"TFL3alt")
    (tmp_path / "alt.bericht.json").write_text(json.dumps({"neu": {"trefferquote": 0.8}}))
    e = s.vorhandenes_uebernehmen(str(datei))
    assert e["status"] == "aktiv" and e["bericht"]["neu"]["trefferquote"] == 0.8
    assert not (tmp_path / "alt.bericht.json").exists()
    assert s.vorhandenes_uebernehmen(str(datei)) is None


def test_zeit_und_id() -> None:
    assert sp._zeit(None) == 0.0 and sp._zeit("2026-01-01T00:00:00Z") > 0
    assert sp.sichere_id("a/b c") == "a_b_c"
    assert abs(time.time() - sp._zeit(sp.jetzt())) < 5


def test_namen_angleichen(s: Speicher) -> None:
    """A renamed device is one device: old recordings take its current name."""
    a = s.daten["aufnahmen"]
    a["k1"] = {"id": "k1", "quelle": "echo", "echo": "Kueche", "knoten": "kueche"}
    a["k2"] = {"id": "kueche-7", "quelle": "echo", "echo": "Kueche"}
    a["k3"] = {"id": "echo2nd-3", "quelle": "echo", "echo": "Echo2nd"}
    a["k4"] = {"id": "echo-1", "quelle": "echo", "echo": "Alt"}
    a["h1"] = {"id": "h1", "quelle": "hochgeladen", "echo": None}
    namen = {"kueche": "Küche", "echo2nd": "Wohnzimmer Echo", "echo": "Flur"}
    assert s.namen_angleichen(namen) is True
    assert [a[k]["echo"] for k in ("k1", "k2", "k3", "k4")] == ["Küche", "Küche", "Wohnzimmer Echo", "Flur"]
    assert a["k2"]["knoten"] == "kueche" and a["k3"]["knoten"] == "echo2nd" and a["k4"]["knoten"] == "echo"
    assert a["h1"]["echo"] is None
    assert s.namen_angleichen(namen) is False
    assert s.namen_angleichen({}) is False
