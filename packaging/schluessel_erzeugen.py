"""Ed25519-Schlüsselpaare für die Update-Signatur erzeugen.

Wird selten gebraucht — einmal zum Aufsetzen, danach nur noch bei einer
Schlüsselrotation. Deshalb liegt das Skript hier bei den übrigen
Erzeugern (icon_erzeugen.py, sprite_erzeugen.py) und nicht im Paket.

    .venv/bin/python packaging/schluessel_erzeugen.py

Erzeugt zwei Paare: HAUPT signiert die Releases, RESERVE ist die
Rückfallebene. Beide öffentlichen Schlüssel werden einkompiliert, damit
ein Wechsel später überhaupt möglich ist — das lässt sich nachträglich
nicht mehr nachrüsten.

Die privaten Schlüssel erscheinen nur auf der Konsole und werden
NIRGENDS gespeichert. Wer sie verliert, kann bereits ausgelieferte
Clients nie wieder mit Updates erreichen.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def paar() -> tuple[str, str]:
    schluessel = Ed25519PrivateKey.generate()
    privat = schluessel.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())
    oeffentlich = schluessel.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    return (base64.b64encode(privat).decode(),
            base64.b64encode(oeffentlich).decode())


def main() -> None:
    print()
    print("=" * 72)
    print("  Update-Signaturschlüssel für BM-Routencheck")
    print("=" * 72)
    for name, zweck in (("HAUPT", "signiert die Releases (GitHub-Secret)"),
                        ("RESERVE", "Rückfallebene — NIEMALS zu GitHub")):
        privat, oeffentlich = paar()
        print(f"\n### {name} — {zweck}\n")
        print(f"  PRIVAT  : {privat}")
        print(f"  ÖFFENTL.: {oeffentlich}")
    print("\n" + "=" * 72)
    print("""
  Was jetzt zu tun ist:

  1. HAUPT/PRIVAT   -> GitHub-Secret »UPDATE_SIGN_KEY«
                       (Repo → Settings → Secrets and variables →
                        Actions → New repository secret)
  2. HAUPT/PRIVAT   -> zusätzlich offline sichern (Passwortmanager)
  3. RESERVE/PRIVAT -> NUR offline sichern, nicht zu GitHub
  4. Beide ÖFFENTL. -> weitergeben, sie werden einkompiliert

  Danach dieses Konsolenfenster schließen bzw. den Verlauf leeren —
  die privaten Schlüssel standen hier im Klartext.
""")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
