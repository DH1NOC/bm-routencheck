/* BM-Routencheck GUI — Workspace-Logik: Modus-Wahl, Formulare und
   Validierung über die Bridge (U1); Pipeline-Lauf mit Fortschritts-
   Karte, Log-Konsole und sofortigem Abbruch (U2). Kein Framework,
   kein CDN (Keyless/offlinefähig, GUI-UMBAU.md). */
"use strict";

let aktiverModus = "bahn";
let laufAktiv = false;
let einstellungen = {};  // persistiert über die Bridge (gui.json)

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
  $("#ergebnis").hidden = true;
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
    // Mit Kartendaten wechselt die Ansicht zur Leaflet-Karte (U4);
    // ohne bleibt die Abschluss-Karte samt Aktionen stehen
    if (ergebnisDa) zeigeErgebnis();
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

/* -------------------------------------------- Ergebnis-Karte (U4) */

let karte = null;  // Leaflet-Map des angezeigten Ergebnisses
let kartenDaten = null;    // letztes karten_daten-Payload (mapview)
let sichtfeldEbene = null; // vom Layer-Control verwaltete Overlay-Ebene
let feldRelais = null;     // Index des einzeln gezeigten Relais (oder null)
/* Popup-Zustand von Leaflet melden lassen statt im DOM nachsehen: beim
   Schließen bleibt .leaflet-popup noch ~400 ms zum Ausblenden stehen,
   eine DOM-Abfrage sähe es also fälschlich weiter als offen. */
let popupOffen = false;

const STATIONS_ICONS = { train: "i-train", car: "i-directions_car",
                         bicycle: "i-pedal_bike" };

function kartenIcon(symbol, klasse) {
  return L.divIcon({
    className: "",
    html: '<div class="kmarker ' + klasse + '">' +
          '<svg class="icon"><use href="#' + symbol + '"/></svg></div>',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -14],
    tooltipAnchor: [0, -14],
  });
}

async function zeigeErgebnis() {
  const r = await window.pywebview.api.lade_ergebnis();
  if (!r || !r.karte) {
    // Ohne Kartendaten bleibt die Abschluss-Karte mit den Aktionen
    $("#lauf-aktionen").hidden = false;
    return;
  }
  // Erst einblenden, dann bauen: Leaflet braucht einen Container mit
  // realer Größe (sonst stimmen fitBounds/Kachelraster nicht)
  $("#lauf").hidden = true;
  $("#ergebnis").hidden = false;
  setzeSplitter(einstellungen.splitter || 0.55, false);
  fuelleTopbar(r.kennzahlen || {});
  baueKarte(r.karte);
  baueTabelle(r.relais || []);
}

function baueKarte(k) {
  if (karte) {
    karte.remove();
    karte = null;
  }
  kartenDaten = k;
  sichtfeldEbene = null;
  feldRelais = null;
  popupOffen = false;
  karte = L.map($("#karte"));
  karte.on("popupopen", () => (popupOffen = true));
  karte.on("popupclose", () => (popupOffen = false));

  const basis = {};
  k.ebenen.forEach((e, i) => {
    const ebene = L.tileLayer(e.url, {
      attribution: e.attribution,
      subdomains: e.subdomains || "abc",
      maxZoom: e.max_zoom || 19,
    });
    basis[e.name] = ebene;
    if (i === 0) ebene.addTo(karte);
  });
  const overlays = {};
  if (k.overlay) {
    sichtfeldEbene = L.imageOverlay(
      k.overlay.uri, k.overlay.bounds, { opacity: 0.8 }).addTo(karte);
    overlays[k.overlay.name] = sichtfeldEbene;
  }
  L.control.layers(basis, overlays).addTo(karte);

  if (k.segmente) {
    k.segmente.forEach((s) => {
      const stil = k.stile[s.status];
      L.polyline(s.punkte, {
        color: stil.farbe,
        weight: 5,
        opacity: 0.95,
        dashArray: stil.dash || null,
      }).bindTooltip(s.tooltip, { sticky: true }).addTo(karte);
    });
  } else if (k.route) {
    L.polyline(k.route, { color: "#c00", weight: 3 })
      .bindTooltip(k.route_label, { sticky: true }).addTo(karte);
  }

  k.stationen.forEach((s) => {
    L.marker([s.lat, s.lon], {
      icon: kartenIcon(STATIONS_ICONS[k.stations_icon] || "i-flag",
                       "station"),
      zIndexOffset: 500,
    }).bindTooltip(s.name).addTo(karte);
  });

  // Marker-Reihenfolge = relais-Zeilen-Reihenfolge (beide entstehen
  // aus derselben results-Liste): index verbindet Tabelle und Karte
  markerRefs = [];
  k.marker.forEach((mk, i) => {
    const m = L.marker([mk.lat, mk.lng],
                       { icon: kartenIcon("i-cell_tower", mk.farbe) })
      .bindTooltip(mk.tooltip)
      .bindPopup(mk.popup, { maxWidth: 340 })
      .addTo(karte);
    m.on("click", () => waehleRelais(i, "karte"));
    markerRefs.push(m);
  });

  // Nimmt der Nutzer die Sichtfeld-Ebene im Layer-Control ab, während
  // ein Einzelrelais gezeigt wird, fällt auch die Legende zurück — sonst
  // benennt sie ein Sichtfeld, das gar nicht mehr zu sehen ist.
  karte.on("overlayremove", () => {
    if (feldRelais !== null) {
      feldRelais = null;
      zeigeSichtfeld();
      zeigeLegende();
    }
  });

  karte.fitBounds(k.bounds, { padding: [24, 24] });
  zeigeLegende();

  // Nur die Stationsnamen — das Routen-Label steht im Tooltip
  // (die Top-Bar ist eng, U5-Eigenbefund: »Bah…«)
  const namen = k.stationen.map((s) => s.name);
  const routeText = namen.length ? namen.join(" → ") : k.route_label;
  const routeEl = $("#ergebnis-route");
  routeEl.textContent = routeText;
  routeEl.title = k.route_label + " · " + routeText;
}

function legendeLinie(farbe, dash) {
  return '<svg width="34" height="8"><line x1="1" y1="4" x2="33" y2="4"' +
         ' stroke="' + farbe + '" stroke-width="4"' +
         (dash ? ' stroke-dasharray="' + dash + '"' : "") + "/></svg> ";
}

function legendeFleck(farbe) {
  return '<span class="legende-stufe" style="background:' + farbe +
         '"></span> ';
}

/* ------------------------------- Einzelrelais-Sichtfeld (Abdeckung) */

/* Ein Relais hat nur dann eine Einzelansicht, wenn Sichtfelder
   gerechnet wurden (Geländemodell) UND die Overlay-Ebene im
   Layer-Control angehakt ist — eine bewusste Abwahl übersteuert der
   Marker-Klick nicht. */
function hatSichtfeld(index) {
  const felder = kartenDaten && kartenDaten.relais_felder;
  return Boolean(sichtfeldEbene && felder && felder[index] &&
                 karte && karte.hasLayer(sichtfeldEbene));
}

/* Bild und Ausdehnung derselben Ebene tauschen, statt Ebenen zu
   wechseln: so bleibt der Haken im Layer-Control gültig und das
   Abhaken versteckt weiter genau das, was gerade zu sehen ist. */
function zeigeSichtfeld() {
  if (!sichtfeldEbene || !kartenDaten) return;
  const felder = kartenDaten.relais_felder || [];
  const feld = feldRelais === null ? kartenDaten.overlay : felder[feldRelais];
  if (!feld) return;
  sichtfeldEbene.setUrl(feld.uri);
  sichtfeldEbene.setBounds(L.latLngBounds(feld.bounds));
}

function alleRelaisZeigen() {
  if (feldRelais === null) return;
  feldRelais = null;
  zeigeSichtfeld();
  zeigeLegende();
}

function zeigeLegende() {
  const k = kartenDaten;
  const el = $("#karten-legende");
  if (!k || !k.legende) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  if (feldRelais !== null) {
    zeigeFeldLegende(el, k);
    return;
  }
  const l = k.legende;
  let inhalt = "<b>Geschätzte " + l.modus_label + "-Abdeckung</b><br>";
  l.linien.forEach((z) => {
    inhalt += legendeLinie(z.farbe, z.dash) + z.text + "<br>";
  });
  if (l.sichtfelder) {
    // Dieselbe Rampe wie das Overlay (mapview.HEATMAP_RAMP)
    inhalt += '<span class="legende-rampe"></span> Relais-Sichtfeld ' +
              "(hellste Stufe: nur Beugung, sonst dunkler = mehr " +
              "Relais)<br>";
    inhalt += "<em>Relais anklicken zeigt nur dessen Sichtfeld.</em><br>";
  }
  inhalt += "Marker: " + l.marker_note;
  el.innerHTML = inhalt;
}

/* Legende der Einzelansicht: Abstandsstufen von nah (dunkel) nach fern
   (hell). Wortlaut und Farben kommen aus mapview._feld_legende(), damit
   GUI-Karte und karte.html dasselbe sagen. */
function zeigeFeldLegende(el, k) {
  const f = k.feld_legende;
  const marker = k.marker[feldRelais] || {};
  let inhalt = "";
  f.stufen.forEach((s) => {
    inhalt += legendeFleck(s.farbe) + s.text + "<br>";
  });
  inhalt += legendeFleck(f.grenz.farbe) + f.grenz.text + "<br>";
  inhalt += "<small>" + f.hinweis + "</small>";
  // Rufzeichen über textContent: es kommt aus der BM-/FM-Quelle und ist
  // anders als die Popups (html.escape in mapview) nicht maskiert
  const titel = document.createElement("b");
  titel.textContent = "Sichtfeld " + (marker.rufzeichen || "");
  el.replaceChildren(titel, document.createElement("br"));
  el.insertAdjacentHTML("beforeend", inhalt);
  // Knopf als echtes Element (Handler statt inline-onclick)
  const b = document.createElement("button");
  b.type = "button";
  b.className = "legende-zurueck";
  b.textContent = f.zurueck;
  b.addEventListener("click", alleRelaisZeigen);
  el.appendChild(b);
}

/* Links auf der Karte (Attribution) dürfen das App-Fenster nicht
   wegnavigieren — Anzeige ja, Navigation nein. */
$("#karte").addEventListener("click", (ev) => {
  const a = ev.target.closest("a[href]");
  if (a) ev.preventDefault();
});

$("#ergebnis-bericht").addEventListener("click", () =>
  window.pywebview.api.oeffne_ergebnis());
$("#ergebnis-ordner").addEventListener("click", () =>
  window.pywebview.api.oeffne_ordner());
$("#ergebnis-csv").addEventListener("click", async () => {
  const r = await window.pywebview.api.export_csv();
  if (r && r.pfad) statusLinks("CSV gespeichert: " + r.pfad);
});

$("#ergebnis-pdf").addEventListener("click", async () => {
  // Kartenkacheln fürs PDF können ein paar Sekunden laden —
  // Doppelklicks abfangen und den Stand in der Statusleiste zeigen
  const knopf = $("#ergebnis-pdf");
  knopf.disabled = true;
  statusRechts("PDF wird erzeugt …");
  try {
    const r = await window.pywebview.api.export_pdf();
    statusRechts(r && r.pfad ? "PDF erzeugt: " + r.pfad
                             : "PDF konnte nicht erzeugt werden.");
  } finally {
    knopf.disabled = false;
  }
});

/* ------------------------------------------------- Top-Bar (U5) */

function fuelleTopbar(kz) {
  const daten = [
    ["#kz-distanz", kz.distanz_km != null ? kz.distanz_km + " km" : ""],
    ["#kz-sicht", kz.sicht_pct != null ? kz.sicht_pct + " %" : ""],
    ["#kz-grenz", kz.grenz_pct != null ? kz.grenz_pct + " %" : ""],
    ["#kz-schatten",
     kz.schatten_pct != null ? kz.schatten_pct + " %" : ""],
  ];
  daten.forEach(([sel, text]) => {
    const el = $(sel);
    const wert = el.querySelector(".kz-wert") || el;
    wert.textContent = text;
    el.hidden = !text;
  });
  const modell = kz.terrain ? "Geländemodell"
                            : "Horizontmodell, ohne Gelände";
  $("#kz-sicht").title = "Freie Sicht (" + modell + ")";
  $("#kz-grenz").title = "Grenzbereich — Beugung möglich (" + modell + ")";
  $("#kz-schatten").title = "Funkschatten (" + modell + ")";
}

/* ------------------------------------------------ DataGrid (U5) */

const SPALTEN = [
  { key: "km", titel: "km", num: true },
  { key: "rufzeichen", titel: "Rufzeichen" },
  { key: "standort", titel: "Standort" },
  { key: "abstand_km", titel: "Abstand", num: true },
  { key: "modus", titel: "Modus" },
  { key: "rx", titel: "RX [MHz]", num: true },
  { key: "tx", titel: "TX [MHz]", num: true },
  { key: "ton", titel: "Tone/CC" },
  { key: "status", titel: "Status" },
];

let relaisZeilen = [];
let markerRefs = [];
let sortKey = "km";
let sortDir = 1;
let offeneZeilen = new Set();
let aktivesRelais = null;

function baueTabelle(zeilen) {
  relaisZeilen = zeilen;
  offeneZeilen = new Set();
  aktivesRelais = null;
  sortKey = "km";
  sortDir = 1;
  $("#relais-suche").value = "";
  baueTabellenkopf();
  tabelleRendern();
}

function baueTabellenkopf() {
  const tr = document.createElement("tr");
  const auf = document.createElement("th");  // Aufklapp-Spalte
  auf.className = "th-auf";
  tr.appendChild(auf);
  SPALTEN.forEach((s) => {
    const th = document.createElement("th");
    th.textContent = s.titel;
    if (s.num) th.classList.add("num");
    th.classList.toggle("sortiert", s.key === sortKey);
    if (s.key === sortKey) {
      th.dataset.richtung = sortDir > 0 ? "auf" : "ab";
    }
    th.addEventListener("click", () => {
      if (sortKey === s.key) sortDir = -sortDir;
      else { sortKey = s.key; sortDir = 1; }
      baueTabellenkopf();
      tabelleRendern();
    });
    tr.appendChild(th);
  });
  $("#relais-kopf").replaceChildren(tr);
}

function gefilterteZeilen() {
  const filter = $("#relais-suche").value.trim().toLowerCase();
  let zeilen = relaisZeilen;
  if (filter) {
    zeilen = zeilen.filter((z) =>
      (z.rufzeichen + " " + z.standort + " " + z.modus + " " + z.ton +
       " " + z.status).toLowerCase().includes(filter));
  }
  const spalte = SPALTEN.find((s) => s.key === sortKey);
  return zeilen.slice().sort((a, b) => {
    let av = a[sortKey];
    let bv = b[sortKey];
    if (spalte.num) {
      av = parseFloat(av);
      bv = parseFloat(bv);
    } else {
      av = String(av).toLowerCase();
      bv = String(bv).toLowerCase();
    }
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });
}

function tabelleRendern() {
  const tbody = $("#relais-zeilen");
  tbody.replaceChildren();
  const zeilen = gefilterteZeilen();
  zeilen.forEach((z) => {
    tbody.appendChild(relaisZeile(z));
    if (offeneZeilen.has(z.index) && z.talkgroups) {
      tbody.appendChild(talkgroupZeile(z));
    }
  });
  $("#relais-zaehler").textContent =
    zeilen.length === relaisZeilen.length
      ? relaisZeilen.length + " Relais"
      : zeilen.length + " von " + relaisZeilen.length + " Relais";
}

function relaisZeile(z) {
  const tr = document.createElement("tr");
  tr.dataset.index = z.index;
  tr.classList.toggle("grenz", z.status === "Grenzbereich");
  tr.classList.toggle("aktiv", z.index === aktivesRelais);

  const auf = document.createElement("td");
  auf.className = "td-auf";
  if (z.talkgroups) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "rund klein aufklappen"
      + (offeneZeilen.has(z.index) ? " offen" : "");
    b.title = "Talkgroups anzeigen";
    b.innerHTML = '<svg class="icon"><use href="#i-chevron_right"/></svg>';
    b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (!offeneZeilen.delete(z.index)) offeneZeilen.add(z.index);
      tabelleRendern();
    });
    auf.appendChild(b);
  }
  tr.appendChild(auf);

  SPALTEN.forEach((s) => {
    const td = document.createElement("td");
    if (s.num) td.classList.add("num");
    if (s.key === "status") {
      const gut = z.status === "Sicht";
      td.className = "status " + (gut ? "gut" : "warnung");
      td.innerHTML = '<svg class="icon"><use href="#'
        + (gut ? "i-check_circle" : "i-warning") + '"/></svg> '
        + z.status;
    } else {
      td.textContent = z[s.key];
    }
    tr.appendChild(td);
  });

  tr.addEventListener("click", () => waehleRelais(z.index, "tabelle"));
  return tr;
}

const TG_ART = { timed: "zeitgeschaltet", cluster: "Cluster" };

function talkgroupZeile(z) {
  const tr = document.createElement("tr");
  tr.className = "tg-zeile";
  const td = document.createElement("td");
  td.colSpan = SPALTEN.length + 1;
  const t = document.createElement("table");
  t.className = "tg-tabelle";
  t.innerHTML = "<tr><th>TS</th><th>TG</th><th>Name</th></tr>";
  z.talkgroups.forEach((tg) => {
    const zeile = document.createElement("tr");
    let name = tg.name || "";
    if (TG_ART[tg.art]) {
      name += (name ? " — " : "") + TG_ART[tg.art]
        + (tg.hinweis ? " (" + tg.hinweis + ")" : "");
    }
    [tg.ts, tg.tg, name].forEach((wert, i) => {
      const zelle = document.createElement("td");
      if (i < 2) zelle.className = "num";
      zelle.textContent = wert;
      zeile.appendChild(zelle);
    });
    t.appendChild(zeile);
  });
  td.appendChild(t);
  tr.appendChild(td);
  return tr;
}

/* Tabelle↔Karte: Zeile wählt Marker (zentrieren + hervorheben),
   Marker wählt Zeile (hinscrollen + hervorheben) — und beide Wege
   schalten das Sichtfeld auf dieses eine Relais um. */
function waehleRelais(index, quelle) {
  if (aktivesRelais !== null && markerRefs[aktivesRelais]) {
    const alt = markerRefs[aktivesRelais];
    alt.setZIndexOffset(0);
    if (alt.getElement()) alt.getElement().classList.remove("aktiv");
  }
  aktivesRelais = index;
  const marker = markerRefs[index];
  if (marker) {
    marker.setZIndexOffset(1000);
    if (marker.getElement()) marker.getElement().classList.add("aktiv");
    if (quelle === "tabelle") karte.panTo(marker.getLatLng());
  }
  $$("#relais-zeilen tr[data-index]").forEach((tr) =>
    tr.classList.toggle("aktiv", Number(tr.dataset.index) === index));
  if (quelle === "karte") {
    const tr = document.querySelector(
      '#relais-zeilen tr[data-index="' + index + '"]');
    if (tr) tr.scrollIntoView({ block: "nearest" });
  }
  // Sichtfeld umschalten; Zweitklick auf dasselbe Relais (oder Escape,
  // oder der Legenden-Knopf) führt zur Summenkarte zurück
  if (hatSichtfeld(index)) {
    feldRelais = feldRelais === index ? null : index;
    zeigeSichtfeld();
    zeigeLegende();
  }
}

/* Escape verlässt die Einzelansicht — gestaffelt: Dialog und Menü
   beanspruchen Escape für sich, danach ein offenes Marker-Popup, erst
   dann die Einzelansicht. Das Popup geht beim Marker-Klick automatisch
   auf, also auf dem üblichen Weg IN die Einzelansicht; ohne Staffelung
   schlösse ein Escape Popup und Einzelansicht in einem Rutsch.

   Das Popup wird hier SELBST geschlossen und nicht Leaflet überlassen:
   dessen Escape-Handler hängt am Kartencontainer und greift nur, wenn
   der den Fokus hat. Bloßes Aussteigen (return) könnte Escape sonst
   dauerhaft wirkungslos machen. */
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape" || feldRelais === null) return;
  if (!$("#dialog-hintergrund").hidden || !$("#menue").hidden) return;
  if (popupOffen && karte) {
    karte.closePopup();
    return;
  }
  alleRelaisZeigen();
});

$("#relais-suche").addEventListener("input", tabelleRendern);

/* ------------------------------------------------- Splitter (U5) */

let splitterAnteil = 0.55;

function setzeSplitter(anteil, speichern) {
  splitterAnteil = Math.min(0.8, Math.max(0.2, anteil));
  $("#karten-bereich").style.flexBasis = (splitterAnteil * 100) + "%";
  if (karte) karte.invalidateSize();
  if (speichern) {
    window.pywebview.api.setze_einstellung("splitter", splitterAnteil);
  }
}

$("#splitter").addEventListener("mousedown", (ev) => {
  ev.preventDefault();
  const bereich = $(".split").getBoundingClientRect();
  const ziehen = (e) =>
    setzeSplitter((e.clientY - bereich.top) / bereich.height, false);
  const loslassen = () => {
    document.removeEventListener("mousemove", ziehen);
    document.removeEventListener("mouseup", loslassen);
    window.pywebview.api.setze_einstellung("splitter", splitterAnteil);
  };
  document.addEventListener("mousemove", ziehen);
  document.addEventListener("mouseup", loslassen);
});

/* ---------------------------------------------- Einstellungen (U6) */

const THEMES = ["system", "hell", "dunkel"];
let aktivesTheme = "system";

function setzeTheme(wahl, speichern) {
  aktivesTheme = THEMES.includes(wahl) ? wahl : "system";
  const wurzel = document.documentElement;
  // data-theme gewinnt gegen das Systemschema (stil.css); ohne
  // Attribut gilt prefers-color-scheme
  if (aktivesTheme === "hell") wurzel.dataset.theme = "light";
  else if (aktivesTheme === "dunkel") wurzel.dataset.theme = "dark";
  else delete wurzel.dataset.theme;
  $$("[data-theme-wahl]").forEach((b) =>
    b.classList.toggle("aktiv", b.dataset.themeWahl === aktivesTheme));
  if (speichern && window.pywebview) {
    window.pywebview.api.setze_einstellung("theme", aktivesTheme);
  }
}

$$("[data-theme-wahl]").forEach((b) =>
  b.addEventListener("click", () =>
    setzeTheme(b.dataset.themeWahl, true)));

async function oeffneMenue() {
  $("#menue").hidden = false;
  $("#menue-ordner").disabled = !ergebnisDa;
  const info = await window.pywebview.api.cache_info();
  $("#menue-cache-info").textContent = info.leer
    ? "Cache ist leer"
    : "Cache: " + info.gesamt + " (" + info.dateien + " Dateien)";
}

$("#einstellungen").addEventListener("click", (ev) => {
  ev.stopPropagation();
  if ($("#menue").hidden) oeffneMenue();
  else $("#menue").hidden = true;
});

document.addEventListener("click", (ev) => {
  if (!$("#menue").hidden && !ev.target.closest("#menue")) {
    $("#menue").hidden = true;
  }
});

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !$("#menue").hidden
      && $("#dialog-hintergrund").hidden) {
    $("#menue").hidden = true;
  }
});

$("#menue-cache-leeren").addEventListener("click", () => {
  $("#menue").hidden = true;
  cacheLeerenDialog();
});

$("#menue-ordner").addEventListener("click", () => {
  $("#menue").hidden = true;
  window.pywebview.api.oeffne_ordner();
});

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

async function cacheLeerenDialog() {
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
}

$("#cache-leeren").addEventListener("click", cacheLeerenDialog);

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
  einstellungen = z.einstellungen || {};
  setzeTheme(einstellungen.theme || "system", false);
  waehleModus(z.tab || "bahn");
});

/* Fallback für Ansicht im Browser (Entwicklung ohne Bridge) */
if (!window.pywebview) waehleModus("bahn");
