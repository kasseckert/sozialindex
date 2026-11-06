"""
Optional: Erzeugt vorschau.html, eine einzelne Datei mit allen Skripten,
Schriften und Daten. Sie lässt sich ohne Webserver per Doppelklick öffnen,
z. B. zum Versenden an Kolleginnen und Kollegen.

Für den Betrieb auf dem Webserver wird sie nicht gebraucht.
"""
import base64
import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
ZIEL = Path(__file__).resolve().parent.parent / "vorschau.html"


def main():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")

    def schrift(m):
        pfad = WEB / m.group(1)
        b64 = base64.b64encode(pfad.read_bytes()).decode()
        return f'url("data:font/woff2;base64,{b64}")'
    css = re.sub(r'url\("(fonts/[^"]+)"\)', schrift, css)

    leaflet_css = (WEB / "vendor/leaflet/leaflet.css").read_text(encoding="utf-8")
    daten = {
        "kreise": json.loads((WEB / "data/kreise.geojson").read_text(encoding="utf-8")),
        "werte": json.loads((WEB / "data/werte.json").read_text(encoding="utf-8")),
        "gemeinden": {
            p.stem: {"geo": json.loads(p.read_text(encoding="utf-8")),
                     "werte": json.loads((WEB / "data/werte_gemeinden" / f"{p.stem}.json").read_text(encoding="utf-8"))}
            for p in sorted((WEB / "data/gemeinden").glob("*.geojson"))
        },
        "schulen": {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((WEB / "data/schulen").glob("*.geojson"))},
    }
    skript = lambda p: (WEB / p).read_text(encoding="utf-8").replace("</script", "<\\/script")

    html = html.replace('<link rel="stylesheet" href="vendor/leaflet/leaflet.css">',
                        f"<style>{leaflet_css}</style>")
    html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>{css}</style>")
    html = html.replace('<script src="vendor/leaflet/leaflet.js"></script>',
                        f"<script>{skript('vendor/leaflet/leaflet.js')}</script>")
    html = html.replace('<script src="vendor/chartjs/chart.umd.js"></script>',
                        f"<script>{skript('vendor/chartjs/chart.umd.js')}</script>")
    html = html.replace('<script src="app.js"></script>',
                        "<script>window.__SOZIALINDEX__=" + json.dumps(daten, ensure_ascii=False,
                        separators=(",", ":")).replace("</", "<\\/") + ";</script>\n"
                        f"<script>{skript('app.js')}</script>")
    ZIEL.write_text(html, encoding="utf-8")
    print(f"Geschrieben: {ZIEL.name} ({ZIEL.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
