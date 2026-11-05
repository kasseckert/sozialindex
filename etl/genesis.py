"""
Schlanker Client für den GENESIS-Webservice (RESTful/JSON, Version 2020).

Unterstützte Datenbanken (gleiche Schnittstelle, andere Domain):
    regio    Regionaldatenbank Deutschland   https://www.regionalstatistik.de
    bayern   GENESIS-Online Bayern           https://www.statistikdaten.bayern.de
    bildung  Kommunale Bildungsdatenbank     https://www.bildungsmonitoring.de
    zensus   Zensus 2022                     https://ergebnisse.zensus2022.de
    destatis GENESIS-Online des Bundes       https://genesis.destatis.de

Zugangsdaten
------------
Die Abfragen laufen per POST; Benutzername/Token und Passwort werden als
HTTP-Header übertragen (die früheren GET-Aufrufe mit Zugangsdaten in der URL
wurden abgeschaltet). Die Zugangsdaten werden aus Umgebungsvariablen gelesen:

    GENESIS_REGIO_USER,    GENESIS_REGIO_PASSWORD
    GENESIS_BAYERN_USER,   GENESIS_BAYERN_PASSWORD
    GENESIS_BILDUNG_USER,  GENESIS_BILDUNG_PASSWORD
    GENESIS_ZENSUS_USER,   GENESIS_ZENSUS_PASSWORD
    GENESIS_DESTATIS_USER, GENESIS_DESTATIS_PASSWORD

Eine kostenlose Registrierung ist auf der jeweiligen Website möglich. Statt
Benutzername und Passwort kann bei manchen Datenbanken ein API-Token als
Benutzername dienen (Passwort dann leer lassen). Ohne Zugangsdaten wird es mit
dem Gastzugang versucht, der aber nicht alle Tabellen und Datenmengen erlaubt.

Bitte die aktuelle Schnittstellenbeschreibung beachten:
https://www-genesis.destatis.de/datenbank/online/docs/GENESIS-Webservices_Einfuehrung.pdf
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import zipfile

import requests

BASIS_URL = {
    "regio":    "https://www.regionalstatistik.de/genesisws/rest/2020",
    "bayern":   "https://www.statistikdaten.bayern.de/genesisWS/rest/2020",
    "bildung":  "https://www.bildungsmonitoring.de/bildungws/rest/2020",
    "zensus":   "https://ergebnisse.zensus2022.de/api/rest/2020",
    "destatis": "https://genesis.destatis.de/genesisWS/rest/2020",
}


class GenesisFehler(RuntimeError):
    pass


def _zugang(datenbank: str) -> tuple[str, str]:
    key = datenbank.upper()
    user = os.environ.get(f"GENESIS_{key}_USER") or "GAST"
    pw = os.environ.get(f"GENESIS_{key}_PASSWORD") or ("GAST" if user == "GAST" else "")
    return user, pw


def hat_zugang(datenbank: str) -> bool:
    """True, wenn für die Datenbank eigene Zugangsdaten hinterlegt sind."""
    return bool(os.environ.get(f"GENESIS_{datenbank.upper()}_USER"))


def _post(datenbank: str, pfad: str, parameter: dict, versuche: int = 2, lesezeit: int = 90) -> requests.Response:
    if datenbank not in BASIS_URL:
        raise GenesisFehler(f"Unbekannte Datenbank '{datenbank}'")
    user, pw = _zugang(datenbank)
    url = f"{BASIS_URL[datenbank]}/{pfad}"
    headers = {
        "username": user,
        "password": pw,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    letzter_fehler = None
    for i in range(versuche):
        try:
            r = requests.post(url, headers=headers, data=parameter, timeout=(15, lesezeit))
            if r.status_code == 200:
                return r
            letzter_fehler = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as e:
            letzter_fehler = str(e)
        time.sleep(3)
    raise GenesisFehler(f"{url} fehlgeschlagen: {letzter_fehler}")


def suche_tabellen(datenbank: str, suchbegriff: str, anzahl: int = 50) -> list[dict]:
    """Durchsucht den Tabellenkatalog (catalogue/tables)."""
    r = _post(datenbank, "catalogue/tables",
              {"selection": f"*{suchbegriff}*" if " " not in suchbegriff else suchbegriff,
               "area": "all", "pagelength": str(anzahl), "language": "de"})
    daten = r.json()
    return daten.get("List") or []


def suche_volltext(datenbank: str, suchbegriff: str) -> list[dict]:
    """Volltextsuche (find/find), liefert Tabellen passend zum Begriff."""
    r = _post(datenbank, "find/find",
              {"term": suchbegriff, "category": "tables", "pagelength": "50", "language": "de"})
    return r.json().get("Tables") or []


def tabelle_ffcsv(datenbank: str, tabelle: str, startjahr: int, endjahr: int,
                  regionalvariable: str | None = None,
                  regionalschluessel: str | None = None) -> list[dict]:
    """
    Ruft eine Tabelle im Flat-File-CSV-Format ab und gibt die Zeilen als
    Liste von Dicts zurück.
    """
    parameter = {
        "name": tabelle,
        "area": "all",
        "compress": "false",
        "startyear": str(startjahr),
        "endyear": str(endjahr),
        "format": "ffcsv",
        "language": "de",
    }
    if regionalvariable:
        parameter["regionalvariable"] = regionalvariable
    if regionalschluessel:
        parameter["regionalkey"] = regionalschluessel

    r = _post(datenbank, "data/tablefile", parameter)
    inhalt = r.content

    # Große Tabellen kommen als ZIP; Fehlermeldungen als JSON.
    if inhalt[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
            inhalt = z.read(z.namelist()[0])
    text = inhalt.decode("utf-8-sig", errors="replace")
    if text.lstrip().startswith("{"):
        meldung = json.loads(text).get("Status", {})
        raise GenesisFehler(f"Tabelle {tabelle}: {meldung}")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def tabellen_katalog(datenbank: str, auswahl: str = "*", anzahl: int = 2500) -> list[dict]:
    """Liste der Tabellen einer Datenbank: [{"code", "titel"}]."""
    r = _post(datenbank, "catalogue/tables",
              {"selection": auswahl, "area": "all", "pagelength": str(anzahl), "language": "de"}, lesezeit=240)
    liste = r.json().get("List") or []
    return [{"code": t.get("Code", ""), "titel": (t.get("Content") or "").strip()} for t in liste if t.get("Code")]


_FUND_CACHE: dict = {}


def finde_tabellen(datenbank: str, suchbegriffe: list[str], anzahl: int = 3) -> list[dict]:
    """
    Sucht Tabellen per Volltext und sortiert sie danach, wie viele Wörter der
    Suchbegriffe im Titel vorkommen. Ergebnis: [{"code", "titel"}].
    """
    schluessel = (datenbank, tuple(suchbegriffe), anzahl)
    if schluessel in _FUND_CACHE:
        return _FUND_CACHE[schluessel]
    gesehen, treffer = set(), []
    for begriff in suchbegriffe:
        try:
            liste = suche_volltext(datenbank, begriff)
        except GenesisFehler:
            continue
        woerter = [w for w in begriff.lower().split() if len(w) > 2]
        for t in liste:
            code, titel = t.get("Code", ""), (t.get("Content") or "")
            if not code or code in gesehen:
                continue
            gesehen.add(code)
            treffer.append((sum(w in titel.lower() for w in woerter), {"code": code, "titel": titel}))
    treffer.sort(key=lambda x: -x[0])
    _FUND_CACHE[schluessel] = [t for _, t in treffer[:anzahl]]
    return _FUND_CACHE[schluessel]


def tabelle_stueckweise(datenbank: str, tabelle: str, startjahr: int, endjahr: int,
                        regionalvariable: str | None = None, regionalschluessel: str | None = None) -> list[dict]:
    """
    Wie tabelle_ffcsv; ist die Tabelle für einen Abruf zu groß (GENESIS-Code 98),
    wird sie Jahr für Jahr abgerufen und zusammengesetzt.
    """
    try:
        return tabelle_ffcsv(datenbank, tabelle, startjahr, endjahr, regionalvariable, regionalschluessel)
    except GenesisFehler as e:
        if not any(k in str(e) for k in ("zu gross", "'Code': 98", "timed out", "Timeout")):
            raise
    zeilen, fehler = [], []
    for jahr in range(startjahr, endjahr + 1):
        try:
            zeilen += tabelle_ffcsv(datenbank, tabelle, jahr, jahr, regionalvariable, regionalschluessel)
        except GenesisFehler as e:
            fehler.append(f"{jahr}: {str(e)[:120]}")
    if not zeilen:
        raise GenesisFehler(f"Tabelle {tabelle}: auch jahresweise kein Abruf möglich ({'; '.join(fehler[:3])})")
    return zeilen


_RV_CACHE: dict = {}


def regionalvariablen(datenbank: str, statistik: str) -> list[dict]:
    """Regionalebenen einer Statistik laut Katalog: [{"code", "titel"}] (leer, wenn nicht ermittelbar)."""
    if (datenbank, statistik) in _RV_CACHE:
        return _RV_CACHE[(datenbank, statistik)]
    ergebnis = []
    try:
        r = _post(datenbank, "catalogue/variables2statistic",
                  {"name": statistik, "selection": "*", "area": "all", "pagelength": "500", "language": "de"})
        for v in r.json().get("List") or []:
            code, titel, typ = v.get("Code", ""), v.get("Content", ""), str(v.get("Type", ""))
            if code and ("räum" in typ.lower() or "raum" in typ.lower() or code.upper().startswith(("GEO", "KREIS", "BY-KRE", "GEMEIN"))
                         or re.search(r"Kreis|Gemeinde|Land|Bezirk", titel)):
                ergebnis.append({"code": code, "titel": titel, "typ": typ})
    except Exception:
        pass
    _RV_CACHE[(datenbank, statistik)] = ergebnis
    return ergebnis


def _gebiete_in(zeilen: list[dict], praefix: str, laenge: int) -> int:
    """Zahl verschiedener Gebietsschlüssel der gewünschten Länge mit Präfix (beide Formate)."""
    codes = set()
    for z in zeilen:
        for k, v in z.items():
            if (k.endswith("_attribute_code") or k.endswith("_Auspraegung_Code")) and v:
                c = re.sub(r"\D", "", v)
                if len(c) >= laenge and c.startswith(praefix):
                    codes.add(c[:laenge])
    return len(codes)


def tabelle_fuer_ebene(datenbank: str, tabelle: str, startjahr: int, endjahr: int, ebene: str,
                       praefix: str, erwartet: int, regionalvariable: str | None = None) -> tuple[list[dict], str]:
    """
    Ruft eine Tabelle für alle Kreise (ebene="kreis") bzw. Gemeinden ab. Die Regionalvariable
    heißt je Datenbank anders (KREISE, BY-KRE, GEO…); sie wird aus der Vorgabe, bekannten Namen
    und dem Katalog der Statistik ermittelt. Ein Ergebnis zählt nur, wenn mindestens 80 % der
    erwarteten Gebiete enthalten sind; so wird ein stillschweigend gelieferter Landeswert erkannt.
    """
    laenge = 5 if ebene == "kreis" else 8
    bekannte = ["KREISE", "BY-KRE", "KRS", "KREIS"] if ebene == "kreis" else ["GEMEIN", "BY-GEM", "GEM", "GEMEINDE"]
    kandidaten = [regionalvariable] if regionalvariable else []
    kandidaten += [k for k in bekannte if k not in kandidaten]
    versucht, fehler = [], []

    def probieren(rv):
        if rv in versucht:
            return None
        versucht.append(rv)
        try:
            zeilen = tabelle_stueckweise(datenbank, tabelle, startjahr, endjahr, rv, praefix + "*")
        except GenesisFehler as e:
            fehler.append(f"{rv}: {str(e)[:120]}")
            return None
        n = _gebiete_in(zeilen, praefix, laenge)
        if n >= 0.8 * erwartet:
            return zeilen
        fehler.append(f"{rv}: nur {n} von {erwartet} Gebieten")
        return None

    for rv in kandidaten[:2]:                      # Vorgabe und häufigster Name zuerst
        z = probieren(rv)
        if z:
            return z, rv
    # Statistik-Code aus der Standardauswahl lesen und deren Regionalebenen abfragen
    try:
        standard = tabelle_ffcsv(datenbank, tabelle, endjahr, endjahr)
        statistik = next((z.get("statistics_code") for z in standard if z.get("statistics_code")), None) or tabelle.split("-")[0]
    except GenesisFehler:
        statistik = tabelle.split("-")[0]
    wort = "Kreis" if ebene == "kreis" else "Gemeind"
    katalog = [v["code"] for v in regionalvariablen(datenbank, statistik) if wort.lower() in v["titel"].lower()]
    for rv in katalog + kandidaten[2:]:
        z = probieren(rv)
        if z:
            return z, rv
    raise GenesisFehler(f"Tabelle {tabelle}: keine Regionalebene mit den {'Kreisen' if ebene == 'kreis' else 'Gemeinden'} gefunden "
                        f"(versucht: {', '.join(map(str, versucht))}; {'; '.join(fehler[-3:])})")
