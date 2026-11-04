"""
Erzeugt plausible, aber FIKTIVE Werte für alle Indikatoren.

Die Demodaten dienen nur dazu, Karte und Diagramme zu testen, solange noch
nicht alle Quellen angebunden sind. Sie sind reproduzierbar (fester Zufalls-
Startwert je Gebiet) und werden in der Ausgabe als "demo" gekennzeichnet.
Für Veröffentlichungen dürfen sie nicht verwendet werden.
"""
from __future__ import annotations

import hashlib
import random

# Ausgangswerte je Kreis für das letzte Jahr (fiktiv, grob an typischen
# Größenordnungen orientiert). Reihenfolge wie SPALTEN.
SPALTEN = ["alq", "sgb2", "eink", "alt65", "bev5", "wand", "u3", "ohneabschl", "wfl", "arzt"]
KREIS_BASIS = {
    "09461": [3.9, 6.5, 23500, 21.0, 2.0, 9.0, 33, 7.5, 47, 7.8],   # Bamberg, Stadt
    "09462": [4.4, 7.4, 23000, 22.5, 1.0, 8.0, 32, 7.0, 46, 7.5],   # Bayreuth, Stadt
    "09463": [5.0, 8.6, 25500, 24.5, -0.5, 7.0, 30, 8.0, 48, 7.2],  # Coburg, Stadt
    "09464": [6.6, 12.0, 21500, 26.0, 0.5, 10.0, 28, 9.5, 45, 6.8], # Hof, Stadt
    "09471": [1.9, 2.6, 25500, 21.5, 2.5, 7.0, 28, 4.5, 52, 5.6],   # Lkr. Bamberg
    "09472": [2.0, 2.8, 25000, 23.5, 0.5, 5.0, 30, 5.0, 53, 5.5],   # Lkr. Bayreuth
    "09473": [2.3, 3.5, 25000, 25.0, -0.5, 4.0, 29, 5.5, 54, 5.8],  # Lkr. Coburg
    "09474": [1.9, 2.4, 26500, 21.0, 3.0, 8.0, 27, 4.0, 51, 5.9],   # Forchheim
    "09475": [2.9, 4.6, 23500, 27.5, -2.5, 4.0, 31, 6.0, 55, 5.4],  # Lkr. Hof
    "09476": [2.8, 4.2, 23500, 27.0, -3.5, 2.0, 29, 6.5, 54, 5.2],  # Kronach
    "09477": [2.7, 4.0, 24000, 25.5, -1.5, 4.0, 30, 6.0, 53, 5.6],  # Kulmbach
    "09478": [2.6, 3.9, 24000, 25.0, -0.5, 5.0, 28, 6.0, 52, 5.5],  # Lichtenfels
    "09479": [3.4, 6.0, 22800, 29.0, -2.0, 6.0, 31, 7.0, 56, 5.3],  # Wunsiedel
}

# Streuung der Gemeinden um ihren Kreiswert
GEMEINDE_STREUUNG = {"alq": 0.7, "sgb2": 1.2, "eink": 900, "alt65": 2.2, "bev5": 2.5, "wand": 5, "u3": 6, "wfl": 4}
# Städte innerhalb der Landkreise: etwas städtischeres Profil
STADT_ZUSCHLAG = {"alq": 0.6, "sgb2": 1.0, "eink": -400, "alt65": 0.8, "bev5": 0.3, "wand": 1.5, "u3": 3, "wfl": -3}


def _zufall(*schluessel) -> random.Random:
    h = hashlib.sha256("|".join(map(str, schluessel)).encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def _verlauf(ind: str, endwert: float, jahr: int, endjahr: int, r: random.Random) -> float:
    """Rechnet einen Endwert plausibel in frühere Jahre zurück."""
    t = endjahr - jahr  # Jahre vor dem Endjahr
    rausch = r.gauss(0, 1)
    if ind == "alq":
        corona = 0.5 if jahr in (2020, 2021) else 0
        return max(0.5, endwert + 0.09 * t + corona + 0.08 * rausch)
    if ind == "sgb2":
        return max(0.5, endwert + 0.18 * t + 0.1 * rausch)
    if ind == "eink":
        return endwert / (1.028 ** t) + 120 * rausch
    if ind == "alt65":
        return endwert - 0.28 * t + 0.05 * rausch
    if ind == "bev5":
        return endwert - 0.15 * t + 0.25 * rausch
    if ind == "wand":
        spitze = {2015: 6, 2016: 3, 2022: 7}.get(jahr, 0)
        return endwert + spitze + 1.2 * rausch
    if ind == "u3":
        return max(5, endwert - 1.1 * t + 0.6 * rausch)
    if ind == "ohneabschl":
        return max(1, endwert - 0.1 * t + 0.4 * rausch)
    if ind == "wfl":
        return endwert - 0.35 * t + 0.1 * rausch
    if ind == "arzt":
        return endwert + 0.06 * t + 0.08 * rausch
    return endwert


def _basis(kreis: str) -> list[float]:
    """Ausgangswerte eines Kreises: Oberfranken fest, übrige Kreise fiktiv erzeugt."""
    if kreis in KREIS_BASIS:
        return KREIS_BASIS[kreis]
    stadt = int(kreis[3:5]) < 70          # kreisfreie Städte haben Kreisnummern unter 70
    vorlage = [v for k, v in KREIS_BASIS.items() if (int(k[3:5]) < 70) == stadt]
    mittel = [sum(x) / len(x) for x in zip(*vorlage)]
    r = _zufall("basis", kreis)
    sued = kreis[:3] in ("091", "097")    # Oberbayern, Schwaben: im Mittel günstigere Lage (fiktiv)
    faktor = {"alq": 0.75, "sgb2": 0.75, "eink": 1.1, "bev5": 1.0, "wand": 1.0}
    ergebnis = []
    for name, m in zip(SPALTEN, mittel):
        w = m * (faktor.get(name, 1) if sued else 1)
        streu = abs(m) * 0.15 if name not in ("bev5", "wand") else 2.0
        ergebnis.append(w + r.gauss(0, streu))
    return ergebnis


def werte(ind: str, ebene: str, gebiete: list[dict], jahre: list[int]) -> dict[tuple[str, int], float]:
    """Liefert {(ags, jahr): wert} für einen Indikator auf einer Ebene."""
    if ind not in SPALTEN:
        return {}
    spalte = SPALTEN.index(ind)
    endjahr = max(jahre)
    out = {}
    for g in gebiete:
        ags = g["ags"]
        kreis = ags[:5]
        basis = _basis(kreis)[spalte]
        if ebene == "gemeinde":
            if ind not in GEMEINDE_STREUUNG:
                continue
        if ebene == "gemeinde" and not ags.endswith("000"):   # nicht kreisfrei
            r0 = _zufall("g", ags, ind)
            basis = basis + r0.gauss(0, GEMEINDE_STREUUNG[ind])
            if g.get("bez") == "Stadt":
                basis += STADT_ZUSCHLAG.get(ind, 0)
        for j in jahre:
            kreisfrei = ebene == "kreis" or ags.endswith("000")
            r = _zufall("kreis", kreis, ind, j) if kreisfrei else _zufall(ebene, ags, ind, j)
            out[(ags, j)] = _verlauf(ind, basis, j, endjahr, r)
    return out
