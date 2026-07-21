"""Icon-Dateien aus dem Master-SVG erzeugen.

Liest packaging/icon/icon.svg und erzeugt daraus alle im Repo
eingecheckten Icon-Artefakte — die CI braucht so weder rsvg noch
iconutil:

    packaging/icon/icon.ico        Windows (PyInstaller --icon)
    packaging/icon/icon.icns       macOS .app-Bundle (nur auf macOS,
                                   braucht iconutil)
    bmtools/gui/static/icon.png    Fenster-Icon (pywebview, Linux)

Für das .icns wird das Motiv nach Apple-Raster auf 824/1024 verkleinert
und transparent aufgefüllt (macOS-Icons haben umlaufenden Rand).
Braucht rsvg-convert (brew install librsvg) und Pillow. Aufruf:

    python packaging/icon_erzeugen.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

WURZEL = Path(__file__).parent.parent
MASTER = WURZEL / "packaging" / "icon" / "icon.svg"
ICO = WURZEL / "packaging" / "icon" / "icon.ico"
ICNS = WURZEL / "packaging" / "icon" / "icon.icns"
FENSTER_PNG = WURZEL / "bmtools" / "gui" / "static" / "icon.png"

ICO_GROESSEN = [256, 128, 64, 48, 32, 24, 16]
# iconset-Namen → Kantenlänge in Pixeln
ICNS_GROESSEN = {
    "icon_16x16": 16, "icon_16x16@2x": 32,
    "icon_32x32": 32, "icon_32x32@2x": 64,
    "icon_128x128": 128, "icon_128x128@2x": 256,
    "icon_256x256": 256, "icon_256x256@2x": 512,
    "icon_512x512": 512, "icon_512x512@2x": 1024,
}
APPLE_RASTER = 824 / 1024  # Motivgröße im macOS-Icon-Raster


def rendern(groesse: int, ziel: Path) -> None:
    subprocess.run(
        ["rsvg-convert", "-w", str(groesse), "-h", str(groesse),
         str(MASTER), "-o", str(ziel)],
        check=True,
    )


def mit_rand(png: Path, kante: int) -> Image.Image:
    """Gerendertes Motiv zentriert auf transparente kante×kante-Fläche."""
    bild = Image.new("RGBA", (kante, kante), (0, 0, 0, 0))
    motiv = Image.open(png)
    versatz = (kante - motiv.width) // 2
    bild.paste(motiv, (versatz, versatz))
    return bild


def main() -> int:
    if shutil.which("rsvg-convert") is None:
        print("rsvg-convert fehlt (brew install librsvg).", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)

        # Windows: Multi-Size-ICO, jede Größe eigenständig gerendert
        # (schärfer als Pillows Herunterskalieren aus einer Größe).
        bilder = []
        for g in ICO_GROESSEN:
            rendern(g, tmp / f"ico-{g}.png")
            bilder.append(Image.open(tmp / f"ico-{g}.png"))
        bilder[0].save(ICO, format="ICO",
                       append_images=bilder[1:],
                       sizes=[(g, g) for g in ICO_GROESSEN])
        print(f"{ICO.relative_to(WURZEL)} ({len(ICO_GROESSEN)} Größen)")

        # Fenster-Icon für pywebview (Linux; Windows nimmt das exe-Icon,
        # macOS das Bundle-Icon).
        rendern(256, tmp / "fenster.png")
        shutil.copyfile(tmp / "fenster.png", FENSTER_PNG)
        print(f"{FENSTER_PNG.relative_to(WURZEL)}")

        # macOS: iconset mit Apple-Rand, dann iconutil → icns.
        if shutil.which("iconutil") is None:
            print("iconutil fehlt (kein macOS) — icon.icns übersprungen.",
                  file=sys.stderr)
            return 0
        iconset = tmp / "icon.iconset"
        iconset.mkdir()
        for name, kante in ICNS_GROESSEN.items():
            motiv = round(kante * APPLE_RASTER)
            rendern(motiv, tmp / "motiv.png")
            mit_rand(tmp / "motiv.png", kante).save(iconset / f"{name}.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(ICNS)],
            check=True,
        )
        print(f"{ICNS.relative_to(WURZEL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
