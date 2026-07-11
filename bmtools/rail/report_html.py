"""HTML-Bericht für die manuelle Codeplug-Eingabe (z. B. Motorola CPS).

Ziel: sauberes Copy&Paste. Pro Relais eine fertige Kanaltabelle
(eine Zeile je Talkgroup) mit allen Werten, die die CPS verlangt —
Frequenzen aus Sicht des Funkgeräts.
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from .report import RepeaterResult
from .route import Route

_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; margin: 2rem auto;
       max-width: 62rem; line-height: 1.45; padding: 0 1rem; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2.2rem; }
table { border-collapse: collapse; width: 100%; margin: .6rem 0 1rem; }
th, td { border: 1px solid #8886; padding: .3rem .55rem; text-align: left;
         font-size: .92rem; }
th { background: #8882; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
code, td.mono { font-family: ui-monospace, 'SF Mono', Consolas, monospace; }
.meta { color: #888; font-size: .85rem; }
.badge { border-radius: .6em; padding: 0 .5em; font-size: .8em; }
.timed { background: #e6a70033; } .cluster { background: #0a84ff22; }
summary-table td { white-space: nowrap; }
@media print { body { margin: 0; } h2 { page-break-before: auto; } }
"""


def _fmt_mhz(v: float | None) -> str:
    return f"{v:.5f}" if v else ""


def write_html_report(results: list[RepeaterResult], route: Route, path: Path,
                      tg_names: dict[int, str] | None = None) -> None:
    tg_names = tg_names or {}
    e = html.escape
    stations = " – ".join(e(s.name) for s in route.stations)
    parts: list[str] = [f"<style>{_CSS}</style>"]
    parts.append(f"<h1>DMR-Relais entlang der Strecke {stations}</h1>")
    parts.append(
        f"<p class='meta'>Erstellt {datetime.now():%d.%m.%Y %H:%M} · "
        f"Quelle: Brandmeister-API · Verbindung: {e(', '.join(route.legs) or 'Luftlinie')}"
        f"{' · <b>Achtung: Luftlinien-Interpolation!</b>' if route.is_interpolated else ''}</p>"
    )
    parts.append(
        "<p><b>Alle Frequenzangaben aus Sicht deines Funkgeräts:</b> "
        "RX = Relais-Ausgabe (du hörst), TX = Relais-Eingabe (du sendest). "
        "Uhrzeiten von Zeitschaltungen sind Lokalzeit.</p>"
    )

    # Übersicht
    parts.append("<h2>Übersicht</h2><table><tr>"
                 "<th class='num'>km</th><th>Rufzeichen</th><th>Standort</th>"
                 "<th class='num'>Abstand</th><th class='num'>RX [MHz]</th>"
                 "<th class='num'>TX [MHz]</th><th class='num'>CC</th></tr>")
    for r in results:
        d = r.device
        parts.append(
            f"<tr><td class='num'>{r.hit.chainage_km:.0f}</td>"
            f"<td><a href='#id{d.id}'>{e(d.callsign)}</a></td><td>{e(d.city)}</td>"
            f"<td class='num'>{r.hit.distance_km:.1f} km</td>"
            f"<td class='num mono'>{_fmt_mhz(d.tx_mhz)}</td>"
            f"<td class='num mono'>{_fmt_mhz(d.rx_mhz)}</td>"
            f"<td class='num'>{d.colorcode or ''}</td></tr>"
        )
    parts.append("</table>")

    # Detail je Relais: fertige Kanalliste für die CPS-Eingabe
    kind_label = {"static": "statisch", "timed": "zeitgeschaltet",
                  "cluster": "Cluster", "implicit": "Lokal (Standard)"}
    for r in results:
        d = r.device
        parts.append(f"<h2 id='id{d.id}'>{e(d.callsign)} — {e(d.city)}</h2>")
        parts.append(
            f"<p class='meta'>DMR-ID {d.id} · Streckenkilometer {r.hit.chainage_km:.0f} · "
            f"Abstand zur Strecke {r.hit.distance_km:.1f} km · "
            f"Antenne {d.agl or '?'} m AGL · {d.pep or '?'} W · "
            f"zuletzt gesehen {e(d.last_seen)}</p>"
        )
        if all(s.kind == "implicit" for s in r.profile.subscriptions):
            parts.append("<p><i>Keine statischen Talkgroups konfiguriert — nur "
                         "TG9 Lokal und dynamische Nutzung (per PTT-Anmeldung).</i></p>")
        parts.append("<table><tr><th>Kanalname</th><th class='num'>RX [MHz]</th>"
                     "<th class='num'>TX [MHz]</th><th class='num'>CC</th>"
                     "<th class='num'>Slot</th><th class='num'>Talkgroup</th>"
                     "<th>TG-Name</th><th>Art</th></tr>")
        for s in r.profile.subscriptions:
            name = f"{d.callsign} {s.talkgroup}"[:16]
            css = f" class='{s.kind}'" if s.kind in ("timed", "cluster") else ""
            art = kind_label[s.kind]
            if s.kind == "cluster":
                ext = s.note.removeprefix("Cluster-TG ").strip()
                art = f"Cluster (⇄ TG {e(ext)})" if ext and ext != "Cluster" else "Cluster"
            elif s.kind == "timed" and s.note:
                art = f"zeitgeschaltet ({e(s.note)})"
            parts.append(
                f"<tr{css}><td class='mono'>{e(name)}</td>"
                f"<td class='num mono'>{_fmt_mhz(d.tx_mhz)}</td>"
                f"<td class='num mono'>{_fmt_mhz(d.rx_mhz)}</td>"
                f"<td class='num'>{d.colorcode or ''}</td>"
                f"<td class='num'>{s.slot if s.slot in (1, 2) else '1 (Simplex)'}</td>"
                f"<td class='num'>{s.talkgroup}</td>"
                f"<td>{e(tg_names.get(s.talkgroup, ''))}</td><td>{art}</td></tr>"
            )
        parts.append("</table>")

    path.write_text("\n".join(parts), encoding="utf-8")
