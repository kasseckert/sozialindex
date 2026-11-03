"""
Erzeugt web/data/kreise.geojson und web/data/gemeinden.geojson aus den
Verwaltungsgrenzen VG250 des BKG (© GeoBasis-DE / BKG, dl-de/by-2-0).

Nur nötig, wenn sich Gebietsstände ändern (z. B. Gemeindefusionen).

Quelle der Grenzen: npm-Paket "german-administrative-areas" (VG250 als
GeoJSON in UTM 32N). Herunterladen und entpacken:
    npm pack german-administrative-areas
    tar xzf german-administrative-areas-*.tgz        → Ordner "package/"
Dann:
    pip install shapely pyproj
    python etl/geodaten_erzeugen.py pfad/zu/package

Alternativ lassen sich die Daten direkt vom BKG (gdz.bkg.bund.de, Produkt
VG250) laden und mit ogr2ogr in GeoJSON umwandeln; die Feldnamen
(AGS, GEN, BEZ, GF) sind identisch.
"""
import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely import transform as shp_transform
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

PRAEFIX = "094"   # Oberfranken
ZIEL = Path(__file__).resolve().parent.parent / "web" / "data"
T = Transformer.from_crs(25832, 4326, always_xy=True)


def merkmale(datei: Path):
    inhalt = json.loads(datei.read_text(encoding="utf-8"))
    teile = inhalt if isinstance(inhalt, list) else [inhalt]
    for x in teile:
        if x["type"] == "Feature":
            yield x
        else:
            yield from x["features"]


def sammeln(datei: Path, toleranz_m: float):
    gruppen = {}
    for f in merkmale(datei):
        p = f["properties"]
        ags = str(p["AGS"])
        if not ags.startswith(PRAEFIX) or p.get("GF") != 4:   # GF 4 = Landfläche
            continue
        gruppen.setdefault(ags, {"p": p, "g": []})["g"].append(shape(f["geometry"]))
    ergebnis = []
    for ags, v in sorted(gruppen.items()):
        geo = unary_union(v["g"]).simplify(toleranz_m, preserve_topology=True)
        geo = shp_transform(geo, lambda xy: list(zip(*T.transform(xy[:, 0], xy[:, 1]))))
        gj = json.loads(json.dumps(mapping(geo)), parse_float=lambda s: round(float(s), 5))
        ergebnis.append({"type": "Feature",
                         "properties": {"ags": ags, "name": v["p"]["GEN"], "bez": v["p"]["BEZ"]},
                         "geometry": gj})
    return ergebnis


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    quelle = Path(sys.argv[1])
    for name, datei, tol in (("kreise", "kreise.geo.json", 120), ("gemeinden", "gemeinden.geo.json", 60)):
        feats = sammeln(quelle / datei, tol)
        ziel = ZIEL / f"{name}.geojson"
        ziel.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{ziel.name}: {len(feats)} Gebiete, {ziel.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
