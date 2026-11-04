# Sozialindex Oberfranken

Interaktive Karte der sozialen Lage in den 13 Kreisen und 214 Gemeinden Oberfrankens, mit Popups (Profil, Verlauf, Kennzahlen), Rangliste und einem Datenassistenten im Browser.

> **Auslieferungszustand:** Die Karte zeigt **fiktive Demodaten** und weist darauf hin. Mit dem ersten automatischen Datenabruf werden sie durch amtliche Daten ersetzt. Die Verwaltungsgrenzen sind echt (BKG, VG250).

## Der einfache Weg: alles im Browser

Die Daten kommen aus dem **Regionalatlas Deutschland** der Statistischen Ämter des Bundes und der Länder. Er braucht keine Registrierung und keinen Zugangsschlüssel und liefert fertige Kennzahlen (Quoten, Anteile, Pro-Kopf-Werte) für Kreise und teils für Gemeinden. Den Abruf übernimmt **GitHub Actions**, ein kostenloser Automatisierungsdienst: monatlich, auf Knopfdruck oder sobald Sie die Indikatoren ändern.

**Einmalig einrichten (etwa 15 Minuten):**

1. Kostenloses Konto auf github.com anlegen, ein neues Repository erstellen (privat oder öffentlich) und den Inhalt dieses Ordners hochladen („Add file“ → „Upload files“, alle Dateien und Ordner hineinziehen, auch `.github`).
2. Festlegen, wohin die Karte veröffentlicht wird. Unter **Settings → Secrets and variables → Actions → Variables** die Variable `DEPLOY_ZIEL` anlegen:
   - `pages`: Veröffentlichung auf GitHub Pages (zusätzlich unter Settings → Pages als Quelle „GitHub Actions“ wählen). Am schnellsten, aber auf einer github.io-Adresse.
   - `ssh`: Übertragung auf Ihren eigenen Webserver per rsync. Secrets `SSH_HOST`, `SSH_USER`, `SSH_KEY` (privater Schlüssel), `SSH_ZIELPFAD`.
   - `ftp`: Übertragung per FTPS, etwa auf klassischen Webspace. Secrets `FTP_HOST`, `FTP_USER`, `FTP_PASSWORT`, `FTP_ZIELPFAD`.
3. Unter **Actions → Daten aktualisieren → Run workflow** den ersten Lauf starten. Nach einigen Minuten steht im Protokoll des Laufs, welcher Indikator aus welcher Quelle kam, und die Karte ist mit echten Daten online.

**Danach im Alltag:** Die Datei `assistent.html` auf Ihrer Website öffnen (also `https://ihre-adresse/assistent.html`).

- Im rechten Bereich den Regionalatlas durchsuchen, etwa nach „arbeitslos“, „einkommen“ oder „betreu“. Jeder Treffer zeigt, für welche Jahre es Kreis- und Gemeindewerte gibt.
- „Vorschau“ zeigt die aktuellen Werte für Oberfranken (sofern der Datenserver Browserabfragen zulässt).
- „Als neuer Indikator“ übernimmt eine Kennzahl; bei bestehenden Indikatoren tauscht „Quelle aus Katalog wählen“ die Quelle aus.
- Dimension und Richtung („hoher Wert ist günstig/ungünstig“) prüfen.
- „In GitHub speichern“: Die Änderung wird ins Repository geschrieben, die Karte wird automatisch neu berechnet und veröffentlicht.

Für das Speichern braucht der Assistent ein **feingranulares GitHub-Token** (github.com → Settings → Developer settings → Fine-grained tokens): nur für dieses Repository, mit den Rechten „Contents: Read and write“ und „Actions: Read and write“, gern mit Ablaufdatum. Das Token wird nicht gespeichert und nur an api.github.com gesendet. Wer kein Token nutzen möchte: „Konfiguration herunterladen“ und die Datei im GitHub-Webeditor unter `konfiguration/indikatoren.json` ersetzen; der Effekt ist derselbe.

Schlägt ein monatlicher Lauf fehl (etwa weil ein Statistikserver gewartet wird), bleiben die bisherigen Daten online und GitHub schickt eine E-Mail. Hinweis: Bei öffentlichen Repositories ohne jede Aktivität pausiert GitHub Zeitpläne nach 60 Tagen; ein Klick auf „Enable workflow“ im Reiter Actions reaktiviert sie.

## Wie die Quellen gefunden werden

Jeder Indikator in `konfiguration/indikatoren.json` hat eine Liste von Quellen, die der Reihe nach probiert werden. Die erste, die mindestens 80 % der Gebiete abdeckt, wird verwendet:

```json
"quellen": [
  {"typ": "regionalatlas", "code": "AI003-3", "feld": "ai0306"},
  {"typ": "regionalatlas", "suche": ["Arbeitslosenquote"], "feld_suche": ["insgesamt"]},
  {"typ": "csv", "datei": "alq.csv"}
]
```

Eine **feste Angabe** (`code`, `feld`) ist eindeutig. Eine **Suche** wird bei jedem Lauf im aktuellen Regionalatlas-Katalog aufgelöst; welcher Code dabei gewählt wurde, zeigen das Laufprotokoll, die Quellenangaben auf der Karte und „Zuletzt genutzt“ im Assistenten. Es empfiehlt sich, eine gefundene Quelle im Assistenten mit „Als Quelle verwenden“ fest einzutragen, sobald sie passt.

`csv`-Quellen sind Dateien in `daten/import/` mit den Spalten `ags;jahr;wert` (Vorlage: `_vorlage.csv`). So lassen sich Daten einbinden, die der Regionalatlas nicht hat: Gemeindedaten der Bundesagentur für Arbeit, Hausarztzahlen der Kassenärztlichen Vereinigung oder eigene kommunale Statistik. Die Dateien lassen sich im GitHub-Webeditor hochladen; das löst ebenfalls eine Neuberechnung aus.

GENESIS-Quellen (statistikdaten.bayern.de, regionalstatistik.de) sind weiter möglich, für Fälle, die beide anderen Wege nicht abdecken; siehe `etl/genesis.py`.

**Grenzen auf Gemeindeebene:** Der Regionalatlas hat für Gemeinden vor allem demografische Kennzahlen; Arbeitsmarkt, Einkommen und Bildung gibt es meist nur für Kreise. Der Gemeindeindex beruht dann auf weniger Dimensionen; die Karte sagt in der Legende genau, auf welchen. Für einen vollständigeren Gemeindeindex lohnen CSV-Importe aus der Gemeindestatistik der Bundesagentur für Arbeit.

## Bildungsdaten

Die Dimension „Bildung und Familie“ greift auf sechs Quellen zurück:

| Indikator | Quelle | Ebene | Zugang |
| --- | --- | --- | --- |
| Betreuungsquote unter 3, Ganztagsbetreuung | Regionalatlas | Kreise | ohne Anmeldung |
| Schulabgänger ohne Abschluss | Regionalatlas, sonst Kommunale Bildungsdatenbank | Kreise | Bildungsdatenbank: Registrierung |
| Ohne beruflichen Abschluss | BA-Datei (jährlich), sonst Zensus 2022 (Stand 15.05.2022, fortgeschrieben) | Kreise | Zensus: Registrierung |
| Übertrittsquote an das Gymnasium | Landtagsdrucksachen 2018, 2020–2024, als Datei beigelegt | Kreise | ohne Anmeldung |
| Kontext: Übertrittsquote Realschule, Gymnasial- und Realschuleignung | Landtagsdrucksachen, als Datei beigelegt | Kreise | ohne Anmeldung |
| Kontext: Abgänger mit mittlerem Abschluss | Regionalatlas, sonst GENESIS Bayern oder Bildungsdatenbank | Kreise | Bildungsdatenbank: Registrierung |
| Kontext: neue Azubis mit mittlerem Abschluss | Bildungsdatenbank, sonst Regionaldatenbank | Kreise | Registrierung |
| Bewerber je Ausbildungsstelle | Statistik der BA, Datei selbst befüllen | Kreise | ohne Anmeldung |
| Entfernung zur nächsten Grundschule / zum nächsten Gymnasium | Schulstandorte Bayern (Kultusministerium, WFS, CC BY 4.0) | Gemeinden und Kreise | ohne Anmeldung |

**Zensus 2022 und Kommunale Bildungsdatenbank** brauchen je eine kostenlose Registrierung (ergebnisse.zensus2022.de und www.bildungsmonitoring.de, jeweils „Registrieren“). Benutzername und Passwort als Secrets `GENESIS_ZENSUS_USER`, `GENESIS_ZENSUS_PASSWORD`, `GENESIS_BILDUNG_USER`, `GENESIS_BILDUNG_PASSWORD` eintragen (wie in der Anleitung, Schritt 4). Ohne Zugangsdaten werden diese Quellen übersprungen; die übrigen laufen weiter. Nach dem ersten Lauf mit Zugangsdaten zeigt der Datenassistent die Tabellen beider Datenbanken zur Auswahl an.

**Grenzen:** Die Bildungsfragen des Zensus gibt es nur für Kreise sowie für Gemeinden ab 10 000 Einwohnern, deshalb nur auf Kreisebene genutzt. Die Schulentfernung ist Luftlinie vom Flächenmittelpunkt der Gemeinde, kein Schulweg. Die Übertrittsquote hängt auch vom Schulangebot vor Ort ab und ist in den Städten traditionell höher. Übertrittsquoten liegen bisher für 2023 und 2024 vor; neue Jahrgänge nach `daten/import/LIESMICH.md` ergänzen.

## Ohne GitHub: auf dem eigenen Server

```bash
pip install -r requirements.txt
./aktualisieren.sh                 # abrufen und berechnen
```

Per cron monatlich: `0 3 6 * * cd /opt/sozialindex-oberfranken && ./aktualisieren.sh >> log/aktualisierung.log 2>&1`. Den Ordner `web/` liefert der Webserver aus (Apache: beiliegende `.htaccess`; nginx: `nginx-beispiel.conf`). Der Assistent funktioniert dann für Suche, Vorschau und Download; gespeichert wird, indem die heruntergeladene Datei nach `konfiguration/` kopiert wird.

Optionen von `etl/abrufen.py`: `--demo-auffuellen` füllt fehlende Indikatoren mit Demowerten (nur zum Testen), `--nur-demo` arbeitet ganz ohne Internet.

## Aufbau

```
.github/workflows/aktualisieren.yml   Automatisierung (Abruf, Berechnung, Veröffentlichung)
konfiguration/indikatoren.json        Indikatoren, Quellen, Dimensionen, Gewichte
web/                                  die Website (statisch, ohne Drittanbieter-Anfragen)
  index.html, app.js, style.css       Karte
  assistent.html, assistent.js/.css   Datenassistent
  data/                               Geodaten, berechnete Werte, Katalog
etl/
  regionalatlas.py                    Client für den Regionalatlas
  schulen.py                          Schulstandorte und Schulerreichbarkeit
  abrufen.py                          Schritt 1: Quellen abrufen
  index_berechnen.py                  Schritt 2: Index berechnen
  genesis.py, genesis_auswerten.py    GENESIS-Webservice (Zensus, Bildungsdatenbank, Landesämter)
  geodaten_erzeugen.py                Grenzen aus VG250 neu erzeugen
daten/import/                         eigene CSV-Dateien
```

## Methode

Jeder Indikator wird standardisiert und so ausgerichtet, dass höhere Werte eine günstigere Lage bedeuten. Die Indikatoren werden je Dimension gemittelt, die Dimensionen gewichtet (Standard: gleich) zum Gesamtindex zusammengefasst und je Jahr auf die Skala 100 ± 10 gebracht: 100 ist der Durchschnitt der oberfränkischen Kreise bzw. Gemeinden im jeweiligen Jahr. Der Index beschreibt die relative Lage innerhalb Oberfrankens; absolute Entwicklungen zeigen die Zeitreihen der Indikatoren. Ist ein Indikator für die jüngsten Jahre noch nicht veröffentlicht (etwa das verfügbare Einkommen mit rund zwei Jahren Verzug), wird der letzte verfügbare Wert für höchstens zwei Jahre fortgeschrieben (`fortschreiben_jahre` in `konfiguration/indikatoren.json`, je Indikator abschaltbar mit `"fortschreiben": 0`). Die Karte kennzeichnet solche Werte in Legende, Kennzahlen (Sternchen) und Verlauf (gestrichelt, hohle Punkte). Kreise und Gemeinden werden getrennt berechnet, jeweils mit den Indikatoren, die auf der Ebene vorliegen. **Kontextindikatoren** (`"im_index": false`) erscheinen in Karte, Rangliste und Popups, gehen aber nicht in den Index ein. Das ist für Kennzahlen gedacht, bei denen ein hoher Wert weder eindeutig günstig noch ungünstig ist, etwa die Übertrittsquote an die Realschule. Sie werden in einer neutralen Blauskala mit den Polen „niedriger“ und „höher“ gezeigt. Im Datenassistenten lässt sich das je Indikator mit „Im Index berücksichtigen“ umschalten. Auswahl und Gewichtung der Indikatoren sind fachliche Entscheidungen und sollten mit den Nutzern abgestimmt werden.

## Datenschutz und Lizenzen

Die Karte lädt nichts von fremden Servern. Der Assistent stellt nur auf Ihre ausdrückliche Aktion hin Verbindungen her: zur Vorschau an den Regionalatlas-Datenserver (gis-idmz.nrw.de), zum Speichern an api.github.com.

- Statistikdaten: © Statistische Ämter des Bundes und der Länder, Datenlizenz Deutschland – Namensnennung – 2.0
- Schulstandorte: Bayerisches Staatsministerium für Unterricht und Kultus, CC BY 4.0
- Übertrittsquoten und Eignungen: Bayerischer Landtag, Drucksachen 18/3249, 18/16091, 18/23567, 18/30611, 19/5789, 19/7981
- Verwaltungsgrenzen: © GeoBasis-DE / BKG, dl-de/by-2-0
- Leaflet (BSD-2), Chart.js (MIT), Atkinson Hyperlegible (SIL OFL)
- Abfrageaufbau des Regionalatlas nach dem quelloffenen Client maschinenlesbar-org/regionalatlas-cli (MIT)
