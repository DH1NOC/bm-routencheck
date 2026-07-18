"""Das GUI-Fenster (pywebview).

G1: Platzhalter-Seite, die den Fensterstart auf allen Plattformen
absichert; Formulare, Fortschritt und Ergebnisanzeige folgen in G3-G5.
pywebview wird erst hier importiert — der Terminal-Modus bleibt frei
von GUI-Importen (und deren Startzeit).
"""
from __future__ import annotations

from bmtools import ui

from . import GuiStartFehler

FENSTER_TITEL = "BM-Routencheck"

# GUI-Toolname -> Anzeigelabel (gleiche Reihenfolge wie das bmtools-Menü)
TOOL_LABEL = {"bahn": "🚆 Bahnstrecke", "auto": "🚗 Autoroute",
              "rad": "🚴 Radroute"}


def _platzhalter_html(tool: str | None) -> str:
    tool_zeile = ""
    if tool in TOOL_LABEL:
        tool_zeile = (f"<p>Vorausgewähltes Tool: "
                      f"<strong>{TOOL_LABEL[tool]}</strong></p>")
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<title>{FENSTER_TITEL}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
         display: flex; align-items: center; justify-content: center;
         min-height: 90vh; margin: 0; color: #222; }}
  .karte {{ max-width: 34rem; padding: 2rem 2.5rem;
            border: 2px solid {ui.BLUE}; border-radius: 12px; }}
  h1 {{ margin: 0 0 .25rem; font-size: 1.5rem; }}
  .unterzeile {{ color: {ui.BLUE}; margin-top: 0; }}
  .hinweis {{ color: #666; font-size: .9rem; }}
  code {{ background: #f0f4f8; padding: .1rem .35rem; border-radius: 4px; }}
</style></head><body>
<div class="karte">
  <h1>📡 BM-Routencheck</h1>
  <p class="unterzeile">Grafische Oberfläche — im Aufbau (Meilenstein G1)</p>
  {tool_zeile}
  <p>Die Formulare für Bahn, Auto und Rad folgen in den nächsten
     Schritten (G3), danach Fortschrittsanzeige und Ergebnisansicht
     (G4/G5).</p>
  <p class="hinweis">Der gewohnte Assistent bleibt erhalten:
     <code>bmtools --terminal</code></p>
</div>
</body></html>"""


def gui_starten(tool: str | None = None) -> int:
    """Fenster öffnen und die pywebview-Hauptschleife laufen lassen.

    Wirft GuiStartFehler statt ImportError/Backend-Exceptions, damit die
    Aufrufer (start_oder_none) sauber ins Terminal zurückfallen können."""
    try:
        import webview
    except ImportError as e:
        raise GuiStartFehler(
            "pywebview ist nicht installiert — nachrüsten mit "
            "'pip install pywebview'") from e
    webview.create_window(FENSTER_TITEL, html=_platzhalter_html(tool),
                          width=1100, height=750)
    try:
        webview.start()
    except Exception as e:
        # Typischer Fall: Linux ohne Webview-Backend (GTK/WebKit2 oder
        # QtWebEngine) — pywebview meldet das erst beim Start.
        raise GuiStartFehler(str(e)) from e
    return 0
