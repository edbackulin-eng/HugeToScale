"""Download and prepare open data for a Short (plain Python, no extra packages).

    python shorts/data_prep.py hdri                    # Poly Haven HDRIs (CC0)
    python shorts/data_prep.py osm <name> <lat> <lon> <radius_m>
    python shorts/data_prep.py borders                 # Natural Earth 1:50m (public domain)
    python shorts/data_prep.py nasa "<model folder>"   # NASA 3D Resources .glb

Everything lands in data/cache/ (git-ignored); every download is listed in data/cache/fetched.json
with URL, licence and date, so a Short's sources.json can be built from it.
"""
import datetime as dt
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cache"
UA = {"User-Agent": "HugeToScale-build/0.1 (+https://github.com/edbackulin-eng/HugeToScale)"}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
HDRIS = ["kloofendal_48d_partly_cloudy_puresky", "spruit_sunrise", "kloppenheim_06_puresky"]


def fetch(url, data=None, timeout=180):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def record(path, url, licence, page=None):
    log = CACHE / "fetched.json"
    items = json.loads(log.read_text()) if log.exists() else {}
    items[str(Path(path).relative_to(ROOT)).replace("\\", "/")] = {
        "url": url, "licence": licence, "licence_page": page, "date": dt.date.today().isoformat()}
    log.write_text(json.dumps(items, indent=1))


def hdri():
    out = ROOT / "assets/hdri"
    out.mkdir(parents=True, exist_ok=True)
    for hid in HDRIS:
        p = out / f"{hid}_2k.hdr"
        if p.exists():
            continue
        files = json.loads(fetch(f"https://api.polyhaven.com/files/{hid}"))
        url = files["hdri"]["2k"]["hdr"]["url"]
        p.write_bytes(fetch(url))
        record(p, f"https://polyhaven.com/a/{hid}", "CC0 1.0", "https://polyhaven.com/license")
        print("hdri", p.name)


def local_xy(lat, lon, lat0, lon0):
    return ((lon - lon0) * math.cos(math.radians(lat0)) * 111320.0, (lat - lat0) * 110574.0)


def parse_height(tags):
    def num(v):
        try:
            return float(str(v).lower().replace("m", "").replace(",", ".").split(";")[0].strip())
        except ValueError:
            return None
    h = num(tags.get("height")) if tags.get("height") else None
    if h is None and tags.get("building:levels"):
        lv = num(tags["building:levels"])
        h = lv * 3.4 + 2 if lv else None
    mh = num(tags.get("min_height")) if tags.get("min_height") else None
    if mh is None and tags.get("building:min_level"):
        ml = num(tags["building:min_level"])
        mh = ml * 3.4 if ml else None
    return h, mh or 0.0


def osm(name, lat0, lon0, radius):
    """Buildings, building parts and water around a point, in local metres (x east, y north)."""
    dlat = radius / 110574.0
    dlon = radius / (111320.0 * math.cos(math.radians(lat0)))
    bbox = f"{lat0 - dlat},{lon0 - dlon},{lat0 + dlat},{lon0 + dlon}"
    q = f"""[out:json][timeout:120];
(way["building"]({bbox});way["building:part"]({bbox});relation["building"]({bbox});
 way["natural"="water"]({bbox});relation["natural"="water"]({bbox});way["highway"]["area"!="yes"]({bbox}););
out geom tags;"""
    data = None
    for url in OVERPASS:
        try:
            data = json.loads(fetch(url, urllib.parse.urlencode({"data": q}).encode()))
            break
        except Exception as e:  # noqa: BLE001 — try the mirror
            print("overpass failed:", url, e)
    if data is None:
        raise SystemExit("Overpass unreachable")
    feats = []
    for el in data["elements"]:
        tags = el.get("tags", {})
        rings = []
        if el["type"] == "way" and "geometry" in el:
            rings = [el["geometry"]]
        elif el["type"] == "relation":
            rings = [m["geometry"] for m in el.get("members", []) if m.get("role") == "outer" and "geometry" in m]
        for g in rings:
            pts = [local_xy(p["lat"], p["lon"], lat0, lon0) for p in g]
            if "highway" in tags:
                kind = "road"
            elif tags.get("natural") == "water":
                kind = "water"
            elif "building:part" in tags:
                kind = "part"
            else:
                kind = "building"
            h, mh = parse_height(tags)
            feats.append({"kind": kind, "id": f'{el["type"]}/{el["id"]}', "name": tags.get("name"),
                          "height": h, "min_height": mh, "highway": tags.get("highway"),
                          "lanes": tags.get("lanes"), "colour": tags.get("building:colour"),
                          "pts": [[round(x, 2), round(y, 2)] for x, y in pts]})
    out = CACHE / f"osm_{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"origin": [lat0, lon0], "radius": radius, "features": feats}))
    record(out, f"https://www.openstreetmap.org/#map=17/{lat0}/{lon0}", "ODbL 1.0 — © OpenStreetMap contributors",
           "https://www.openstreetmap.org/copyright")
    n = {k: sum(f["kind"] == k for f in feats) for k in ("building", "part", "water", "road")}
    print("osm", name, n)


NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"


def borders():
    for f in ("ne_50m_admin_0_countries.geojson", "ne_50m_admin_1_states_provinces.geojson",
              "ne_10m_admin_1_states_provinces.geojson"):
        p = CACHE / f
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(fetch(NE + f))
            record(p, NE + f, "public domain (Natural Earth)", "https://www.naturalearthdata.com/about/terms-of-use/")
        print("borders", f)


def nasa(folder):
    base = "https://raw.githubusercontent.com/nasa/NASA-3D-Resources/master/3D%20Models/"
    url = base + urllib.parse.quote(folder) + "/" + urllib.parse.quote(folder) + ".glb"
    p = ROOT / "assets/models" / f"{folder}.glb"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_bytes(fetch(url))
    record(p, url, "NASA 3D Resources: free and without copyright; NASA media usage guidelines "
                   "(no endorsement implied, no NASA insignia)",
           "https://www.nasa.gov/nasa-brand-center/images-and-media")
    print("nasa", p.name, p.stat().st_size)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "hdri":
        hdri()
    elif cmd == "osm":
        osm(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]))
    elif cmd == "borders":
        borders()
    elif cmd == "nasa":
        nasa(sys.argv[2])
