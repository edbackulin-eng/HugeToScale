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
HDRIS = ["kloofendal_43d_clear_puresky", "kloofendal_48d_partly_cloudy_puresky"]  # bright daytime only (owner 17.11)


def fetch(url, data=None, timeout=180, tries=4):
    """GET/POST with retries: public map services (USGS, Overpass) answer 5xx/429 now and then."""
    import time
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise
            print(f"fetch retry {k + 1} after {e}")
            time.sleep(20 * (k + 1))


def record(path, url, licence, page=None):
    CACHE.mkdir(parents=True, exist_ok=True)
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


def mercator_bbox(lat0, lon0, half):
    """Square of 2*half GROUND metres as a Web Mercator (EPSG:3857) bbox.
    A degree bbox (EPSG:4326) is not square in degrees, and the image server widens it to square degree
    pixels: the result is squeezed north-south by cos(latitude) (found 17.11 by the crater size check).
    In Web Mercator, ground metres scale by 1/cos(lat), so a square bbox gives square ground pixels."""
    Rm = 6378137.0
    x = Rm * math.radians(lon0)
    y = Rm * math.log(math.tan(math.pi / 4 + math.radians(lat0) / 2))
    hm = half / math.cos(math.radians(lat0))
    return f"{x - hm},{y - hm},{x + hm},{y + hm}"


def naip(name, lat0, lon0, half, px=3000):
    """USGS NAIP Plus orthoimagery (public domain), a square of 2*half metres around a point."""
    q = urllib.parse.urlencode({"bbox": mercator_bbox(lat0, lon0, half), "bboxSR": 3857,
                                "imageSR": 3857, "size": f"{px},{px}", "format": "jpg", "compressionQuality": 92,
                                "f": "image"})
    url = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage?" + q
    p = CACHE / f"naip_{name}.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(fetch(url, timeout=300))
    (CACHE / f"naip_{name}.json").write_text(json.dumps({"origin": [lat0, lon0], "half_m": half, "px": px}))
    record(p, url.split("?")[0], "public domain (USGS / USDA, The National Map: Orthoimagery)",
           "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits")
    print("naip", name, p.stat().st_size)


def dem(name, lat0, lon0, half, px=1000):
    """USGS 3DEP elevation (public domain), float32 metres on a px x px grid over 2*half metres.
    Saved as raw little-endian float32 (row 0 = north) + json, so Blender reads it without extra packages."""
    import array
    import io

    from PIL import Image
    q = urllib.parse.urlencode({"bbox": mercator_bbox(lat0, lon0, half), "bboxSR": 3857,
                                "imageSR": 3857, "size": f"{px},{px}", "format": "tiff", "pixelType": "F32",
                                "interpolation": "RSP_BilinearInterpolation", "f": "image"})
    url = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?" + q
    im = Image.open(io.BytesIO(fetch(url, timeout=300)))
    vals = array.array("f", (float(v) for v in im.getdata()))
    p = CACHE / f"dem_{name}.f32"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(vals.tobytes())
    (CACHE / f"dem_{name}.json").write_text(json.dumps({"origin": [lat0, lon0], "half_m": half, "px": px,
                                                        "min": min(vals), "max": max(vals)}))
    record(p, url.split("?")[0], "public domain (USGS 3D Elevation Program)",
           "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits")
    print("dem", name, px, round(min(vals), 1), round(max(vals), 1))


def textures(*ids, res="2k"):
    """Poly Haven CC0 PBR textures: diffuse, normal (GL), roughness."""
    out = ROOT / "assets/textures"
    out.mkdir(parents=True, exist_ok=True)
    for tid in ids:
        files = json.loads(fetch(f"https://api.polyhaven.com/files/{tid}"))
        for key, fname in (("Diffuse", "diff"), ("nor_gl", "nor"), ("Rough", "rough"), ("Displacement", "disp")):
            if key not in files:
                continue
            p = out / f"{tid}_{fname}_{res}.jpg"
            if not p.exists():
                p.write_bytes(fetch(files[key][res]["jpg"]["url"]))
        record(out / f"{tid}_diff_{res}.jpg", f"https://polyhaven.com/a/{tid}", "CC0 1.0", "https://polyhaven.com/license")
        print("texture", tid)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "hdri":
        hdri()
    elif cmd == "osm":
        osm(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]))
    elif cmd == "borders":
        borders()
    elif cmd == "dem":
        dem(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), *(int(a) for a in sys.argv[6:7]))
    elif cmd == "naip":
        naip(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), *(int(a) for a in sys.argv[6:7]))
    elif cmd == "textures":
        textures(*sys.argv[2:])
    elif cmd == "nasa":
        nasa(sys.argv[2])
