"""Der zusammengesetzte Ablauf plus Terminal- und Bridge-Anbindung.

Hier zählt vor allem, dass im Zweifel NICHTS passiert und dass ein
Fehlschlag die installierte Fassung unangetastet lässt.
"""
from __future__ import annotations

import hashlib

import pytest
from rich.console import Console

from bmtools.update import ablauf
from bmtools.update import laden as ld
from bmtools.update import tausch as t
from bmtools.update.manifest import Artefakt
from bmtools.update.pruefen import Angebot

INHALT = b"neue fassung"


def angebot(version: str = "0.4.1") -> Angebot:
    return Angebot(version=version,
                   artefakt=Artefakt(datei="bmtools-0.4.1-linux-x64.tar.gz",
                                     sha256=hashlib.sha256(INHALT).hexdigest()),
                   basis_url="https://example.invalid/v0.4.1",
                   vorabversion=False)


@pytest.fixture
def installation(tmp_path, monkeypatch):
    """Eine gefrorene Installation, die ersetzt werden darf."""
    ziel = tmp_path / "bmtools"
    ziel.write_bytes(b"alte fassung")
    monkeypatch.setattr(ablauf, "eigenes_programm", lambda: ziel)
    monkeypatch.setattr(ablauf, "plattform", lambda: "linux-x64")
    monkeypatch.setattr(ablauf, "beschreibbar", lambda p: True)
    return ziel


def test_ohne_gefrorenes_programm_kein_angebot(monkeypatch):
    """Quellcode-Checkout: nichts anzubieten, git pull ist der Weg."""
    monkeypatch.setattr(ablauf, "eigenes_programm", lambda: None)
    assert ablauf.suche() is None


def test_durchfuehren_im_quellcode_wirft_verstaendlich(monkeypatch):
    monkeypatch.setattr(ablauf, "eigenes_programm", lambda: None)
    monkeypatch.setattr(ablauf, "plattform", lambda: None)
    with pytest.raises(ablauf.UpdateFehler, match="git pull"):
        ablauf.durchfuehren(angebot())


def test_ohne_schreibrecht_wird_nichts_geladen(installation, monkeypatch):
    """Früh scheitern — nicht erst nach 240 MB Download."""
    monkeypatch.setattr(ablauf, "beschreibbar", lambda p: False)
    geladen = []
    monkeypatch.setattr(ld, "hole", lambda *a, **k: geladen.append(1))
    with pytest.raises(ablauf.UpdateFehler, match="Schreibrecht"):
        ablauf.durchfuehren(angebot())
    assert geladen == []


def test_erfolgreicher_ablauf(installation, monkeypatch):
    def hole(ang, nach, fortschritt=None, client=None):
        p = nach / ang.artefakt.datei
        p.write_bytes(INHALT)
        return p

    monkeypatch.setattr(ld, "hole", hole)
    monkeypatch.setattr(ld, "packe_aus", lambda archiv, nach, plat: archiv)
    monkeypatch.setattr(t, "ersetze", lambda ziel, neu: True)

    assert ablauf.durchfuehren(angebot()) is True
    # Arbeitsordner ist nach dem Tausch wieder weg
    assert not (installation.parent / ablauf.ARBEITSORDNER).exists()


def test_fehlschlag_raeumt_auf_und_meldet_verstaendlich(installation,
                                                        monkeypatch):
    def kaputt(*a, **k):
        raise ld.LadeFehler("Prüfsumme weicht ab")

    monkeypatch.setattr(ld, "hole", kaputt)
    with pytest.raises(ablauf.UpdateFehler, match="Prüfsumme"):
        ablauf.durchfuehren(angebot())
    assert not (installation.parent / ablauf.ARBEITSORDNER).exists()
    assert installation.read_bytes() == b"alte fassung"


def test_arbeitsordner_liegt_neben_dem_ziel(installation, monkeypatch):
    """os.replace kann keine Dateisystemgrenzen überschreiten — der
    Arbeitsordner darf deshalb nicht im System-Temp liegen."""
    gesehen = {}

    def hole(ang, nach, fortschritt=None, client=None):
        gesehen["ordner"] = nach
        p = nach / ang.artefakt.datei
        p.write_bytes(INHALT)
        return p

    monkeypatch.setattr(ld, "hole", hole)
    monkeypatch.setattr(ld, "packe_aus", lambda archiv, nach, plat: archiv)
    monkeypatch.setattr(t, "ersetze", lambda ziel, neu: True)
    ablauf.durchfuehren(angebot())
    assert gesehen["ordner"].parent == installation.parent


def test_start_aufraeumen_verwirft_das_backup(installation):
    t.backup_pfad(installation).write_bytes(b"vorversion")
    ablauf.beim_start_aufraeumen()
    assert not t.backup_pfad(installation).exists()


def test_start_aufraeumen_entsorgt_den_helfer(installation):
    """Ein Helfer-Skript, das nie zum Selbstlöschen kam, verschwindet
    beim nächsten Start — es hat seinen Zweck erfüllt oder verfehlt,
    gebraucht wird es jedenfalls nicht mehr."""
    helfer = installation.with_name(t.HELFER_NAME)
    helfer.write_text("@echo off")
    ablauf.beim_start_aufraeumen()
    assert not helfer.exists()


def test_start_aufraeumen_stoert_nie(monkeypatch):
    """Auch wenn darunter alles schiefgeht: der Start läuft weiter."""
    def kaputt():
        raise RuntimeError("kaputt")

    monkeypatch.setattr(ablauf, "eigenes_programm", kaputt)
    ablauf.beim_start_aufraeumen()      # darf nicht werfen


def test_hinweiszeilen_nennen_beide_versionen():
    zeilen = ablauf.hinweis_zeilen(angebot("0.4.1"))
    assert "0.4.1" in zeilen[0]
    assert "--update" in zeilen[1]


# ---------------------------------------------------------- Terminal

def test_terminal_hinweis_nur_auf_einer_konsole(monkeypatch, capsys):
    """In einer Pipe oder im Cronjob bleibt es still."""
    from bmtools.update import terminal

    monkeypatch.setattr("bmtools.update.terminal.ablauf.suche",
                        lambda **k: angebot())
    pruefung = terminal.Hintergrundpruefung().starten()
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    pruefung.hinweis_ausgeben(Console())
    assert capsys.readouterr().out == ""


def test_terminal_pruefung_schluckt_fehler(monkeypatch):
    from bmtools.update import terminal

    def kaputt(**k):
        raise RuntimeError("kein Netz")

    monkeypatch.setattr("bmtools.update.terminal.ablauf.suche", kaputt)
    pruefung = terminal.Hintergrundpruefung().starten()
    pruefung._thread.join(timeout=2)
    assert pruefung._angebot is None


@pytest.fixture
def ausgeliefert(tmp_path, monkeypatch):
    """`--update` tut nur im ausgelieferten Programm überhaupt etwas."""
    monkeypatch.setattr("bmtools.update.terminal.eigenes_programm",
                        lambda: tmp_path / "bmtools")


def test_update_ausfuehren_verweist_im_quellcode_auf_git(monkeypatch, capsys):
    """Kein »Bereits aktuell« im Checkout — das wäre schlicht falsch.

    Hier gibt es nichts zu tauschen, also darf auch nicht der Eindruck
    entstehen, man sei auf dem neuesten Stand (Befund 2026-07-27).
    """
    from bmtools.update import terminal

    monkeypatch.setattr("bmtools.update.terminal.eigenes_programm",
                        lambda: None)

    def nie(**k):
        raise AssertionError("darf gar nicht erst suchen")

    monkeypatch.setattr("bmtools.update.terminal.ablauf.suche", nie)
    assert terminal.update_ausfuehren(Console()) == 0
    ausgabe = capsys.readouterr().out
    assert "git pull" in ausgabe
    assert "aktuell" not in ausgabe.lower()


def test_update_ausfuehren_meldet_aktuell(monkeypatch, capsys, ausgeliefert):
    from bmtools.update import terminal

    monkeypatch.setattr("bmtools.update.terminal.ablauf.suche",
                        lambda **k: None)
    assert terminal.update_ausfuehren(Console()) == 0
    assert "aktuell" in capsys.readouterr().out.lower()


def test_update_ausfuehren_meldet_fehlschlag_klar(monkeypatch, capsys,
                                                  ausgeliefert):
    from bmtools.update import terminal

    monkeypatch.setattr("bmtools.update.terminal.ablauf.suche",
                        lambda **k: angebot())

    def kaputt(ang, fortschritt=None):
        raise ablauf.UpdateFehler("Kein Schreibrecht in /opt")

    monkeypatch.setattr("bmtools.update.terminal.ablauf.durchfuehren",
                        kaputt)
    assert terminal.update_ausfuehren(Console()) == 1
    ausgabe = capsys.readouterr().out
    assert "Schreibrecht" in ausgabe
    assert "unverändert" in ausgabe   # beruhigt: nichts kaputtgemacht


# ------------------------------------------------------------ Bridge

def test_bridge_respektiert_die_abschaltung(monkeypatch):
    from bmtools.gui import einstellungen
    from bmtools.gui.bridge import Bridge

    monkeypatch.setattr(einstellungen, "laden",
                        lambda: {"update_pruefen": False})
    monkeypatch.setattr(ablauf, "suche",
                        lambda **k: pytest.fail("hätte nicht suchen dürfen"))
    assert Bridge().suche_update() is None


def test_bridge_reicht_das_angebot_durch(monkeypatch):
    from bmtools.gui import einstellungen
    from bmtools.gui.bridge import Bridge

    monkeypatch.setattr(einstellungen, "laden", lambda: {})
    monkeypatch.setattr(ablauf, "suche", lambda **k: angebot())
    info = Bridge().suche_update()
    assert info == {"version": "0.4.1", "vorabversion": False,
                    "datei": "bmtools-0.4.1-linux-x64.tar.gz"}


def test_angezeigte_version_traegt_die_label_schreibweise(monkeypatch):
    """Beta-Versionen erreichen die Oberfläche als `0.4.1-beta.2`.

    Intern und beim Vergleichen gilt die PEP-440-Form `0.4.1b2`; auf der
    Releases-Seite und in jedem Dateinamen steht aber `0.4.1-beta.2`.
    Zeigte das Programm die interne Form, vergliche ein Tester zwei
    Schreibweisen desselben Standes und meldete einen Fehler, der keiner
    ist (Nutzerentscheidung 2026-07-27).

    Der Test hängt an den WEGEN nach draußen, nicht an `version_anzeige`
    selbst — sonst bliebe er grün, wenn der Aufruf irgendwo herausfällt.
    """
    import dataclasses

    from bmtools.gui import einstellungen
    from bmtools.gui.bridge import Bridge

    beta = dataclasses.replace(angebot("0.4.1b2"), vorabversion=True)
    monkeypatch.setattr(einstellungen, "laden", lambda: {"update_vorab": True})
    monkeypatch.setattr(ablauf, "suche", lambda **k: beta)

    info = Bridge().suche_update()
    assert info is not None and info["version"] == "0.4.1-beta.2"
    assert "0.4.1-beta.2" in ablauf.hinweis_zeilen(beta)[0]


def test_bridge_zerstoert_das_fenster_nicht_im_eigenen_aufruf(monkeypatch):
    """destroy() mitten im Bridge-Aufruf riss die WKWebView ab, bevor
    sie die Antwort auf genau diesen Aufruf liefern konnte — das
    Fenster fror bei »Neustart …« ein (Beta-Befund 2026-07-27, macOS).
    Der Abriss muss nachgelagert laufen, nie synchron."""
    import threading

    from bmtools.gui.bridge import Bridge

    monkeypatch.setattr(ablauf, "neustart", lambda: None)
    geplant = []

    class TimerAttrappe:
        def __init__(self, wartezeit, funktion):
            geplant.append((wartezeit, funktion))

        def start(self):
            pass

    monkeypatch.setattr(threading, "Timer", TimerAttrappe)

    class Fenster:
        def destroy(self):
            pytest.fail("destroy() lief synchron im Bridge-Aufruf")

    bridge = Bridge()
    bridge._fenster = Fenster()
    bridge.neustart_nach_update()
    assert len(geplant) == 1
    wartezeit, funktion = geplant[0]
    assert funktion == bridge._fenster.destroy    # DER Abriss, nur später
    assert wartezeit > 0


def test_bridge_schluckt_netzfehler(monkeypatch):
    from bmtools.gui import einstellungen
    from bmtools.gui.bridge import Bridge

    def kaputt(**k):
        raise RuntimeError("kein Netz")

    monkeypatch.setattr(einstellungen, "laden", lambda: {})
    monkeypatch.setattr(ablauf, "suche", kaputt)
    assert Bridge().suche_update() is None
