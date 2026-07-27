"""Manifest-Signatur — die Stelle, an der MITM-Schutz steht oder fällt.

Jeder Test hier beschreibt einen Angriff oder eine Panne, die still
durchgehen würde, wenn die Prüfung nachlässig wäre. Die Regel lautet:
Im Zweifel KEIN Update anbieten — nie »trotzdem versuchen«.
"""
from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bmtools.update import manifest as m
from bmtools.update import schluessel as s


def privat_zu_b64(k: Ed25519PrivateKey) -> str:
    return base64.b64encode(k.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())).decode()


def oeffentlich_zu_b64(k: Ed25519PrivateKey) -> str:
    return base64.b64encode(k.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)).decode()


@pytest.fixture
def schluesselpaar(monkeypatch):
    """Testschlüssel an die Stelle der einkompilierten setzen."""
    k = Ed25519PrivateKey.generate()
    monkeypatch.setattr(s, "OEFFENTLICHE_SCHLUESSEL",
                        (oeffentlich_zu_b64(k),))
    monkeypatch.setattr(m, "OEFFENTLICHE_SCHLUESSEL",
                        (oeffentlich_zu_b64(k),))
    return k


def baue(version="0.4.1", datei="bmtools-0.4.1-linux-x64.tar.gz",
         inhalt=b"neues binary"):
    art = {"linux-x64": m.Artefakt(
        datei=datei, sha256=hashlib.sha256(inhalt).hexdigest())}
    return m.serialisieren(version, art), inhalt


def test_echtes_manifest_wird_angenommen(schluesselpaar):
    roh, inhalt = baue()
    geprueft = m.pruefe_manifest(roh, schluesselpaar.sign(roh))
    assert geprueft.version == "0.4.1"
    artefakt = geprueft.fuer("linux-x64")
    assert artefakt is not None
    assert artefakt.passt_zu(inhalt)


def test_verfaelschtes_manifest_fliegt_auf(schluesselpaar):
    """Angreifer ändert die Version im Manifest — Signatur passt nicht mehr."""
    roh, _ = baue()
    signatur = schluesselpaar.sign(roh)
    manipuliert = roh.replace(b'"0.4.1"', b'"9.9.9"')
    assert manipuliert != roh
    with pytest.raises(m.ManifestFehler, match="Signatur"):
        m.pruefe_manifest(manipuliert, signatur)


def test_fremder_schluessel_wird_abgelehnt(schluesselpaar):
    """Der klassische MITM: eigenes, in sich stimmiges Manifest."""
    fremd = Ed25519PrivateKey.generate()
    roh, _ = baue(version="9.9.9")
    with pytest.raises(m.ManifestFehler, match="Signatur"):
        m.pruefe_manifest(roh, fremd.sign(roh))


def test_reserveschluessel_gilt_ebenfalls(monkeypatch):
    """Rotation: Ein mit dem Reserveschlüssel signiertes Manifest muss
    durchgehen, sonst wäre der zweite Platz wertlos."""
    haupt = Ed25519PrivateKey.generate()
    reserve = Ed25519PrivateKey.generate()
    monkeypatch.setattr(m, "OEFFENTLICHE_SCHLUESSEL",
                        (oeffentlich_zu_b64(haupt),
                         oeffentlich_zu_b64(reserve)))
    roh, _ = baue()
    assert m.pruefe_manifest(roh, reserve.sign(roh)).version == "0.4.1"


def test_verfaelschtes_artefakt_faellt_beim_hash_auf(schluesselpaar):
    """Manifest echt, aber die ausgelieferte Datei ausgetauscht."""
    roh, _ = baue()
    geprueft = m.pruefe_manifest(roh, schluesselpaar.sign(roh))
    artefakt = geprueft.fuer("linux-x64")
    assert artefakt is not None
    assert not artefakt.passt_zu(b"schadsoftware")


def test_leere_signatur(schluesselpaar):
    roh, _ = baue()
    with pytest.raises(m.ManifestFehler):
        m.pruefe_manifest(roh, b"")


def test_pfad_im_dateinamen_wird_verworfen(schluesselpaar):
    """Ein Dateiname geht später in URL und Pfad — »../« hätte dort
    nichts verloren, auch nicht aus einem echt signierten Manifest."""
    for boese in ("../../etc/passwd", "unter/ordner.zip", ".versteckt"):
        roh = m.serialisieren("0.4.1", {"linux-x64": m.Artefakt(
            datei=boese, sha256="0" * 64)})
        with pytest.raises(m.ManifestFehler, match="Dateinamen"):
            m.pruefe_manifest(roh, schluesselpaar.sign(roh))


@pytest.mark.parametrize("kaputt,muster", [
    (b"kein json", "nicht lesbar"),
    (json.dumps({"artefakte": {}}).encode(), "Version"),
    (json.dumps({"version": "1.0"}).encode(), "Artefakte"),
    (json.dumps({"version": "1.0", "artefakte": {
        "linux-x64": {"datei": "x.tar.gz"}}}).encode(), "SHA256"),
    (json.dumps({"version": "1.0", "artefakte": {
        "linux-x64": {"datei": "x.tar.gz",
                      "sha256": "z" * 64}}}).encode(), "hexadezimal"),
])
def test_unbrauchbares_manifest(schluesselpaar, kaputt, muster):
    """Echt signiert, aber inhaltlich Unsinn — trotzdem ablehnen."""
    with pytest.raises(m.ManifestFehler, match=muster):
        m.pruefe_manifest(kaputt, schluesselpaar.sign(kaputt))


def test_serialisierung_ist_stabil():
    """Signieren und Prüfen müssen exakt dieselben Bytes sehen —
    sonst passt keine Signatur je wieder."""
    art = {"b": m.Artefakt("b.zip", "1" * 64),
           "a": m.Artefakt("a.zip", "2" * 64)}
    einmal = m.serialisieren("1.0", art)
    andersherum = m.serialisieren("1.0", dict(reversed(list(art.items()))))
    assert einmal == andersherum
    assert b'"a"' in einmal[:einmal.index(b'"b"')]  # sortiert


def test_einkompilierte_schluessel_sind_brauchbar():
    """Die echten Schlüssel im Auslieferungszustand: ladbar, 32 Byte,
    verschieden."""
    roh = [s.als_bytes(b64) for b64 in s.OEFFENTLICHE_SCHLUESSEL]
    assert len(roh) == 2
    assert all(len(r) == 32 for r in roh)
    assert roh[0] != roh[1]
