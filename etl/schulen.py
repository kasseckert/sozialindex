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

# Zwei Dienste des Kultusministeriums: „schulstandorte_bayern“ umfasst alle Schulen (auch kommunale,
# kirchliche und private, z. B. im Datensatz „weitere Schulen“); „schulstandortebayern“ nur die
# staatlichen. Der umfassende Dienst wird bevorzugt, der zweite dient als Rückfall.
WFS_URLS = [u for u in (os.environ.get("SCHULEN_WFS_URL"),
                        "https://gdiserv.bayern.de/srv112940/services/schulstandorte_bayern-wfs",
                        "https://gdiserv.bayern.de/srv112940/services/schulstandortebayern-wfs") if u]
WFS_URL = WFS_URLS[0]
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
    "fos": "Fachoberschul",
}

# Schreibweisen der Schulart in gemischten Ebenen (Feld „Schulart“)
SCHULART_MUSTER = {
    "grundschule": ["grundschul", "grund- und"],
    "mittelschule": ["mittelschul", "hauptschul", "- und mittel"],
    "realschule": ["realschul"],
    "gymnasium": ["gymnas"],
    "berufliche": ["berufs", "fachoberschul", "berufsoberschul", "wirtschaftsschul"],
    "foerderzentrum": ["förder", "foerder"],
    "fos": ["fachoberschul", "fos/bos", "fos-bos", "fos und bos"],
}

SITZUNG = requests.Session()
SITZUNG.headers["User-Agent"] = "sozialindex-oberfranken"


class SchulFehler(RuntimeError):
    pass


SCHULEN_BUDGET_S = 900      # höchstens 15 Minuten für alle Abrufe beim Schuldienst je Lauf
_START = None


def _budget_pruefen():
    global _START
    import time
    if _START is None:
        _START = time.time()
    if time.time() - _START > SCHULEN_BUDGET_S:
        raise SchulFehler(f"Zeitbudget von {SCHULEN_BUDGET_S // 60} Minuten für den Schuldienst aufgebraucht")


def _get(params: dict, timeout: int = 90) -> requests.Response:
    _budget_pruefen()
    letzter = None
    for _ in range(2):
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


_EBENEN_CACHE: list = []
_DIENST_AUS: str = ""


def ebenen_mit_titel() -> list[tuple[str, str]]:
    """(Name, Titel) aller FeatureTypes aus GetCapabilities."""
    global WFS_URL, _DIENST_AUS
    if _EBENEN_CACHE:
        return _EBENEN_CACHE
    if _DIENST_AUS:                            # im selben Lauf schon gescheitert: nicht erneut warten
        raise SchulFehler(_DIENST_AUS)
    fehler = []
    for url in WFS_URLS:                       # ersten erreichbaren Dienst verwenden
        WFS_URL = url
        try:
            r = _get({"SERVICE": "WFS", "REQUEST": "GetCapabilities", "VERSION": "2.0.0"})
            wurzel = ET.fromstring(r.content)
            if any(_lokal(el.tag) == "FeatureType" for el in wurzel.iter()):
                break
            fehler.append(f"{url}: keine Ebenen")
        except (SchulFehler, ET.ParseError) as e:
            fehler.append(f"{url}: {str(e)[:100]}")
    else:
        _DIENST_AUS = "Kein Schuldienst erreichbar: " + "; ".join(fehler)
        raise SchulFehler(_DIENST_AUS)
    for el in wurzel.iter():
        if _lokal(el.tag) == "FeatureType":
            name = next((k.text.strip() for k in el if _lokal(k.tag) == "Name" and k.text), None)
            titel = next((k.text.strip() for k in el if _lokal(k.tag) == "Title" and k.text), "")
            if name:
                _EBENEN_CACHE.append((name, titel))
    if not _EBENEN_CACHE:
        raise SchulFehler("GetCapabilities enthält keine FeatureTypes.")
    return _EBENEN_CACHE


def ebenen() -> list[str]:
    return [n for n, _ in ebenen_mit_titel()]


_FORMAT: dict = {}          # je Dienst das funktionierende Ausgabeformat ("gml" = Standard)


def _ebene_lesen(name: str) -> list[tuple[float, float, dict]]:
    """Alle Objekte einer Ebene mit Eigenschaften (GeoJSON, sonst GML); das Format wird je Dienst gemerkt."""
    basis = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
             "TYPENAMES": name, "SRSNAME": "EPSG:25832", "COUNT": "50000"}
    roh: list[tuple[float, float, dict]] = []
    bekannt = _FORMAT.get(WFS_URL)
    formate = [] if bekannt == "gml" else ([bekannt] if bekannt else ["application/json", "application/geo+json", "json", "geojson"])
    for fmt in formate:
        try:
            daten = _get({**basis, "OUTPUTFORMAT": fmt}).json()
            for f in daten.get("features") or []:
                g = f.get("geometry") or {}
                k = g.get("coordinates")
                if g.get("type") == "MultiPoint" and k:
                    k = k[0]
                if k:
                    roh.append((float(k[0]), float(k[1]), f.get("properties") or {}))
            if roh:
                _FORMAT[WFS_URL] = fmt
                return roh
        except (SchulFehler, ValueError, AttributeError) as e:
            if "Zeitbudget" in str(e):
                raise
            continue
    inhalt = _get(basis).content
    if b"ExceptionReport" in inhalt[:500] or b"ServiceException" in inhalt[:500]:
        raise SchulFehler("Fehlermeldung des Dienstes: " + inhalt[:200].decode("utf-8", "replace"))
    objekte = _eigenschaften_aus_gml(inhalt)
    if objekte:
        _FORMAT[WFS_URL] = "gml"
    return objekte


def _traeger_aus(titel: str, name: str, schulname: str) -> str:
    """
    Träger einer Schule: zuerst aus dem Schulnamen („Staatliche …“, „Städtische …“), dann aus dem
    Titel der Ebene. „Weitere Schulen“ sind nichtstaatlich, umfassen aber kommunale und private.
    """
    sn = f" {schulname.lower()} "
    if " staatliche " in sn or " staatl. " in sn:
        return "staatlich"
    if any(w in sn for w in (" städtische ", " staedtische ", " stadt ", " landkreis ", " zweckverband ")):
        return "kommunal"
    if any(w in sn for w in ("evang", "kath.", "katholisch", "erzbisch", "bischöfl", "diözes", "kirchl", "kloster",
                             "maria-ward", "schulwerk", "ordens", "benedikt", "franziskan", "ursulin", "englische fräulein")):
        return "kirchlich"
    if any(w in sn for w in (" priv.", " private ", " privates ", "privatschule", " freie ", "waldorf", "montessori")):
        return "privat"
    t = f"{titel} {name}".lower()
    if "kommunal" in t:
        return "kommunal"
    if "staatl" in t and "nichtstaatl" not in t:
        return "staatlich"
    if any(w in t for w in ("privat", "kirchl")):
        return "privat oder kirchlich"
    if any(w in t for w in ("nichtstaatl", "freie")):
        return "nichtstaatlich"
    return ""


_ALLE_CACHE: dict = {}
DIAGNOSE: dict = {}          # je Schulart: alle gelesenen Schulen mit Quelle und ggf. Grund des Verwerfens


def schulen_einer_art(schulart: str) -> tuple[list[tuple[float, float, dict]], list[str]]:
    """
    Alle Schulen einer Schulart aus allen Ebenen des Dienstes: Ebenen, deren Name die Schulart
    trägt, und gemischte Ebenen (z. B. „weitere Schulen“), gefiltert über das Feld „Schulart“.
    Doppelte Standorte werden entfernt. Gibt die Schulen (UTM 32N) und Protokollzeilen zurück.
    """
    schluessel = SCHULARTEN.get(schulart, schulart).lower()
    protokoll, ergebnis, gesehen = [], [], set()
    DIAGNOSE[schulart] = []
    for name, titel in ebenen_mit_titel():
        if not _ALLE_CACHE.get(name):         # nur erfolgreich gelesene Ebenen merken; leere erneut versuchen
            fehler = "leere Antwort"
            for versuch in (1, 2):
                try:
                    _ALLE_CACHE[name] = _ebene_lesen(name)
                except SchulFehler as e:
                    _ALLE_CACHE[name] = []
                    fehler = str(e)[:120]
                if _ALLE_CACHE[name]:
                    break
            if not _ALLE_CACHE[name]:
                protokoll.append(f"{titel or name}: NICHT LESBAR ({fehler})")
        objekte = _ALLE_CACHE[name]
        muster = SCHULART_MUSTER.get(schulart, [schluessel])
        if schluessel in f"{name} {titel}".lower():
            treffer = objekte                      # Ebene eigens für diese Schulart: vollständig übernehmen
        elif any(_feld(p, "schulart") for _, _, p in objekte[:50]):
            treffer = [o for o in objekte if any(m in _feld(o[2], "schulart").lower() for m in muster)]
        else:
            treffer = []
        neu = 0
        for x, y, p in treffer:
            p = dict(p)
            p.setdefault("_traeger", _traeger_aus(titel, name, _feld(p, "schulname", "name", "bezeichnung")))
            nr = _feld(p, "schulnummer", "schulnr")
            k = ("nr", nr) if nr else (round(x), round(y), _feld(p, "schulname", "name").lower())
            DIAGNOSE.setdefault(schulart, []).append({"name": _feld(p, "schulname", "name"), "quelle": titel or name,
                "schulart": _feld(p, "schulart"), "ort": _feld(p, "ort"), **({"verworfen": "doppelt im Dienst"} if k in gesehen else {})})
            if k not in gesehen:
                gesehen.add(k)
                ergebnis.append((x, y, p))
                neu += 1
        if treffer:
            arten = sorted({_feld(o[2], "schulart") for o in treffer if _feld(o[2], "schulart")})[:4]
            protokoll.append(f"{titel or name}: {neu} {schulart}" + (f" (Schulart: {', '.join(arten)})" if arten else ""))
    # Schulen, die nur im Dienst der staatlichen Schulen stehen, ergänzen (z. B. fehlende Einträge im
    # umfassenden Dienst). Dort ist jede Schule staatlich.
    if WFS_URL != URL_STAATLICH:
        staatliche_schulen()
        ergaenzt = []
        for n, t, x, y, p in _STAATLICH_OBJEKTE:
            passt = schluessel in f"{n} {t}".lower() or any(m in _feld(p, "schulart").lower() for m in SCHULART_MUSTER.get(schulart, [schluessel]))
            if not passt:
                continue
            kandidat = (x, y, p)
            gleich = next((vorh for vorh in ergebnis if _gleiche_schule(kandidat, vorh)
                           or (math.hypot(vorh[0] - x, vorh[1] - y) < 100
                               and _traeger_aus("", "", _feld(vorh[2], "schulname", "name")) == "staatlich")), None)
            if gleich:
                DIAGNOSE.setdefault(schulart, []).append({"name": _feld(p, "schulname", "name"), "quelle": "staatlicher Dienst",
                    "verworfen": "gleiche Schule wie " + _feld(gleich[2], "schulname", "name")})
                continue
            p = dict(p, _traeger="staatlich")
            ergebnis.append((x, y, p))
            ergaenzt.append(_feld(p, "schulname", "name"))
        if ergaenzt:
            protokoll.append(f"ergänzt aus dem Dienst der staatlichen Schulen: {len(ergaenzt)} (z. B. {', '.join(ergaenzt[:3])})")
    ergebnis = korrekturen_anwenden(schulart, ergebnis, protokoll)
    dienst = WFS_URL.rsplit("/", 1)[-1]
    protokoll.insert(0, f"Dienst {dienst} mit {len(ebenen_mit_titel())} Ebenen: " + ", ".join(t or n for n, t in ebenen_mit_titel())[:600])
    return ergebnis, protokoll


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

    objekte, _ = schulen_einer_art(schulart)
    if not objekte:
        raise SchulFehler(f"Keine Standorte für Schulart '{schulart}' im Dienst gefunden.")
    punkte = [_nach_utm((x, y)) for x, y, _ in objekte]
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


def gemeinde_mittelpunkte(gemeinden_geojson) -> dict[str, tuple[float, float]]:
    """Innenpunkt jeder Gemeindefläche in UTM 32N (eine Datei oder Liste von Dateien)."""
    from pyproj import Transformer
    from shapely import transform as shp_transform
    from shapely.geometry import shape
    t = Transformer.from_crs(4326, 25832, always_xy=True)
    dateien = gemeinden_geojson if isinstance(gemeinden_geojson, (list, tuple)) else [gemeinden_geojson]
    feats = [f for d in dateien for f in json.loads(Path(d).read_text(encoding="utf-8"))["features"]]
    ergebnis = {}
    for f in feats:
        p = f["properties"]
        if p.get("bez") == "Gemeindefreies Gebiet":
            continue
        g = shp_transform(shape(f["geometry"]), lambda xy: list(zip(*t.transform(xy[:, 0], xy[:, 1]))))
        pt = g.representative_point()
        ergebnis[p["ags"]] = (pt.x, pt.y)
    return ergebnis


def entfernungen(schulart: str, gemeinden_geojson) -> dict[str, float]:
    """{gemeinde_ags: Entfernung in km zur nächsten Schule der Schulart}."""
    schulen = standorte(schulart)
    mitte = gemeinde_mittelpunkte(gemeinden_geojson)
    # nur Schulen im Umkreis betrachten (Untersuchungsgebiet + 40 km), spart Rechenzeit
    xs = [p[0] for p in mitte.values()]
    ys = [p[1] for p in mitte.values()]
    rand = 40_000
    nah = [s for s in schulen if min(xs) - rand <= s[0] <= max(xs) + rand and min(ys) - rand <= s[1] <= max(ys) + rand]
    if not nah:
        raise SchulFehler("Keine Schulen im Untersuchungsgebiet gefunden (Koordinatensystem prüfen).")
    # Gitterindex mit 10-km-Zellen: zuerst nur Schulen in benachbarten Zellen prüfen.
    # Nach Suche mit Radius r Zellen ist jede Schule außerhalb mindestens (r - 1) Zellen
    # entfernt; liegt der beste Treffer darunter, ist er garantiert der nächste.
    zelle = 10_000
    gitter: dict = {}
    for sx, sy in nah:
        gitter.setdefault((int(sx // zelle), int(sy // zelle)), []).append((sx, sy))
    ergebnis = {}
    for ags, (x, y) in mitte.items():
        cx, cy = int(x // zelle), int(y // zelle)
        best = None
        for r in range(1, 60):
            kandidaten = [p for dx in range(-r, r + 1) for dy in range(-r, r + 1) for p in gitter.get((cx + dx, cy + dy), [])]
            if kandidaten:
                best = min(math.hypot(x - sx, y - sy) for sx, sy in kandidaten)
                if best <= (r - 1) * zelle:
                    break
        if best is None:
            best = min(math.hypot(x - sx, y - sy) for sx, sy in nah)
        ergebnis[ags] = best / 1000
    return ergebnis


# ---------------------------------------------------------------- Standorte mit Eigenschaften für die Karte
def _eigenschaften_aus_gml(inhalt: bytes) -> list[tuple[float, float, dict]]:
    ergebnis = []
    wurzel = ET.fromstring(inhalt)
    for mitglied in wurzel.iter():
        if _lokal(mitglied.tag) not in ("member", "featureMember"):
            continue
        punkt, props = None, {}
        for el in mitglied.iter():
            name = _lokal(el.tag)
            if name == "pos" and el.text and punkt is None:
                z = el.text.split()
                punkt = (float(z[0]), float(z[1]))
            elif name == "coordinates" and el.text and punkt is None:
                z = re.split(r"[,\s]+", el.text.strip())
                punkt = (float(z[0]), float(z[1]))
            elif len(el) == 0 and el.text and el.text.strip() and name not in ("pos", "coordinates", "posList"):
                props.setdefault(name, el.text.strip())
        if punkt:
            ergebnis.append((punkt[0], punkt[1], props))
    return ergebnis


def _feld(props: dict, *muster: str) -> str:
    """
    Wert des passendsten Feldes: zuerst exakt gleich benannte Felder, dann solche, die das
    Muster enthalten (Groß-/Kleinschreibung egal). So trifft „ort“ das Feld „Ort“ vor „Standort_ID“.
    """
    gefuellt = {k: str(v).strip() for k, v in props.items() if v is not None and str(v).strip()}
    for m in muster:
        for k, v in gefuellt.items():
            if k.lower() == m or k.lower().endswith(":" + m):
                return v
    for m in muster:
        for k, v in gefuellt.items():
            if m in k.lower():
                return v
    return ""


def standorte_fuer_karte(schulart: str) -> tuple[list[dict], list[str]]:
    """
    Standorte einer Schulart mit Name, Adresse und Träger in WGS84 (für Markierungen in der Karte).
    Gibt auch die im Dienst gefundenen Feldnamen zurück, damit sie im Protokoll stehen.
    """
    from pyproj import Transformer
    roh, ebenenprotokoll = schulen_einer_art(schulart)
    if not roh:
        raise SchulFehler(f"Keine Standorte für Schulart '{schulart}' im Dienst gefunden.")
    t = Transformer.from_crs(25832, 4326, always_xy=True)
    felder = sorted({k for _, _, p in roh for k in p if not k.startswith("_")}) + ["Ebenen: " + "; ".join(ebenenprotokoll)]
    standorte = []
    for x, y, p in roh:
        if abs(x) <= 180 and abs(y) <= 90:          # schon geografisch
            lon, lat = (y, x) if abs(x) <= 90 and abs(y) > 90 else (x, y)
        else:
            lon, lat = t.transform(x, y)
        standorte.append({
            "lon": round(lon, 5), "lat": round(lat, 5),
            "name": _feld(p, "schulname", "name", "bezeichnung") or "Schule",
            "strasse": _feld(p, "strasse", "straße", "anschrift", "adresse"),
            "plz": _feld(p, "plz", "postleit"),
            "ort": _feld(p, "ort", "gemeinde", "stadt"),
            "traeger": _feld(p, "traeger", "träger", "rechtsform", "schultraeger") or p.get("_traeger") or traeger_bestimmen(x, y, p),
            "url": _feld(p, "homepage", "internet", "url", "web"),
            "nummer": _feld(p, "schulnummer", "schulnr", "nummer"),
            "schulart": _feld(p, "schulart"),
        })
    return standorte, felder


_STAATLICH_CACHE: set | None = None
_STAATLICH_OBJEKTE: list = []        # [(ebene, titel, x, y, props)] aus dem Dienst der staatlichen Schulen
URL_STAATLICH = "https://gdiserv.bayern.de/srv112940/services/schulstandortebayern-wfs"


def staatliche_schulen() -> set:
    """
    Kennungen (gerundete Lage, normierter Name) aller Schulen des Dienstes für staatliche
    Schulen; die Objekte selbst werden für die Ergänzung fehlender Schulen gemerkt.
    Leer, wenn der Dienst nicht erreichbar ist.
    """
    global _STAATLICH_CACHE, WFS_URL
    if _STAATLICH_CACHE is not None:
        return _STAATLICH_CACHE
    _STAATLICH_CACHE = set()
    vorher = WFS_URL
    try:
        WFS_URL = URL_STAATLICH
        r = _get({"SERVICE": "WFS", "REQUEST": "GetCapabilities", "VERSION": "2.0.0"})
        typen = []
        for el in ET.fromstring(r.content).iter():
            if _lokal(el.tag) == "FeatureType":
                n = next((k.text.strip() for k in el if _lokal(k.tag) == "Name" and k.text), None)
                t = next((k.text.strip() for k in el if _lokal(k.tag) == "Title" and k.text), "")
                if n:
                    typen.append((n, t))
        for n, t in typen:
            for versuch in (1, 2):
                try:
                    objekte = _ebene_lesen(n)
                except SchulFehler:
                    objekte = []
                if objekte:
                    break
            for x, y, p in objekte:
                _STAATLICH_OBJEKTE.append((n, t, x, y, p))
                _STAATLICH_CACHE.add(("lage", round(x / 50), round(y / 50)))
                _STAATLICH_CACHE.add(("name", _name_norm(_feld(p, "schulname", "name"))))
    except (SchulFehler, ET.ParseError):
        pass
    finally:
        WFS_URL = vorher
    return _STAATLICH_CACHE


def _gleiche_schule(a: tuple, b: tuple) -> bool:
    """Gleiche Schule in zwei Diensten: gleicher Name, oder nah beieinander mit gemeinsamem Namensteil."""
    (xa, ya, pa), (xb, yb, pb) = a, b
    na, nb = _feld(pa, "schulname", "name"), _feld(pb, "schulname", "name")
    if _name_norm(na) == _name_norm(nb):
        return True
    if math.hypot(xa - xb, ya - yb) > 150:
        return False
    allgemein = {"staatliche", "staatliches", "staatl", "städtische", "städtisches", "gymnasium", "realschule", "schule",
                 "mittelschule", "grundschule", "fachoberschule", "berufsoberschule", "private", "privates",
                 "erzdiözese", "diözese", "schulwerk", "schulwerks", "stiftung", "evangelische", "katholische"}
    orte = {w for p in (pa, pb) for w in re.findall(r"[a-zäöüß]{3,}", _feld(p, "ort").lower())}
    woerter = lambda n: {w for w in re.findall(r"[a-zäöüß]{5,}", n.lower())} - allgemein - orte
    return bool(woerter(na) & woerter(nb))


def _name_norm(name: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", name.lower())


def traeger_bestimmen(x: float, y: float, props: dict) -> str:
    """Träger über den Namen; sonst über den Abgleich mit dem Dienst der staatlichen Schulen."""
    name = _feld(props, "schulname", "name", "bezeichnung")
    aus_name = _traeger_aus("", "", name)
    if aus_name:
        return aus_name
    st = staatliche_schulen()
    if not st:
        return ""
    zx, zy = round(x / 50), round(y / 50)
    if any(("lage", zx + dx, zy + dy) in st for dx in (-1, 0, 1) for dy in (-1, 0, 1)) or ("name", _name_norm(name)) in st:
        return "staatlich"
    return "nichtstaatlich"


KORREKTUREN = Path(__file__).resolve().parent.parent / "konfiguration" / "schulen_korrekturen.json"


def korrekturen_anwenden(schulart: str, ergebnis: list, protokoll: list) -> list:
    """
    Eigene Korrekturen aus konfiguration/schulen_korrekturen.json: Schulen entfernen (z. B. nach einer
    Zusammenlegung) und fehlende Schulen ergänzen. Die Dienste des Kultusministeriums sind nicht
    vollständig; so lassen sich Lücken dauerhaft schließen.
    """
    if not KORREKTUREN.exists():
        return ergebnis
    try:
        k = json.loads(KORREKTUREN.read_text(encoding="utf-8"))
    except ValueError as e:
        protokoll.append(f"Korrekturdatei fehlerhaft, nicht angewendet: {e}")
        return ergebnis
    vorher = len(ergebnis)
    for e in k.get("entfernen", []):
        if e.get("schulart", schulart) != schulart or not e.get("name_enthaelt"):
            continue
        muster = e["name_enthaelt"].lower()
        ergebnis = [o for o in ergebnis if muster not in _feld(o[2], "schulname", "name").lower()]
    entfernt = vorher - len(ergebnis)
    from pyproj import Transformer
    t = Transformer.from_crs(4326, 25832, always_xy=True)
    ergaenzt = 0
    for e in k.get("ergaenzen", []):
        if e.get("schulart") != schulart or e.get("lat") is None or e.get("lon") is None:
            continue
        x, y = t.transform(float(e["lon"]), float(e["lat"]))
        p = {"schulname": e.get("name", "Schule"), "schulart": e.get("schulart_text", ""), "strasse": e.get("strasse", ""),
             "plz": e.get("plz", ""), "ort": e.get("ort", ""), "_traeger": e.get("traeger", "")}
        if any(_name_norm(_feld(o[2], "schulname", "name")) == _name_norm(p["schulname"]) for o in ergebnis):
            continue                                   # schon vorhanden (z. B. inzwischen im Dienst nachgetragen)
        ergebnis.append((x, y, p))
        ergaenzt += 1
    if entfernt or ergaenzt:
        protokoll.append(f"Korrekturdatei: {entfernt} entfernt, {ergaenzt} ergänzt")
    return ergebnis
