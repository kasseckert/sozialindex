"""
Erkundet den Aufbau von GENESIS-Tabellen, bevor sie als Indikator eingerichtet
werden: Untergliederungen (Merkmale und ihre Ausprägungen), Wertspalten mit
Einheit, vorhandene Jahre, Zahl der Kreise und ein Beispiel.

Welche Tabellen erkundet werden, steht in konfiguration/erkunden.json:
    {"tabellen": [{"datenbank": "bildung", "tabelle": "BY-D07.1i"}, ...]}

Ergebnis: daten/genesis_struktur.md (lesbar) und daten/genesis_struktur.json.
Läuft im Workflow nach dem Datenabruf; Fehler einzelner Tabellen werden im
Bericht vermerkt und brechen nichts ab.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import konfiguration as K
from genesis import GenesisFehler, suche_tabellen, tabelle_stueckweise
from genesis_auswerten import normalisieren

WURZEL = Path(__file__).resolve().parent.parent
LISTE = WURZEL / "konfiguration" / "erkunden.json"
ZIEL_MD = WURZEL / "daten" / "genesis_struktur.md"
ZIEL_JSON = WURZEL / "daten" / "genesis_struktur.json"


def abrufen(db: str, code: str):
    """
    Tabelle für die Kreise abrufen; probiert gängige Regionalvariablen und zuletzt
    die Standardauswahl der Tabelle (zeigt dann, wie die Regionalvariable dort heißt).
    """
    fehler = []
    for rv in ("KREISE", "KRS", "KREIS", None):
        try:
            roh = tabelle_stueckweise(db, code, min(K.JAHRE) - 5, max(K.JAHRE) + 1, rv,
                                      K.REGIERUNGSBEZIRK_PRAEFIX + "*" if rv else None)
            return roh, rv, fehler
        except GenesisFehler as e:
            fehler.append(f"{rv or 'Standard'}: {str(e)[:220]}")
    return None, None, fehler


def titel(db: str, code: str) -> str:
    try:
        treffer = suche_tabellen(db, code, 5)
        return next((t.get("Content", "") for t in treffer if t.get("Code") == code), "")
    except Exception:
        return ""


def beschreiben(db: str, code: str) -> dict:
    roh, rv, fehler = abrufen(db, code)
    info = {"datenbank": db, "tabelle": code, "titel": re.sub(r"\s+", " ", titel(db, code)), "regionalvariable": rv, "fehler": fehler}
    if not roh:
        return info
    # Rohdaten für die Nachprüfung: Spalten, erste Zeilen, vorkommende Werte je Textspalte
    info["roh_spalten"] = list(dict.fromkeys(k for z in roh for k in z))
    info["roh_beispiel"] = roh[:8]
    info["roh_werte"] = {k: list(Counter(z.get(k, "") for z in roh))[:60]
                         for k in info["roh_spalten"] if k not in ("value",) and not k.endswith("attribute_code")}
    zeilen = normalisieren(roh)
    spalten = list(dict.fromkeys(k for z in zeilen for k in z))
    nummern = sorted({s.split("_")[0] for s in spalten if s.endswith("_Merkmal_Label")}, key=int)
    merkmale = []
    region_nr = None
    for n in nummern:
        label = zeilen[0].get(f"{n}_Merkmal_Label", "")
        codes = [z.get(f"{n}_Auspraegung_Code", "") for z in zeilen]
        if region_nr is None and any(re.sub(r"\D", "", c).startswith(K.REGIERUNGSBEZIRK_PRAEFIX) for c in codes[:200]):
            region_nr = n
            merkmale.append({"nr": n, "merkmal": label, "rolle": "Region",
                             "anzahl_kreise": len({re.sub(r"\D", "", c)[:5] for c in codes if re.sub(r"\D", "", c).startswith(K.REGIERUNGSBEZIRK_PRAEFIX)})})
            continue
        auspr = Counter(z.get(f"{n}_Auspraegung_Label", "") for z in zeilen)
        merkmale.append({"nr": n, "merkmal": label, "auspraegungen": list(auspr)[:40], "anzahl": len(auspr)})
    wertspalten = [c for c in spalten if "__" in c and not c.endswith(("_Code", "_Label"))]
    belegung = {w: sum(1 for z in zeilen if z.get(w) not in (None, "", "-", ".", "x")) for w in wertspalten}
    jahre = sorted({m.group(0) for z in zeilen for m in [re.search(r"(19|20)\d\d", z.get("Zeit", "") or "")] if m})
    beispiel = [z for z in zeilen if re.sub(r"\D", "", z.get(f"{region_nr}_Auspraegung_Code", ""))[:5] == "09461"][:6] if region_nr else zeilen[:6]
    info.update({
        "zeilen": len(zeilen), "jahre": jahre, "merkmale": merkmale, "wertspalten": wertspalten, "belegung": belegung,
        "spalten": spalten,
        "beispiel": [{k: v for k, v in z.items() if k == "Zeit" or k.endswith("_Auspraegung_Label") or (k in wertspalten and v not in (None, ""))} for z in beispiel],
    })
    return info


def markdown(ergebnisse: list[dict]) -> str:
    t = ["# Aufbau erkundeter GENESIS-Tabellen", ""]
    for e in ergebnisse:
        t += [f"## {e['tabelle']} ({e['datenbank']})", "", f"**Titel:** {e['titel'] or 'unbekannt'}", ""]
        if not e.get("zeilen"):
            t += ["**Abruf fehlgeschlagen:**", *[f"- {f}" for f in e["fehler"]], ""]
            continue
        t += [f"Regionalvariable: `{e['regionalvariable']}` · Zeilen: {e['zeilen']} · Jahre: {', '.join(e['jahre'])}", ""]
        for m in e["merkmale"]:
            if m.get("rolle") == "Region":
                t.append(f"- Merkmal {m['nr']}: **{m['merkmal']}** (Region, {m['anzahl_kreise']} Kreise)")
            else:
                t.append(f"- Merkmal {m['nr']}: **{m['merkmal']}** ({m['anzahl']} Ausprägungen): " + "; ".join(m["auspraegungen"]))
        t += ["", "Wertspalten (mit Zahl belegter Zeilen):", *[f"- `{w}` ({e.get('belegung', {}).get(w, '?')})" for w in e["wertspalten"]], "", "Beispiel Bamberg (Stadt):", "", "```",
              *[json.dumps(b, ensure_ascii=False) for b in e["beispiel"]], "```", ""]
    return "\n".join(t)


def main():
    if not LISTE.exists():
        print("Keine Tabellen zum Erkunden (konfiguration/erkunden.json fehlt).")
        return
    tabellen = json.loads(LISTE.read_text(encoding="utf-8")).get("tabellen", [])
    ergebnisse = []
    for t in tabellen:
        try:
            ergebnisse.append(beschreiben(t["datenbank"], t["tabelle"]))
        except Exception as e:      # eine fehlerhafte Tabelle soll die anderen nicht verhindern
            ergebnisse.append({"datenbank": t["datenbank"], "tabelle": t["tabelle"], "titel": "", "fehler": [str(e)[:300]]})
        print(f"{t['tabelle']}: {'ok' if ergebnisse[-1].get('zeilen') else 'Fehler'}")
    ZIEL_JSON.write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=1), encoding="utf-8")
    ZIEL_MD.write_text(markdown(ergebnisse), encoding="utf-8")


if __name__ == "__main__":
    main()
