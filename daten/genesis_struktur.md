# Aufbau erkundeter GENESIS-Tabellen

## BY-D12.1i (bildung)

**Titel:** D12.1: Übergange von der Grundschule auf weiterführende Schulen

Regionalvariable: `BY-KRE` · Zeilen: 32980 · Jahre: 2022, 2023, 2024, 2025

- Merkmal 1: **Kreise, kreisfreie Städte und Land** (Region, 96 Kreise)
- Merkmal 2: **Schulart (allgemeinbildend)** (13 Ausprägungen): Mittel-/Hauptschulen; Integrierte Gesamtschulen; Realschulen zur sonderpädagogischen Förderung; Schulartunabhängige Orientierungsstufe; Förderzentren; Freie Waldorfschulen; Realschulen; Gymnasien; Deutsche; Männlich; Insgesamt; Ausländer; Weiblich
- Merkmal 3: **Geschlecht und Nationalität** (6 Ausprägungen): Weiblich; Männlich; Insgesamt; Ausländer; Deutsche; 

Wertspalten (mit Zahl belegter Zeilen):
- `None__None__%` (7473)
- `BY-W03__Schüler/innen, Eingangskl. Sek. I (absolut)__Anzahl` (9413)

Beispiel Bamberg (Stadt):

```
{"Zeit": "2022-P1Y", "1_Auspraegung_Label": "Bamberg", "2_Auspraegung_Label": "Mittel-/Hauptschulen", "3_Auspraegung_Label": "Deutsche", "None__None__%": "10,1"}
{"Zeit": "2022-P1Y", "1_Auspraegung_Label": "Bamberg", "2_Auspraegung_Label": "Mittel-/Hauptschulen", "3_Auspraegung_Label": "Deutsche", "BY-W03__Schüler/innen, Eingangskl. Sek. I (absolut)__Anzahl": "82"}
{"Zeit": "2025-P1Y", "1_Auspraegung_Label": "Bamberg", "2_Auspraegung_Label": "Realschulen", "3_Auspraegung_Label": "Männlich", "None__None__%": "6,5"}
{"Zeit": "2025-P1Y", "1_Auspraegung_Label": "Bamberg", "2_Auspraegung_Label": "Realschulen", "3_Auspraegung_Label": "Männlich", "BY-W03__Schüler/innen, Eingangskl. Sek. I (absolut)__Anzahl": "28"}
{"Zeit": "2023-P1Y", "1_Auspraegung_Label": "Bamberg", "2_Auspraegung_Label": "Realschulen zur sonderpädagogischen Förderung", "3_Auspraegung_Label": "Ausländer", "None__None__%": "-"}
{"Zeit": "2023-P1Y", "1_Auspraegung_Label": "Bamberg", "2_Auspraegung_Label": "Realschulen zur sonderpädagogischen Förderung", "3_Auspraegung_Label": "Ausländer", "BY-W03__Schüler/innen, Eingangskl. Sek. I (absolut)__Anzahl": "-"}
```
