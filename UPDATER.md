# Selbst-Updater — Plan und Festlegungen

Arbeitsdokument für `feature/updater`. Wird nach Abschluss aufgelöst
(wie `GUI-UMBAU.md` und `FM-UMBAU.md`); die Historie bleibt in Git.

**Ziel:** Die App erkennt neue GitHub-Releases, zeigt eine Info-Leiste
mit „Jetzt aktualisieren" und ersetzt sich am eigenen Ort selbst.
Windows, macOS und Linux. Im Terminal ein Hinweis nach dem Lauf plus
`--update`.

## 1. Sicherheitsmodell

Anforderung des Nutzers: **Man-in-the-Middle muss ausgeschlossen
sein.** HTTPS mit Zertifikatsprüfung allein reicht dafür nicht — ein
Angreifer mit eigener Root-CA im System (Firmen-Proxy, untergeschobenes
Zertifikat) sieht und ändert alles. Belastbar ist nur eine Signatur.

### Signiert wird ein Manifest, nicht die einzelne Datei

```json
{ "version": "0.4.1",
  "artefakte": {
    "windows-x64": {"datei": "BM-Routencheck-0.4.1-windows-x64.exe", "sha256": "…"},
    "macos-arm64": {"datei": "BM-Routencheck-0.4.1-macos-arm64.zip",  "sha256": "…"},
    "linux-x64":   {"datei": "bmtools-0.4.1-linux-x64.tar.gz",        "sha256": "…"} } }
```

Als Release-Assets liegen `manifest.json` und `manifest.json.sig` bei.

**Warum nicht einfach die Artefakte signieren?** Dann bliebe *Replay*
offen: Wer die API-Antwort fälschen kann, liefert eine **ältere, echt
signierte** Version aus. Die Signatur wäre gültig, die Version käme
aber aus der gefälschten JSON. Nur wenn die Version selbst aus dem
signierten Manifest stammt, greift die Downgrade-Sperre.

### Ablauf im Client, strikt in dieser Reihenfolge

1. Release-Liste über die GitHub-API — **nur Hinweis, wo zu suchen ist**
2. `manifest.json` + `.sig` laden, Signatur gegen den **einkompilierten**
   Ed25519-Schlüssel prüfen
3. ab hier zählt **ausschließlich** der Manifest-Inhalt
4. Manifest-Version gegen die laufende vergleichen, `≤` ablehnen
5. Artefakt laden, SHA256 gegen das Manifest prüfen
6. erst dann tauschen

### Schlüssel

Privater Schlüssel als GitHub-Secret `UPDATE_SIGN_KEY`, die CI signiert
jedes Release. **Zusätzlich offline sichern** — geht er verloren, sind
alle bereits ausgelieferten Clients dauerhaft von Updates
abgeschnitten.

Es sind **zwei Schlüsselplätze** einkompiliert (Haupt + Reserve). Das
kostet jetzt nichts und ist später nicht nachrüstbar: Ohne zweiten
Platz gibt es bei Verlust oder Kompromittierung des Hauptschlüssels
keinen Weg zurück. Der Reserve-Privatschlüssel liegt **nur offline**,
nie bei GitHub.

**Bewusst akzeptiertes Restrisiko:** Wer Schreibrechte auf das Repo
hat, kann gültig signieren. Gegen MITM schützt das Verfahren
vollständig, gegen ein übernommenes GitHub-Konto nicht. Der Nutzer hat
diesen Kompromiss gewählt (2026-07-27); die Alternative wäre lokales
Signieren mit einem manuellen Schritt je Release.

**Kein Zertifikats-Pinning** — GitHub rotiert seine CAs, das wäre nur
eine zusätzliche Bruchstelle. Die Signatur ist der Schutz.

## 2. Festlegungen des Nutzers (2026-07-27)

| Punkt | Festlegung |
|---|---|
| Beta-Kanal | Einstellung im Menü, **Vorgabe aus** — Tester schalten sie ein |
| Prüfzeitpunkt | bei **jedem Start**, frisch, im **Hintergrund** — keine Startverzögerung, der Hinweis erscheint etwas später |
| Rückfallebene | alte Fassung bleibt liegen, bis die neue **einmal sauber gestartet** ist |
| Windows | voll unterstützt; der Nutzer testet selbst auf seinem Windows-Notebook |

Angenommen und nicht widersprochen: abschaltbar im Einstellungsmenü;
nur im gefrorenen Binary (Quellcode-Installation bekommt „aktualisiere
mit `git pull`"); an nicht beschreibbaren Orten Download-Link statt
halbem Tausch, **keine Elevation-Dialoge** (passt zur Festlegung „keine
Installer").

## 3. Schritte

| # | Inhalt | Stand |
|---|---|---|
| 1 | Versionsanzeige: `bmtools.version`, `--version` überall, `--copy-metadata` im Build, Rauchtest prüft die Version im Artefakt | **fertig** |
| 2 | Signatur-Infrastruktur: Manifest + Signierschritt in `release.yml`, Abhängigkeiten `cryptography` und `packaging` | offen |
| 3 | Prüflogik (rein, testbar): Signatur, Versionsvergleich, Artefaktauswahl, Beta-Filter | offen |
| 4 | Tausch je System hinter einer Test-Naht: Linux `os.replace()`, macOS Bundle + `codesign --verify`, Windows Helfer-Prozess | offen |
| 5 | Info-Leiste in der GUI, Terminal-Hinweis nach dem Lauf, `--update` | offen |
| 6 | Doku und Beta-Zyklus | offen |

## 4. Fallstricke

- **Version im gefrorenen Binary.** `importlib.metadata` liefert im
  Checkout die Version des letzten `pip install` — im venv kam 0.1.2
  heraus, während pyproject auf 0.3.0 stand. Deshalb liest
  `bmtools/version.py` im Quellbaum `pyproject.toml` und der
  CI-Rauchtest prüft das Artefakt gegen die gebaute Version. Dieselbe
  Fehlerklasse wie `mypy bmtools` statt `mypy`: im Quellbaum grün, im
  Artefakt kaputt.
- **Henne-Ei beim Testen.** 0.3.0 hat keinen Updater. Der Update-Weg
  ist erstmals von 0.4.0 auf 0.4.1-beta.1 erprobbar — es braucht
  **zwei Builds**, bevor irgendetwas als getestet gelten darf.
- **Windows.** Eine laufende `.exe` ist gesperrt, daher der
  Helfer-Prozess. Die Exe ist nicht code-signiert; das Muster
  „unsigniertes Programm lädt eine Exe und führt sie aus" kann
  Virenscanner-Heuristiken auslösen.
- **macOS.** Vor dem Tausch `codesign --verify` auf das entpackte
  Bundle; ein selbst heruntergeladenes Archiv trägt kein
  Quarantäne-Attribut, Gatekeeper prüft also nicht für uns mit.
