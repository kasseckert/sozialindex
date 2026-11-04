"""
Schulerreichbarkeit aus den Schulstandorten Bayern.

Quelle: Bayerisches Staatsministerium für Unterricht und Kultus,
"Schulstandorte in Bayern", WFS-Downloaddienst, jährlich aktualisiert,
Lizenz CC BY 4.0 (Namensnennung: "Bayerisches Staatsministerium für
Unterricht und Kultus").
https://gdiserv.bayern.de/srv112940/services/schulstandortebayern-wfs

Berechnet für jede Gemeinde die Luftlinienentfernung (km) vom Mittelpunkt
der Gemeindefläche zur nächsten Schule einer Schulart. Für Kreise wird der
Mittelwert ihrer Gemeinden gebildet.

Einschränkungen (auch in der Karte erläutert):
- Luftlinie, nicht Schulweg; Bezugspunkt ist der Flächenmittelpunkt der
  Gemeinde, nicht der Wohnort der Kinder.
- Nur Schulen in Bayern; bayerische Kinder besuchen in aller Regel
  bayerische Schulen.
"""
from __future__ import annotations

import json
import math
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

WFS_URL = os.environ.get("SCHULEN_WFS_URL", "https://gdiserv.bayern.de/srv112940/services/schulstandortebayern-wfs")
WURZEL = Path(__file__).resolve().parent.parent
CACHE = WURZEL / "daten" / "cache"

# Schlüsselwörter der Ebenen im Dienst (Name des FeatureTypes)
SCHULARTEN = {
    "grundschule": "Grundschul",
    "mittelschule": "Mittelschul",
    "realschule": "Realschul",
    "gymnasium": "Gymnas",
    "berufliche": "Beruflich",
    "foerderzentrum": "Foerderzentr",
}

SITZUNG = requests.Session()
SITZUNG.headers["User-Agent"] = "sozialindex-oberfranken"


class SchulFehler(RuntimeError):
    pass


def _get(params: dict, timeout: int = 120) -> requests.Response:
    letzter = None
    for _ in range(3):
        try:
            r = SITZUNG.get(WFS_URL, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            letzter = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            letzter = str(e)
    raise SchulFehler(f"WFS nicht erreichbar: {letzter}")


def _lokal(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def ebenen() -> list[str]:
    """Namen der FeatureTypes aus GetCapabilities."""
    r = _get({"SERVICE": "WFS", "REQUEST": "GetCapabilities", "VERSION": "2.0.0"})
    wurzel = ET.fromstring(r.content)
    namen = []
    for el in wurzel.iter():
        if _lokal(el.tag) == "FeatureType":
            for kind in el:
                if _lokal(kind.tag) == "Name" and kind.text:
                    namen.append(kind.text.strip())
    if not namen:
        raise SchulFehler("GetCapabilities enthält keine FeatureTypes.")
    return namen


def _punkte_aus_json(daten: dict) -> list[tuple[float, float]]:
    punkte = []
    for f in daten.get("features") or []:
        g = f.get("geometry") or {}
        k = g.get("coordinates")
        if g.get("type") == "Point" and k:
            punkte.append((float(k[0]), float(k[1])))
        elif g.get("type") == "MultiPoint" and k:
            punkte.append((float(k[0][0]), float(k[0][1])))
    return punkte


def _punkte_aus_gml(inhalt: bytes) -> list[tuple[float, float]]:
    punkte = []
    wurzel = ET.fromstring(inhalt)
    for mitglied in wurzel.iter():
        if _lokal(mitglied.tag) not in ("member", "featureMember"):
            continue
        for el in mitglied.iter():
            name = _lokal(el.tag)
            if name == "pos" and el.text:
                z = el.text.split()
                punkte.append((float(z[0]), float(z[1])))
                break
            if name == "coordinates" and el.text:
                z = re.split(r"[,\s]+", el.text.strip())
                punkte.append((float(z[0]), float(z[1])))
                break
    return punkte


def standorte(schulart: str) -> list[tuple[float, float]]:
    """
    Schulstandorte einer Schulart als Punkte in UTM 32N (EPSG:25832, Meter).
    Ergebnisse werden für einen Tag zwischengespeichert.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"schulen_{schulart}.json"
    import time
    if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
        return [tuple(p) for p in json.loads(cache.read_text())]

    schluessel = SCHULARTEN.get(schulart, schulart).lower()
    passend = [n for n in ebenen() if schluessel in n.lower()]
    if not passend:
        raise SchulFehler(f"Keine Ebene für Schulart '{schulart}' im Dienst gefunden.")
    name = passend[0]

    basis = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
             "TYPENAMES": name, "SRSNAME": "EPSG:25832", "COUNT": "50000"}
    punkte: list[tuple[float, float]] = []
    for fmt in ("application/json", "application/geo+json", "json", "geojson"):
        try:
            r = _get({**basis, "OUTPUTFORMAT": fmt})
            punkte = _punkte_aus_json(r.json())
            if punkte:
                break
        except (SchulFehler, ValueError):
            continue
    if not punkte:   # Standardformat GML
        r = _get(basis)
        punkte = _punkte_aus_gml(r.content)
    if not punkte:
        raise SchulFehler(f"Ebene {name}: keine Standorte gelesen.")
    punkte = [_nach_utm(p) for p in punkte]
    cache.write_text(json.dumps(punkte))
    return punkte


def _nach_utm(p: tuple[float, float]) -> tuple[float, float]:
    """Erkennt versehentlich gelieferte geografische Koordinaten und rechnet um."""
    x, y = p
    if abs(x) <= 90 and abs(y) <= 180:          # lat, lon (Achsenfolge EPSG:4326)
        from pyproj import Transformer
        return Transformer.from_crs(4326, 25832, always_xy=True).transform(y, x)
    if abs(x) <= 180 and abs(y) <= 90:          # lon, lat
        from pyproj import Transformer
        return Transformer.from_crs(4326, 25832, always_xy=True).transform(x, y)
    return x, y


def gemeinde_mittelpunkte(gemeinden_geojson: Path) -> dict[str, tuple[float, float]]:
    """Innenpunkt jeder Gemeindefläche in UTM 32N."""
    from pyproj import Transformer
    from shapely import transform as shp_transform
    from shapely.geometry import shape
    t = Transformer.from_crs(4326, 25832, always_xy=True)
    fc = json.loads(gemeinden_geojson.read_text(encoding="utf-8"))
    ergebnis = {}
    for f in fc["features"]:
        p = f["properties"]
        if p.get("bez") == "Gemeindefreies Gebiet":
            continue
        g = shp_transform(shape(f["geometry"]), lambda xy: list(zip(*t.transform(xy[:, 0], xy[:, 1]))))
        pt = g.representative_point()
        ergebnis[p["ags"]] = (pt.x, pt.y)
    return ergebnis


def entfernungen(schulart: str, gemeinden_geojson: Path) -> dict[str, float]:
    """{gemeinde_ags: Entfernung in km zur nächsten Schule der Schulart}."""
    schulen = standorte(schulart)
    mitte = gemeinde_mittelpunkte(gemeinden_geojson)
    # nur Schulen im Umkreis betrachten (Oberfranken + 40 km), spart Rechenzeit
    xs = [p[0] for p in mitte.values()]
    ys = [p[1] for p in mitte.values()]
    rand = 40_000
    nah = [s for s in schulen if min(xs) - rand <= s[0] <= max(xs) + rand and min(ys) - rand <= s[1] <= max(ys) + rand]
    if not nah:
        raise SchulFehler("Keine Schulen im Umkreis von Oberfranken gefunden (Koordinatensystem prüfen).")
    return {ags: min(math.hypot(x - sx, y - sy) for sx, sy in nah) / 1000 for ags, (x, y) in mitte.items()}
