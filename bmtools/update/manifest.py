"""Das signierte Update-Manifest — Aufbau, Signatur, Prüfung.

Warum ein Manifest und nicht einfach die Artefakte signiert werden,
steht in UPDATER.md §1. Kurz: Sonst bliebe *Replay* offen — wer die
GitHub-Antwort fälschen kann, liefert eine ältere, echt signierte
Version aus. Nur wenn die Version selbst aus dem signierten Manifest
stammt, greift die Downgrade-Sperre.

**Die eine Regel:** Nach `pruefe_manifest()` handelt der Client
ausschließlich auf dem Rückgabewert. Alles aus der GitHub-API — Tags,
Asset-Namen, Versionsnummern — ist bis dahin unbeglaubigter Hinweis und
danach bedeutungslos.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .schluessel import OEFFENTLICHE_SCHLUESSEL, als_bytes

# Beim Signieren wie beim Prüfen exakt gleich serialisieren, sonst
# passt die Signatur nie: feste Schlüsselreihenfolge, keine Leerzeichen,
# UTF-8 ohne ASCII-Escapes.
_JSON = {"sort_keys": True, "separators": (",", ":"), "ensure_ascii": False}

MANIFEST_DATEI = "manifest.json"
SIGNATUR_DATEI = "manifest.json.sig"


class ManifestFehler(Exception):
    """Manifest fehlt, ist unlesbar oder nicht echt.

    Wird vom Aufrufer immer als »kein Update anbieten« behandelt — nie
    als »trotzdem versuchen«.
    """


@dataclass(frozen=True)
class Artefakt:
    datei: str
    sha256: str

    def passt_zu(self, daten: bytes) -> bool:
        return hashlib.sha256(daten).hexdigest() == self.sha256.lower()


@dataclass(frozen=True)
class Manifest:
    version: str
    artefakte: dict[str, Artefakt]

    def fuer(self, plattform: str) -> Artefakt | None:
        return self.artefakte.get(plattform)


def serialisieren(version: str, artefakte: dict[str, Artefakt]) -> bytes:
    """Die Bytes, über die signiert und geprüft wird."""
    inhalt: dict[str, Any] = {
        "version": version,
        "artefakte": {p: {"datei": a.datei, "sha256": a.sha256}
                      for p, a in sorted(artefakte.items())},
    }
    return json.dumps(inhalt, **_JSON).encode("utf-8")  # type: ignore[arg-type]


def pruefe_manifest(roh: bytes, signatur: bytes) -> Manifest:
    """Manifest gegen die einkompilierten Schlüssel prüfen.

    Gültig, sobald EIN Schlüssel passt (Haupt oder Reserve). Wirft
    ManifestFehler, wenn keiner passt oder der Inhalt nicht stimmt —
    der Aufrufer bietet dann kein Update an.
    """
    fuer_schluessel_gueltig = False
    for b64 in OEFFENTLICHE_SCHLUESSEL:
        try:
            Ed25519PublicKey.from_public_bytes(als_bytes(b64)).verify(
                signatur, roh)
        except (InvalidSignature, ValueError):
            continue
        fuer_schluessel_gueltig = True
        break
    if not fuer_schluessel_gueltig:
        raise ManifestFehler(
            "Signatur passt zu keinem bekannten Schlüssel — Manifest "
            "verworfen")

    try:
        inhalt = json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ManifestFehler(f"Manifest nicht lesbar: {e}") from e
    if not isinstance(inhalt, dict):
        raise ManifestFehler("Manifest ist kein Objekt")

    version = inhalt.get("version")
    if not isinstance(version, str) or not version:
        raise ManifestFehler("Manifest ohne brauchbare Version")

    roh_artefakte = inhalt.get("artefakte")
    if not isinstance(roh_artefakte, dict) or not roh_artefakte:
        raise ManifestFehler("Manifest ohne Artefakte")

    artefakte: dict[str, Artefakt] = {}
    for plattform, eintrag in roh_artefakte.items():
        if not isinstance(eintrag, dict):
            raise ManifestFehler(f"Artefakt {plattform!r} ist kein Objekt")
        datei, sha = eintrag.get("datei"), eintrag.get("sha256")
        if not isinstance(datei, str) or not datei:
            raise ManifestFehler(f"Artefakt {plattform!r} ohne Dateinamen")
        # Der Dateiname geht später in eine URL und einen Pfad — hier
        # einmal hart begrenzen statt später an drei Stellen hoffen.
        if "/" in datei or "\\" in datei or datei.startswith("."):
            raise ManifestFehler(
                f"Artefakt {plattform!r} hat einen unzulässigen Dateinamen: "
                f"{datei!r}")
        if not isinstance(sha, str) or len(sha) != 64:
            raise ManifestFehler(f"Artefakt {plattform!r} ohne SHA256")
        try:
            int(sha, 16)
        except ValueError as e:
            raise ManifestFehler(
                f"Artefakt {plattform!r}: SHA256 ist nicht hexadezimal") from e
        artefakte[str(plattform)] = Artefakt(datei=datei, sha256=sha.lower())

    return Manifest(version=version, artefakte=artefakte)
