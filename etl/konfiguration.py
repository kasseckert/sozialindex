"""
Lädt die Konfiguration aus konfiguration/indikatoren.json.

Die JSON-Datei lässt sich im Datenassistenten (web/assistent.html) bequem
im Browser bearbeiten oder direkt im Editor bzw. im GitHub-Webeditor.

Felder je Indikator
-------------------
id, name, einheit, nachkommastellen, beschreibung
dimension     eine der Dimensions-IDs
polaritaet    +1 = hoher Wert günstig, -1 = hoher Wert ungünstig
ebenen        gewünschte Ebenen ("kreis", "gemeinde")
quellen       Liste, wird der Reihe nach versucht; die erste mit Daten gewinnt:
  {"typ": "regionalatlas", "code": "AI003-3", "feld": "ai0306"}      fest
  {"typ": "regionalatlas", "suche": [...], "feld_suche": [...]}      automatisch
     optional "berechnung": "veraenderung", "jahre": 5
  {"typ": "csv", "datei": "name.csv"}    Datei in daten/import/ (ags;jahr;wert)
  {"typ": "genesis", ...}                siehe etl/genesis.py
"""
import json
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
_K = json.loads((WURZEL / "konfiguration" / "indikatoren.json").read_text(encoding="utf-8"))

REGIERUNGSBEZIRK_PRAEFIX = _K.get("praefix", "094")          # Oberfranken
JAHRE = list(range(_K["jahre"][0], _K["jahre"][1] + 1))
DIMENSIONEN = _K["dimensionen"]
INDIKATOREN = _K["indikatoren"]
GEWICHTE = _K.get("gewichte") or {d["id"]: 1 for d in DIMENSIONEN}
# Fehlen bei einem Indikator die jüngsten Jahre (Veröffentlichungsverzug), wird
# der letzte verfügbare Wert für höchstens so viele Jahre fortgeschrieben und in
# der Karte gekennzeichnet. 0 schaltet das ab; je Indikator mit "fortschreiben".
FORTSCHREIBEN_JAHRE = int(_K.get("fortschreiben_jahre", 2))
INDEX_MITTE = 100
INDEX_STREUUNG = 10

# Plausibilitätsprüfung: Mindestanteil der Gebiete mit Werten im letzten Jahr,
# damit ein Indikator auf einer Ebene verwendet wird.
MINDEST_ABDECKUNG = 0.8
