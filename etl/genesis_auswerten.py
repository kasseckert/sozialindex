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


def normalisieren(zeilen: list[dict]) -> list[dict]:
    """
    Bringt beide Flat-File-Formate auf eine Form.

    Älteres Format: Zeit; 1_Merkmal_Label; 1_Auspraegung_Code; …; CODE__Bezeichnung__Einheit (je Wert eine Spalte)
    Neueres Format (u. a. Bildungsdatenbank, Zensus): time; 1_variable_label; 1_variable_attribute_code; …;
                    value; value_unit; value_variable_code; value_variable_label (je Wert eine Zeile)
    Ergebnis ist immer das ältere Format; im neueren wird jede Wertzeile zu einer Spalte
    „CODE__Bezeichnung__Einheit“.
    """
    if not zeilen or "value" not in zeilen[0]:
        return zeilen
    ergebnis = []
    for z in zeilen:
        d = {"Zeit": z.get("time") or z.get("time_label") or z.get("time_code") or ""}
        for k, v in z.items():
            m = re.match(r"(\d+)_variable_(label|attribute_code|attribute_label)$", k)
            if m:
                ziel = {"label": "Merkmal_Label", "attribute_code": "Auspraegung_Code",
                        "attribute_label": "Auspraegung_Label"}[m.group(2)]
                d[f"{m.group(1)}_{ziel}"] = v
        name = f"{z.get('value_variable_code', 'WERT')}__{z.get('value_variable_label', '')}__{z.get('value_unit', '')}"
        d[name] = z.get("value")
        ergebnis.append(d)
    return ergebnis


def ffcsv_auswerten(zeilen: list[dict], spec: dict, ebene: str, praefix: str) -> dict[tuple[str, int], float]:
    """Holt aus einer Flat-File-CSV die Werte {(ags, jahr): wert}."""
    zeilen = normalisieren(zeilen)
    if not zeilen:
        return {}
    spalten = list(dict.fromkeys(k for z in zeilen for k in z))   # alle Spalten aller Zeilen
    # Wertspalten der Flat-File-CSV enthalten "__" (Code__Bezeichnung__Einheit)
    kandidaten = [c for c in spalten if "__" in c and not c.endswith(("_Code", "_Label", "_q"))]
    muster = (spec.get("wert_spalte") or "").lower()
    wertspalten = [c for c in kandidaten if muster in c.lower()] if muster else kandidaten
    if not wertspalten:
        raise ValueError(f"Keine Wertspalte{' mit ' + repr(muster) if muster else ''}. Vorhanden: {kandidaten}")
    if len(wertspalten) > 1:
        # nicht raten: bei mehreren passenden Wertspalten muss die Konfiguration eindeutig sein
        raise ValueError(f"Wertspalte nicht eindeutig{' für ' + repr(muster) if muster else ''}: {wertspalten}")
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
    # Jeder Filter muss ein Merkmal der Tabelle treffen; ein ins Leere laufender Filter
    # würde sonst still übergangen und z. B. „Insgesamt“ statt der gewünschten Zeile liefern.
    merkmalnamen = {z.get(f"{n}_Merkmal_Label", "") for z in zeilen[:200] for n in nummern if n != region_nr}
    for schluessel in filter_:
        if not any(schluessel.lower() in m.lower() for m in merkmalnamen):
            raise ValueError(f"Filter „{schluessel}“ passt zu keinem Merkmal der Tabelle. Vorhanden: {sorted(merkmalnamen)}")
    ergebnis: dict[tuple[str, int], float] = {}
    zaehler = {"kreis": 0, "filter": 0, "jahr": 0, "wert": 0}
    for z in zeilen:
        ags = _ags_normalisieren(z.get(f"{region_nr}_Auspraegung_Code", ""), ebene)
        if not ags or not ags.startswith(praefix):
            continue
        zaehler["kreis"] += 1
        # Filter und "Insgesamt"-Logik für alle übrigen Merkmale
        passt = True
        for n in nummern:
            if n == region_nr:
                continue
            merkmal = z.get(f"{n}_Merkmal_Label", "")
            auspraegung = z.get(f"{n}_Auspraegung_Label", "")
            vorgabe = next((v for k, v in filter_.items() if k.lower() in merkmal.lower()), None)
            if vorgabe is not None:
                # mehrere zulässige Schreibweisen mit "|" getrennt, z. B. "Realschul|mittler";
                # ein vorangestelltes "=" verlangt Gleichheit statt Enthaltensein ("=Realschulen")
                passt &= any((auspraegung.strip().lower() == v.strip()[1:].strip().lower()) if v.strip().startswith("=")
                             else (v.strip().lower() in auspraegung.strip().lower()) for v in vorgabe.split("|"))
            else:
                passt &= auspraegung.strip().lower() in ("", "insgesamt")
        if not passt:
            continue
        zaehler["filter"] += 1
        jahr_text = z.get("Zeit") or z.get("Zeit_Label") or ""
        m = re.search(r"(19|20)\d\d", jahr_text)
        wert = _zahl(z.get(wertspalte))
        zaehler["jahr"] += bool(m)
        zaehler["wert"] += bool(m and wert is not None)
        if m and wert is not None:
            k = (ags, int(m.group(0)))
            if k in ergebnis and ergebnis[k] != wert:
                # zwei verschiedene Zeilen für denselben Kreis und dasselbe Jahr: Filter nicht eindeutig
                raise ValueError(f"Filter nicht eindeutig: {k[0]} {k[1]} hat mehrere passende Zeilen "
                                 f"({ergebnis[k]} und {wert}); bitte genauer filtern, z. B. mit „=“")
            ergebnis[k] = wert
    if not ergebnis:
        # nachvollziehbar machen, wo die Zeilen verloren gingen
        auspr = {}
        for n in nummern:
            if n == region_nr:
                continue
            werte_n = list(dict.fromkeys(z.get(f"{n}_Auspraegung_Label", "") for z in zeilen))
            auspr[zeilen[0].get(f"{n}_Merkmal_Label", n)] = werte_n[:12]
        codes = list(dict.fromkeys(z.get(f"{region_nr}_Auspraegung_Code", "") for z in zeilen))[:6]
        beleg = [z.get(wertspalte) for z in zeilen if z.get(wertspalte) not in (None, "")][:5]
        raise ValueError(f"Keine Werte aus {len(zeilen)} Zeilen: {zaehler['kreis']} mit Kreisschlüssel, "
                         f"{zaehler['filter']} passend zu Filtern/Insgesamt, {zaehler['wert']} mit Zahlwert. "
                         f"Gebietscodes z. B. {codes}; Wertbeispiele {beleg}; Ausprägungen {auspr}")
    return ergebnis
