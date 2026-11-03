"""Auswertung von GENESIS-Flat-File-CSV (format=ffcsv)."""
from __future__ import annotations

import re


def _zahl(text: str):
    text = (text or "").strip()
    if text in ("", "-", ".", "...", "x", "/", "–"):
        return None
    try:
        return float(text.replace(".", "").replace(",", ".")) if "," in text else float(text)
    except ValueError:
        return None


def _ags_normalisieren(code: str, ebene: str) -> str | None:
    code = re.sub(r"\D", "", code or "")
    if ebene == "kreis" and len(code) >= 5:
        return code[:5]
    if ebene == "gemeinde" and len(code) == 8:
        return code
    if ebene == "gemeinde" and len(code) == 9:      # mit Gemeindeverbandsziffer
        return code[:5] + code[6:]
    return None


def ffcsv_auswerten(zeilen: list[dict], spec: dict, ebene: str, praefix: str) -> dict[tuple[str, int], float]:
    """Holt aus einer Flat-File-CSV die Werte {(ags, jahr): wert}."""
    if not zeilen:
        return {}
    spalten = list(zeilen[0].keys())
    wertspalten = [s for s in spalten if spec["wert_spalte"].lower() in s.lower()
                   and not s.endswith(("_Code", "_Label"))]
    if not wertspalten:
        raise ValueError(f"Keine Wertspalte mit '{spec['wert_spalte']}'. Spalten: {spalten}")
    wertspalte = wertspalten[0]

    # Merkmalsnummern (1_, 2_, …) ermitteln
    nummern = sorted({s.split("_")[0] for s in spalten if s.endswith("_Merkmal_Label")})
    region_nr = None
    for n in nummern:
        codes = [z.get(f"{n}_Auspraegung_Code", "") for z in zeilen[:50]]
        if any(re.sub(r"\D", "", c).startswith(praefix) for c in codes):
            region_nr = n
            break
    if region_nr is None:
        raise ValueError("Keine Spalte mit Regionalschlüsseln gefunden.")

    filter_ = spec.get("filter") or {}
    ergebnis: dict[tuple[str, int], float] = {}
    for z in zeilen:
        ags = _ags_normalisieren(z.get(f"{region_nr}_Auspraegung_Code", ""), ebene)
        if not ags or not ags.startswith(praefix):
            continue
        # Filter und "Insgesamt"-Logik für alle übrigen Merkmale
        passt = True
        for n in nummern:
            if n == region_nr:
                continue
            merkmal = z.get(f"{n}_Merkmal_Label", "")
            auspraegung = z.get(f"{n}_Auspraegung_Label", "")
            vorgabe = next((v for k, v in filter_.items() if k.lower() in merkmal.lower()), None)
            if vorgabe is not None:
                passt &= auspraegung == vorgabe
            else:
                passt &= auspraegung in ("", "Insgesamt")
        if not passt:
            continue
        jahr_text = z.get("Zeit") or z.get("Zeit_Label") or ""
        m = re.search(r"(19|20)\d\d", jahr_text)
        wert = _zahl(z.get(wertspalte))
        if m and wert is not None:
            ergebnis[(ags, int(m.group(0)))] = wert
    return ergebnis
