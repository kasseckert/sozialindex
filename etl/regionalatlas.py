"""
Client für den Regionalatlas Deutschland der Statistischen Ämter des Bundes
und der Länder. Kein Zugangsschlüssel nötig.

Zwei Server:
  Katalog  https://regionalatlas.statistikportal.de/taskrunner/services.json
           (alle Indikatoren mit Code, Titeln, Wertspalten, Jahren, Ebenen)
  Daten    ArcGIS-MapServer https://www.gis-idmz.nrw.de/arcgis/rest/services/
           stba/regionalatlas/MapServer/dynamicLayer/query

Die Datenabfrage verknüpft die Grenztabelle mit der Indikatortabelle per SQL.
Tabellenname, Ebene und Jahr werden vor dem Einbau streng geprüft.

Daten: © Statistische Ämter des Bundes und der Länder, dl-de/by-2-0.
Aufbau der Abfrage nach dem quelloffenen Client
github.com/maschinenlesbar-org/regionalatlas-cli (MIT).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

KATALOG_URL = os.environ.get("REGIONALATLAS_KATALOG_URL",
                             "https://regionalatlas.statistikportal.de/taskrunner/services.json")
DATEN_URL = os.environ.get("REGIONALATLAS_DATEN_URL", "https://www.gis-idmz.nrw.de") + \
    "/arcgis/rest/services/stba/regionalatlas/MapServer/dynamicLayer/query"

EBENEN = {"land": 1, "regierungsbezirk": 2, "kreis": 3, "gemeinde": 5}
EBENEN_REIHENFOLGE = ["land", "regierungsbezirk", "kreis", "gemeinde"]   # wie geom_levels

# Sonderwerte (Tabellenzeichen der amtlichen Statistik als Zahl)
SONDERWERTE = {
    2222222222: 0.0,      # "-" nichts vorhanden → 0
    5555555555: None,     # geheim zu halten
    6666666666: None,     # Aussage nicht sinnvoll
    7777777777: None,     # nicht sicher genug
    8888888888: None,     # fällt später an
}

SITZUNG = requests.Session()
SITZUNG.headers["User-Agent"] = "sozialindex-oberfranken (+https://github.com)"


class RegionalatlasFehler(RuntimeError):
    pass


def _get(url: str, params: dict | None = None, versuche: int = 3, timeout: int = 90):
    fehler = None
    for i in range(versuche):
        try:
            r = SITZUNG.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            fehler = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            fehler = str(e)
        time.sleep(1.5 * (i + 1))
    raise RegionalatlasFehler(f"{url}: {fehler}")


# ------------------------------------------------------------------ Katalog
def tabelle_fuer_code(code: str) -> str:
    return code.lower().replace("-", "_")


def katalog_laden(cache: Path | None = None, max_alter_stunden: float = 20) -> list[dict]:
    """
    Lädt den Indikatorenkatalog und bringt ihn in eine flache, schlanke Form:
    [{code, tabelle, thema, titel, titel_lang, felder:[{code,titel,einheit}],
      jahre:{"2023":["kreis","gemeinde",…]}}]
    """
    if cache and cache.exists() and (time.time() - cache.stat().st_mtime) < max_alter_stunden * 3600:
        return json.loads(cache.read_text(encoding="utf-8"))
    roh = _get(KATALOG_URL)
    if not isinstance(roh, list):
        raise RegionalatlasFehler("Katalog hat ein unerwartetes Format.")
    katalog = []
    for thema in roh:
        if not isinstance(thema, dict):
            continue
        for kind in thema.get("children") or []:
            code = kind.get("code") if isinstance(kind, dict) else None
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", code):
                continue
            jahre = {}
            for jahr, eintraege in (kind.get("years") or {}).items():
                if not re.fullmatch(r"\d{4}", jahr) or not isinstance(eintraege, list):
                    continue
                veroeffentlicht = [False] * 4
                for e in eintraege:
                    zahlen = e.get("geom_levels") if isinstance(e, dict) else None
                    if isinstance(zahlen, list) and len(zahlen) == 4:
                        for k, n in enumerate(zahlen):
                            if isinstance(n, (int, float)) and n > 0:
                                veroeffentlicht[k] = True
                jahre[jahr] = [EBENEN_REIHENFOLGE[k] for k, v in enumerate(veroeffentlicht) if v]
            felder = []
            for a in kind.get("attributes") or []:
                if isinstance(a, dict) and isinstance(a.get("code"), str):
                    fc = a["code"].lower().replace("-", "_")
                    if re.fullmatch(r"[a-z0-9_]+", fc):
                        felder.append({"code": fc, "titel": a.get("title_short") or "",
                                       "einheit": a.get("unit") or ""})
            katalog.append({
                "code": code, "tabelle": tabelle_fuer_code(code),
                "thema": thema.get("title") or "",
                "titel": kind.get("title_short") or "", "titel_lang": kind.get("title_long") or "",
                "felder": felder, "jahre": dict(sorted(jahre.items())),
            })
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(katalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return katalog


def _woerter(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.lower().strip()) if w]


def _enthaelt(text: str, suche: str) -> bool:
    t = text.lower()
    return all(w in t for w in _woerter(suche))


def aufloesen(katalog: list[dict], spec: dict, ebene: str, jahre: list[int]) -> tuple[dict, dict] | None:
    """
    Findet Indikator und Wertspalte. spec enthält entweder feste Angaben
    {"code": "AI003-3", "feld": "ai0306"} oder Suchbegriffe
    {"suche": ["Betreuungsquote"], "feld_suche": ["0 bis 2"]}.
    Gibt (Katalogeintrag, Feld) zurück oder None.
    """
    def verfuegbar(ind):
        return sum(1 for j in jahre if ebene in ind["jahre"].get(str(j), []))

    if spec.get("code"):
        tab = tabelle_fuer_code(spec["code"])
        ind = next((i for i in katalog if i["tabelle"] == tab), None)
        if not ind:
            return None
        kandidaten = [ind]
    else:
        suchen = spec.get("suche") or []
        suchen = [suchen] if isinstance(suchen, str) else suchen
        kandidaten = [i for i in katalog
                      if any(_enthaelt(f"{i['titel']} {i['titel_lang']} " +
                                       " ".join(f["titel"] for f in i["felder"]), s) for s in suchen)]
    beste, bester_wert = None, -1
    for ind in kandidaten:
        if verfuegbar(ind) == 0:
            continue
        if spec.get("feld"):
            feld = next((f for f in ind["felder"] if f["code"] == spec["feld"].lower()), None)
            treffer_feld = 3 if feld else 0
        else:
            fsuchen = spec.get("feld_suche") or []
            fsuchen = [fsuchen] if isinstance(fsuchen, str) else fsuchen
            feld = next((f for f in ind["felder"] if any(_enthaelt(f["titel"], s) for s in fsuchen)), None)
            treffer_feld = 2 if feld else 0
            if not fsuchen:            # nur ohne Feldsuche ist die erste Spalte eine zulässige Wahl
                feld = ind["felder"][0] if ind["felder"] else None
            # mit Feldsuche und ohne Treffer: Quelle verwerfen statt eine falsche Spalte zu nehmen
        if not feld:
            continue
        titeltreffer = 2 if any(_enthaelt(ind["titel"], s)
                                for s in ([spec.get("suche")] if isinstance(spec.get("suche"), str)
                                          else spec.get("suche") or [])) else 0
        wert = treffer_feld * 100 + titeltreffer * 50 + verfuegbar(ind)
        if wert > bester_wert:
            beste, bester_wert = (ind, feld), wert
    return beste


# -------------------------------------------------------------------- Daten
def _sql(tabelle: str, typ: int, jahr: int) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", tabelle) or tabelle == "verwaltungsgrenzen_gesamt":
        raise RegionalatlasFehler(f"Ungültiger Tabellenname {tabelle!r}")
    if typ not in EBENEN.values():
        raise RegionalatlasFehler(f"Ungültige Ebene {typ}")
    if not (1000 <= int(jahr) <= 9999):
        raise RegionalatlasFehler(f"Ungültiges Jahr {jahr}")
    return (f"SELECT * FROM verwaltungsgrenzen_gesamt "
            f"LEFT OUTER JOIN {tabelle} ON ags = ags2 and jahr = jahr2 "
            f"WHERE typ = {typ} AND jahr = {int(jahr)} AND (jahr2 = {int(jahr)} OR jahr2 IS NULL)")


def _wert(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        z = float(v)
    except (TypeError, ValueError):
        return None
    if z > 2_000_000_000:
        return SONDERWERTE.get(int(z))
    return z


def _amtlicher_schluessel(ags: str, ebene: str) -> str:
    ziffern = re.sub(r"\D", "", str(ags))
    laenge = {"land": 2, "regierungsbezirk": 3, "kreis": 5, "gemeinde": 8}[ebene]
    return ziffern.zfill(laenge)


def abfragen(tabelle: str, feld: str, ebene: str, jahr: int, praefix: str = "") -> dict[str, float]:
    """
    Werte eines Feldes für alle Gebiete einer Ebene in einem Jahr.
    praefix schränkt per where-Klausel ein (z. B. "094" für Oberfranken);
    lehnt der Server das ab, wird ungefiltert und seitenweise abgerufen.
    """
    layer = json.dumps({"source": {"type": "dataLayer", "dataSource": {
        "type": "queryTable", "geometryType": "esriGeometryPolygon", "workspaceId": "gdb",
        "oidFields": "id", "spatialReference": {"wkid": 25832},
        "query": _sql(tabelle, EBENEN[ebene], jahr)}}})
    if praefix and not re.fullmatch(r"\d{1,8}", praefix):
        raise RegionalatlasFehler("Ungültiges Präfix")

    def lauf(where: str):
        werte, offset = {}, 0
        while True:
            antwort = _get(DATEN_URL, {
                "layer": layer, "f": "json", "outFields": "*", "returnGeometry": "false",
                "where": where, "spatialRel": "esriSpatialRelIntersects",
                "resultOffset": str(offset), "resultRecordCount": "2000",
            })
            if "error" in antwort:
                raise RegionalatlasFehler(str(antwort["error"])[:300])
            merkmale = antwort.get("features")
            if not isinstance(merkmale, list):
                raise RegionalatlasFehler("Antwort ohne features")
            for m in merkmale:
                a = m.get("attributes") or {}
                ags = _amtlicher_schluessel(a.get("ags", ""), ebene)
                if praefix and not ags.startswith(praefix):
                    continue
                w = _wert(a.get(feld))
                if w is not None:
                    werte[ags] = w
            if antwort.get("exceededTransferLimit") is True and merkmale:
                offset += len(merkmale)
                continue
            return werte

    if praefix:
        try:
            return lauf(f"ags LIKE '{praefix}%'")
        except RegionalatlasFehler:
            pass
    return lauf("1=1")
