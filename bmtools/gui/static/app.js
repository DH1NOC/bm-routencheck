/* BM-Routencheck GUI — Workspace-Logik: Modus-Wahl, Formulare und
   Validierung über die Bridge (U1); Pipeline-Lauf mit Fortschritts-
   Karte, Log-Konsole und sofortigem Abbruch (U2). Kein Framework,
   kein CDN (Keyless/offlinefähig, GUI-UMBAU.md). */
"use strict";

let aktiverModus = "bahn";
let laufAktiv = false;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ----------------------------------------------------- Modus-Wahl */

const MODUS_UNTERTITEL = { bahn: "Bahnstrecke prüfen",
                           auto: "Autoroute prüfen",
                           rad: "Radroute prüfen" };

function waehleModus(modus) {
  aktiverModus = modus;
  $$(".segment").forEach((b) =>
    b.classList.toggle("aktiv", b.dataset.modus === modus));
  $$(".formular").forEach((f) => (f.hidden = f.id !== "form-" + modus));
  // Während eines Laufs zeigt der Knopf »Abbrechen« — nicht übermalen
  if (!laufAktiv) {
    $("#berechnen-untertitel").textContent =
      MODUS_UNTERTITEL[modus] || "Route berechnen";
  }
  meldung(null);
}

$$(".segment").forEach((b) =>
  b.addEventListener("click", () => waehleModus(b.dataset.modus)));

/* ------------------------------------------- Link/GPX vs. manuell */

function gpxPfad(tool) {
  const el = document.getElementById(tool + "-gpx");
  return el ? el.dataset.pfad : "";
}

function dimmen(tool) {
  // Ein gesetzter Link oder eine GPX-Datei macht die manuellen Felder
  // gegenstandslos — sichtbar zurücknehmen statt still ignorieren.
  const link = document.getElementById(tool + "-link").value.trim();
  const perLinkOderGpx = Boolean(link || gpxPfad(tool));
  const manuell = document.querySelector('.manuell[data-tool="' + tool + '"]');
  manuell.classList.toggle("gedimmt", perLinkOderGpx);
}

["bahn", "auto", "rad"].forEach((tool) => {
  document.getElementById(tool + "-link")
    .addEventListener("input", () => dimmen(tool));
});

/* --------------------------------------------------- Feld-Fehler */

function zeigeFeldfehler(feldId, text) {
  const ziel = document.querySelector('.feldfehler[data-fuer="' + feldId + '"]');
  if (ziel) ziel.textContent = text || "";
  const feld = document.getElementById(feldId);
  if (feld && feld.matches("input")) {
    feld.classList.toggle("fehlerhaft", Boolean(text));
  }
}

function alleFeldfehlerLoeschen() {
  $$(".feldfehler").forEach((e) => (e.textContent = ""));
  $$("input.fehlerhaft").forEach((e) => e.classList.remove("fehlerhaft"));
}

/* Live-Prüfung beim Verlassen von Link-/Zeitfeldern */
[["bahn", "link"], ["bahn", "zeit"], ["auto", "link"], ["rad", "link"]]
  .forEach(([tool, feld]) => {
    const el = document.getElementById(tool + "-" + feld);
    el.addEventListener("blur", async () => {
      const r = await window.pywebview.api.pruefe_feld(
        tool, feld, el.value);
      zeigeFeldfehler(tool + "-" + feld, r.ok ? "" : r.fehler);
    });
  });

/* ------------------------------------------------------ GPX-Wahl */

function zeigeGpx(tool, pfad) {
  const el = document.getElementById(tool + "-gpx");
  el.dataset.pfad = pfad || "";
  // Nur den Dateinamen anzeigen, der volle Pfad steht im Tooltip
  el.textContent = pfad ? pfad.split("/").pop() : "";
  el.title = pfad || "";
  document.querySelector('[data-gpx-leeren="' + tool + '"]').hidden = !pfad;
  dimmen(tool);
}

$$("[data-gpx]").forEach((b) =>
  b.addEventListener("click", async () => {
    const r = await window.pywebview.api.waehle_gpx();
    if (r && r.pfad) zeigeGpx(b.dataset.gpx, r.pfad);
  }));

$$("[data-gpx-leeren]").forEach((b) =>
  b.addEventListener("click", () => zeigeGpx(b.dataset.gpxLeeren, "")));

/* ------------------------------------------------------ Berechnen */

function formulardaten(tool) {
  const daten = { modus: $("#modus").value };
  $$("#form-" + tool + " [data-feld]").forEach((el) => {
    const feld = el.dataset.feld;
    if (el.matches("input[type=checkbox]")) daten[feld] = el.checked;
    else if (feld === "gpx") daten[feld] = el.dataset.pfad;
    else daten[feld] = el.value.trim();
  });
  return daten;
}

function meldung(text, istFehler) {
  const el = $("#meldung");
  el.hidden = !text;
  el.textContent = text || "";
  el.classList.toggle("fehler", Boolean(istFehler));
}

function zeigeFormularfehler(fehler) {
  const allgemein = [];
  for (const [feld, text] of Object.entries(fehler)) {
    if (feld === "_formular") allgemein.push(text);
    else zeigeFeldfehler(feld, text);
  }
  meldung(allgemein.join(" ") ||
          "Bitte die markierten Felder korrigieren.", true);
}

/* Der Berechnen-Knopf startet den Lauf (start_lauf validiert die
   Formulardaten in der Bridge, bevor der Thread startet); während
   des Laufs wird er zum Abbrechen-Knopf — Abbruch wirkt sofort
   (G4-Mechanik). */
$("#berechnen").addEventListener("click", () => {
  if (laufAktiv) window.pywebview.api.abbrechen();
  else starteLauf();
});

function setzeLaufKnopf(laeuft) {
  $("#berechnen").classList.toggle("abbruch", laeuft);
  $("#berechnen-icon").setAttribute("href",
    laeuft ? "#i-close" : "#i-route");
  $("#berechnen-text").textContent = laeuft ? "Abbrechen" : "Berechnen";
  $("#berechnen-untertitel").textContent = laeuft
    ? "Abbruch wirkt sofort"
    : (MODUS_UNTERTITEL[aktiverModus] || "Route berechnen");
}

async function starteLauf() {
  alleFeldfehlerLoeschen();
  meldung(null);
  const r = await window.pywebview.api.start_lauf(
    aktiverModus, formulardaten(aktiverModus));
  if (!r.ok) {
    if (r.hinweis) meldung(r.hinweis, true);
    else zeigeFormularfehler(r.fehler || {});
    return;
  }
  laufAktiv = true;
  setzeLaufKnopf(true);
  zeigeLaufansicht();
  konsole("SYSTEM", "Lauf gestartet (" +
          (MODUS_UNTERTITEL[aktiverModus] || aktiverModus) + ").");
  statusRechts("Berechnung läuft …");
}

/* -------------------------------------------- Fortschrittsansicht */

let ergebnisDa = false;
let gesamtStand = null;   // letztes schritt-Ereignis {nummer, gesamt}
let gesamtProzent = 0;    // monoton — springt nie zurück
const tasks = new Map();  // task-id -> {beschreibung, sichtbar, …}

function zeigeLaufansicht() {
  $("#leer").hidden = true;
  $("#lauf").hidden = false;
  $("#konsole").replaceChildren();
  tasks.clear();
  gesamtStand = null;
  gesamtProzent = 0;
  $("#gesamt-name").textContent = "Route vorbereiten …";
  $("#gesamt-wert").textContent = "";
  $("#gesamt-fuellung").style.width = "0";
  $("#phase-schritt").hidden = true;
  ergebnisDa = false;
  $("#lauf-spinner").hidden = false;
  // toggleAttribute statt .hidden: SVG-Elemente haben die
  // hidden-Eigenschaft nicht (sie ist HTMLElement-API)
  $("#lauf-icon").toggleAttribute("hidden", true);
  $("#lauf-titel").textContent = "Routenberechnung läuft…";
  $("#lauf-hinweis").hidden = true;
  $("#lauf-erfolg").hidden = true;
  $("#lauf-erfolg").textContent = "";
  $("#lauf-aktionen").hidden = true;
}

function beendeLauf(code) {
  laufAktiv = false;
  setzeLaufKnopf(false);
  if (code === 0) setzeGesamt(100);
  $("#lauf-spinner").hidden = true;
  const icon = $("#lauf-icon");
  const use = $("#lauf-icon-use");
  icon.toggleAttribute("hidden", false);
  if (code === 0) {
    use.setAttribute("href", "#i-check_circle");
    icon.setAttribute("class", "icon lauf-icon gut");
    $("#lauf-titel").textContent = "Berechnung abgeschlossen";
    $("#lauf-aktionen").hidden = !ergebnisDa;
    const j = new Date();
    statusRechts("Letzte Berechnung: " +
                 String(j.getHours()).padStart(2, "0") + ":" +
                 String(j.getMinutes()).padStart(2, "0"));
  } else if (code === 130) {
    use.setAttribute("href", "#i-cancel");
    icon.setAttribute("class", "icon lauf-icon warnung");
    $("#lauf-titel").textContent = "Berechnung abgebrochen";
    konsole("SYSTEM", "Abgebrochen — die Eingaben bleiben erhalten.");
    statusRechts("");
  } else {
    use.setAttribute("href", "#i-warning");
    icon.setAttribute("class", "icon lauf-icon schlecht");
    $("#lauf-titel").textContent = "Berechnung fehlgeschlagen";
    statusRechts("");
  }
}

/* Zwei Balken (U2-Befund 2026-07-20): Gesamt-Fortschritt aus den
   schritt-Ereignissen der Pipeline, darunter EIN Balken für den
   jeweils aktuellen Einzelschritt (task-Ereignisse). */

function setzeGesamt(prozent, name) {
  // Monoton: Innerhalb eines Schritts laufen z. T. zwei Tasks
  // nacheinander (Kacheln laden, dann rechnen) — der Gesamt-Balken
  // darf dabei nie zurückspringen.
  gesamtProzent = Math.max(gesamtProzent, Math.min(100, prozent));
  $("#gesamt-fuellung").style.width = gesamtProzent + "%";
  $("#gesamt-wert").textContent = gesamtProzent + " %";
  if (name) $("#gesamt-name").textContent = name;
}

function neuerSchritt(e) {
  gesamtStand = e;
  setzeGesamt(Math.round(100 * (e.nummer - 1) / e.gesamt),
              "Schritt " + e.nummer + "/" + e.gesamt + " · " + e.text);
  // Der Einzelschritt-Balken gehört ab jetzt zum neuen Schritt
  $("#phase-schritt").hidden = true;
  $("#schritt-fuellung").style.width = "0";
  $("#schritt-wert").textContent = "";
}

function etaText(s) {
  return s >= 90 ? "≈ " + Math.round(s / 60) + " min" : "≈ " + s + " s";
}

function neuerTask(e) {
  tasks.set(e.task, { beschreibung: e.beschreibung,
                      sichtbar: e.sichtbar });
  if (e.sichtbar) {
    $("#phase-schritt").hidden = false;
    $("#schritt-name").textContent = e.beschreibung;
    $("#schritt-fuellung").style.width = "0";
    $("#schritt-wert").textContent = "";
    statusRechts(e.beschreibung);
  }
}

function aktualisiereTask(e) {
  const t = tasks.get(e.task);
  if (!t) return;
  if (e.sichtbar !== undefined) t.sichtbar = e.sichtbar;
  if (e.beschreibung !== undefined) t.beschreibung = e.beschreibung;
  if (e.fertig !== undefined) t.fertig = e.fertig;
  if (e.gesamt !== undefined) t.gesamt = e.gesamt;
  if (!t.sichtbar) return;
  // Der zuletzt gemeldete sichtbare Task IST der aktuelle Einzelschritt
  $("#phase-schritt").hidden = false;
  $("#schritt-name").textContent = t.beschreibung;
  if (t.fertig === undefined || !t.gesamt) return;
  const anteil = Math.min(1, t.fertig / t.gesamt);
  const prozent = Math.round(anteil * 100);
  $("#schritt-fuellung").style.width = prozent + "%";
  $("#schritt-wert").textContent = prozent + " %" +
    (e.eta_s !== undefined ? " · " + etaText(e.eta_s) : "");
  if (gesamtStand) {
    setzeGesamt(Math.round(
      100 * (gesamtStand.nummer - 1 + anteil) / gesamtStand.gesamt));
  }
}

/* Log-Konsole (Monospace, auto-scrollend, in beiden Themes dunkel) */

const KONSOLE_MAX_ZEILEN = 1000;

function konsole(praefix, text, klasse) {
  const k = $("#konsole");
  // Nur nachscrollen, wenn der Nutzer nicht selbst hochgescrollt hat
  const amEnde =
    k.scrollTop + k.clientHeight >= k.scrollHeight - 24;
  const zeile = document.createElement("div");
  zeile.className = "kzeile" + (klasse ? " " + klasse : "");
  const p = document.createElement("span");
  p.className = "kpraefix";
  p.textContent = "[" + praefix + "]";
  zeile.append(p, " " + text);
  k.appendChild(zeile);
  while (k.childElementCount > KONSOLE_MAX_ZEILEN) {
    k.firstElementChild.remove();
  }
  if (amEnde) k.scrollTop = k.scrollHeight;
}

$("#lauf-bericht").addEventListener("click", () =>
  window.pywebview.api.oeffne_ergebnis());
$("#lauf-ordner").addEventListener("click", () =>
  window.pywebview.api.oeffne_ordner());

/* -------------------------------------------------- Einstellungen */

$("#einstellungen").addEventListener("click", () =>
  meldung("Einstellungen (Theme, Cache) folgen mit Meilenstein U6."));

/* ---------------------------------------------------- Statusleiste */

function statusLinks(text) {
  $("#status-links").textContent = text || "Bereit";
}

function statusRechts(text) {
  $("#status-rechts").textContent = text || "";
}

/* ------------------------------------------------------- Dialog */

let dialogHandler = null;

function antworte(wert) {
  const handler = dialogHandler;
  schliesseDialog();
  if (handler) handler(wert);
}

function schliesseDialog() {
  dialogHandler = null;
  $("#dialog-hintergrund").hidden = true;
}

function knopf(text, klasse, handler) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = klasse;
  b.textContent = text;
  b.addEventListener("click", handler);
  return b;
}

function zeigeDialog(e, handler) {
  dialogHandler = handler;
  $("#dialog-frage").textContent = e.frage;
  const optionen = $("#dialog-optionen");
  const knoepfe = $("#dialog-knoepfe");
  optionen.replaceChildren();
  knoepfe.replaceChildren();

  if (e.art === "auswahl") {
    // Klickbare Liste (U3): EIN Klick wählt aus und schließt sofort.
    // Die Vorgabe (Top-Treffer) ist markiert und fokussiert — Enter
    // übernimmt sie, wie die Vorauswahl im Terminal.
    e.optionen.forEach((text, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "dialog-eintrag"
        + (i === (e.default ?? 0) ? " vorgabe" : "");
      b.textContent = text;
      b.addEventListener("click", () => antworte(i));
      optionen.appendChild(b);
    });
    knoepfe.appendChild(knopf("Abbrechen", "neben", () => antworte(null)));
  } else {  // ja_nein
    knoepfe.appendChild(knopf("Ja", e.default ? "start" : "neben",
                              () => antworte(true)));
    knoepfe.appendChild(knopf("Nein", e.default ? "neben" : "start",
                              () => antworte(false)));
  }
  $("#dialog-hintergrund").hidden = false;
  const fokus = optionen.querySelector(".vorgabe")
    || knoepfe.querySelector(".start");
  if (fokus) fokus.focus();
}

/* Tastatur im Dialog: Escape bricht ab (Auswahl-Abbruch beendet den
   Lauf — wie bisher), Pfeiltasten wandern durch die Einträge. */
document.addEventListener("keydown", (ev) => {
  if ($("#dialog-hintergrund").hidden) return;
  if (ev.key === "Escape") {
    ev.preventDefault();
    antworte(null);
    return;
  }
  if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
  const eintraege = $$("#dialog-optionen .dialog-eintrag");
  if (!eintraege.length) return;
  ev.preventDefault();
  const i = eintraege.indexOf(document.activeElement);
  const n = eintraege.length;
  const runter = ev.key === "ArrowDown";
  const ziel = i === -1 ? (runter ? 0 : n - 1)
                        : (runter ? (i + 1) % n : (i - 1 + n) % n);
  eintraege[ziel].focus();
});

/* --------------------------------------------------- Cache leeren */

$("#cache-leeren").addEventListener("click", async () => {
  const info = await window.pywebview.api.cache_info();
  if (info.leer) {
    statusLinks("Der Cache ist bereits leer.");
    return;
  }
  zeigeDialog(
    { art: "ja_nein", default: false,
      frage: "Alle gecachten Daten löschen (" + info.gesamt + ", " +
             info.dateien + " Dateien)? Der nächste Lauf lädt " +
             "Relais-Daten und Höhenkacheln neu herunter." },
    async (wert) => {
      if (!wert) return;
      const r = await window.pywebview.api.cache_leeren();
      statusLinks("Cache geleert — " + r.frei + " freigegeben.");
    });
});

/* --------------------------------------- Ereignisse aus Python */
/* Alle Ereignisse des GuiMelders (siehe melder.py). Konsolen-Präfixe:
   SYSTEM = Meldungen der Oberfläche selbst, INFO = Statuswechsel der
   Pipeline, LOG = Pipeline-Textausgaben, FEHLER = Fehlertexte. */

window.bmEreignis = (e) => {
  switch (e.typ) {
    case "frage":
      zeigeDialog(e, (wert) => window.pywebview.api.antwort(e.id, wert));
      break;
    case "text":
      konsole("LOG", e.text);
      break;
    case "status":
      // text=null (Kontext-Ende) lässt den letzten Schritt stehen
      if (e.text) {
        konsole("INFO", e.text);
        statusRechts(e.text);
      }
      break;
    case "schritt":
      neuerSchritt(e);
      break;
    case "task_neu":
      neuerTask(e);
      break;
    case "task_update":
      aktualisiereTask(e);
      break;
    case "balken_ende":
      break;  // Einzelschritt-Balken bleibt bis zum nächsten Task stehen
    case "fehler":
      konsole("FEHLER", e.text, "kfehler");
      $("#lauf-hinweis").textContent = e.text;
      $("#lauf-hinweis").hidden = false;
      break;
    case "erfolg":
      $("#lauf-erfolg").textContent = e.zeilen.join("\n");
      $("#lauf-erfolg").hidden = false;
      e.zeilen.forEach((z) => konsole("LOG", z));
      break;
    case "ergebnis":
      ergebnisDa = true;
      konsole("SYSTEM", "Ergebnisse in " + e.ordner + "/");
      break;
    case "fertig":
      beendeLauf(e.code);
      break;
  }
};

/* -------------------------------------------------------- Start */

window.addEventListener("pywebviewready", async () => {
  const z = await window.pywebview.api.init_zustand();
  waehleModus(z.tab || "bahn");
});

/* Fallback für Ansicht im Browser (Entwicklung ohne Bridge) */
if (!window.pywebview) waehleModus("bahn");
