"""Gebietsgliederung aus konfiguration/gebiete.json: Region je Kreis."""
import json
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
G = json.loads((WURZEL / "konfiguration" / "gebiete.json").read_text(encoding="utf-8"))
LAND = G["land"]
REGIONEN = G["regionen"]


def region_von(ags: str) -> str | None:
    """Region-ID für einen Kreis- oder Gemeindeschlüssel."""
    kreis = str(ags)[:5]
    for r in REGIONEN:
        if kreis in r.get("kreise", []):
            return r["id"]
    for r in REGIONEN:
        if r.get("praefix") and kreis.startswith(r["praefix"]) and not any(
                kreis in x.get("kreise", []) for x in REGIONEN):
            return r["id"]
    return None
