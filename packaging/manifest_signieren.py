"""Update-Manifest erzeugen und signieren (nur im Release-Workflow).

    python packaging/manifest_signieren.py <version> <ausgabeordner> \
        <plattform>=<datei> [<plattform>=<datei> …]

Der private Schlüssel kommt aus der Umgebungsvariablen
UPDATE_SIGN_KEY (Base64, 32 Byte Ed25519) — nie als Argument, sonst
stünde er in der Prozessliste.

Liegt bewusst in packaging/ und nicht im Paket `bmtools`: Signieren
passiert ausschließlich beim Bauen. Was Nutzer bekommen, soll gar
keinen Code enthalten, der mit privaten Schlüsseln umgeht.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bmtools.update.manifest import (
    MANIFEST_DATEI,
    SIGNATUR_DATEI,
    Artefakt,
    ManifestFehler,
    pruefe_manifest,
    serialisieren,
)
from bmtools.update.schluessel import als_bytes

UMGEBUNGSVARIABLE = "UPDATE_SIGN_KEY"


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    version, ausgabe = argv[0], Path(argv[1])

    roh_schluessel = os.environ.get(UMGEBUNGSVARIABLE, "").strip()
    if not roh_schluessel:
        print(f"FEHLER: {UMGEBUNGSVARIABLE} ist nicht gesetzt.",
              file=sys.stderr)
        return 1
    try:
        privat = Ed25519PrivateKey.from_private_bytes(als_bytes(roh_schluessel))
    except Exception as e:
        print(f"FEHLER: {UMGEBUNGSVARIABLE} unbrauchbar ({e}).",
              file=sys.stderr)
        return 1

    artefakte: dict[str, Artefakt] = {}
    for zuweisung in argv[2:]:
        plattform, _, pfad_text = zuweisung.partition("=")
        pfad = Path(pfad_text)
        if not plattform or not pfad_text:
            print(f"FEHLER: {zuweisung!r} ist kein <plattform>=<datei>.",
                  file=sys.stderr)
            return 2
        if not pfad.is_file():
            print(f"FEHLER: {pfad} gibt es nicht.", file=sys.stderr)
            return 1
        sha = hashlib.sha256(pfad.read_bytes()).hexdigest()
        artefakte[plattform] = Artefakt(datei=pfad.name, sha256=sha)
        print(f"  {plattform:14s} {pfad.name}  {sha[:16]}…")

    roh = serialisieren(version, artefakte)
    signatur = privat.sign(roh)

    # Gegenprobe auf dem öffentlichen Weg: Was hier herausgeht, muss der
    # Client auch annehmen können. Ein falsch hinterlegtes Secret oder
    # eine Änderung an der Serialisierung fällt so beim Bauen auf und
    # nicht erst beim Nutzer, dessen Update dann stumm ausbliebe.
    try:
        geprueft = pruefe_manifest(roh, signatur)
    except ManifestFehler as e:
        print(
            f"FEHLER: Die eigene Signatur wird nicht angenommen ({e}).\n"
            f"        Der Schlüssel in {UMGEBUNGSVARIABLE} gehört zu keinem "
            f"der einkompilierten\n"
            f"        öffentlichen Schlüssel in bmtools/update/schluessel.py. "
            f"Entweder ist das\n"
            f"        Secret falsch, oder die Schlüssel wurden gewechselt, "
            f"ohne den neuen\n"
            f"        öffentlichen Teil einzutragen. So signiert würde JEDER "
            f"Client das\n"
            f"        Update verwerfen.", file=sys.stderr)
        return 1
    if geprueft.version != version:
        print("FEHLER: Gegenprobe liefert eine andere Version.",
              file=sys.stderr)
        return 1

    ausgabe.mkdir(parents=True, exist_ok=True)
    (ausgabe / MANIFEST_DATEI).write_bytes(roh)
    (ausgabe / SIGNATUR_DATEI).write_bytes(signatur)
    print(f"\n{MANIFEST_DATEI} und {SIGNATUR_DATEI} in {ausgabe} — "
          f"Gegenprobe bestanden (Version {geprueft.version}, "
          f"{len(geprueft.artefakte)} Artefakte).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
