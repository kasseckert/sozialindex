# Sozialindex Bayern

Interaktive Karte der sozialen Lage in den 96 Kreisen und 2.056 Gemeinden Bayerns, gegliedert in neun Aufsichtsbezirke, mit Popups (Profil, Verlauf, Kennzahlen), Rangliste und einem Datenassistenten im Browser. Entstanden aus dem Sozialindex Oberfranken.

> **Auslieferungszustand:** Die Karte zeigt **fiktive Demodaten** und weist darauf hin. Mit dem ersten automatischen Datenabruf werden sie durch amtliche Daten ersetzt. Die Verwaltungsgrenzen sind echt (BKG, VG250).

## Regionen und Vergleichsmaßstab

Die Karte zeigt wahlweise ganz Bayern oder einen der neun Aufsichtsbezirke: München (Landeshauptstadt und Landkreis), Oberbayern-Ost, Oberbayern-West, Niederbayern, Oberpfalz, Oberfranken, Mittelfranken, Unterfranken und Schwaben. Die Zuordnung der Kreise steht in `konfiguration/gebiete.json` und lässt sich dort ändern. Jede Region hat eine eigene Adresse zum Weitergeben, etwa `…/#oberfranken` oder `…/#oberbayern-ost`; Kreise außerhalb der gewählten Region erscheinen grau, ein Klick darauf wechselt die Region.

**Vergleichsmaßstab:** Standard ist „100 = bayerischer Durchschnitt“; damit sind alle Regionen direkt vergleichbar. Bei gewählter Region lässt sich auf „100 = Durchschnitt der Region“ umschalten, sofern die Region dafür groß genug ist (mindestens 10 Kreise bzw. 20 Gemeinden, einstellbar in `gebiete.json`). Für den Aufsichtsbezirk München mit nur zwei Kreisen ist der Regionalvergleich auf Kreisebene deshalb gesperrt, auf Gemeindeebene (30 Gemeinden) möglich. Rang und Durchschnitt werden im Popup für Region und Land angegeben.

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
- „Vorschau“ zeigt die aktuellen Werte für die bayerischen Kreise (sofern der Datenserver Browserabfragen zulässt).
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

**Erstbefüllung der Übertrittsquoten für ganz Bayern:** Die beigelegten Dateien enthalten zunächst nur die 13 oberfränkischen Kreise; bayernweit werden die Übertrittsindikatoren deshalb übersprungen, bis alle Kreise vorliegen. Einmalig unter **Actions → Jahresdaten und Erinnerungen → Run workflow** diese Nummern eintragen: `18/3249, 18/16091, 18/23567, 18/30611, 19/5789, 19/7981`. Der Workflow liest alle sechs Jahrgänge für alle 96 Kreise, prüft sie und legt einen Änderungsvorschlag an.

**Grenzen auf Gemeindeebene:** Der Regionalatlas hat für Gemeinden vor allem demografische Kennzahlen; Arbeitsmarkt, Einkommen und Bildung gibt es meist nur für Kreise. Der Gemeindeindex beruht dann auf weniger Dimensionen; die Karte sagt in der Legende genau, auf welchen. Für einen vollständigeren Gemeindeindex lohnen CSV-Importe aus der Gemeindestatistik der Bundesagentur für Arbeit.

## Bildungsdaten

Die Dimension „Bildung und Familie“ greift auf sechs Quellen zurück:

| Indikator | Quelle | Ebene | Zugang |
| --- | --- | --- | --- |
| Betreuungsquote unter 3, Ganztagsbetreuung | Regionalatlas | Kreise | ohne Anmeldung |
| Schulabgänger ohne Abschluss, Abgänger mit Hochschulreife (Kontext) | Regionalatlas | Kreise | ohne Anmeldung |
| Kontext: ausländische Schüler, Schüler je Lehrkraft, Teilzeitlehrkräfte, früh/spät eingeschulte Kinder | Kommunale Bildungsdatenbank (BY-D07.1i, D09.1i, D11.1i), öffentliche Schulen | Kreise | Registrierung |
| Kontext: Fünftklässler nach Schulart (am Schulort), Schulartwechsel Klassen 7–9 | Kommunale Bildungsdatenbank (BY-D12.1i, D12.3i) | Kreise | Registrierung |
| Ohne beruflichen Abschluss | BA-Datei (jährlich), sonst Zensus 2022 (Stand 15.05.2022, fortgeschrieben) | Kreise | Zensus: Registrierung |
| Übertrittsquote an das Gymnasium | Landtagsdrucksachen 2018, 2020–2024, als Datei beigelegt | Kreise | ohne Anmeldung |
| Kontext: Übertrittsquote Realschule, Gymnasial- und Realschuleignung | Landtagsdrucksachen, als Datei beigelegt | Kreise | ohne Anmeldung |
| Bewerber je Ausbildungsstelle | Statistik der BA, Datei selbst befüllen | Kreise | ohne Anmeldung |
| Entfernung zur nächsten Grundschule / zum nächsten Gymnasium | Schulstandorte Bayern (Kultusministerium, WFS, CC BY 4.0) | Gemeinden und Kreise | ohne Anmeldung |

**Zensus 2022 und Kommunale Bildungsdatenbank** brauchen je eine kostenlose Registrierung (ergebnisse.zensus2022.de und www.bildungsmonitoring.de, jeweils „Registrieren“). Benutzername und Passwort als Secrets `GENESIS_ZENSUS_USER`, `GENESIS_ZENSUS_PASSWORD`, `GENESIS_BILDUNG_USER`, `GENESIS_BILDUNG_PASSWORD` eintragen (wie in der Anleitung, Schritt 4). Ohne Zugangsdaten werden diese Quellen übersprungen; die übrigen laufen weiter. Nach dem ersten Lauf mit Zugangsdaten zeigt der Datenassistent die Tabellen beider Datenbanken zur Auswahl an.

**Nicht verfügbar für Bayern:** Abgänger nach Abschlussart (also mit mittlerem Abschluss) und Ausbildungsverträge nach schulischer Vorbildung führt die Bildungsdatenbank für Bayern nicht, Klassenwiederholungen (BY-D13.1i) nur als Landeswert ohne Kreise (Kennzahl D15.1 „in Bayern nicht verfügbar“; Vorbildung nur für andere Länder). Auf Kreisebene veröffentlicht sie Schuldaten außerdem nur für staatliche und kommunale Schulen; Summen einschließlich Privatschulen sind gesperrt. Die Übergänge nach der Grundschule zählt sie am Ort der weiterführenden Schule; für den Übertritt der Kinder eines Kreises bleiben die Landtagsdaten maßgeblich.

**Grenzen:** Die Bildungsfragen des Zensus gibt es nur für Kreise sowie für Gemeinden ab 10 000 Einwohnern, deshalb nur auf Kreisebene genutzt. Die Schulentfernung ist Luftlinie vom Flächenmittelpunkt der Gemeinde, kein Schulweg. Die Übertrittsquote hängt auch vom Schulangebot vor Ort ab und ist in den Städten traditionell höher. Übertrittsquoten liegen bisher für 2023 und 2024 vor; neue Jahrgänge nach `daten/import/LIESMICH.md` ergänzen.

## Schulstandorte in der Karte

Unter „Schulstandorte einblenden“ lassen sich die Realschulen als Stecknadeln anzeigen; ein Klick zeigt Name, Adresse, Träger, Kreis sowie Links zur Website und zu OpenStreetMap. Bei gewählter Region erscheinen nur deren Schulen. Die Standorte stammen aus dem Dienst „Schulstandorte in Bayern“ des Kultusministeriums (CC BY 4.0) und werden mit jedem Lauf aktualisiert (`web/data/schulen/`). Weitere Schularten lassen sich in `konfiguration/indikatoren.json` unter `"schulstandorte_karte"` ergänzen, z. B. `["realschule", "gymnasium", "mittelschule", "fos"]` (mögliche Werte: grundschule, mittelschule, realschule, gymnasium, fos, berufliche, foerderzentrum); die Karte bietet dann je Schulart einen Schalter.

**Vollständigkeit der Schulstandorte:** Die Standorte kommen aus zwei Diensten des Kultusministeriums: dem umfassenden Dienst `schulstandorte_bayern` und dem Dienst der staatlichen Schulen, der fehlende staatliche Schulen ergänzt und den Träger „staatlich“ bestätigt. Beide sind nicht ganz vollständig und nicht immer aktuell (Zusammenlegungen, einzelne kommunale Schulen). Für solche Fälle gibt es `konfiguration/schulen_korrekturen.json`: Unter `entfernen` werden Schulen weggelassen, deren Name einen Text enthält; unter `ergaenzen` lassen sich fehlende Schulen mit Koordinaten eintragen (in OpenStreetMap per Rechtsklick → „Adresse anzeigen“). Die Korrekturen gelten bei jedem Lauf, auch für die Entfernungsberechnung. Welche Schulen gelesen und welche verworfen wurden, steht nach jedem Lauf in `daten/schulen_diagnose.json`.

## Was sich automatisch aktualisiert

| Daten | Aktualisierung |
| --- | --- |
| Regionalatlas, Bildungsdatenbank, GENESIS, Schulstandorte | automatisch, monatlich (Workflow „Daten aktualisieren“) |
| Zensus 2022 | automatisch abgerufen; Stichtagswerte, ändern sich erst mit dem nächsten Zensus |
| Übertrittsquoten und Eignungen (Landtag) | halbautomatisch (Workflow „Jahresdaten und Erinnerungen“) |
| BA-Daten (Ausbildungsmarkt, ohne Berufsabschluss) | von Hand, mit jährlicher Erinnerung |
| Verwaltungsgrenzen | von Hand, nur bei Gebietsreformen |

**Übertrittsquoten:** Von September bis Dezember sucht der Workflow „Jahresdaten und Erinnerungen“ am 1. jedes Monats nach der neuen Landtagsdrucksache „Übertrittsquoten in Bayern“. Findet er sie, liest er die Werte aller 96 Kreise aus, prüft sie (13 Kreise je Tabelle, Wertebereich, Spaltenreihenfolge, auffällige Sprünge zum Vorjahr) und legt einen Änderungsvorschlag (Pull Request) mit einer Übersichtstabelle an. Erst wenn Sie ihn mit **Merge** bestätigen, gehen die Werte in die Karte ein. Findet er die Drucksache nicht, legt er eine Erinnerung (Issue) an; dann unter **Actions → Jahresdaten und Erinnerungen → Run workflow** die Drucksachennummer eintragen (z. B. `19/7981`), der Rest läuft wie oben. Damit Pull Requests angelegt werden dürfen: **Settings → Actions → General → „Allow GitHub Actions to create and approve pull requests“**. Ohne diese Einstellung erstellt der Workflow stattdessen ein Issue mit Link zu den Änderungen.

**BA-Daten:** Im November (Ausbildungsmarkt) und Februar (Beschäftigte nach Berufsabschluss) legt derselbe Workflow eine Erinnerung mit Anleitung an.

**Datenstand:** Unter „Quellen und Lizenzen“ zeigt die Karte für jede Quelle das jüngste Datenjahr. Liegt es mehr als ein Jahr zurück, ist der Eintrag farbig hervorgehoben.

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
.github/workflows/jahresdaten.yml     Übertrittsquoten aus dem Landtag, Erinnerungen
konfiguration/indikatoren.json        Indikatoren, Quellen, Dimensionen, Gewichte
konfiguration/gebiete.json            Regionen (Aufsichtsbezirke) und ihre Kreise
web/                                  die Website (statisch, ohne Drittanbieter-Anfragen)
  index.html, app.js, style.css       Karte
  assistent.html, assistent.js/.css   Datenassistent
  data/                               Kreisgrenzen, Kreiswerte (werte.json), Katalog
  data/gemeinden/, data/werte_gemeinden/  Gemeindegrenzen und -werte je Region (werden bei Bedarf nachgeladen)
etl/
  regionalatlas.py                    Client für den Regionalatlas
  schulen.py                          Schulstandorte und Schulerreichbarkeit
  landtag_uebertritt.py               Übertrittsquoten aus Landtagsdrucksachen lesen
  abrufen.py                          Schritt 1: Quellen abrufen
  index_berechnen.py                  Schritt 2: Index berechnen
  genesis.py, genesis_auswerten.py    GENESIS-Webservice (Zensus, Bildungsdatenbank, Landesämter)
  geodaten_erzeugen.py                Grenzen aus VG250 neu erzeugen (je Region aufgeteilt)
  gebiete.py                          Gebietsgliederung lesen
daten/import/                         eigene CSV-Dateien
```

## Methode

Jeder Indikator wird standardisiert und so ausgerichtet, dass höhere Werte eine günstigere Lage bedeuten. Die Indikatoren werden je Dimension gemittelt, die Dimensionen gewichtet (Standard: gleich) zum Gesamtindex zusammengefasst und je Jahr auf die Skala 100 ± 10 gebracht: 100 ist der Durchschnitt der bayerischen Kreise bzw. Gemeinden im jeweiligen Jahr. Der Index beschreibt die relative Lage innerhalb Bayerns (bzw. der Region beim regionalen Maßstab); absolute Entwicklungen zeigen die Zeitreihen der Indikatoren. Ist ein Indikator für die jüngsten Jahre noch nicht veröffentlicht (etwa das verfügbare Einkommen mit rund zwei Jahren Verzug), wird der letzte verfügbare Wert für höchstens zwei Jahre fortgeschrieben (`fortschreiben_jahre` in `konfiguration/indikatoren.json`, je Indikator abschaltbar mit `"fortschreiben": 0`). Die Karte kennzeichnet solche Werte in Legende, Kennzahlen (Sternchen) und Verlauf (gestrichelt, hohle Punkte). Kreise und Gemeinden werden getrennt berechnet, jeweils mit den Indikatoren, die auf der Ebene vorliegen. **Kontextindikatoren** (`"im_index": false`) erscheinen in Karte, Rangliste und Popups, gehen aber nicht in den Index ein. Das ist für Kennzahlen gedacht, bei denen ein hoher Wert weder eindeutig günstig noch ungünstig ist, etwa die Übertrittsquote an die Realschule. Sie werden in einer neutralen Blauskala mit den Polen „niedriger“ und „höher“ gezeigt. Im Datenassistenten lässt sich das je Indikator mit „Im Index berücksichtigen“ umschalten. Auswahl und Gewichtung der Indikatoren sind fachliche Entscheidungen und sollten mit den Nutzern abgestimmt werden.

## Datenschutz und Lizenzen

Die Karte lädt nichts von fremden Servern. Der Assistent stellt nur auf Ihre ausdrückliche Aktion hin Verbindungen her: zur Vorschau an den Regionalatlas-Datenserver (gis-idmz.nrw.de), zum Speichern an api.github.com.

- Statistikdaten: © Statistische Ämter des Bundes und der Länder, Datenlizenz Deutschland – Namensnennung – 2.0
- Schulstandorte: Bayerisches Staatsministerium für Unterricht und Kultus, CC BY 4.0
- Übertrittsquoten und Eignungen: Bayerischer Landtag, Drucksachen 18/3249, 18/16091, 18/23567, 18/30611, 19/5789, 19/7981
- Verwaltungsgrenzen: © GeoBasis-DE / BKG, dl-de/by-2-0
- Leaflet (BSD-2), Chart.js (MIT), Atkinson Hyperlegible (SIL OFL)
- Abfrageaufbau des Regionalatlas nach dem quelloffenen Client maschinenlesbar-org/regionalatlas-cli (MIT)
