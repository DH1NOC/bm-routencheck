"""Update-Prüfung: Versionsvergleich, Plattformwahl, Angebotslogik.

Der Kern ist die Reihenfolge: Die GitHub-Antwort sagt nur, wo ein
Manifest liegt. Verglichen wird ausschließlich gegen die Version AUS
dem signierten Manifest — sonst könnte eine gefälschte API-Antwort eine
ältere, echt signierte Fassung als »neu« ausgeben.
"""
from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bmtools.update import manifest as m
from bmtools.update import pruefen as p
from bmtools.update import ziel as z

INHALT = b"das neue binary"


@pytest.fixture
def signierer(monkeypatch):
    k = Ed25519PrivateKey.generate()
    pub = base64.b64encode(k.public_key().public_bytes(
        ser.Encoding.Raw, ser.PublicFormat.Raw)).decode()
    monkeypatch.setattr(m, "OEFFENTLICHE_SCHLUESSEL", (pub,))
    return k


def manifest_bytes(version: str, datei: str = "bmtools-x-linux-x64.tar.gz",
                   plattform: str = "linux-x64", inhalt: bytes = INHALT):
    return m.serialisieren(version, {plattform: m.Artefakt(
        datei=datei, sha256=hashlib.sha256(inhalt).hexdigest())})


def fake_api(releases, signierer, fehlend=()):
    """httpx.Client-Ersatz: liefert Release-Liste, Manifeste, Signaturen."""
    ablage: dict[str, bytes] = {}
    eintraege = []
    for tag, version, vorab in releases:
        basis = f"https://example.invalid/{tag}"
        roh = manifest_bytes(version)
        ablage[f"{basis}/{m.MANIFEST_DATEI}"] = roh
        ablage[f"{basis}/{m.SIGNATUR_DATEI}"] = signierer.sign(roh)
        assets = []
        if tag not in fehlend:
            assets = [{"name": m.MANIFEST_DATEI,
                       "browser_download_url": f"{basis}/{m.MANIFEST_DATEI}"},
                      {"name": m.SIGNATUR_DATEI,
                       "browser_download_url": f"{basis}/{m.SIGNATUR_DATEI}"}]
        eintraege.append({"tag_name": tag, "prerelease": vorab,
                          "draft": False, "assets": assets})

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(p.API):
            return httpx.Response(200, json=eintraege)
        if url in ablage:
            return httpx.Response(200, content=ablage[url])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(z, "plattform", lambda: z.LINUX)
    monkeypatch.setattr(p, "plattform", lambda: z.LINUX)
    monkeypatch.setattr(p, "version_bekannt", lambda: True)
    monkeypatch.setattr(p, "eigene_version", lambda: "0.4.0")


# ------------------------------------------------- Versionsvergleich

@pytest.mark.parametrize("kandidat,laufend,erwartet", [
    ("0.4.1", "0.4.0", True),
    ("0.4.0", "0.4.0", False),      # gleich ist kein Update
    ("0.3.9", "0.4.0", False),      # Downgrade-Sperre
    ("0.4.1b1", "0.4.0", True),     # Beta ist neuer als das Release davor
    ("0.4.0", "0.4.0b2", True),     # Release schlägt die eigene Beta
    ("0.4.0b1", "0.4.0b2", False),  # ältere Beta
    ("kaputt", "0.4.0", False),     # unlesbar gilt nie als neuer
    ("0.4.1", "kaputt", False),
])
def test_ist_neuer(kandidat, laufend, erwartet):
    assert p.ist_neuer(kandidat, laufend) is erwartet


# ------------------------------------------------------- Angebotslogik

def test_neueres_release_wird_angeboten(signierer, linux):
    with fake_api([("v0.4.1", "0.4.1", False)], signierer) as c:
        angebot = p.suche_update(client=c)
    assert angebot is not None
    assert angebot.version == "0.4.1"
    assert angebot.artefakt.passt_zu(INHALT)
    assert angebot.datei_url.endswith("bmtools-x-linux-x64.tar.gz")


def test_aeltere_version_wird_nicht_angeboten(signierer, linux):
    """Der Replay-Fall: echt signiert, aber älter."""
    with fake_api([("v0.3.0", "0.3.0", False)], signierer) as c:
        assert p.suche_update(client=c) is None


def test_beta_nur_wenn_gewuenscht(signierer, linux):
    releases = [("v0.4.1-beta.1", "0.4.1b1", True)]
    with fake_api(releases, signierer) as c:
        assert p.suche_update(client=c) is None
    with fake_api(releases, signierer) as c:
        angebot = p.suche_update(mit_vorabversionen=True, client=c)
    assert angebot is not None and angebot.vorabversion


def test_beta_erkennung_kommt_aus_dem_manifest(signierer, linux):
    """Die Kanalwahl gehört dem Nutzer, nicht dem Netzweg.

    Hier lügt die GitHub-Antwort: `prerelease: false` auf einer echten,
    korrekt signierten Beta. Käme die Einstufung von dort, bekäme ein
    Nutzer mit abgeschaltetem Beta-Kanal sie untergeschoben.
    """
    releases = [("v0.4.1-beta.1", "0.4.1b1", False)]   # gelogenes Flag
    with fake_api(releases, signierer) as c:
        assert p.suche_update(client=c) is None
    with fake_api(releases, signierer) as c:
        angebot = p.suche_update(mit_vorabversionen=True, client=c)
    assert angebot is not None and angebot.vorabversion


def test_neuestes_gewinnt(signierer, linux):
    with fake_api([("v0.4.1", "0.4.1", False),
                   ("v0.5.0", "0.5.0", False),
                   ("v0.4.2", "0.4.2", False)], signierer) as c:
        angebot = p.suche_update(client=c)
    assert angebot is not None and angebot.version == "0.5.0"


def test_fremde_signatur_wird_verworfen(signierer, linux, monkeypatch):
    """Klassischer MITM: eigenes Manifest mit höherer Version."""
    fremd = Ed25519PrivateKey.generate()
    with fake_api([("v9.9.9", "9.9.9", False)], fremd) as c:
        assert p.suche_update(client=c) is None


def test_release_ohne_manifest_wird_uebersprungen(signierer, linux):
    """Alte Releases (vor 0.4.0) haben keins — kein Grund zu scheitern."""
    with fake_api([("v0.4.1", "0.4.1", False)], signierer,
                  fehlend={"v0.4.1"}) as c:
        assert p.suche_update(client=c) is None


def test_andere_plattform_kein_angebot(signierer, linux, monkeypatch):
    """Manifest kennt nur linux-x64, wir laufen auf macOS."""
    monkeypatch.setattr(p, "plattform", lambda: z.MACOS)
    with fake_api([("v0.4.1", "0.4.1", False)], signierer) as c:
        assert p.suche_update(client=c) is None


def test_ohne_bekannte_eigene_version_kein_angebot(signierer, linux,
                                                   monkeypatch):
    monkeypatch.setattr(p, "version_bekannt", lambda: False)
    with fake_api([("v9.9.9", "9.9.9", False)], signierer) as c:
        assert p.suche_update(client=c) is None


def test_netzfehler_ist_kein_fehlerfall(linux):
    def kaputt(request):
        raise httpx.ConnectError("kein Netz")

    with httpx.Client(transport=httpx.MockTransport(kaputt)) as c:
        assert p.suche_update(client=c) is None


def test_muell_statt_json(linux):
    def muell(request):
        return httpx.Response(200, content=b"<html>Proxy-Fehlerseite</html>")

    with httpx.Client(transport=httpx.MockTransport(muell)) as c:
        assert p.suche_update(client=c) is None


# ------------------------------------------------------------- Ziel

def test_plattformnamen_decken_sich_mit_dem_workflow():
    """release.yml trägt die Artefakte unter genau diesen Namen ein —
    weichen sie ab, findet der Client sein Artefakt nie."""
    from pathlib import Path
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    for name in (z.WINDOWS, z.MACOS, z.LINUX):
        assert f'"{name}=' in workflow, f"{name} fehlt in release.yml"


@pytest.mark.parametrize("plattform_name,maschine,erwartet", [
    ("win32", "AMD64", z.WINDOWS),
    ("darwin", "arm64", z.MACOS),
    ("darwin", "x86_64", None),      # Intel-Mac: bewusst kein Binary
    ("linux", "x86_64", z.LINUX),
    ("linux", "aarch64", None),
    ("freebsd", "x86_64", None),
])
def test_plattformerkennung(monkeypatch, plattform_name, maschine, erwartet):
    monkeypatch.setattr("bmtools.update.ziel.sys.platform", plattform_name)
    monkeypatch.setattr("bmtools.update.ziel.platform.machine",
                        lambda: maschine)
    assert z.plattform() == erwartet


def test_aus_dem_quellcode_gibt_es_nichts_zu_tauschen(monkeypatch):
    monkeypatch.delattr("bmtools.update.ziel.sys.frozen", raising=False)
    assert z.eigenes_programm() is None


def test_macos_zielt_aufs_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "BM-Routencheck.app"
    binaer = bundle / "Contents" / "MacOS" / "BM-Routencheck"
    binaer.parent.mkdir(parents=True)
    binaer.write_text("x")
    monkeypatch.setattr("bmtools.update.ziel.sys.frozen", True,
                        raising=False)
    monkeypatch.setattr("bmtools.update.ziel.sys.platform", "darwin")
    monkeypatch.setattr("bmtools.update.ziel.sys.executable",
                        str(binaer))
    assert z.eigenes_programm() == bundle.resolve()


def test_schreibrecht_am_ordner_entscheidet(tmp_path):
    datei = tmp_path / "bmtools"
    datei.write_text("x")
    assert z.beschreibbar(datei)
    tmp_path.chmod(0o500)          # nur lesen/betreten
    try:
        assert not z.beschreibbar(datei)
    finally:
        tmp_path.chmod(0o700)


def test_json_ist_kein_dict(linux):
    def liste(request):
        return httpx.Response(200, json={"message": "rate limit"})

    with httpx.Client(transport=httpx.MockTransport(liste)) as c:
        assert p.suche_update(client=c) is None


def test_manifest_wird_nicht_unbegrenzt_gelesen(signierer, linux):
    """Ein manipuliertes Gegenüber darf uns nicht zumüllen."""
    assert p.MANIFEST_MAX <= 1024 * 1024
    roh = manifest_bytes("0.4.1")
    assert len(roh) < p.MANIFEST_MAX
    json.loads(roh)                # weiterhin gültiges JSON


def test_uebergrosses_manifest_wird_beim_laden_abgebrochen(linux):
    """Die Grenze muss beim STREAMEN greifen (Befund 2026-07-27: der
    Zuschnitt kam erst, nachdem .content den kompletten Body gepuffert
    hatte — eine Gigabyte-Antwort hätte den Speicher gefüllt, bevor je
    eine Signatur geprüft war). Ein solches Release wird übersprungen,
    die Suche selbst scheitert nicht."""
    basis = "https://example.invalid/v9.9.9"
    eintraege = [{"tag_name": "v9.9.9", "prerelease": False, "draft": False,
                  "assets": [
                      {"name": m.MANIFEST_DATEI,
                       "browser_download_url": f"{basis}/{m.MANIFEST_DATEI}"},
                      {"name": m.SIGNATUR_DATEI,
                       "browser_download_url": f"{basis}/{m.SIGNATUR_DATEI}"}]}]
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(p.API):
            return httpx.Response(200, json=eintraege)
        return httpx.Response(200, content=b"x" * (p.MANIFEST_MAX * 4))

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(m.ManifestFehler, match="unplausibel"):
            p._begrenzt_laden(c, f"{basis}/{m.MANIFEST_DATEI}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert p.suche_update(client=c) is None
