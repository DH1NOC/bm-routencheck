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
Signieren mit einem manuellen Schritt je Release. Der Rettungsweg bei
Kompromittierung des Hauptschlüssels ist der RESERVE-Schlüssel
(offline): ein mit ihm signiertes Release wird von allen Clients
angenommen und kompiliert neue Schlüssel ein.

**Zweites akzeptiertes Restrisiko: kein Widerruf, kein Ablaufdatum.**
Ein einmal signiertes Manifest bleibt für immer gültig. Wer die
Release-Antworten kontrolliert (dieselbe MITM-Position wie oben), kann
Clients deshalb eine ältere, echt signierte Version dauerhaft als
„neueste" vorsetzen, solange sie neuer als die installierte ist — und
so das Ausrollen eines Sicherheitsfixes verzögern (Freeze-Angriff).
Ein Downgrade bleibt ausgeschlossen; das Fenster ist nur „Fix
vorenthalten". Frische ließe sich allein mit Ablaufdaten im Manifest
und regelmäßigem Neusignieren erzwingen (TUF-Territorium) — für die
Größe dieses Projekts bewusst nicht gebaut.

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
| 2 | Signatur-Infrastruktur: Manifest + Signierschritt in `release.yml`, Abhängigkeiten `cryptography` und `packaging` | **fertig** |
| 3 | Prüflogik (rein, testbar): Signatur, Versionsvergleich, Artefaktauswahl, Beta-Filter | **fertig** |
| 4 | Tausch je System hinter einer Test-Naht: Linux `os.replace()`, macOS Bundle + `codesign --verify`, Windows Helfer-Prozess | **fertig** |
| 5 | Info-Leiste in der GUI, Terminal-Hinweis nach dem Lauf, `--update` | **fertig** (Sichtprüfung abgenommen 2026-07-27) |
| 6 | Doku und Beta-Zyklus | Doku **fertig**, Beta-Zyklus offen (§5) |

Zu Schritt 6 gehörte ein Befund an der Prüflogik: Der Beta-Filter hing
am `prerelease`-Flag der GitHub-Antwort — also an einer unbeglaubigten
Angabe, mitten in einem Verfahren, dessen ganzer Zweck es ist, genau
solchen Angaben nicht zu trauen. Ein Angreifer hätte damit zwar kein
Downgrade erzwingen können (die Versionsprüfung stammt aus dem
Manifest), aber einem Nutzer mit abgeschaltetem Beta-Kanal eine echte
Vorabversion unterschieben. Die Einstufung kommt jetzt aus der
Versionsnummer im signierten Manifest
(`ist_vorabversion()`, `test_beta_erkennung_kommt_aus_dem_manifest`).
Aufgefallen ist das erst beim Aufschreiben — die Zusicherung „ab hier
zählt ausschließlich der Manifest-Inhalt" sollte in den PROJEKTPLAN, und
sie stimmte noch nicht ganz.

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
  Dazu der **Team-Anker** (Härtung 2026-07-27): `--verify` allein
  nimmt jede intakte Signatur an, auch ad-hoc — das neue Bundle muss
  deshalb vom selben Apple-Team stammen wie das laufende
  (`_team_id()`; Referenz ist das laufende Bundle, kein
  einkompiliertes Team).
- **zipfile zerstört Symlinks.** `extractall` macht aus einem Symlink
  eine reguläre Datei mit dem Linkziel als Inhalt — das Bundle enthält
  Symlinks, codesign hätte danach jedes Update abgelehnt. Deshalb
  packt `_zip_auspacken()` selbst aus: Symlinks bleiben Symlinks,
  Linkziele werden gegen Ausbruch geprüft, Dateirechte bleiben
  erhalten. Und: ditto legt neben das Bundle AppleDouble-DATEIEN wie
  `._BM-Routencheck.app` — die Bundle-Suche nimmt nur echte Ordner
  (beides Befunde des ditto-Probelaufs 2026-07-27).

## 5. Beta-Zyklus

**Vorbedingung, ohne die gar nichts geht:** Das Repository-Secret
`UPDATE_SIGN_KEY` muss gesetzt sein — sonst bricht der Release-Workflow
ab (Anleitung: DEVELOPER.md, „Update-Signierung"). Die öffentlichen
Schlüssel stehen bereits einkompiliert in `bmtools/update/schluessel.py`;
gebraucht wird der private HAUPT-Schlüssel aus demselben Lauf von
`packaging/schluessel_erzeugen.py`.

### Warum zwei Betas nötig sind

0.3.0 kennt keinen Updater — von dort führt kein Weg. Erprobbar ist der
Ablauf erst zwischen zwei Ständen, die ihn beide schon haben: **beta.1
wird von Hand installiert, beta.2 wird von beta.1 aus eingespielt.** Das
ist der eigentliche Test; alles davor ist nur die Vorbereitung darauf.

### Ablauf

1. **beta.1 bauen** — Actions → Release → Branch `feature/updater`,
   Sprung `major` → `v0.4.0-beta.1`. Prüfen, dass der Lauf durchläuft
   und im Release **`manifest.json` + `manifest.json.sig`** liegen (der
   Signierschritt ist noch nie gelaufen).
2. **beta.1 von Hand installieren** — Windows, macOS, Linux. Auf jedem
   System einmal `--version` aufrufen: Es muss `BM-Routencheck 0.4.0-beta.1`
   erscheinen. Meldet eines `0+unbekannt`, greift `--copy-metadata`
   dort nicht und der Updater bliebe stumm.
3. **Beta-Kanal einschalten** — Fenster, ☰ → *Updates* → „Auch
   Vorabversionen anbieten". Ohne das bekommt beta.1 nie ein Angebot.
4. **beta.2 bauen** — derselbe Weg, `v0.4.0-beta.2`.
5. **Den Sprung durchspielen**, je Plattform:
   - beta.1 starten → Info-Leiste „Version 0.4.0-beta.2 ist verfügbar
     (Vorabversion)" erscheint kurz nach dem Fensteraufbau
   - „Jetzt aktualisieren" → Fortschritt in der Leiste → Neustart
     (Windows: Hinweis „Tausch beim Beenden", danach beenden)
   - neue Fassung meldet `--version` = `0.4.0-beta.2`
   - macOS zusätzlich: `codesign --verify --deep --strict` auf das
     getauschte Bundle muss stumm durchlaufen (bestätigt, dass das
     symlink-erhaltende Auspacken die Signatur wirklich bewahrt)
   - im Terminal derselbe Weg über `bmtools --update --mit-vorabversionen`
   - **Solange beta.2 noch angeboten wird**, auch den Fall ohne
     Schreibrecht prüfen: eine Kopie von beta.1 an einen fremden Ort
     legen (`sudo cp`, Eigentümer root) und von dort `--update` rufen →
     Meldung mit Verweis auf die Releases-Seite, **kein**
     Passwortdialog. Danach ist das Fenster zu — sobald der Client auf
     beta.2 steht, gibt es kein Angebot mehr, an dem sich das zeigen
     ließe.
6. **Rückfallebene prüfen:** Nach dem ersten Tausch liegt neben dem
   Programm ein `…​.vorher`. Nach dem **nächsten** Start der neuen
   Fassung muss es verschwunden sein (`beim_start_aufraeumen()` in
   `packaging/entry.py` — der Einstieg aller drei gebauten Programme).
7. **Ablehnungen prüfen** — die Fälle, in denen nichts passieren darf:
   - Beta-Kanal wieder aus → beta.2 bietet nichts mehr an
   - „Beim Start nach Updates suchen" aus → keine Leiste, keine Anfrage
     beim Start. `bmtools --update` sucht weiterhin — ein ausdrücklicher
     Befehl schlägt eine passive Einstellung, das ist kein Befund.
   - Quellcode-Checkout (`.venv/bin/bmtools --update`) → Verweis auf
     `git pull`, kein Downloadversuch

### Was danach passiert

Läuft alles durch: von `main` den regulären Release **0.4.0** bauen und
die Betas samt Tags und Build-Artefakten abräumen (Reihenfolge und
Befehle in DEVELOPER.md, „Nachbereitung eines Releases"). Danach ist
dieses Dokument erledigt und wird aufgelöst — die Sicherheits- und
Betriebsteile stehen dauerhaft in DEVELOPER.md und PROJEKTPLAN §3.

### Text für die Tester (Discord, ohne Markdown-Links)

> **BM-Routencheck 0.4.0-beta.1 — bitte testen**
>
> Neu: Das Programm sucht beim Start selbst nach Updates und kann sich
> auf Knopfdruck ersetzen. Genau das soll diese Runde prüfen.
>
> So geht's:
> 1. beta.1 herunterladen und wie gewohnt starten (einmal noch von Hand).
> 2. Im Fenster oben rechts auf das Menü, unter „Updates" den Punkt
>    „Auch Vorabversionen anbieten" einschalten.
> 3. Programm neu starten. Sobald beta.2 da ist, erscheint oben eine
>    Leiste „Version … ist verfügbar" — dann bitte auf „Jetzt
>    aktualisieren" klicken.
>
> Bitte meldet mir:
> - Kam die Leiste? Wie lange hat sie gebraucht?
> - Lief das Aktualisieren durch, und startete das Programm danach neu?
> - Zeigt es danach die neue Versionsnummer? Sie steht im Menü unter
>   „Updates" (im Terminal: ./bmtools --version)
> - Blieb irgendwo eine Datei mit der Endung .vorher liegen?
> - Kam eine Warnung von Virenscanner oder System?
>
> Wenn etwas schiefgeht: Bitte den genauen Wortlaut der Meldung
> schicken. Euer installiertes Programm bleibt in dem Fall unverändert
> — kaputtgehen kann dabei nichts.
>
> Downloads: github.com/DH1NOC/bm-routencheck/releases
