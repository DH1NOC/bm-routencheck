# GUI-Umbau — Plan für feature/gui-umbau

Stand: 2026-07-18 · Branch: `feature/gui-umbau`

## Ziel

BM-Routencheck bekommt eine grafische Oberfläche, bleibt aber im Terminal
voll nutzbar. Ein und dieselben Kommandos (`bmtools`, `bm-bahn`, `bm-auto`,
`bm-rad`) bedienen beide Welten — kein separates GUI-Programm, kein
App-Bundle (Festlegung 2026-07-18: »alles in einem Binary«).

## Festlegungen (Nutzerentscheidungen 2026-07-18)

| Punkt | Entscheidung |
|---|---|
| GUI-Technik | **pywebview** — natives Fenster mit System-Webview; Karte (Folium) und HTML-Bericht existieren bereits als HTML und werden direkt im Fenster angezeigt. Eine schlanke Zusatzabhängigkeit, läuft auf macOS/Windows/Linux. |
| Startlogik | **Automatisch:** Aufruf ohne Argumente + Desktop-Umgebung verfügbar → GUI. Jeder Aufruf mit Argumenten sowie fehlende Desktop-Umgebung (SSH, Server, keine `DISPLAY`/`WAYLAND_DISPLAY` unter Linux) → Terminal wie bisher. Erzwingbar per `--gui` bzw. `--terminal`. Bestehende Skript-Aufrufe laufen unverändert. |
| Umfang | **Voll integriert:** ein Fenster für alle drei Tools (Bahn/Auto/Rad), Eingabeformular statt Assistent, Fortschrittsanzeige während der Pipeline, danach Karte und Bericht im Fenster, Export-/Ordner-öffnen-Buttons. |
| Paketierung | Kein PyInstaller/App-Bundle — weiterhin nur das pip-Paket mit seinen Kommandos. |
| Sprache | GUI durchgängig Deutsch, wie die CLI. |

Bestehende Projektprinzipien gelten weiter (PROJEKTPLAN.md §3), insbesondere
Keyless, Kein Try&Error (jeder Meilenstein endet mit abgenommenem Testlauf)
und Konsistenz der Ausgaben.

## Architektur in Kürze

- **`bmtools/gui/`** (neu): Fenster-Start (pywebview), HTML/JS/CSS-Frontend
  (lokal gebündelt, keine CDN-Zugriffe — Keyless/offlinefähig), JS-Bridge
  (pywebview `js_api`) zu den bestehenden Bausteinen.
- **Pipeline bleibt die eine Quelle der Wahrheit:** `routelib/pipeline.py`
  wird nicht dupliziert, sondern um injizierbare Fortschritts-/Melde-Hooks
  entkoppelt. Terminal-Implementierung = heutiges rich-Verhalten
  (Texte unverändert), GUI-Implementierung = Events an das Fenster.
- **Interaktive Rückfragen** (Bahn-Verbindungswahl, Geocoding-Kandidaten,
  Modus-Frage) laufen in der GUI als Formular-Schritte; die
  Assistenten-Reihenfolge-Regel (Modus-Frage zuletzt) gilt auch dort.
- Die Pipeline läuft in einem Hintergrund-Thread, damit das Fenster
  bedienbar bleibt; Fortschritt kommt über die vorhandenen
  `progress`-Callbacks.

## Meilensteine (ein Commit je Schritt)

- [x] **G0 — Plan:** Branch `feature/gui-umbau`, dieses Dokument.
- [x] **G1 — Startlogik** *(abgenommen 2026-07-18: Fenster auf macOS,
      Terminal-Menü mit `--terminal`, Vorauswahl via `bm-bahn --gui`)*: `pywebview`-Abhängigkeit; Desktop-Erkennung
      (macOS/Windows: ja außer SSH-Sitzung; Linux: `DISPLAY`/
      `WAYLAND_DISPLAY`); Flags `--gui`/`--terminal` in allen vier
      Kommandos; ohne Argumente + Desktop → leeres GUI-Fenster
      (Platzhalter), sonst unverändert Terminal.
      *Abnahme:* `bmtools --terminal` verhält sich exakt wie heute;
      `bmtools` auf dem Desktop öffnet ein Fenster; Aufruf mit
      Argumenten bleibt Terminal.
- [x] **G2 — Pipeline entkoppeln** *(2026-07-18)*: Melde-/Fortschritts-
      Hooks in `run_pipeline` injizierbar (`routelib/melden.py`:
      `Melder`-Protocol + `TerminalMelder`); Konsolen-Ausgaben bleiben
      byte-identisch. *Abnahme:* `make qs` grün (167 Tests, neu:
      Melder-Verhalten + Pipeline-Integrationslauf mit Fake-Clients);
      deterministischer Referenzlauf vor/nach Umbau per `diff`
      byte-identisch (einzige gewollte Abweichung: der Profil-Balken
      läuft jetzt über die übergebene Konsole statt implizit stdout —
      im Terminal dasselbe Bild).
- [ ] **G3 — Fenster-Grundgerüst:** Tabs Bahn/Auto/Rad, deutsche
      Formulare mit den Assistenten-Feldern (inkl. Link-/GPX-Eingabe),
      JS-Bridge mit Formular-Validierung; noch ohne Pipeline-Lauf.
      *Abnahme:* Sichtprüfung aller drei Formulare auf macOS.
- [ ] **G4 — Lauf + Fortschritt:** Start aus dem Formular, Pipeline im
      Hintergrund-Thread, Fortschrittsbalken (X/Y, Prozent, ETA-Regel
      wie im Terminal: erst ab > 10 s Restzeit) im Fenster; Abbrechen
      möglich. Interaktive Rückfragen der Tools (Verbindungs-/
      Geocoding-Auswahl, Modus zuletzt) als GUI-Schritte.
      *Abnahme:* je ein kompletter Bahn-, Auto- und Rad-Lauf aus der GUI.
- [ ] **G5 — Ergebnisanzeige:** Karte und Bericht im Fenster (Umschalter
      oder geteilte Ansicht), Buttons »Ausgabeordner öffnen« und Hinweise
      auf CSV/Codeplug-Dateien; Cache-leeren-Funktion im GUI-Menü.
      *Abnahme:* Ergebnis eines Laufs vollständig im Fenster geprüft,
      Dateien identisch zu einem Terminal-Lauf derselben Route.
- [ ] **G6 — QS + Doku:** `make qs` grün (Lint, mypy strict, Tests;
      GUI-Logik so weit wie sinnvoll unit-getestet, Webview-Teile
      ausgenommen wie bisher Karten-Rendering), README (Endnutzer:
      GUI-Start, `--terminal`) und DEVELOPER.md (Technik: Bridge,
      Hooks, Desktop-Erkennung) ergänzt, PROJEKTPLAN.md nachgeführt.
      *Abnahme:* interaktiver Gegentest (Beta) wie bei v0.1.2, danach
      Merge-Entscheidung.

## Risiken / offene Punkte

- pywebview braucht unter Linux ein Webview-Backend (GTK/WebKit2 oder
  QtWebEngine) — auf Desktop-Distributionen meist vorhanden; README
  bekommt einen Hinweis. macOS (WKWebView) und Windows (WebView2/Edge)
  bringen ihres mit.
- questionary/rich bleiben für den Terminal-Modus vollwertig erhalten —
  kein schleichender Rückbau.
- Threading: rich-Progress ist threadsicher (siehe pipeline.py), die
  GUI-Hooks müssen es ebenso sein (Events nur über die pywebview-Bridge).
