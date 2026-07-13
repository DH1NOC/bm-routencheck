"""HTML-Bericht für die manuelle Codeplug-Eingabe (z. B. Motorola CPS).

Ziel: sauberes Copy&Paste. Pro Relais eine fertige Kanaltabelle
(eine Zeile je Talkgroup) mit allen Werten, die die CPS verlangt —
Frequenzen aus Sicht des Funkgeräts.

Gerendert per jinja2 (Autoescaping) als vollständiges HTML5-Dokument:
<meta charset> ist Pflicht — ohne sie riet z. B. Samsung Internet die
Kodierung falsch und zeigte Umlaute/Symbole als Zeichensalat
(gemeldet 2026-07-13); der Viewport-Tag macht den Bericht auf dem
Smartphone lesbar, breite Tabellen scrollen im eigenen Wrapper.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import jinja2

from .coverage import MIN_GAP_KM, CoverageEstimate
from .model import Route
from .report import RepeaterResult

MIN_RANGE_KM = 2.0  # kürzere Relais-Abschnitte werden mit dem Vorgänger verschmolzen


def _contact_ranges(coverage: CoverageEstimate):
    """Strecke in Abschnitte gleicher erreichbarer Relais gliedern.

    Im Stadtgebiet wechselt die sichtbare Relais-Menge fast an jedem
    Abtastpunkt (Abtastrauschen im Geländemodell) — deshalb wird je
    Relais zuerst jede Mikro-Lücke < MIN_RANGE_KM in seiner
    Erreichbarkeit überbrückt. Verbleibende Mikro-Abschnitte werden per
    VEREINIGUNG in den Vorgänger gefaltet, nicht verworfen: Das alte
    Verwerfen ließ z. B. DM0RBB auf den letzten 35 km einer Route nach
    Berlin aus der Tabelle verschwinden (gemeldet 2026-07-13).

    Liefert (start_km, end_km, los, marginal): Rufzeichen mit Sicht-
    kontakt bzw. (nur wenn keine Sicht besteht) im Grenzbereich.
    """
    samples = coverage.samples
    if not samples:
        return []
    kms = [s.km for s in samples]
    ends = kms[1:] + [coverage.total_km]

    def smooth(present: list[bool]) -> list[bool]:
        out = present[:]
        prev_true = None
        for i, p in enumerate(present):
            if p:
                if (prev_true is not None and i - prev_true > 1
                        and kms[i] - ends[prev_true] < MIN_RANGE_KM):
                    for j in range(prev_true + 1, i):
                        out[j] = True
                prev_true = i
        return out

    calls = sorted({c for s in samples for c in s.los + s.marginal})
    los_p = {c: smooth([c in s.los for s in samples]) for c in calls}
    marg_p = {c: smooth([c in s.marginal for s in samples]) for c in calls}

    ranges = []
    for i in range(len(samples)):
        los = tuple(c for c in calls if los_p[c][i])
        marginal = (() if los
                    else tuple(c for c in calls if marg_p[c][i]))
        if ranges and ranges[-1][2:] == (los, marginal):
            ranges[-1] = (ranges[-1][0], ends[i], los, marginal)
        else:
            ranges.append((kms[i], ends[i], los, marginal))

    merged = []
    for r in ranges:
        if merged and r[1] - r[0] < MIN_RANGE_KM:
            prev = merged[-1]
            los = tuple(sorted(set(prev[2]) | set(r[2])))
            marginal = (() if los
                        else tuple(sorted(set(prev[3]) | set(r[3]))))
            merged[-1] = (prev[0], r[1], los, marginal)
        else:
            merged.append(r)
    final = []
    for r in merged:
        if final and final[-1][2:] == r[2:]:
            final[-1] = (final[-1][0], r[1], r[2], r[3])
        else:
            final.append(r)
    return final


_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; margin: 2rem auto;
       max-width: 62rem; line-height: 1.45; padding: 0 1rem; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2.2rem; }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: .6rem 0 1rem; }
th, td { border: 1px solid #8886; padding: .3rem .55rem; text-align: left;
         font-size: .92rem; }
th { background: #8882; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
code, td.mono { font-family: ui-monospace, 'SF Mono', Consolas, monospace; }
.meta { color: #888; font-size: .85rem; }
.badge { border-radius: .6em; padding: 0 .5em; font-size: .8em;
         background: #b8620033; border: 1px solid #b8620066;
         white-space: nowrap; }
.timed { background: #e6a70033; } .cluster { background: #0a84ff22; }
@media print { body { margin: 0; } h2 { page-break-before: auto; } }
"""

_TEMPLATE = jinja2.Environment(autoescape=True).from_string("""\
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DMR-Relais {{ stations }}</title>
<style>{{ css }}</style>
</head>
<body>
<h1>DMR-Relais entlang der Strecke {{ stations }}</h1>
<p class="meta">Erstellt {{ created }} · Quelle: Brandmeister-API ·
Verbindung: {{ legs }}{% if interpolated %} ·
<b>Achtung: Luftlinien-Interpolation!</b>{% endif %}</p>
<p><b>Alle Frequenzangaben aus Sicht deines Funkgeräts:</b>
RX = Relais-Ausgabe (du hörst), TX = Relais-Eingabe (du sendest).
Uhrzeiten von Zeitschaltungen sind Lokalzeit.</p>

<h2>Übersicht</h2>
<div class="tablewrap"><table>
<tr><th class="num">km</th><th>Rufzeichen</th><th>Standort</th>
<th class="num">Abstand</th><th class="num">RX [MHz]</th>
<th class="num">TX [MHz]</th><th class="num">CC</th></tr>
{% for r in overview %}
<tr><td class="num">{{ r.km }}</td>
<td><a href="#id{{ r.id }}">{{ r.callsign }}</a>{% if r.marginal %}
<span class="badge">Grenzbereich</span>{% endif %}</td><td>{{ r.city }}</td>
<td class="num">{{ r.dist }} km</td>
<td class="num mono">{{ r.rx }}</td>
<td class="num mono">{{ r.tx }}</td>
<td class="num">{{ r.cc }}</td></tr>
{% endfor %}
</table></div>

{% if cov %}
<h2>Abdeckungsschätzung</h2>
{% if cov.terrain %}
<p>Voraussichtlich <b>ca. {{ cov.uncovered_pct }} %</b> der Strecke ohne
DMR-Abdeckung (Funkschatten; {{ cov.uncovered_km }} von
{{ cov.total_km }} km). Dazu {{ cov.marginal_pct }} %
({{ cov.marginal_km }} km) im Grenzbereich, wo Empfang durch Beugung
möglich ist. Freie Sicht zu einem Relais: {{ cov.covered_pct }} %.</p>
{% else %}
<p>Voraussichtlich <b>ca. {{ cov.uncovered_pct }} %</b> der Strecke ohne
DMR-Abdeckung ({{ cov.uncovered_km }} von {{ cov.total_km }} km).</p>
{% endif %}
{% if cov.gaps %}
<p>Größere {{ "Funkschatten-Abschnitte" if cov.terrain else "Lücken" }}
(≥ {{ cov.min_gap_km }} km):</p>
<div class="tablewrap"><table>
<tr><th class="num">von km</th><th class="num">bis km</th>
<th class="num">Länge</th></tr>
{% for g in cov.gaps %}
<tr><td class="num">{{ g.start }}</td><td class="num">{{ g.end }}</td>
<td class="num">{{ g.len }} km</td></tr>
{% endfor %}
</table></div>
{% else %}
<p>Keine Lücken ≥ {{ cov.min_gap_km }} km.</p>
{% endif %}
{% if cov.terrain %}
<p class="meta">Methodik: Sichtlinienprüfung gegen ein digitales
Höhenmodell (SRTM-basiert, ~50 m Raster) mit 4/3-Erdradius;
Mobilantenne 2 m. „Grenzbereich“ = Hindernis bis 30 m über der
Sichtlinie (Beugungsempfang plausibel). Vegetation/Bebauung und
Sendeleistung sind nicht modelliert. Die Relais-Auswahl folgt der
rechnerischen Erreichbarkeit von der Strecke (kein fester Korridor);
geprüft werden alle aktuell online gemeldeten Repeater der Umgebung.</p>
{% else %}
<p class="meta">Methodik: Sichtlinien-Funkhorizont je Relais aus der
Antennenhöhe (d ≈ 4,12·(√h<sub>Antenne</sub> + √2 m) km), ohne
Geländemodell — in Tälern und Mittelgebirgen optimistisch, der Wert
ist also eine Untergrenze. Berücksichtigt sind alle aktuell online
gemeldeten Repeater der Umgebung, auch außerhalb des Suchkorridors.</p>
{% endif %}
{% endif %}

{% if ranges %}
<h2>Erreichbare Relais je Streckenabschnitt</h2>
<p class="meta">Unterbrechungen kürzer als {{ min_range_km }} km sind
überbrückt (Abtastrauschen, v. a. im Stadtgebiet).</p>
<div class="tablewrap"><table>
<tr><th class="num">von km</th><th class="num">bis km</th>
<th>Relais (potenziell erreichbar)</th></tr>
{% for r in ranges %}
<tr><td class="num">{{ r.start }}</td><td class="num">{{ r.end }}</td>
<td>{% if r.kind == "los" %}{{ r.names | join(", ") }}
{%- elif r.kind == "marginal" %}<i>nur grenzwertig:</i> {{ r.names | join(", ") }}
{%- else %}<i>— Funkschatten</i>{% endif %}</td></tr>
{% endfor %}
</table></div>
{% endif %}

{% for rep in repeaters %}
<h2 id="id{{ rep.id }}">{{ rep.callsign }} — {{ rep.city }}{% if rep.marginal %}
<span class="badge">nur Grenzbereich</span>{% endif %}</h2>
<p class="meta">DMR-ID {{ rep.id }} · Streckenkilometer {{ rep.km }} ·
Abstand zur Strecke {{ rep.dist }} km · Antenne {{ rep.agl }} m AGL ·
{{ rep.pep }} W · zuletzt gesehen {{ rep.last_seen }}</p>
{% if rep.marginal %}
<p><i>Keine freie Sicht zu einem Streckenpunkt — Empfang nur per
Beugung plausibel (Hindernis ≤ 30 m über der Sichtlinie).</i></p>
{% endif %}
{% if rep.only_implicit %}
<p><i>Keine statischen Talkgroups konfiguriert — nur TG9 Lokal und
dynamische Nutzung (per PTT-Anmeldung).</i></p>
{% endif %}
<div class="tablewrap"><table>
<tr><th>Kanalname</th><th class="num">RX [MHz]</th>
<th class="num">TX [MHz]</th><th class="num">CC</th>
<th class="num">Slot</th><th class="num">Talkgroup</th>
<th>TG-Name</th><th>Art</th></tr>
{% for c in rep.channels %}
<tr{% if c.css %} class="{{ c.css }}"{% endif %}><td class="mono">{{ c.name }}</td>
<td class="num mono">{{ c.rx }}</td>
<td class="num mono">{{ c.tx }}</td>
<td class="num">{{ c.cc }}</td>
<td class="num">{{ c.slot }}</td>
<td class="num">{{ c.tg }}</td>
<td>{{ c.tg_name }}</td><td>{{ c.art }}</td></tr>
{% endfor %}
</table></div>
{% endfor %}
</body>
</html>
""")

_KIND_LABEL = {"static": "statisch", "timed": "zeitgeschaltet",
               "cluster": "Cluster", "implicit": "Lokal (Standard)"}


def _fmt_mhz(v: float | None) -> str:
    return f"{v:.5f}" if v else ""


def _art(sub) -> str:
    if sub.kind == "cluster":
        ext = sub.note.removeprefix("Cluster-TG ").strip()
        return f"Cluster (⇄ TG {ext})" if ext and ext != "Cluster" else "Cluster"
    if sub.kind == "timed" and sub.note:
        return f"zeitgeschaltet ({sub.note})"
    return _KIND_LABEL[sub.kind]


def write_html_report(results: list[RepeaterResult], route: Route, path: Path,
                      tg_names: dict[int, str] | None = None,
                      coverage: CoverageEstimate | None = None) -> None:
    tg_names = tg_names or {}

    overview = [{
        "km": f"{r.hit.chainage_km:.0f}", "id": r.device.id,
        "callsign": r.device.callsign, "city": r.device.city,
        "dist": f"{r.hit.distance_km:.1f}", "marginal": r.marginal_only,
        "rx": _fmt_mhz(r.device.tx_mhz), "tx": _fmt_mhz(r.device.rx_mhz),
        "cc": r.device.colorcode or "",
    } for r in results]

    cov = None
    ranges = []
    if coverage is not None:
        cov = {
            "terrain": coverage.terrain_used,
            "uncovered_pct": f"{coverage.uncovered_pct:.0f}",
            "uncovered_km": f"{coverage.uncovered_km:.0f}",
            "total_km": f"{coverage.total_km:.0f}",
            "marginal_pct": f"{coverage.pct(coverage.marginal_km):.0f}",
            "marginal_km": f"{coverage.marginal_km:.0f}",
            "covered_pct": f"{coverage.pct(coverage.covered_km):.0f}",
            "min_gap_km": f"{MIN_GAP_KM:.0f}",
            "gaps": [{"start": f"{g.start_km:.0f}", "end": f"{g.end_km:.0f}",
                      "len": f"{g.length_km:.0f}"} for g in coverage.gaps],
        }
        if coverage.samples:
            for a, b, los, marginal in _contact_ranges(coverage):
                kind = "los" if los else ("marginal" if marginal else "shadow")
                ranges.append({"start": f"{a:.0f}", "end": f"{b:.0f}",
                               "kind": kind, "names": los or marginal})

    repeaters = []
    for r in results:
        d = r.device
        # Slot 0 kommt nach der Profil-Bereinigung (Pipeline) nur noch
        # bei Simplex-Repeatern vor — auf Duplex ist es Miskonfiguration
        # und wird verworfen.
        repeaters.append({
            "id": d.id, "callsign": d.callsign, "city": d.city,
            "km": f"{r.hit.chainage_km:.0f}",
            "dist": f"{r.hit.distance_km:.1f}", "marginal": r.marginal_only,
            "agl": d.agl or "?", "pep": d.pep or "?",
            "last_seen": d.last_seen,
            "only_implicit": all(s.kind == "implicit"
                                 for s in r.profile.subscriptions),
            "channels": [{
                "name": f"{d.callsign} {s.talkgroup}"[:16],
                "css": s.kind if s.kind in ("timed", "cluster") else "",
                "rx": _fmt_mhz(d.tx_mhz), "tx": _fmt_mhz(d.rx_mhz),
                "cc": d.colorcode or "",
                "slot": s.slot if s.slot in (1, 2) else "1 (Simplex)",
                "tg": s.talkgroup, "tg_name": tg_names.get(s.talkgroup, ""),
                "art": _art(s),
            } for s in r.profile.subscriptions],
        })

    html = _TEMPLATE.render(
        css=_CSS,
        stations=" – ".join(s.name for s in route.stations),
        created=f"{datetime.now():%d.%m.%Y %H:%M}",
        legs=", ".join(route.legs) or "Luftlinie",
        interpolated=route.is_interpolated,
        min_range_km=f"{MIN_RANGE_KM:.0f}",
        overview=overview, cov=cov, ranges=ranges, repeaters=repeaters,
    )
    path.write_text(html, encoding="utf-8")
