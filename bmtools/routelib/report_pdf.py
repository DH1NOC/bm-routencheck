"""PDF-Bericht (U8, GUI-UMBAU.md): Deckblatt + Karte + Relais-Tabelle.

reportlab (reines Python, Helvetica deckt die Umlaute ab — kein
Font-Embedding). Eingabe ist das ergebnis_daten-Payload der Pipeline
({karte, kennzahlen, relais}) — dieselbe Quelle wie GUI-Karte,
Top-Bar und DataGrid; das Kartenbild kommt aus mapimage (U7).
"""
from __future__ import annotations

import html
import io
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RlImage,
)
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .mapimage import KartenbildFehler, render_kartenbild

# Statusfarben wie GUI/Bericht (Spezifikation §2 — identisch in
# Tabelle, Top-Bar, Karte und PDF)
GRUEN = colors.HexColor("#10B981")
AMBER = colors.HexColor("#F59E0B")
GRAU = colors.HexColor("#5a6a7a")
LINIE = colors.HexColor("#c9d2db")
TEXT = colors.HexColor("#1c2733")

RAND = 15 * mm
INHALT_BREITE = A4[0] - 2 * RAND
KARTE_HOEHE = 168 * mm
# Druckauflösung der Übersichtskarte (U8-Befund: 300 dpi; 600 hieße
# ~4-fache Kachelzahl — Tile-Server-Höflichkeit geht vor)
KARTE_DPI = 300

_TITEL = ParagraphStyle("titel", fontName="Helvetica-Bold", fontSize=20,
                        leading=24, textColor=TEXT)
_UNTERTITEL = ParagraphStyle("untertitel", fontName="Helvetica",
                             fontSize=12, leading=16, textColor=GRAU)
_ABSCHNITT = ParagraphStyle("abschnitt", fontName="Helvetica-Bold",
                            fontSize=13, leading=16, textColor=TEXT,
                            spaceBefore=10, spaceAfter=4)
_NORMAL = ParagraphStyle("normal", fontName="Helvetica", fontSize=10,
                         leading=14, textColor=TEXT)
_HINWEIS = ParagraphStyle("hinweis", fontName="Helvetica-Oblique",
                          fontSize=9, leading=12, textColor=GRAU)
_ZELLE = ParagraphStyle("zelle", fontName="Helvetica", fontSize=8.5,
                        leading=11, textColor=TEXT)
_TG = ParagraphStyle("tg", fontName="Helvetica", fontSize=8, leading=10,
                     textColor=GRAU, leftIndent=2)


def _e(text: object) -> str:
    return html.escape(str(text))


def _tg_text(talkgroups: list[dict[str, Any]]) -> str:
    """Talkgroup-Details einer DMR-Zeile: »TS1: … — TS2: …«."""
    je_ts: dict[int, list[dict[str, Any]]] = {}
    for tg in talkgroups:
        je_ts.setdefault(int(tg["ts"]), []).append(tg)
    teile = []
    for ts in sorted(je_ts):
        eintraege = []
        for tg in je_ts[ts]:
            e = str(tg["tg"])
            if tg.get("name"):
                e += f" {tg['name']}"
            if tg.get("art") == "timed":
                e += (f" (zeitgeschaltet {tg['hinweis']})" if tg.get("hinweis")
                      else " (zeitgeschaltet)")
            elif tg.get("art") == "cluster":
                e += f" ({tg.get('hinweis') or 'Cluster'})"
            eintraege.append(e)
        teile.append(f"TS{ts}: " + ", ".join(eintraege))
    return " — ".join(teile)


def _kennzahlen_tabelle(kz: dict[str, Any], anzahl_relais: int) -> Table:
    zellen = []
    if kz.get("distanz_km") is not None:
        zellen.append(("Distanz", f"{kz['distanz_km']} km", TEXT))
    zellen.append(("Relais", str(anzahl_relais), TEXT))
    if kz.get("sicht_pct") is not None:
        zellen += [("Freie Sicht", f"{kz['sicht_pct']} %", GRUEN),
                   ("Grenzbereich", f"{kz['grenz_pct']} %", AMBER),
                   ("Funkschatten", f"{kz['schatten_pct']} %",
                    colors.HexColor("#EF4444"))]
    t = Table([[Paragraph(f"<b>{wert}</b><br/>"
                          f'<font size="8" color="#5a6a7a">{name}</font>',
                          ParagraphStyle(
                              f"kz-{name}", fontName="Helvetica",
                              fontSize=13, leading=16, textColor=farbe))
                for name, wert, farbe in zellen]],
              colWidths=[INHALT_BREITE / len(zellen)] * len(zellen))
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINIE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINIE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _km_bereich(r: dict[str, Any]) -> str:
    """Voraussichtlicher Empfangsabschnitt »von–bis km« (U8-Befund);
    Fallback auf den nächstgelegenen km bei alten Payloads."""
    von = r.get("km_von")
    bis = r.get("km_bis")
    if von is None or bis is None:
        return f"{r['km']:g}"
    if round(von) == round(bis):
        return f"{von:.0f}"
    return f"{von:.0f}–{bis:.0f}"


def _relais_tabelle(relais: list[dict[str, Any]]) -> Table:
    # Nr. verweist auf den gleichnummerierten Marker der
    # Übersichtskarte (U8-Befund: Nummern statt Punkte)
    kopf = ["Nr.", "Empfang km", "Rufzeichen", "Standort", "Modus",
            "RX [MHz]", "TX [MHz]", "Tone/CC", "Status"]
    breiten = [9 * mm, 20 * mm, 22 * mm, 34 * mm, 13 * mm, 21 * mm,
               21 * mm, 16 * mm, 22 * mm]
    daten: list[list[Any]] = [kopf]
    stil: list[tuple[Any, ...]] = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), GRAU),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, TEXT),
        ("ALIGN", (0, 0), (1, -1), "RIGHT"),
        ("ALIGN", (5, 0), (7, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    zeile = 1
    for i, r in enumerate(relais):
        grenz = r["status"] == "Grenzbereich"
        daten.append([
            str(i + 1), _km_bereich(r), _e(r["rufzeichen"]),
            Paragraph(_e(r["standort"]), _ZELLE), r["modus"],
            r["rx"], r["tx"], r["ton"] or "–", r["status"],
        ])
        stil.append(("LINEBELOW", (0, zeile), (-1, zeile), 0.4, LINIE))
        stil.append(("TEXTCOLOR", (8, zeile), (8, zeile),
                     AMBER if grenz else GRUEN))
        if grenz:  # gedimmt wie Terminal-Tabelle und DataGrid
            stil.append(("TEXTCOLOR", (0, zeile), (7, zeile), GRAU))
        zeile += 1
        if r.get("talkgroups"):
            daten.append([
                "", "", Paragraph(_e(_tg_text(r["talkgroups"])), _TG),
                "", "", "", "", "", ""])
            stil.append(("SPAN", (2, zeile), (-1, zeile)))
            stil.append(("LINEBELOW", (0, zeile), (-1, zeile), 0.4,
                         LINIE))
            stil.append(("TOPPADDING", (0, zeile), (-1, zeile), 0))
            zeile += 1
    t = Table(daten, colWidths=breiten, repeatRows=1)
    t.setStyle(TableStyle(stil))
    return t


def write_pdf(daten: dict[str, Any], pfad: Path, *,
              tile_progress: Callable[[int, int], None] | None = None,
              ) -> None:
    """bericht.pdf aus dem ergebnis_daten-Payload schreiben.

    Ohne erreichbare Kartenkacheln entsteht das PDF trotzdem — dann
    mit Hinweis statt Übersichtskarte (Keyless heißt ohne Schlüssel,
    nicht offline; Risiken-Abschnitt GUI-UMBAU.md)."""
    karte = daten.get("karte") or {}
    kz = daten.get("kennzahlen") or {}
    relais = daten.get("relais") or []
    stationen = [s["name"] for s in karte.get("stationen") or []]
    route_text = " → ".join(stationen) if stationen else ""
    legende = karte.get("legende") or {}
    modus_label = legende.get("modus_label") or "/".join(
        sorted({str(r["modus"]) for r in relais})) or "Relais"
    jetzt = datetime.now()
    stand = str(kz.get("stand") or jetzt.strftime("%d.%m.%Y"))

    story: list[Any] = [
        Paragraph("BM-Routencheck", _TITEL),
        Spacer(0, 2 * mm),
        Paragraph(_e(f"{modus_label}-Relais entlang der "
                     f"{karte.get('route_label') or 'Strecke'}"),
                  _UNTERTITEL),
    ]
    if route_text:
        story += [Spacer(0, 4 * mm), Paragraph(_e(route_text), _ABSCHNITT)]
    story += [Spacer(0, 4 * mm), _kennzahlen_tabelle(kz, len(relais)),
              Spacer(0, 6 * mm)]
    if kz.get("sicht_pct") is not None:
        modell = ("Geländemodell" if kz.get("terrain")
                  else "Horizontmodell, ohne Gelände")
        story.append(Paragraph(
            f"Abdeckung rechnerisch geschätzt ({modell}); "
            f"RX/TX aus Sicht des Funkgeräts.", _HINWEIS))
        story.append(Spacer(0, 4 * mm))

    try:
        # Volle Papierbreite in Druckauflösung (U8-Befunde): fuellen
        # zentriert die Route und füllt mit Umgebung exakt auf das
        # Seitenmaß auf; Punkte = Inch/72
        bild = render_kartenbild(
            karte,
            max_breite_px=round(INHALT_BREITE / 72 * KARTE_DPI),
            max_hoehe_px=round(KARTE_HOEHE / 72 * KARTE_DPI),
            fuellen=True, tile_progress=tile_progress)
    except KartenbildFehler as e:
        story.append(Paragraph(
            _e(f"Übersichtskarte nicht verfügbar ({e}) — die "
               f"interaktive Karte liegt als karte.html bei."),
            _HINWEIS))
    else:
        buf = io.BytesIO()
        bild.save(buf, format="PNG")
        buf.seek(0)
        story.append(RlImage(buf, width=INHALT_BREITE,
                             height=KARTE_HOEHE))
        story.append(Spacer(0, 2 * mm))
        marker_note = legende.get("marker_note")
        story.append(Paragraph(
            _e("Marker: "
               + (marker_note + " · " if marker_note else "")
               + "Nummer = Nr. in der Relais-Tabelle"), _HINWEIS))

    story += [PageBreak(),
              Paragraph(f"Relais entlang der Strecke ({len(relais)})",
                        _ABSCHNITT),
              Spacer(0, 2 * mm)]
    if relais:
        story.append(_relais_tabelle(relais))
    else:
        story.append(Paragraph("Keine Relais im Ergebnis.", _HINWEIS))

    def fusszeile(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRAU)
        canvas.drawString(RAND, 10 * mm,
                          f"BM-Routencheck · erzeugt am "
                          f"{jetzt:%d.%m.%Y %H:%M} · Datenstand {stand}")
        canvas.drawRightString(A4[0] - RAND, 10 * mm,
                               f"Seite {canvas.getPageNumber()}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(pfad), pagesize=A4, leftMargin=RAND, rightMargin=RAND,
        topMargin=RAND, bottomMargin=18 * mm,
        title=f"BM-Routencheck — {route_text or 'Bericht'}")
    doc.build(story, onFirstPage=fusszeile, onLaterPages=fusszeile)
