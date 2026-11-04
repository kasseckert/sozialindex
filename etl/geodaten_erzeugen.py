"""
Erzeugt die Geodaten der Karte aus den Verwaltungsgrenzen VG250 des BKG
(© GeoBasis-DE / BKG, dl-de/by-2-0):

  web/data/kreise.geojson              alle Kreise des Landes
  web/data/gemeinden/<region>.geojson  Gemeinden je Region (Aufsichtsbezirk)

Die Regionen kommen aus konfiguration/gebiete.json. Nur nötig bei
Gebietsreformen oder geänderter Gliederung.

Quelle der Grenzen: npm-Paket "german-administrative-areas" (VG250 als GeoJSON
in UTM 32N):
    npm pack german-administrative-areas && tar xzf german-administrative-areas-*.tgz
    pip install shapely pyproj
    python etl/geodaten_erzeugen.py package
"""
import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely import transform as shp_transform
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from gebiete import LAND, REGIONEN, region_von

ZIEL = Path(__file__).resolve().parent.parent / "web" / "data"
T = Transformer.from_crs(25832, 4326, always_xy=True)


def merkmale(datei: Path):
    inhalt = json.loads(datei.read_text(encoding="utf-8"))
    for x in (inhalt if isinstance(inhalt, list) else [inhalt]):
        if x["type"] == "Feature":
            yield x
        else:
            yield from x["features"]


def sammeln(datei: Path, toleranz_m: float):
    gruppen = {}
    for f in merkmale(datei):
        p = f["properties"]
        ags = str(p["AGS"])
        if not ags.startswith(LAND["praefix"]) or p.get("GF") != 4:   # GF 4 = Landfläche
            continue
        gruppen.setdefault(ags, {"p": p, "g": []})["g"].append(shape(f["geometry"]))
    ergebnis = []
    for ags, v in sorted(gruppen.items()):
        geo = unary_union(v["g"]).simplify(toleranz_m, preserve_topology=True)
        geo = shp_transform(geo, lambda xy: list(zip(*T.transform(xy[:, 0], xy[:, 1]))))
        gj = json.loads(json.dumps(mapping(geo)), parse_float=lambda s: round(float(s), 4))
        region = region_von(ags)
        if region is None:
            raise SystemExit(f"Kreis {ags[:5]} ist in konfiguration/gebiete.json keiner Region zugeordnet.")
        ergebnis.append({"type": "Feature",
                         "properties": {"ags": ags, "name": v["p"]["GEN"], "bez": v["p"]["BEZ"], "region": region},
                         "geometry": gj})
    return ergebnis


def schreiben(pfad: Path, feats):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{pfad.relative_to(ZIEL.parent.parent)}: {len(feats)} Gebiete, {pfad.stat().st_size / 1024:.0f} KB")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    quelle = Path(sys.argv[1])
    schreiben(ZIEL / "kreise.geojson", sammeln(quelle / "kreise.geo.json", 120))
    gemeinden = sammeln(quelle / "gemeinden.geo.json", 100)
    for r in REGIONEN:
        schreiben(ZIEL / "gemeinden" / f"{r['id']}.geojson", [f for f in gemeinden if f["properties"]["region"] == r["id"]])
    alt = ZIEL / "gemeinden.geojson"
    if alt.exists():
        alt.unlink()
        print("Alte Datei web/data/gemeinden.geojson entfernt.")


if __name__ == "__main__":
    main()
