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


def gebiete(ebene: str) -> list[dict]:
    datei = WEB_DATEN / ("kreise.geojson" if ebene == "kreis" else "gemeinden.geojson")
    fc = json.loads(datei.read_text(encoding="utf-8"))
    return [f["properties"] for f in fc["features"]
            if f["properties"].get("bez") != "Gemeindefreies Gebiet"]


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
    return werte, f"csv:{spec['datei']}", {"quelle": f"Eigene Datei {spec['datei']}"}


def quelle_genesis(spec: dict, ebene: str):
    if not spec.get("tabelle"):
        return None
    from genesis import tabelle_ffcsv
    from genesis_auswerten import ffcsv_auswerten
    zeilen = tabelle_ffcsv(spec["datenbank"], spec["tabelle"], min(K.JAHRE), max(K.JAHRE),
                           spec.get("regionalvariable", {"kreis": "KREISE", "gemeinde": "GEMEIN"}[ebene]),
                           K.REGIERUNGSBEZIRK_PRAEFIX + "*")
    werte = ffcsv_auswerten(zeilen, spec, ebene, K.REGIERUNGSBEZIRK_PRAEFIX)
    return werte, f"genesis:{spec['tabelle']}", {"quelle": f"GENESIS {spec['datenbank']}", "code": spec["tabelle"]}


QUELLEN = {"regionalatlas": quelle_regionalatlas, "csv": quelle_csv, "genesis": quelle_genesis}


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
