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
  // Ansicht VOR dem Start leeren und umschalten: der Lauf-Thread
  // sendet seine ersten Ereignisse sonst schneller, als die
  // start_lauf-Antwort hier ankommt (erste Log-Zeile ging verloren)
  zeigeLaufansicht();
  const r = await window.pywebview.api.start_lauf(
    aktiverTab, formulardaten(aktiverTab));
  if (r.ok) return;
  zeigeFormulare();
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

/* ------------------------------------------------ Lauf-Ansicht (G4) */

const TOOL_TITEL = { bahn: "🚆 Bahnstrecke", auto: "🚗 Autoroute",
                     rad: "🚴 Radroute" };

function zeigeLaufansicht() {
  $(".tabs").hidden = true;
  $$(".formular").forEach((f) => (f.hidden = true));
  $(".abschluss").hidden = true;
  $("#lauf-balken").replaceChildren();
  $("#lauf-log").replaceChildren();
  Object.keys(tasks).forEach((k) => delete tasks[k]);
  $("#lauf-status").hidden = true;
  ergebnisDaten = null;
  Object.keys(ergebnisInhalte).forEach((k) => delete ergebnisInhalte[k]);
  $("#ergebnis").hidden = true;
  $("#ergebnis-rahmen").removeAttribute("srcdoc");
  $("#ergebnis-rahmen").src = "about:blank";
  document.body.classList.remove("breit");
  $("#lauf-titel").textContent =
    (TOOL_TITEL[aktiverTab] || "") + " — Suche läuft …";
  $("#lauf-abbrechen").hidden = false;
  $("#lauf-abbrechen").disabled = false;
  $("#lauf-zurueck").hidden = true;
  $("#lauf").hidden = false;
}

function zeigeFormulare() {
  $("#lauf").hidden = true;
  document.body.classList.remove("breit");
  $(".tabs").hidden = false;
  $(".abschluss").hidden = false;
  waehleTab(aktiverTab);
}

function logZeile(text, istFehler) {
  if (!text.trim()) return;
  const p = document.createElement("p");
  p.textContent = text;
  if (istFehler) p.classList.add("fehler");
  const log = $("#lauf-log");
  log.appendChild(p);
  log.scrollTop = log.scrollHeight;
}

/* Fortschrittsbalken: task-id -> DOM-Referenzen */
const tasks = {};

function taskNeu(e) {
  const wrap = document.createElement("div");
  wrap.className = "task aktiv unbestimmt";
  wrap.hidden = !e.sichtbar;
  wrap.innerHTML =
    '<span class="task-text"></span>' +
    '<div class="task-balken"><div class="task-fuellung"></div></div>' +
    '<span class="task-zaehler"></span><span class="task-eta"></span>';
  wrap.querySelector(".task-text").textContent = e.beschreibung;
  $("#lauf-balken").appendChild(wrap);
  tasks[e.task] = wrap;
}

function taskUpdate(e) {
  const wrap = tasks[e.task];
  if (!wrap) return;
  if (e.sichtbar !== undefined) wrap.hidden = !e.sichtbar;
  if (e.beschreibung !== undefined)
    wrap.querySelector(".task-text").textContent = e.beschreibung;
  if (e.fertig !== undefined && e.gesamt) {
    wrap.classList.remove("unbestimmt");
    const pct = Math.min(100, Math.round((e.fertig / e.gesamt) * 100));
    wrap.querySelector(".task-fuellung").style.width = pct + "%";
    wrap.querySelector(".task-zaehler").textContent =
      e.fertig + "/" + e.gesamt + " · " + pct + " %";
  }
  // ETA-Regel wie im Terminal (ui.EtaSpalte): erscheint ab > 10 s
  // Restzeit — sticky macht das der GuiMelder, hier nur anzeigen
  wrap.querySelector(".task-eta").textContent =
    e.eta_s !== undefined ? "noch ~" + etaText(e.eta_s) : "";
}

function etaText(s) {
  if (s < 60) return s + " s";
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0") + " min";
}

function balkenEnde() {
  $$("#lauf-balken .task.aktiv").forEach((t) => {
    t.classList.remove("aktiv", "unbestimmt");
    t.classList.add("fertig");
    t.querySelector(".task-eta").textContent = "";
  });
}

function statusZeile(text) {
  const el = $("#lauf-status");
  el.hidden = !text;
  el.textContent = text ? "⏳ " + text : "";
}

function erfolgBlock(zeilen) {
  const div = document.createElement("div");
  div.className = "erfolg";
  zeilen.forEach((z) => {
    const p = document.createElement("p");
    p.textContent = z;
    div.appendChild(p);
  });
  const log = $("#lauf-log");
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function laufFertig(code) {
  balkenEnde();
  statusZeile(null);
  schliesseDialog();
  $("#lauf-titel").textContent =
    (TOOL_TITEL[aktiverTab] || "") +
    (code === 0 ? " — fertig" : code === 130 ? " — abgebrochen"
                                             : " — fehlgeschlagen");
  $("#lauf-abbrechen").hidden = true;
  $("#lauf-zurueck").hidden = false;
  if (code === 0 && ergebnisDaten) zeigeErgebnis();
}

/* ---------------------------------------------- Ergebnisansicht (G5) */

let ergebnisDaten = null;
let aktiveAnsicht = "bericht";
const ergebnisInhalte = {};  // ansicht -> geladenes HTML (Cache)

function zeigeErgebnis() {
  document.body.classList.add("breit");
  $("#ergebnis").hidden = false;
  ansichtWaehlen("bericht");
}

async function ansichtWaehlen(ansicht) {
  if (!ergebnisDaten) return;
  aktiveAnsicht = ansicht;
  $$(".ergebnis-knoepfe .ansicht").forEach((b) =>
    b.classList.toggle("aktiv", b.dataset.ansicht === ansicht));
  // Inhalt über die Bridge statt file-URL: WKWebView blockiert
  // file-iframes außerhalb des static-Verzeichnisses
  if (!(ansicht in ergebnisInhalte)) {
    const r = await window.pywebview.api.lade_ergebnis(ansicht);
    if (!r) return;
    ergebnisInhalte[ansicht] = r.html;
  }
  $("#ergebnis-rahmen").srcdoc = ergebnisInhalte[ansicht];
}

$$(".ergebnis-knoepfe .ansicht").forEach((b) =>
  b.addEventListener("click", () => ansichtWaehlen(b.dataset.ansicht)));

$("#ordner-oeffnen").addEventListener("click", () =>
  window.pywebview.api.oeffne_ordner());

$("#browser-oeffnen").addEventListener("click", () =>
  window.pywebview.api.oeffne_ergebnis(aktiveAnsicht));

$("#lauf-abbrechen").addEventListener("click", () => {
  $("#lauf-abbrechen").disabled = true;
  window.pywebview.api.abbrechen();
});

$("#lauf-zurueck").addEventListener("click", zeigeFormulare);

/* ------------------------------------------------ Frage-Dialog (G4) */

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

/* --------------------------------------- Ereignisse aus Python (G4) */

window.bmEreignis = (e) => {
  switch (e.typ) {
    case "text": logZeile(e.text); break;
    case "task_neu": taskNeu(e); break;
    case "task_update": taskUpdate(e); break;
    case "balken_ende": balkenEnde(); break;
    case "status": statusZeile(e.text); break;
    case "frage":
      zeigeDialog(e, (wert) => window.pywebview.api.antwort(e.id, wert));
      break;
    case "ergebnis": ergebnisDaten = e; break;
    case "erfolg": erfolgBlock(e.zeilen); break;
    case "fehler": logZeile("Fehler: " + e.text, true); break;
    case "fertig": laufFertig(e.code); break;
  }
};

/* ------------------------------------------------ Cache leeren (G5) */

$("#cache-leeren").addEventListener("click", async () => {
  const info = await window.pywebview.api.cache_info();
  if (info.leer) {
    meldung("Der Cache ist bereits leer.");
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
      meldung("Cache geleert — " + r.frei + " freigegeben.");
    });
});

/* -------------------------------------------------------- Start */

window.addEventListener("pywebviewready", async () => {
  const z = await window.pywebview.api.init_zustand();
  waehleTab(z.tab || "bahn");
});

/* Fallback für Ansicht im Browser (Entwicklung ohne Bridge) */
if (!window.pywebview) waehleTab("bahn");
