"""Artefakt holen, prüfen und auspacken — alles vor dem Tausch.

Reihenfolge ist auch hier Sicherheit: Erst vollständig herunterladen,
dann den SHA256 **aus dem signierten Manifest** vergleichen, erst dann
auspacken. Ein Archiv, dessen Prüfsumme nicht stimmt, wird nie geöffnet.
"""
from __future__ import annotations

import os
import shutil
import stat
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx

from .pruefen import ZEITLIMIT, Angebot

# Reichlich Luft über dem Linux-Bundle (rund 240 MB) — aber nicht
# unbegrenzt: Ein manipuliertes Gegenüber soll uns nicht die Platte
# vollschreiben können.
ARTEFAKT_MAX = 600 * 1024 * 1024


class LadeFehler(Exception):
    """Herunterladen, Prüfen oder Auspacken gescheitert."""


def _sicherer_pfad(ziel: Path, name: str) -> Path:
    """Archiv-Eintrag auf `ziel` abbilden — oder werfen.

    Verhindert Zip-Slip: Ein Eintrag namens `../../.bashrc` würde sonst
    beim Auspacken außerhalb des Zielordners landen. Das Manifest ist
    zwar signiert, der Archivinhalt aber nicht einzeln — und ein
    kompromittierter Bauprozess soll hier nicht durchgreifen.
    """
    aufgeloest = (ziel / name).resolve()
    if not aufgeloest.is_relative_to(ziel.resolve()):
        raise LadeFehler(f"Archiv-Eintrag zeigt aus dem Ordner heraus: {name!r}")
    return aufgeloest


def _linkziel_pruefen(eintrag: Path, linkziel: str, wurzel: Path) -> None:
    """Symlink-Ziel muss innerhalb des Auspack-Ordners bleiben.

    Rein lexikalisch geprüft (normpath statt resolve): Beim Prüfen ist
    noch nichts ausgepackt, und da JEDES Linkziel im Ordner bleiben
    muss, kann auch eine Kette von Verknüpfungen nicht hinausführen.
    """
    if Path(linkziel).is_absolute():
        raise LadeFehler(f"Verknüpfung mit absolutem Ziel: {linkziel!r}")
    aufgeloest = Path(os.path.normpath(eintrag.parent / linkziel))
    if not aufgeloest.is_relative_to(wurzel.resolve()):
        raise LadeFehler(
            f"Verknüpfung zeigt aus dem Ordner heraus: {linkziel!r}")


def _zip_auspacken(z: zipfile.ZipFile, nach: Path) -> None:
    """extractall-Ersatz, der Symlinks als Symlinks auspackt.

    `zipfile.extractall` macht aus einem Symlink eine reguläre Datei
    mit dem Linkziel als Inhalt. Das .app-Bundle enthält aber Symlinks
    (Frameworks) — so entpackt wäre seine Signatur zerstört, codesign
    lehnte ab und jedes macOS-Update bräche folgenlos ab. Deshalb
    selbst auspacken: Symlinks bleiben Symlinks (Ziele geprüft, gleiche
    Tiefenverteidigung wie beim Zip-Slip), Dateirechte aus dem Archiv
    bleiben erhalten (ditto packt sie beim Bauen mit ein).
    """
    for eintrag in z.infolist():
        pfad = _sicherer_pfad(nach, eintrag.filename)
        modus = eintrag.external_attr >> 16
        if stat.S_ISLNK(modus):
            linkziel = z.read(eintrag).decode("utf-8", errors="replace")
            _linkziel_pruefen(pfad, linkziel, nach)
            pfad.parent.mkdir(parents=True, exist_ok=True)
            pfad.symlink_to(linkziel)
        elif eintrag.is_dir():
            pfad.mkdir(parents=True, exist_ok=True)
        else:
            pfad.parent.mkdir(parents=True, exist_ok=True)
            with z.open(eintrag) as quelle, pfad.open("wb") as datei:
                shutil.copyfileobj(quelle, datei)
            if stat.S_IMODE(modus):
                pfad.chmod(stat.S_IMODE(modus))


def hole(angebot: Angebot, nach: Path,
         fortschritt: Callable[[int, int], None] | None = None,
         client: httpx.Client | None = None) -> Path:
    """Artefakt herunterladen und gegen das Manifest prüfen."""
    ziel = nach / angebot.artefakt.datei
    eigener = client is None
    client = client or httpx.Client(timeout=ZEITLIMIT, verify=True,
                                    follow_redirects=True)
    try:
        with client.stream("GET", angebot.datei_url) as antwort:
            antwort.raise_for_status()
            gesamt = int(antwort.headers.get("content-length") or 0)
            geladen = 0
            with ziel.open("wb") as f:
                for stueck in antwort.iter_bytes(64 * 1024):
                    geladen += len(stueck)
                    if geladen > ARTEFAKT_MAX:
                        raise LadeFehler("Artefakt ist unplausibel groß")
                    f.write(stueck)
                    if fortschritt:
                        fortschritt(geladen, gesamt)
    except httpx.HTTPError as e:
        raise LadeFehler(f"Download gescheitert: {e}") from e
    finally:
        if eigener:
            client.close()

    if not angebot.artefakt.passt_zu(ziel.read_bytes()):
        ziel.unlink(missing_ok=True)
        raise LadeFehler(
            "Prüfsumme weicht vom signierten Manifest ab — Artefakt "
            "verworfen")
    return ziel


def packe_aus(archiv: Path, nach: Path, plattform: str) -> Path:
    """Aus dem geprüften Artefakt das herausholen, was ersetzt wird.

    Liefert den Pfad des neuen Programms: die Exe, das .app-Bundle bzw.
    das Linux-Binary.
    """
    from .ziel import LINUX, MACOS, WINDOWS

    if plattform == WINDOWS:
        return archiv                       # die Exe ist das Artefakt

    nach.mkdir(parents=True, exist_ok=True)
    if plattform == MACOS:
        try:
            with zipfile.ZipFile(archiv) as z:
                _zip_auspacken(z, nach)
        except (zipfile.BadZipFile, OSError) as e:
            raise LadeFehler(f"ZIP nicht lesbar: {e}") from e
        # Nur echte Ordner: ditto legt neben das Bundle AppleDouble-
        # DATEIEN wie »._BM-Routencheck.app«, und »._« sortiert vor
        # jedem Buchstaben — glob allein erwischte zuverlässig die
        # falsche (Befund 2026-07-27, ditto-Probelauf).
        bundles = sorted(p for p in nach.glob("*.app") if p.is_dir())
        if not bundles:
            raise LadeFehler("Kein .app-Bundle im Archiv")
        # Netz für ZIPs ohne Rechte-Einträge (Fremd-Werkzeuge)
        binaer = bundles[0] / "Contents" / "MacOS" / "BM-Routencheck"
        if binaer.is_file():
            binaer.chmod(0o755)
        return bundles[0]

    if plattform == LINUX:
        try:
            with tarfile.open(archiv, "r:gz") as t:
                for mitglied in t.getmembers():
                    if mitglied.issym() or mitglied.islnk():
                        raise LadeFehler(
                            f"Archiv enthält eine Verknüpfung: {mitglied.name!r}")
                    _sicherer_pfad(nach, mitglied.name)
                t.extractall(nach, filter="data")
        except (tarfile.TarError, OSError) as e:
            raise LadeFehler(f"tar.gz nicht lesbar: {e}") from e
        treffer = [p for p in nach.rglob("bmtools") if p.is_file()]
        if not treffer:
            raise LadeFehler("Kein bmtools-Binary im Archiv")
        treffer[0].chmod(0o755)
        return treffer[0]

    raise LadeFehler(f"Unbekannte Plattform: {plattform!r}")


def aufraeumen(ordner: Path) -> None:
    """Arbeitsordner wegwerfen; Fehler dabei sind belanglos."""
    shutil.rmtree(ordner, ignore_errors=True)
