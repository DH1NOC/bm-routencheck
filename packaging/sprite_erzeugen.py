"""Material-Symbols-Sprite in static/index.html einsetzen.

Liest die Original-SVGs aus static/vendor/material-symbols/svg/ und
ersetzt in static/index.html den Block zwischen den Markern
<!-- sprite:anfang --> und <!-- sprite:ende --> durch ein verstecktes
Inline-Sprite (<symbol id="i-<name>">). Inline statt externer Datei,
weil <use href="datei.svg#id"> unter file:// nicht auf allen
Webview-Backends auflöst (WKWebView). Aufruf:

    python packaging/sprite_erzeugen.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

STATIC = Path(__file__).parent.parent / "bmtools" / "gui" / "static"
SVG_DIR = STATIC / "vendor" / "material-symbols" / "svg"
INDEX = STATIC / "index.html"
ANFANG = "<!-- sprite:anfang -->"
ENDE = "<!-- sprite:ende -->"


def sprite() -> str:
    zeilen = [ANFANG,
              '<svg id="symbole" xmlns="http://www.w3.org/2000/svg" '
              'style="display:none" aria-hidden="true">']
    for datei in sorted(SVG_DIR.glob("*.svg")):
        svg = datei.read_text()
        m = re.search(r'viewBox="([^"]+)"', svg)
        inhalt = re.sub(r"^<svg[^>]*>|</svg>$", "", svg.strip())
        if m is None or not inhalt:
            raise SystemExit(f"Unerwartetes SVG-Format: {datei}")
        zeilen.append(f'<symbol id="i-{datei.stem}" viewBox="{m.group(1)}">'
                      f"{inhalt}</symbol>")
    zeilen += ["</svg>", ENDE]
    return "\n".join(zeilen)


def main() -> int:
    html = INDEX.read_text()
    if ANFANG not in html or ENDE not in html:
        print(f"Marker {ANFANG!r}/{ENDE!r} fehlen in {INDEX}",
              file=sys.stderr)
        return 1
    anfang = html.index(ANFANG)
    ende = html.index(ENDE) + len(ENDE)
    INDEX.write_text(html[:anfang] + sprite() + html[ende:])
    print(f"Sprite mit {len(list(SVG_DIR.glob('*.svg')))} Symbolen "
          f"in {INDEX.name} eingesetzt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
