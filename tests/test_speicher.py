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


def test_entscheidungen_zweifel_zuerst(s: Speicher) -> None:
    """History -> reviewed: counts of said / not said, and the answers the device disagreed with first."""
    for i, (u, score) in enumerate([("wort", 0.99), ("wort", 0.05), ("kein_wort", 0.2), ("kein_wort", 0.98),
                                    ("wort", None), ("wort", 0.6)]):
        s.aufnahme_neu({"id": f"e{i}", "quelle": "echo", "echo": "Kitchen", "art": "wake", "score": score,
                        "urteil": u, "zeit": f"2026-11-2{i}T10:00:00+00:00"}, wav())
    s.aufnahme_neu({"id": "offen", "quelle": "echo", "art": "nearmiss", "score": 0.9}, wav())
    alle = s.liste("bewertet", None, None, 0)
    assert alle["anzahl"] == {"wort": 4, "kein_wort": 2} and alle["gesamt"] == 6
    assert [e["id"] for e in alle["eintraege"]][:2] == ["e5", "e4"]  # newest first by default
    z = s.liste("bewertet", None, None, 0, sortierung="zweifel")
    assert [e["id"] for e in z["eintraege"]] == ["e3", "e1", "e5", "e2", "e0", "e4"]  # no score last
    nur = s.liste("bewertet", None, "wort", 0, sortierung="zweifel")
    assert [e["id"] for e in nur["eintraege"]] == ["e1", "e5", "e0", "e4"] and nur["anzahl"]["kein_wort"] == 2


def test_verlauf_filter_art_person_nichts_gehoert(s: Speicher) -> None:
    """History: device, kind, person or 'nothing intelligible heard' one at a time; each chip counts what you
    would see after tapping it. The one-tap 'unusable' takes only what the list counts for it: unanswered,
    nothing heard, and never a recording where the device woke up (possible false wake)."""
    for aid, art, urteil, person, gehoert, echo in [
            ("w1", "wake", "wort", "Anna", "alisa", "Kitchen"), ("w2", "wake", "wort", "Ben", "", "Kitchen"),
            ("m1", "mistake", "kein_wort", None, "", "Hall"), ("n1", "nearmiss", None, None, "", "Kitchen"),
            ("n2", "nearmiss", None, None, "", "Hall"), ("n3", "nearmiss", None, None, "hallo", "Kitchen"),
            ("x1", "wake", None, None, "", "Kitchen"), ("g1", "noise", None, None, "", "Kitchen")]:
        s.aufnahme_neu({"id": aid, "quelle": "echo", "echo": echo, "art": art, "score": 0.5, "urteil": urteil,
                        "person": person}, wav())
        s.daten["aufnahmen"][aid]["gehoert"] = gehoert
    alle = s.liste("alle", None, None, 0)
    assert alle["arten"] == {"wake": 3, "mistake": 1, "nearmiss": 3, "noise": 1}
    assert alle["echos"] == {"Kitchen": 6, "Hall": 2}
    assert alle["personen"] == {"Anna": 1, "Ben": 1} and alle["nichts"] == 6
    assert alle["nichts_offen"] == 3  # n1, n2, g1: x1 woke the device, w2/m1 are answered
    knapp = s.liste("alle", None, None, 0, typ="nearmiss")
    assert {e["id"] for e in knapp["eintraege"]} == {"n1", "n2", "n3"}
    assert knapp["arten"]["wake"] == 3 and knapp["echos"] == {"Kitchen": 2, "Hall": 1} and knapp["nichts"] == 2
    assert [e["id"] for e in s.liste("alle", None, None, 0, person="Ben")["eintraege"]] == ["w2"]
    assert s.liste("alle", None, None, 0, person="Ben")["arten"] == {"wake": 1}
    nichts = s.liste("alle", None, None, 0, nichts=True)
    assert {e["id"] for e in nichts["eintraege"]} == {"w2", "m1", "n1", "n2", "x1", "g1"}
    assert nichts["arten"] == {"wake": 2, "mistake": 1, "nearmiss": 2, "noise": 1} and nichts["nichts"] == 6
    kueche = s.liste("alle", "Kitchen", None, 0, nichts=True)
    assert kueche["echos"] == {"Kitchen": 4, "Hall": 2} and kueche["nichts_offen"] == 2
    assert sorted(s.nichts_sammeln("alle")) == ["g1", "n1", "n2"] and s.nichts_sammeln("offen", "Hall") == ["n2"]
    assert s.nichts_sammeln("alle", typ="wake") == [] and s.nichts_sammeln("bewertet") == []
    assert s.nichts_sammeln("alle", person="Ben") == []
    s.urteilen(s.nichts_sammeln("offen", "Kitchen"), "verworfen", None)
    a = s.daten["aufnahmen"]
    assert a["n1"]["urteil"] == a["g1"]["urteil"] == "verworfen" and not a["n2"].get("urteil")
    assert not a["x1"].get("urteil") and a["w2"]["urteil"] == "wort"


def test_beinahe_unter_08_selbst_nicht_gesagt(s: Speicher) -> None:
    """Pre-review: low near misses in which speech recognition heard neither the word nor anything like it."""
    faelle = {"tv": ("nearmiss", 0.6, "привет как дела"), "still": ("nearmiss", 0.7, ""),
              "knapp": ("nearmiss", 0.85, ""), "lisa": ("nearmiss", 0.6, "Лиза, иди сюда"),
              "wort": ("nearmiss", 0.6, "Алиса включи свет"), "wake": ("wake", 0.6, ""),
              "ohne_score": ("nearmiss", None, "")}
    for aid, (art, score, _) in faelle.items():
        s.aufnahme_neu({"id": aid, "quelle": "echo", "echo": "Kitchen", "art": art, "score": score}, wav())
    s.aufnahme_neu({"id": "offen", "quelle": "echo", "art": "nearmiss", "score": 0.5}, wav())  # not heard yet
    n = s.gehoert_setzen({k: v[2] for k, v in faelle.items()}, "Алиса", True)
    a = s.daten["aufnahmen"]
    assert a["tv"]["urteil"] == "kein_wort" and a["tv"]["auto"] and a["still"]["urteil"] == "kein_wort"
    assert a["wort"]["urteil"] == "wort" and n == 3
    for aid in ("knapp", "lisa", "wake", "ohne_score", "offen"):
        assert not a[aid].get("urteil"), aid
    # switched off: nothing decided by itself; afterwards the sweep catches up
    s.urteilen(["tv"], None, None)
    s.daten["aufnahmen"]["tv"].pop("auto", None)
    assert s.gehoert_setzen({"tv": "привет"}, "Алиса", False) == 0 and not a["tv"].get("urteil")
    assert s.beinahe_nachziehen("Алиса") == 1 and a["tv"]["urteil"] == "kein_wort"


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
    assert beschreibung["micro"]["tensor_arena_size"] == 30000


def test_gemitteltes_modell_braucht_mehr_speicher(s: Speicher, tmp_path) -> None:
    s.version_neu(b"TFL3gemittelt", {"tensor_arena": 90000, "modell_teile": 3})
    s.version_neu(b"TFL3kaputt", {"tensor_arena": "viel"})
    ziel = str(tmp_path / "custom_wake_words")
    s.einspielen_dateien(1, ziel, "hey_lumi", "Hey Lumi", 0.95, "en")
    assert json.load(open(os.path.join(ziel, "hey_lumi.json"), encoding="utf-8"))["micro"]["tensor_arena_size"] == 90000
    s.einspielen_dateien(2, ziel, "hey_lumi", "Hey Lumi", 0.95, "en")
    assert json.load(open(os.path.join(ziel, "hey_lumi.json"), encoding="utf-8"))["micro"]["tensor_arena_size"] == 30000


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


def test_testsatz_tageweise() -> None:
    """Older recordings keep their place; from TEST_NEU_AB on whole days go to the test."""
    from custom_components.sprachmodell.speicher import TEST_NEU_AB, ist_test

    alt = [ist_test(f"id{i}", "2026-11-10T10:00:00+00:00") for i in range(200)]
    assert alt == [ist_test(f"id{i}") for i in range(200)] and 20 < sum(alt) < 60
    for tag in range(17, 30):
        am_tag = {ist_test(f"id{i}", f"2026-11-{tag}T{h:02d}:00:00+00:00") for i in range(20) for h in (1, 13, 23)}
        assert len(am_tag) == 1  # one day: all train or all test
    tage = [ist_test("x", f"2026-12-{t:02d}T12:00:00+00:00") for t in range(1, 31)]
    assert 4 <= sum(tage) <= 18
    assert TEST_NEU_AB.startswith("2026-11-17")


def test_gehoert_gleicher_ton_schnitt(tmp_path) -> None:
    from custom_components.sprachmodell.speicher import Speicher, wort_gehoert

    sp = Speicher(str(tmp_path))
    sp.laden()
    sp.aufnahme_neu({"id": "a", "quelle": "echo", "art": "wake"}, wav(ton=500))
    sp.aufnahme_neu({"id": "b", "quelle": "echo", "art": "nearmiss"}, wav(ton=600))
    assert sp.gleicher_ton(wav(ton=500)) and not sp.gleicher_ton(wav(ton=700))
    assert sp.zum_hoeren(10) and set(sp.zum_hoeren(10)) == {"a", "b"}
    assert sp.gehoert_setzen({"a": "Алиса!", "b": "Алина", "c": "x"}, "Алиса", True) == 1
    assert sp.daten["aufnahmen"]["a"]["urteil"] == "wort" and sp.daten["aufnahmen"]["b"]["urteil"] is None
    assert sp.zum_hoeren(10) == []
    assert wort_gehoert("ну, Алиса, включи", "алиса") and wort_gehoert("Hey, Lumi!", "Hey Lumi")
    assert wort_gehoert("ёлка", "Елка") and not wort_gehoert("", "x") and not wort_gehoert("Alexa", "Alisa")
    assert sp.schnitt_setzen("a", 0.1, 0.9)["schnitt"] == [0.1, 0.9]
    assert sp.schnitt_setzen("a", 0.5, None)["schnitt"] == [0.5, 1.0]  # end: the whole length
    assert "schnitt" not in sp.schnitt_setzen("a", None, None)


def test_an_anderes_wort_geben(tmp_path) -> None:
    jarvis, casita = Speicher(str(tmp_path / "j")), Speicher(str(tmp_path / "c"))
    jarvis.laden()
    casita.laden()
    jarvis.aufnahme_neu({"id": "x", "quelle": "echo", "art": "wake", "score": 0.97, "cutoff": 0.9, "echo": "Küche"},
                        wav(ton=500))
    jarvis.schnitt_setzen("x", 0.1, 0.8)
    von, zu = {"id": "j", "wort": "hey jarvis"}, {"id": "c", "wort": "hey casita"}
    with pytest.raises(ValueError, match="gleiches_wort"):
        jarvis.an_wort_geben("x", jarvis, von, von, None)
    with pytest.raises(ValueError, match="aufnahme_fehlt"):
        jarvis.an_wort_geben("nix", casita, von, zu, None)
    neu = jarvis.an_wort_geben("x", casita, von, zu, "Wadim")
    assert neu["urteil"] == "wort" and neu["person"] == "Wadim" and neu["schnitt"] == [0.1, 0.8]
    assert neu["score"] is None and neu["art"] == "wake" and neu["von_wort"]["score"] == 0.97
    assert os.path.exists(casita.pfad("aufnahmen", "x.wav"))
    a = jarvis.daten["aufnahmen"]["x"]
    assert a["urteil"] == "kein_wort" and a["zu_wort"]["wort"] == "hey casita"
    # for "hey jarvis" it was a false wake; at "hey casita" the other model's wake-up does not count
    assert jarvis.statistik()["alltag"]["falsch"] == 1
    st = casita.statistik()
    assert st["wort"] == 1 and st["alltag"]["aufgewacht"] == 0 and st["schwelle_basis"]["wort"] == 0
    assert [e["id"] for e in casita.trainer_liste()] == ["x"]
    with pytest.raises(ValueError, match="schon_da"):
        jarvis.an_wort_geben("x", casita, von, zu, None)
    # undo: copy gone, answer as before (not reviewed)
    jarvis.zurueckholen("x", casita)
    assert "x" not in casita.daten["aufnahmen"] and not os.path.exists(casita.pfad("aufnahmen", "x.wav"))
    assert jarvis.daten["aufnahmen"]["x"]["urteil"] is None and "zu_wort" not in jarvis.daten["aufnahmen"]["x"]
    with pytest.raises(ValueError, match="aufnahme_fehlt"):
        jarvis.zurueckholen("x", casita)
