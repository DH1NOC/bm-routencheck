"""Changelog-Abfrage: Versionsfenster, Beta-Filter, Fehlertoleranz."""
from __future__ import annotations

import httpx

from bmtools.update import changelog as c


def api_client(eintraege) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=eintraege)
    return httpx.Client(transport=httpx.MockTransport(handler))


def eintrag(tag: str, body: str, *, draft: bool = False) -> dict[str, object]:
    return {"tag_name": tag, "draft": draft, "body": body}


def test_fenster_und_reihenfolge():
    with api_client([eintrag("v0.4.0", "alt"), eintrag("v0.4.1", "eins"),
                     eintrag("v0.4.2", "zwei")]) as cl:
        notes = c.notes_zwischen("0.4.0", "0.4.2", client=cl)
    assert [(n.version, n.notes) for n in notes] == [
        ("0.4.2", "zwei"), ("0.4.1", "eins")]


def test_betas_nur_wenn_selbst_installiert():
    eintraege = [eintrag("v0.5.0b1", "beta"), eintrag("v0.4.2", "stabil")]
    with api_client(eintraege) as cl:
        assert [n.version for n in
                c.notes_zwischen("0.4.1", "0.4.2", client=cl)] == ["0.4.2"]
        assert [n.version for n in
                c.notes_zwischen("0.4.2", "0.5.0b1", client=cl)] == ["0.5.0b1"]


def test_muell_wird_uebergangen():
    with api_client([
        eintrag("v0.4.2", "gut"),
        eintrag("kein-tag", "unlesbare Version"),
        {"tag_name": "v0.4.1"},                    # ohne Body
        eintrag("v0.4.15", "   "),                 # nur Leerraum
        eintrag("v0.4.1", "Entwurf", draft=True),
        "kein-dict",
    ]) as cl:
        notes = c.notes_zwischen("0.4.0", "0.5.0", client=cl)
    assert [n.version for n in notes] == ["0.4.2"]


def test_lange_notes_werden_gekappt():
    with api_client([eintrag("v0.4.2", "x" * (c.NOTES_MAX + 500))]) as cl:
        (n,) = c.notes_zwischen("0.4.1", "0.4.2", client=cl)
    assert len(n.notes) == c.NOTES_MAX


def test_notes_zu_liefert_genau_die_eigene_version():
    """Erster Lauf nach einem Update ohne Marker: Die Vorversion ist
    unbekannt, gezeigt wird genau das Neue der laufenden Version —
    nicht die ganze Historie."""
    with api_client([eintrag("v0.4.2", "alt"), eintrag("v0.4.3", "neu"),
                     eintrag("v0.5.0b1", "beta")]) as cl:
        notes = c.notes_zu("0.4.3", client=cl)
    assert [(n.version, n.notes) for n in notes] == [("0.4.3", "neu")]


def test_notes_zu_mit_unlesbarer_version_bleibt_leer():
    with api_client([eintrag("v0.4.3", "neu")]) as cl:
        assert c.notes_zu("quatsch", client=cl) == []


def test_offline_ergibt_leere_liste():
    def kaputt(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kein Netz")
    with httpx.Client(transport=httpx.MockTransport(kaputt)) as cl:
        assert c.notes_zwischen("0.4.0", "0.4.2", client=cl) == []


def test_unlesbare_eigene_versionen_ergeben_leere_liste():
    with api_client([eintrag("v0.4.2", "x")]) as cl:
        assert c.notes_zwischen("quatsch", "0.4.2", client=cl) == []
