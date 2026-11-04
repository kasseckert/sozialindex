# Eigene Daten in daten/import

Jede CSV-Datei hat die Spalten `ags;jahr;wert` (Semikolon, Dezimalkomma oder -punkt).
`ags` ist der Kreisschlüssel (5-stellig, z. B. 09471) oder Gemeindeschlüssel (8-stellig).
Liegt eine Datei unter dem Namen vor, den `konfiguration/indikatoren.json` nennt,
wird sie beim nächsten Lauf automatisch verwendet.

## Bereits enthalten

Aus den Antworten des Kultusministeriums auf die jährliche Schriftliche Anfrage
„Übertrittsquoten in Bayern“ im Bayerischen Landtag, Drucksachen 18/3249 (2018),
18/16091 (2020), 18/23567 (2021), 18/30611 (2022), 19/5789 (2023) und 19/7981 (2024).
Für 2019 wurde keine entsprechende Anfrage gefunden. Die beigelegten Dateien enthalten zunächst nur die 13 oberfränkischen Kreise; die Erstbefüllung für ganz Bayern beschreibt die README. Jahr = Kalenderjahr des
Übertritts (2024 = zum Schuljahr 2024/2025).

| Datei | Inhalt |
| --- | --- |
| uebertritt_gymnasium.csv | Quote der direkten Übertritte aus Jgst. 4 an das Gymnasium |
| uebertritt_realschule.csv | Quote der direkten Übertritte aus Jgst. 4 an die Realschule |
| eignung_gymnasium.csv | Anteil mit Eignung für das Gymnasium im Übertrittsgutachten |
| eignung_realschule.csv | Anteil mit Eignung für die Realschule, aber nicht das Gymnasium |
| uebertritt_rohdaten.csv, eignung_rohdaten.csv | Ausgangswerte getrennt nach Jungen und Mädchen, mit Drucksache |

Die Werte sind jeweils das Mittel aus Jungen- und Mädchenquote, da keine
Gesamtquote veröffentlicht wird. Achtung beim Ergänzen: In Drucksache 18/3249
stehen die Spalten in der Reihenfolge Realschule vor Gymnasium, sonst umgekehrt.
Neue Jahrgänge übernimmt der Workflow „Jahresdaten und Erinnerungen“ halbautomatisch
(siehe README). Von Hand: `python etl/landtag_uebertritt.py --drucksache 19/7981`
liest, prüft und schreibt alle sechs Dateien; mit `--pruefen` nur Bericht ohne Schreiben.

## Vorlagen zum Befüllen (Statistik der Bundesagentur für Arbeit)

Die BA bietet für diese Kennzahlen keine offene Schnittstelle; die Tabellen
gibt es kostenlos unter statistik.arbeitsagentur.de als Excel-Datei.

**ausbildungsmarkt.csv**: gemeldete Bewerber je gemeldeter Berufsausbildungsstelle,
Berichtsjahr (Oktober bis September) je Kreis. Tabelle „Ausbildungsmarkt –
Bewerber und Berufsausbildungsstellen“ (Regionalauswahl: Kreise). Ein Wert über 1
heißt: mehr Bewerber als Stellen.

**ohne_berufsabschluss.csv**: Anteil der sozialversicherungspflichtig Beschäftigten
am Wohnort ohne beruflichen Abschluss in Prozent, Stichtag 30. Juni, je Kreis.
Tabelle „Beschäftigte nach Berufsabschluss“ bzw. Kreisreport.

Zum Aktivieren die Vorlage in `ausbildungsmarkt.csv` bzw. `ohne_berufsabschluss.csv`
umbenennen und befüllen (im GitHub-Webeditor: Datei öffnen, Stift, Inhalt einfügen,
Commit changes).
