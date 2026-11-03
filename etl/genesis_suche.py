"""
Findet Tabellencodes in einer GENESIS-Datenbank.

Beispiele:
    python etl/genesis_suche.py bayern "Arbeitslose"
    python etl/genesis_suche.py regio "Betreuungsquote"
    python etl/genesis_suche.py bayern 12411-*      (Katalogsuche mit Platzhalter)
"""
import sys

from genesis import suche_tabellen, suche_volltext, GenesisFehler


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    datenbank, begriff = sys.argv[1], " ".join(sys.argv[2:])
    try:
        if "*" in begriff:
            treffer = suche_tabellen(datenbank, begriff)
        else:
            treffer = suche_volltext(datenbank, begriff)
    except GenesisFehler as e:
        print(f"Fehler: {e}")
        sys.exit(2)
    if not treffer:
        print("Keine Tabellen gefunden.")
        return
    for t in treffer:
        print(f"{t.get('Code', ''):<20} {t.get('Content', '')[:110]}")


if __name__ == "__main__":
    main()
