/* BM-Routencheck GUI — Workspace-Logik (U1): Modus-Wahl, Formulare,
   Validierung über die Bridge. Kein Framework, kein CDN
   (Keyless/offlinefähig, GUI-UMBAU.md). Lauf/Fortschritt folgt U2. */
"use strict";

let aktiverModus = "bahn";

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
  $("#berechnen-untertitel").textContent =
    MODUS_UNTERTITEL[modus] || "Route berechnen";
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

/* U1: Berechnen validiert vollständig über die Bridge; der Lauf
   selbst (Fortschrittsansicht) kommt mit U2. */
$("#berechnen").addEventListener("click", async () => {
  alleFeldfehlerLoeschen();
  meldung(null);
  const r = await window.pywebview.api.pruefe_eingaben(
    aktiverModus, formulardaten(aktiverModus));
  if (r.ok) {
    meldung("Eingaben vollständig — die Berechnung folgt mit " +
            "Meilenstein U2.");
  } else {
    zeigeFormularfehler(r.fehler || {});
  }
});

/* -------------------------------------------------- Einstellungen */

$("#einstellungen").addEventListener("click", () =>
  meldung("Einstellungen (Theme, Cache) folgen mit Meilenstein U6."));

/* ---------------------------------------------------- Statusleiste */

function statusLinks(text) {
  $("#status-links").textContent = text || "Bereit";
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
    e.optionen.forEach((text, i) => {
      const label = document.createElement("label");
      label.className = "dialog-option";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "dialog-auswahl";
      radio.value = i;
      radio.checked = i === (e.default ?? 0);
      label.appendChild(radio);
      label.appendChild(document.createTextNode(" " + text));
      optionen.appendChild(label);
    });
    knoepfe.appendChild(knopf("Übernehmen", "start", () =>
      antworte(Number($('input[name="dialog-auswahl"]:checked').value))));
    knoepfe.appendChild(knopf("Abbrechen", "neben", () => antworte(null)));
  } else {  // ja_nein
    knoepfe.appendChild(knopf("Ja", e.default ? "start" : "neben",
                              () => antworte(true)));
    knoepfe.appendChild(knopf("Nein", e.default ? "neben" : "start",
                              () => antworte(false)));
  }
  $("#dialog-hintergrund").hidden = false;
}

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
/* U1 startet noch keinen Lauf; der Handler nimmt Dialog-Fragen an
   und ignoriert Lauf-Ereignisse defensiv (kein JS-Fehler, falls
   doch eines eintrifft). Voller Umfang folgt mit U2. */

window.bmEreignis = (e) => {
  if (e.typ === "frage") {
    zeigeDialog(e, (wert) => window.pywebview.api.antwort(e.id, wert));
  }
};

/* -------------------------------------------------------- Start */

window.addEventListener("pywebviewready", async () => {
  const z = await window.pywebview.api.init_zustand();
  waehleModus(z.tab || "bahn");
});

/* Fallback für Ansicht im Browser (Entwicklung ohne Bridge) */
if (!window.pywebview) waehleModus("bahn");
