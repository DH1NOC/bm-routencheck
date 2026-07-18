/* BM-Routencheck GUI — Tab-Logik, Formulardaten, Bridge-Aufrufe.
   Kein Framework, kein CDN (Keyless/offlinefähig, GUI-UMBAU.md). */
"use strict";

let aktiverTab = "bahn";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ----------------------------------------------------------- Tabs */

function waehleTab(tab) {
  aktiverTab = tab;
  $$(".tabs button").forEach((b) =>
    b.classList.toggle("aktiv", b.dataset.tab === tab));
  $$(".formular").forEach((f) => (f.hidden = f.id !== "tab-" + tab));
  meldung(null);
}

$$(".tabs button").forEach((b) =>
  b.addEventListener("click", () => waehleTab(b.dataset.tab)));

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

/* -------------------------------------------------------- Start */

function formulardaten(tool) {
  const daten = { modus: $("#modus").value };
  $$("#tab-" + tool + " [data-feld]").forEach((el) => {
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

$("#start").addEventListener("click", async () => {
  alleFeldfehlerLoeschen();
  meldung(null);
  const r = await window.pywebview.api.start_lauf(
    aktiverTab, formulardaten(aktiverTab));
  if (r.fehler) {
    let allgemein = [];
    for (const [feld, text] of Object.entries(r.fehler)) {
      if (feld === "_formular") allgemein.push(text);
      else zeigeFeldfehler(feld, text);
    }
    meldung(allgemein.join(" ") ||
            "Bitte die markierten Felder korrigieren.", true);
  } else if (r.hinweis) {
    meldung(r.hinweis, false);
  }
});

/* -------------------------------------------------------- Start */

window.addEventListener("pywebviewready", async () => {
  const z = await window.pywebview.api.init_zustand();
  waehleTab(z.tab || "bahn");
});

/* Fallback für Ansicht im Browser (Entwicklung ohne Bridge) */
if (!window.pywebview) waehleTab("bahn");
