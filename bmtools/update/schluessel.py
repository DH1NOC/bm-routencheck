"""Öffentliche Signaturschlüssel für Update-Manifeste.

Diese Werte sind **absichtlich öffentlich** — sie stecken in jedem
ausgelieferten Binary und im Quelltext. Sie prüfen nur, sie signieren
nicht. Die privaten Gegenstücke liegen als GitHub-Secret
(`UPDATE_SIGN_KEY`) bzw. offline beim Betreiber.

Zwei Plätze, weil eine Rotation sonst unmöglich wäre: Ein bereits
ausgeliefertes Binary akzeptiert nur Schlüssel, die es kennt. Ohne
zweiten Platz wäre bei Verlust oder Kompromittierung des
Hauptschlüssels jeder Client dauerhaft von Updates abgeschnitten.
RESERVE wird im Normalbetrieb nie benutzt; er ist der Weg zurück.

Neue Schlüssel erzeugt `packaging/schluessel_erzeugen.py`.
"""
from __future__ import annotations

import base64

# Erzeugt 2026-07-27 von DH1NOC.
HAUPT = "+ahQj8bG29q68rO/R1hh83rbjMnBaHNQRLuB3SgL82w="
RESERVE = "R9whp7TGaUpSLkrczXewdDaFQZQcFMsRrHo0E5K3Jg0="

# Reihenfolge = Prüfreihenfolge. Eine Signatur gilt, wenn EINER der
# Schlüssel passt.
OEFFENTLICHE_SCHLUESSEL: tuple[str, ...] = (HAUPT, RESERVE)


def als_bytes(b64: str) -> bytes:
    """Base64-Schlüssel zu 32 Rohbytes; wirft bei allem anderen."""
    roh = base64.b64decode(b64, validate=True)
    if len(roh) != 32:
        raise ValueError(f"Ed25519-Schlüssel muss 32 Byte haben, hat {len(roh)}")
    return roh
