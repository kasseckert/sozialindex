# Eigene Daten in daten/import

Jede CSV-Datei hat die Spalten `ags;jahr;wert` (Semikolon, Dezimalkomma oder -punkt).
`ags` ist der Kreisschlüssel (5-stellig, z. B. 09471) oder Gemeindeschlüssel (8-stellig).
Liegt eine Datei unter dem Namen vor, den `konfiguration/indikatoren.json` nennt,
wird sie beim nächsten Lauf automatisch verwendet.

## Bereits enthalten

**uebertritt_gymnasium.csv**: Quote der direkten Übertritte aus Jahrgangsstufe 4
an das Gymnasium, Mittel aus Jungen- und Mädchenquote (die Gesamtquote wird nicht
veröffentlicht). Rohwerte mit Realschulquoten in `uebertritt_rohdaten.csv`.
Quelle: Antworten des Kultusministeriums auf Schriftliche Anfragen im Bayerischen
Landtag, Drucksachen 19/5789 (Schuljahr 2023/2024) und 19/7981 (2024/2025).
Die Anfrage wird jährlich gestellt; neue Werte unter
www.bayern.landtag.de/parlament/dokumente (Suche „Übertrittsquoten“) und hier als
neue Zeilen ergänzen. Jahr = Kalenderjahr des Übertritts (2024 = zum Schuljahr 2024/2025).

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
