"""
Schritt 2: Sozialindex berechnen und die Webdaten schreiben.

Methode (je Ebene getrennt: Kreise und Gemeinden)
--------------------------------------------------
1. Jeder Indikator wird über alle Gebiete und Jahre der Ebene standardisiert
   (z-Wert), damit Indikatoren mit unterschiedlichen Einheiten vergleichbar
   werden.
2. Die z-Werte werden mit der Polarität multipliziert, sodass ein höherer
   Wert immer eine günstigere Lage bedeutet.
3. Dimensionswert = Mittel der z-Werte der Indikatoren dieser Dimension.
4. Gesamtindex = gewichtetes Mittel der Dimensionswerte.
5. Dimensionen und Gesamtindex werden je Jahr erneut standardisiert und auf
   die Skala 100 ± 10 gebracht: 100 = Durchschnitt der oberfränkischen Kreise
   bzw. Gemeinden in diesem Jahr, 110 = eine Standardabweichung günstiger,
   90 = eine Standardabweichung ungünstiger. Der Index beschreibt also die
   relative Lage innerhalb Oberfrankens; absolute Entwicklungen zeigen die
   Zeitreihen der einzelnen Indikatoren.

Gemeinden werden nur mit Indikatoren bewertet, die auf Gemeindeebene vorliegen.
Kreiswerte weiterer Indikatoren werden im Popup als Kontext angezeigt.

Ergebnis: web/data/werte.json
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

import konfiguration as K

WURZEL = Path(__file__).resolve().parent.parent
ROH = WURZEL / "daten" / "rohdaten.csv"
ZIEL = WURZEL / "web" / "data" / "werte.json"

IND = {i["id"]: i for i in K.INDIKATOREN}


def lade_roh():
    daten = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))  # ebene→ags→ind→jahr
    herkunft = defaultdict(dict)
    with ROH.open(encoding="utf-8") as f:
        for z in csv.DictReader(f, delimiter=";"):
            daten[z["ebene"]][z["ags"]][z["indikator"]][int(z["jahr"])] = float(z["wert"])
            herkunft[z["ebene"]][z["indikator"]] = z["herkunft"]
    return daten, herkunft


def fortschreiben(daten):
    """
    Schreibt den letzten verfügbaren Wert eines Indikators für höchstens
    K.FORTSCHREIBEN_JAHRE Jahre fort, wenn die jüngsten Jahre noch nicht
    veröffentlicht sind. Gibt {ebene: {ags: {ind: [jahre]}}} der ergänzten Werte zurück.
    """
    markiert = defaultdict(lambda: defaultdict(dict))
    letztes_jahr = max(K.JAHRE)
    for ebene, gebiete in daten.items():
        for ags, inds in gebiete.items():
            for ind_id, reihe in inds.items():
                ind = IND.get(ind_id, {})
                n = int(ind.get("fortschreiben", K.FORTSCHREIBEN_JAHRE))
                if n <= 0 or not reihe or ind.get("zeitlich_konstant"):
                    continue
                zuletzt = max(reihe)
                ergaenzt = [j for j in range(zuletzt + 1, min(zuletzt + n, letztes_jahr) + 1) if j not in reihe]
                for j in ergaenzt:
                    reihe[j] = reihe[zuletzt]
                if ergaenzt:
                    markiert[ebene][ags][ind_id] = {"jahre": [str(j) for j in ergaenzt], "aus": str(zuletzt)}
    return markiert


def lade_namen():
    namen = {}
    for ebene, datei in (("kreis", "kreise.geojson"), ("gemeinde", "gemeinden.geojson")):
        fc = json.loads((WURZEL / "web" / "data" / datei).read_text(encoding="utf-8"))
        namen[ebene] = {f["properties"]["ags"]: f["properties"] for f in fc["features"]}
    return namen


def mittel_sd(werte):
    werte = [w for w in werte if w is not None]
    if len(werte) < 2:
        return None, None
    sd = statistics.pstdev(werte)
    return statistics.fmean(werte), (sd or 1.0)


def standardisieren(tabelle):
    """
    tabelle: {ags: {jahr: x}} → gleiche Struktur auf Skala 100 ± 10,
    jahresweise: 100 = Durchschnitt aller Gebiete der Ebene im jeweiligen Jahr.
    """
    out = defaultdict(dict)
    for j in K.JAHRE:
        m, sd = mittel_sd([reihe[j] for reihe in tabelle.values() if j in reihe])
        if m is None:
            continue
        for a, reihe in tabelle.items():
            if j in reihe:
                out[a][j] = K.INDEX_MITTE + K.INDEX_STREUUNG * (reihe[j] - m) / sd
    return dict(out)


def berechne_ebene(ebene, daten, markiert=None):
    gebiete = daten[ebene]
    # nur Indikatoren, für die auf dieser Ebene tatsächlich Daten vorliegen
    inds = [i for i in K.INDIKATOREN if any(i["id"] in g for g in gebiete.values())]

    # 1–2: polaritätsbereinigte z-Werte
    statistik, z = {}, defaultdict(lambda: defaultdict(dict))
    for i in inds:
        alle = [w for g in gebiete.values() for w in g.get(i["id"], {}).values()]
        m, sd = mittel_sd(alle)
        if m is None:
            continue
        statistik[i["id"]] = {"mittel": round(m, 4), "sd": round(sd, 4)}
        for ags, g in gebiete.items():
            for j, w in g.get(i["id"], {}).items():
                z[ags][i["id"]][j] = i["polaritaet"] * (w - m) / sd

    # 3: Dimensionen
    dim_roh = {d["id"]: defaultdict(dict) for d in K.DIMENSIONEN}
    for ags in gebiete:
        for d in K.DIMENSIONEN:
            ids = [i["id"] for i in inds if i["dimension"] == d["id"] and i["id"] in statistik]
            for j in K.JAHRE:
                vals = [z[ags][i][j] for i in ids if j in z[ags][i]]
                if vals:
                    dim_roh[d["id"]][ags][j] = statistics.fmean(vals)

    # 4: Gesamtindex (wenn mindestens die Hälfte der auf dieser Ebene
    #    verfügbaren Dimensionen für das Gebiet vorliegt)
    verfuegbare_dims = [d for d in dim_roh if dim_roh[d]]
    gesamt_roh = defaultdict(dict)
    for ags in gebiete:
        for j in K.JAHRE:
            teile = [(K.GEWICHTE.get(d, 1), dim_roh[d][ags][j]) for d in dim_roh if j in dim_roh[d].get(ags, {})]
            if teile and len(teile) * 2 >= len(verfuegbare_dims):
                gew = sum(g for g, _ in teile)
                gesamt_roh[ags][j] = sum(g * x for g, x in teile) / gew

    # 5: auf 100 ± 10 skalieren
    dims = {d: standardisieren(dict(t)) for d, t in dim_roh.items()}
    gesamt = standardisieren(dict(gesamt_roh))

    # Ränge je Jahr (1 = günstigste Lage)
    raenge = defaultdict(dict)
    for j in K.JAHRE:
        liste = sorted(((gesamt[a][j], a) for a in gesamt if j in gesamt[a]), reverse=True)
        for pos, (_, a) in enumerate(liste, 1):
            raenge[a][j] = pos

    # Oberfranken-Mittel je Indikator und Jahr (ungewichtetes Gebietsmittel)
    referenz = {}
    for i in inds:
        referenz[i["id"]] = {}
        for j in K.JAHRE:
            vals = [g[i["id"]][j] for g in gebiete.values() if j in g.get(i["id"], {})]
            if vals:
                referenz[i["id"]][j] = round(statistics.fmean(vals), 3)

    r1 = lambda reihe: {str(j): round(x, 1) for j, x in sorted(reihe.items())}
    r3 = lambda reihe: {str(j): round(x, 3) for j, x in sorted(reihe.items())}
    gebiete_out = {}
    for ags, g in gebiete.items():
        gebiete_out[ags] = {
            "werte": {i: r3(reihe) for i, reihe in g.items()},
            "dimensionen": {d: r1(dims[d][ags]) for d in dims if ags in dims[d]},
            "index": r1(gesamt.get(ags, {})),
            "rang": {str(j): r for j, r in sorted(raenge[ags].items())},
            **({"fortgeschrieben": markiert[ags]} if markiert and markiert.get(ags) else {}),
        }
    return {
        "indikatoren": [i["id"] for i in inds],
        "dimensionen": [d for d in verfuegbare_dims],
        "statistik": statistik,
        "referenz": {i: {str(j): v for j, v in r.items()} for i, r in referenz.items()},
        "anzahl": len(gebiete_out),
        "gebiete": gebiete_out,
    }


def main():
    daten, herkunft = lade_roh()
    markiert = fortschreiben(daten)
    namen = lade_namen()
    protokoll_datei = WURZEL / "daten" / "quellenprotokoll.json"
    quellen = json.loads(protokoll_datei.read_text(encoding="utf-8")) if protokoll_datei.exists() else {}
    ausgabe = {
        "meta": {
            "titel": "Sozialindex Oberfranken",
            "erstellt": date.today().isoformat(),
            "jahre": K.JAHRE,
            "index_mitte": K.INDEX_MITTE,
            "index_streuung": K.INDEX_STREUUNG,
            "demo": any(h == "demo" for e in herkunft.values() for h in e.values()),
            "herkunft": herkunft,
            "dimensionen": K.DIMENSIONEN,
            "gewichte": K.GEWICHTE,
            "fortschreiben_jahre": K.FORTSCHREIBEN_JAHRE,
            "indikatoren": [{k: v for k, v in i.items() if k not in ("quelle", "quellen")} for i in K.INDIKATOREN],
            "quellen": quellen,
        },
    }
    for ebene in ("kreis", "gemeinde"):
        ausgabe[ebene] = berechne_ebene(ebene, daten, markiert.get(ebene))
        fehlend = set(namen[ebene]) - set(ausgabe[ebene]["gebiete"])
        fehlend = [a for a in fehlend if namen[ebene][a].get("bez") != "Gemeindefreies Gebiet"]
        if fehlend:
            print(f"Hinweis: {len(fehlend)} Gebiete der Ebene {ebene} ohne Daten: {sorted(fehlend)[:5]} …")

    ZIEL.write_text(json.dumps(ausgabe, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # Kopie der Konfiguration für den Datenassistenten
    (ZIEL.parent / "indikatoren.json").write_text(
        (WURZEL / "konfiguration" / "indikatoren.json").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Geschrieben: {ZIEL.relative_to(WURZEL)} ({ZIEL.stat().st_size / 1024:.0f} KB)")
    for ebene in ("kreis", "gemeinde"):
        g = ausgabe[ebene]["gebiete"]
        letzt = str(max(K.JAHRE))
        top = sorted(g, key=lambda a: -g[a]["index"].get(letzt, 0))
        print(f"{ebene}: günstigste {[namen[ebene][a]['name'] for a in top[:3]]}, "
              f"ungünstigste {[namen[ebene][a]['name'] for a in top[-3:]]}")


if __name__ == "__main__":
    main()
