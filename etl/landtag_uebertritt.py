"""
Übertrittsquoten und Eignungen aus der jährlichen Landtagsdrucksache
„Übertrittsquoten in Bayern“ lesen und in daten/import/ übernehmen.

Aufruf
  python etl/landtag_uebertritt.py --drucksache 19/7981   bestimmte Drucksache
  python etl/landtag_uebertritt.py --suchen               neue Drucksache suchen (bestmöglich)
  python etl/landtag_uebertritt.py --datei antwort.pdf    lokale PDF-Datei
  Zusatz --pruefen: nur lesen und prüfen, nichts schreiben

Der Lauf schreibt einen Prüfbericht nach daten/uebertritt_bericht.md. Werte
werden nur übernommen, wenn alle harten Prüfungen bestehen (13 Kreise je
Tabelle, Werte zwischen 0 und 100, Spaltenreihenfolge eindeutig erkannt).
Auffällige Sprünge gegenüber dem Vorjahr werden im Bericht markiert.

Exit-Code: 0 = neue Werte übernommen, 3 = nichts Neues gefunden, 1 = Fehler.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
IMPORT = WURZEL / "daten" / "import"
BERICHT = WURZEL / "daten" / "uebertritt_bericht.md"
BASIS = "https://www.bayern.landtag.de/www/ElanTextAblage_WP{wp}/Drucksachen/Schriftliche%20Anfragen/{wp}_{nr:07d}.pdf"
SUCHSEITE = "https://www.bayern.landtag.de/parlament/dokumente/drucksachen"

KREISE = {  # (Name in der Drucksache, kreisfreie Stadt?) -> AGS
    ("bamberg", True): "09461", ("bayreuth", True): "09462", ("coburg", True): "09463", ("hof", True): "09464",
    ("bamberg", False): "09471", ("bayreuth", False): "09472", ("coburg", False): "09473",
    ("forchheim", False): "09474", ("hof", False): "09475", ("kronach", False): "09476",
    ("kulmbach", False): "09477", ("lichtenfels", False): "09478", ("wunsiedel", False): "09479",
}
ZAHL = r"(\d{1,3},\d)\s*%?"
ZEILE = re.compile(r"Oberfranken\s+([A-Za-zÄÖÜäöüß][^\d\n]*?)\s+" + r"\s+".join([ZAHL] * 4))


class Lesefehler(RuntimeError):
    pass


# ------------------------------------------------------------------- Lesen
def pdf_text(inhalt: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(inhalt)) as pdf:
        return "\n".join((s.extract_text() or "") for s in pdf.pages)


def url_fuer(drucksache: str) -> str:
    m = re.fullmatch(r"\s*(\d{2})\s*/\s*(\d{1,7})\s*", drucksache)
    if not m:
        raise Lesefehler(f"Drucksachennummer '{drucksache}' nicht erkannt; erwartet z. B. 19/7981")
    return BASIS.format(wp=int(m.group(1)), nr=int(m.group(2)))


def herunterladen(url: str) -> bytes:
    import requests
    r = requests.get(url, timeout=60, headers={"User-Agent": "sozialindex-oberfranken"})
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        raise Lesefehler(f"{url}: keine PDF erhalten (HTTP {r.status_code})")
    return r.content


def _normalisieren(text: str) -> str:
    text = text.replace("Prozent", "%").replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", text)


def _reihenfolge_uebertritt(vorspann: str) -> bool:
    """True, wenn Gymnasium zuerst steht; Fehler, wenn nicht erkennbar."""
    kurz = re.sub(r"\s+", " ", vorspann)
    treffer = [(m.start(), m.group(1)) for m in re.finditer(r"(Gymnasien Realschulen|Realschulen Gymnasien)", kurz)]
    if not treffer:
        raise Lesefehler("Spaltenkopf der Übertrittstabelle nicht gefunden")
    return treffer[-1][1].startswith("Gymnasien")


def _reihenfolge_eignung(vorspann: str) -> bool:
    kurz = re.sub(r"\s+", " ", vorspann)
    k = [m.group(1) for m in re.finditer(r"Eignung für d(?:as|ie) (Gymnasium|Realschule)", kurz)]
    if len(k) < 2:
        raise Lesefehler("Spaltenkopf der Eignungstabelle nicht gefunden")
    return k[-2] == "Gymnasium"   # die letzten beiden Köpfe vor der Tabelle: Jungen-Paar


def lesen(text: str) -> tuple[int, dict, dict, list[str]]:
    """Gibt (jahr, übertritte, eignungen, hinweise) zurück; Werte je AGS (Gym J, RS J, Gym M, RS M)."""
    text = _normalisieren(text)
    hinweise = []
    if "bertritt" not in text:
        raise Lesefehler("Dokument enthält keine Übertrittsdaten")
    m = re.search(r"(?:zum|im) Schuljahr (\d{4})\s*/\s*(\d{4})", text)
    if not m:
        raise Lesefehler("Schuljahr nicht erkannt")
    jahr = int(m.group(1))

    treffer = []
    for z in ZEILE.finditer(text):
        name = z.group(1).strip()
        if name.lower().startswith("insgesamt"):
            continue
        kreisfrei = bool(re.search(r"Kfr\.?\s*St", name))
        schluessel = (name.split(",")[0].split()[0].lower(), kreisfrei)
        ags = KREISE.get(schluessel)
        if not ags:
            hinweise.append(f"Unbekannte Zeile übersprungen: {name}")
            continue
        werte = tuple(float(z.group(i).replace(",", ".")) for i in range(2, 6))
        treffer.append((z.start(), ags, werte))

    if len(treffer) < 26:
        raise Lesefehler(f"Nur {len(treffer)} Oberfranken-Zeilen gefunden, erwartet 26 (zwei Tabellen à 13)")
    tab1, tab2 = treffer[:13], treffer[13:26]
    for nr, tab in ((1, tab1), (2, tab2)):
        if len({a for _, a, _ in tab}) != 13:
            raise Lesefehler(f"Tabelle {nr}: nicht alle 13 Kreise eindeutig erkannt")

    gym_zuerst = _reihenfolge_uebertritt(text[:tab1[0][0]])
    if not gym_zuerst:
        hinweise.append("Spaltenreihenfolge Realschule vor Gymnasium erkannt und umgestellt.")
    uebertritt = {a: (w if gym_zuerst else (w[1], w[0], w[3], w[2])) for _, a, w in tab1}

    gym_zuerst_e = _reihenfolge_eignung(text[tab1[-1][0]:tab2[0][0]])
    eignung = {a: (w if gym_zuerst_e else (w[1], w[0], w[3], w[2])) for _, a, w in tab2}
    return jahr, uebertritt, eignung, hinweise


# ------------------------------------------------------------------ Prüfen
def _vorjahr(datei: str, jahr: int) -> dict:
    pfad = IMPORT / datei
    if not pfad.exists():
        return {}
    werte = {}
    with pfad.open(encoding="utf-8") as f:
        for z in csv.DictReader(f, delimiter=";"):
            if int(z["jahr"]) < jahr:
                werte[(z["ags"], int(z["jahr"]))] = float(z["wert"])
    letzte = max((j for _, j in werte), default=None)
    return {a: w for (a, j), w in werte.items() if j == letzte}


def pruefen(jahr, uebertritt, eignung) -> tuple[list[str], list[str]]:
    fehler, auffaellig = [], []
    for name, tab in (("Übertritt", uebertritt), ("Eignung", eignung)):
        for ags, werte in tab.items():
            if not all(0 <= w <= 100 for w in werte):
                fehler.append(f"{name} {ags}: Wert außerhalb 0–100")
    for ags in ("09461", "09462"):
        gj, rj, gm, rm = uebertritt[ags]
        if gj + gm <= rj + rm:
            fehler.append(f"Kreisfreie Stadt {ags}: Gymnasialquote nicht über Realschulquote, Spalten vermutlich vertauscht")
    for ags, (gj, rj, gm, rm) in eignung.items():
        if gj + rj > 100.5 or gm + rm > 100.5:
            fehler.append(f"Eignung {ags}: Summe über 100 %")
    for datei, tab, idx in (("uebertritt_gymnasium.csv", uebertritt, (0, 2)), ("uebertritt_realschule.csv", uebertritt, (1, 3))):
        vor = _vorjahr(datei, jahr)
        for ags, w in tab.items():
            neu = (w[idx[0]] + w[idx[1]]) / 2
            if ags in vor and abs(neu - vor[ags]) > 12:
                auffaellig.append(f"{datei} {ags}: {vor[ags]:.1f} → {neu:.1f}")
    return fehler, auffaellig


# --------------------------------------------------------------- Schreiben
def _ersetzen(datei: str, kopf: list[str], neue_zeilen: list[list], jahr: int):
    pfad = IMPORT / datei
    alt = []
    if pfad.exists():
        with pfad.open(encoding="utf-8") as f:
            r = csv.reader(f, delimiter=";")
            next(r, None)
            alt = [z for z in r if z and z[1] != str(jahr)]
    zeilen = sorted(alt + neue_zeilen, key=lambda z: (int(z[1]), z[0]))
    with pfad.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(kopf)
        w.writerows(zeilen)


def schreiben(jahr, uebertritt, eignung, quelle):
    _ersetzen("uebertritt_rohdaten.csv",
              ["ags", "jahr", "gymnasium_jungen", "realschule_jungen", "gymnasium_maedchen", "realschule_maedchen", "quelle"],
              [[a, str(jahr), *map(str, w), quelle] for a, w in sorted(uebertritt.items())], jahr)
    _ersetzen("eignung_rohdaten.csv",
              ["ags", "jahr", "eignung_gymnasium_jungen", "eignung_realschule_jungen", "eignung_gymnasium_maedchen", "eignung_realschule_maedchen", "quelle"],
              [[a, str(jahr), *map(str, w), quelle] for a, w in sorted(eignung.items())], jahr)
    for datei, tab, idx in (("uebertritt_gymnasium.csv", uebertritt, (0, 2)), ("uebertritt_realschule.csv", uebertritt, (1, 3)),
                            ("eignung_gymnasium.csv", eignung, (0, 2)), ("eignung_realschule.csv", eignung, (1, 3))):
        _ersetzen(datei, ["ags", "jahr", "wert"],
                  [[a, str(jahr), f"{(w[idx[0]] + w[idx[1]]) / 2:.2f}"] for a, w in sorted(tab.items())], jahr)


def vorhandene_jahre() -> set[int]:
    pfad = IMPORT / "uebertritt_rohdaten.csv"
    if not pfad.exists():
        return set()
    with pfad.open(encoding="utf-8") as f:
        return {int(z["jahr"]) for z in csv.DictReader(f, delimiter=";")}


# ------------------------------------------------------------------ Suchen
def suchen() -> list[str]:
    """
    Bestmögliche Suche nach neuen Drucksachen über die Suchseite des Landtags.
    Die Seite hat keine dokumentierte Schnittstelle; schlägt die Suche fehl,
    liefert die Funktion eine leere Liste und der Workflow legt eine Erinnerung an.
    """
    import requests
    kandidaten = []
    for parameter in ("suchbegriff", "q", "volltext", "suche"):
        try:
            r = requests.get(SUCHSEITE, params={"isInitialCheck": "0", "ist_basisdokument": "off", parameter: "Übertrittsquoten in Bayern"},
                             timeout=30, headers={"User-Agent": "sozialindex-oberfranken"})
        except Exception:
            continue
        for wp, nr in re.findall(r"ElanTextAblage_WP(\d+)/Drucksachen/Schriftliche(?:%20| )Anfragen/\d+_(\d{7})\.pdf", r.text):
            ds = f"{int(wp)}/{int(nr)}"
            if ds not in kandidaten:
                kandidaten.append(ds)
    return kandidaten


# ------------------------------------------------------------------- Ablauf
def bericht_schreiben(zeilen: list[str]):
    BERICHT.parent.mkdir(parents=True, exist_ok=True)
    BERICHT.write_text("\n".join(zeilen) + "\n", encoding="utf-8")


def ausgabe(schluessel: str, wert: str):
    pfad = os.environ.get("GITHUB_OUTPUT")
    if pfad:
        with open(pfad, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")


def verarbeiten(text: str, quelle: str, nur_pruefen: bool) -> int:
    jahr, ue, ei, hinweise = lesen(text)
    fehler, auffaellig = pruefen(jahr, ue, ei)
    tabelle = ["| Kreis | Gymnasium | Realschule | Gymnasialeignung | Realschuleignung |", "| --- | --- | --- | --- | --- |"]
    for ags in sorted(ue):
        g, r = (ue[ags][0] + ue[ags][2]) / 2, (ue[ags][1] + ue[ags][3]) / 2
        eg, er = (ei[ags][0] + ei[ags][2]) / 2, (ei[ags][1] + ei[ags][3]) / 2
        tabelle.append(f"| {ags} | {g:.1f} % | {r:.1f} % | {eg:.1f} % | {er:.1f} % |")
    bericht = [f"## Übertrittsquoten zum Schuljahr {jahr}/{jahr + 1}", "", f"Quelle: Bayerischer Landtag, {quelle}", "",
               "Mittel aus Jungen- und Mädchenquote:", "", *tabelle, ""]
    if hinweise:
        bericht += ["**Hinweise beim Lesen:**", *[f"- {h}" for h in hinweise], ""]
    if auffaellig:
        bericht += ["**Auffällige Veränderungen gegenüber dem Vorjahr (über 12 Prozentpunkte), bitte mit der Drucksache vergleichen:**",
                    *[f"- {a}" for a in auffaellig], ""]
    if fehler:
        bericht += ["**Prüfung nicht bestanden, Werte wurden nicht übernommen:**", *[f"- {f}" for f in fehler]]
        bericht_schreiben(bericht)
        print("\n".join(bericht))
        return 1
    bericht += ["Alle Prüfungen bestanden."]
    bericht_schreiben(bericht)
    print("\n".join(bericht))
    ausgabe("jahr", str(jahr))
    if not nur_pruefen:
        schreiben(jahr, ue, ei, quelle)
    return 0


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--drucksache")
    g.add_argument("--datei")
    g.add_argument("--suchen", action="store_true")
    ap.add_argument("--pruefen", action="store_true")
    a = ap.parse_args()
    try:
        if a.datei:
            inhalt = Path(a.datei).read_bytes()
            text = pdf_text(inhalt) if inhalt.startswith(b"%PDF") else inhalt.decode("utf-8")
            sys.exit(verarbeiten(text, Path(a.datei).name, a.pruefen))
        if a.drucksache:
            url = url_fuer(a.drucksache)
            sys.exit(verarbeiten(pdf_text(herunterladen(url)), f"Drucksache {a.drucksache.strip()}", a.pruefen))
        # --suchen: nur Drucksachen mit noch nicht vorhandenem Jahrgang übernehmen
        bekannt = vorhandene_jahre()
        for ds in suchen():
            try:
                text = pdf_text(herunterladen(url_fuer(ds)))
                jahr = lesen(text)[0]
            except Exception:
                continue
            if jahr not in bekannt:
                sys.exit(verarbeiten(text, f"Drucksache {ds}", a.pruefen))
        print("Keine neue Drucksache gefunden.")
        sys.exit(3)
    except Lesefehler as e:
        bericht_schreiben([f"**Lesen fehlgeschlagen:** {e}"])
        print(f"FEHLER: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
