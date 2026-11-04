"""
Schritt 1: Daten aus allen konfigurierten Quellen abrufen.

Ergebnis
  daten/rohdaten.csv           ebene;ags;jahr;indikator;wert;herkunft
  daten/quellenprotokoll.json  welche Quelle (Code/Feld) je Indikator und Ebene genutzt wurde
  web/data/katalog.json        schlanker Regionalatlas-Katalog für den Datenassistenten

Aufruf
  python etl/abrufen.py                   echte Quellen; Indikatoren ohne Daten entfallen
  python etl/abrufen.py --demo-auffuellen echte Quellen, Lücken mit Demowerten (nur zum Testen)
  python etl/abrufen.py --nur-demo        nur Demowerte, ohne Internet

Wenn keine einzige echte Quelle Daten liefert (z. B. Server nicht erreichbar),
bricht das Skript mit Fehlercode ab und lässt die bisherigen Daten unverändert.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import demodaten
import konfiguration as K

WURZEL = Path(__file__).resolve().parent.parent
DATEN = WURZEL / "daten"
IMPORT = DATEN / "import"
WEB_DATEN = WURZEL / "web" / "data"
KATALOG_CACHE = DATEN / "cache" / "regionalatlas_katalog.json"

_katalog = None
_katalog_fehler = None


def geodateien(ebene: str) -> list[Path]:
    if ebene == "kreis":
        return [WEB_DATEN / "kreise.geojson"]
    return sorted((WEB_DATEN / "gemeinden").glob("*.geojson"))


def gebiete(ebene: str) -> list[dict]:
    ergebnis = []
    for datei in geodateien(ebene):
        fc = json.loads(datei.read_text(encoding="utf-8"))
        ergebnis += [f["properties"] for f in fc["features"] if f["properties"].get("bez") != "Gemeindefreies Gebiet"]
    return ergebnis


def _zahl(text):
    text = (text or "").strip()
    if text in ("", "-", ".", "...", "x", "/", "–"):
        return None
    try:
        return float(text.replace(".", "").replace(",", ".")) if "," in text else float(text)
    except ValueError:
        return None


def _ags(code: str, ebene: str):
    code = re.sub(r"\D", "", code or "")
    if ebene == "kreis" and len(code) >= 5:
        return code[:5]
    if ebene == "gemeinde" and len(code) == 8:
        return code
    if ebene == "gemeinde" and len(code) == 9:
        return code[:5] + code[6:]
    return None


def katalog():
    global _katalog, _katalog_fehler
    if _katalog_fehler:
        raise RuntimeError("Regionalatlas-Katalog nicht erreichbar (siehe oben)")
    if _katalog is None:
        import regionalatlas as RA
        try:
            _katalog = RA.katalog_laden(KATALOG_CACHE)
        except Exception as e:
            _katalog_fehler = e
            raise RuntimeError(f"Regionalatlas-Katalog nicht erreichbar: {str(e)[:160]}") from None
        (WEB_DATEN / "katalog.json").write_text(
            json.dumps({"stand": date.today().isoformat(), "indikatoren": _katalog},
                       ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return _katalog


# ------------------------------------------------------------- Quellen
def quelle_regionalatlas(spec: dict, ebene: str):
    import regionalatlas as RA
    zusatz = spec.get("jahre", 0) if spec.get("berechnung") == "veraenderung" else 0
    jahre = list(range(min(K.JAHRE) - zusatz, max(K.JAHRE) + 1))
    treffer = RA.aufloesen(katalog(), spec, ebene, K.JAHRE)
    if not treffer:
        return None
    ind, feld = treffer
    werte = {}
    for j in jahre:
        if ebene not in ind["jahre"].get(str(j), []):
            continue
        for ags, w in RA.abfragen(ind["tabelle"], feld["code"], ebene, j, K.REGIERUNGSBEZIRK_PRAEFIX).items():
            werte[(ags, j)] = w
    if spec.get("berechnung") == "veraenderung":
        n = spec.get("jahre", 5)
        werte = {(a, j): (w / werte[(a, j - n)] - 1) * 100
                 for (a, j), w in werte.items() if werte.get((a, j - n))}
    herkunft = f"regionalatlas:{ind['code']}/{feld['code']}"
    info = {"quelle": "Regionalatlas Deutschland", "code": ind["code"], "feld": feld["code"],
            "titel": ind["titel"], "feld_titel": feld["titel"], "einheit": feld["einheit"]}
    return werte, herkunft, info


def quelle_csv(spec: dict, ebene: str):
    datei = IMPORT / spec["datei"]
    if not datei.exists():
        return None
    werte = {}
    with datei.open(encoding="utf-8-sig") as f:
        for z in csv.DictReader(f, delimiter=";"):
            ags = _ags(z.get("ags", ""), ebene)
            w = _zahl(z.get("wert"))
            if ags and w is not None and re.fullmatch(r"\d{4}", (z.get("jahr") or "").strip()):
                werte[(ags, int(z["jahr"]))] = w
    if not werte:
        return None
    return werte, f"csv:{spec['datei']}", {"quelle": spec.get("quellenangabe") or f"Eigene Datei {spec['datei']}"}


_genesis_cache: dict = {}


def _genesis_zeilen(datenbank: str, tabelle: str, ebene: str, spec: dict):
    """Ruft eine Tabelle ab; probiert gängige Namen der Regionalvariable durch."""
    from genesis import tabelle_ffcsv, GenesisFehler
    schluessel = (datenbank, tabelle, ebene)
    if schluessel in _genesis_cache:
        return _genesis_cache[schluessel]
    varianten = [spec["regionalvariable"]] if spec.get("regionalvariable") else (
        ["KREISE", "KRS", "KREIS"] if ebene == "kreis" else ["GEMEIN", "GEM", "GEMEINDE"])
    zusatz = spec.get("jahre", 0) if spec.get("berechnung") == "veraenderung" else 0
    fehler = None
    for rv in varianten:
        try:
            zeilen = tabelle_ffcsv(datenbank, tabelle, min(K.JAHRE) - zusatz, max(K.JAHRE),
                                   rv, K.REGIERUNGSBEZIRK_PRAEFIX + "*")
            _genesis_cache[schluessel] = zeilen
            return zeilen
        except GenesisFehler as e:
            fehler = e
    raise fehler


def quelle_genesis(spec: dict, ebene: str):
    from genesis_auswerten import ffcsv_auswerten
    from genesis import finde_tabellen
    db = spec["datenbank"]
    if spec.get("tabelle"):
        kandidaten = [{"code": spec["tabelle"], "titel": ""}]
    elif spec.get("suche"):
        kandidaten = finde_tabellen(db, spec["suche"] if isinstance(spec["suche"], list) else [spec["suche"]])
    else:
        return None
    letzter_fehler = None
    for kand in kandidaten:
        try:
            zeilen = _genesis_zeilen(db, kand["code"], ebene, spec)
            werte = ffcsv_auswerten(zeilen, spec, ebene, K.REGIERUNGSBEZIRK_PRAEFIX)
        except Exception as e:
            letzter_fehler = e
            continue
        if spec.get("berechnung") == "veraenderung":
            n = spec.get("jahre", 5)
            werte = {(a, j): (w / werte[(a, j - n)] - 1) * 100
                     for (a, j), w in werte.items() if werte.get((a, j - n))}
        if werte:
            return werte, f"genesis:{db}/{kand['code']}", {
                "quelle": {"bildung": "Kommunale Bildungsdatenbank", "zensus": "Zensus 2022",
                           "regio": "Regionaldatenbank Deutschland", "bayern": "GENESIS-Online Bayern"}.get(db, f"GENESIS {db}"),
                "code": kand["code"], "titel": kand.get("titel", "")}
    if letzter_fehler and spec.get("tabelle"):
        raise letzter_fehler
    return None


def quelle_quotient(spec: dict, ebene: str):
    z = QUELLEN[spec["zaehler"]["typ"]](spec["zaehler"], ebene)
    n = QUELLEN[spec["nenner"]["typ"]](spec["nenner"], ebene)
    if not z or not n:
        return None
    faktor = spec.get("faktor", 1)
    werte = {k: z[0][k] / n[0][k] * faktor for k in z[0] if n[0].get(k)}
    info = dict(z[2])
    return werte, f"{z[1]} / {n[1]}", info


def quelle_schulen(spec: dict, ebene: str):
    import schulen
    gem = schulen.entfernungen(spec["schulart"], geodateien("gemeinde"))
    if ebene == "kreis":
        summen: dict = {}
        for ags, km in gem.items():
            summen.setdefault(ags[:5], []).append(km)
        werte_ohne_jahr = {k: sum(v) / len(v) for k, v in summen.items()}
    else:
        werte_ohne_jahr = gem
    jahr = max(K.JAHRE)
    werte = {(ags, jahr): km for ags, km in werte_ohne_jahr.items()}
    return werte, f"schulen:{spec['schulart']}", {
        "quelle": "Schulstandorte in Bayern, Bayerisches Staatsministerium für Unterricht und Kultus (CC BY 4.0)",
        "code": spec["schulart"]}


def zeitlich_konstant(werte: dict) -> dict:
    """Überträgt den jeweils jüngsten Wert eines Gebiets auf alle Jahre (Strukturmerkmale)."""
    letzter: dict = {}
    for (ags, jahr), w in sorted(werte.items(), key=lambda x: x[0][1]):
        letzter[ags] = w
    return {(ags, j): w for ags, w in letzter.items() for j in K.JAHRE}


def genesis_katalog_schreiben():
    """Tabellenlisten von Bildungsdatenbank und Zensus für den Datenassistenten."""
    from genesis import hat_zugang, tabellen_katalog
    katalog = {}
    for db, auswahl in (("bildung", "*"), ("zensus", "2000S*")):
        if not hat_zugang(db):
            continue
        try:
            katalog[db] = tabellen_katalog(db, auswahl)
        except Exception as e:
            print(f"  ! Tabellenliste {db}: {str(e)[:160]}")
    if katalog:
        (WEB_DATEN / "genesis_katalog.json").write_text(
            json.dumps({"stand": date.today().isoformat(), **katalog}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")


QUELLEN = {"regionalatlas": quelle_regionalatlas, "csv": quelle_csv, "genesis": quelle_genesis,
           "quotient": quelle_quotient, "schulen": quelle_schulen}


def abdeckung(werte: dict, anzahl_gebiete: int) -> float:
    if not werte:
        return 0.0
    letztes = max(j for _, j in werte)
    return len({a for a, j in werte if j == letztes}) / max(anzahl_gebiete, 1)


# ---------------------------------------------------------------- Ablauf
def main():
    nur_demo = "--nur-demo" in sys.argv
    auffuellen = "--demo-auffuellen" in sys.argv
    DATEN.mkdir(exist_ok=True)
    IMPORT.mkdir(exist_ok=True)
    zeilen, protokoll, quellenprotokoll = [], [], {"kreis": {}, "gemeinde": {}}
    echte_werte = 0

    for ebene in ("kreis", "gemeinde"):
        gebiet_liste = gebiete(ebene)
        for ind in K.INDIKATOREN:
            if ebene not in ind["ebenen"]:
                continue
            werte, herkunft, info = {}, None, None
            if not nur_demo:
                for spec in ind["quellen"]:
                    try:
                        res = QUELLEN[spec["typ"]](spec, ebene)
                    except Exception as e:  # Quelle gestört → nächste Quelle
                        protokoll.append(f"  ! {ind['id']} ({ebene}, {spec['typ']}): {e}")
                        continue
                    if not res:
                        continue
                    w, h, i = res
                    if ind.get("zeitlich_konstant") or spec.get("zeitlich_konstant"):
                        w = zeitlich_konstant(w)
                        h += " (konstant fortgeschrieben)"
                    deckung = abdeckung(w, len(gebiet_liste))
                    if deckung < K.MINDEST_ABDECKUNG:
                        protokoll.append(f"  · {ind['id']} ({ebene}): {h} deckt nur {deckung:.0%} der Gebiete ab, übersprungen")
                        continue
                    werte, herkunft, info = w, h, i
                    break
            if werte:
                echte_werte += len(werte)
            elif nur_demo or auffuellen:
                werte = demodaten.werte(ind["id"], ebene, gebiet_liste, K.JAHRE)
                herkunft, info = "demo", {"quelle": "Demodaten (fiktiv)"}
            if not werte:
                protokoll.append(f"{ebene:<9} {ind['id']:<11}     – keine Daten, entfällt auf dieser Ebene")
                continue
            for (ags, jahr), wert in sorted(werte.items()):
                if jahr in K.JAHRE:
                    zeilen.append([ebene, ags, jahr, ind["id"], round(wert, 4), herkunft])
            quellenprotokoll[ebene][ind["id"]] = {"herkunft": herkunft, **(info or {})}
            protokoll.append(f"{ebene:<9} {ind['id']:<11} {len(werte):>5} Werte  {herkunft}")

    if not nur_demo:
        genesis_katalog_schreiben()
    print("\n".join(protokoll))
    if not nur_demo and echte_werte == 0:
        print("\nFEHLER: Keine Quelle hat echte Daten geliefert. Bisherige Daten bleiben unverändert.")
        sys.exit(1)

    with (DATEN / "rohdaten.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(["ebene", "ags", "jahr", "indikator", "wert", "herkunft"])
        w.writerows(zeilen)
    (DATEN / "quellenprotokoll.json").write_text(
        json.dumps(quellenprotokoll, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(zeilen)} Zeilen geschrieben nach daten/rohdaten.csv")


if __name__ == "__main__":
    main()
