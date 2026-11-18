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
import urllib.error
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
            if k == tries - 1 or (isinstance(e, urllib.error.HTTPError) and e.code in (403, 404)):
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


COPDEM = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{t}_DEM/Copernicus_DSM_COG_10_{t}_DEM.tif"
COPDEM_LICENCE = ("Copernicus DEM GLO-30: produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus "
                  "Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved")


def copdem(name, lat0, lon0, half, px=600):
    """Copernicus DEM GLO-30 (free licence, attribution above) on a px x px local metric grid of 2*half metres
    around a summit (row 0 = north). Needs numpy + rasterio (runner only). Saved like dem(): raw float32 + json."""
    import numpy as np
    import rasterio
    dlat = half / 110574.0
    dlon = half / (111320.0 * math.cos(math.radians(lat0)))
    g = np.linspace(-1, 1, px)
    lat = lat0 - g[:, None] * dlat + 0 * g[None, :]
    lon = lon0 + g[None, :] * dlon + 0 * g[:, None]
    out = np.full((px, px), np.nan, dtype=np.float64)
    tiles = set()
    for la in np.unique(np.floor(lat)):
        for lo in np.unique(np.floor(lon)):
            tiles.add((int(la), int(lo)))
    urls = []
    for la, lo in sorted(tiles):
        t = f"{'N' if la >= 0 else 'S'}{abs(la):02d}_00_{'E' if lo >= 0 else 'W'}{abs(lo):03d}_00"
        url = COPDEM.format(t=t)
        urls.append(url)
        try:
            raw = fetch(url, timeout=300)
        except urllib.error.HTTPError as e:     # GLO-30 has no tile over open sea: that part is sea level
            if e.code not in (403, 404):
                raise
            print("copdem: no tile", t, "(sea)")
            out[(np.floor(lat) == la) & (np.floor(lon) == lo)] = 0.0
            urls.pop()
            continue
        with rasterio.MemoryFile(raw) as mf, mf.open() as ds:
            z = ds.read(1).astype(np.float64)
            inv = ~ds.transform
            m = (np.floor(lat) == la) & (np.floor(lon) == lo)
            c, r = inv * (lon[m], lat[m])
            c = np.clip(c - 0.5, 0, z.shape[1] - 1.001); r = np.clip(r - 0.5, 0, z.shape[0] - 1.001)
            i, j = r.astype(int), c.astype(int); fr, fc = r - i, c - j
            out[m] = ((z[i, j] * (1 - fc) + z[i, j + 1] * fc) * (1 - fr)
                      + (z[i + 1, j] * (1 - fc) + z[i + 1, j + 1] * fc) * fr)
    out = np.nan_to_num(out, nan=0.0).astype("<f4")
    p = CACHE / f"dem_{name}.f32"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(out.tobytes())
    # the summit: highest DEM value within 1.5 km of the given point
    yy, xx = np.meshgrid(g * half, g * half, indexing="ij")
    near = np.hypot(xx, yy) < 1500
    k = np.argmax(np.where(near, out, -1e9))
    (CACHE / f"dem_{name}.json").write_text(json.dumps({
        "origin": [lat0, lon0], "half_m": half, "px": px, "min": float(out.min()), "max": float(out.max()),
        "summit_m": float(out.flat[k]), "summit_xy": [float(xx.flat[k]), float(-yy.flat[k])], "tiles": urls}))
    record(p, urls[0], COPDEM_LICENCE, "https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model")
    print("copdem", name, px, "summit", round(float(out.flat[k]), 1))


def overpass(q):
    for url in OVERPASS:
        try:
            return json.loads(fetch(url, urllib.parse.urlencode({"data": q}).encode()))
        except Exception as e:  # noqa: BLE001 — try the mirror
            print("overpass failed:", url, e)
    raise SystemExit("Overpass unreachable")


def ll_bbox(lat0, lon0, half):
    dlat = half / 110574.0
    dlon = half / (111320.0 * math.cos(math.radians(lat0)))
    return f"{lat0 - dlat},{lon0 - dlon},{lat0 + dlat},{lon0 + dlon}"


def water(name, lat0, lon0, half, px=4000):
    """Water mask (white = water) on the same square as naip(name, ...): OSM coastline (sea, tidal rivers
    such as the Hudson and East River) + natural=water areas. Needs shapely (runner: pip install shapely).
    Coastline ways keep land on their LEFT; faces cut out by the coastline are classified by that rule."""
    from PIL import Image, ImageDraw, ImageFilter
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import linemerge, polygonize, unary_union
    pad = half * 1.15
    d = overpass(f"""[out:json][timeout:180];
(way["natural"="coastline"]({ll_bbox(lat0, lon0, pad)});way["natural"="water"]({ll_bbox(lat0, lon0, pad)});
 relation["natural"="water"]({ll_bbox(lat0, lon0, pad)}););out geom tags;""")

    def xy(g):
        return [local_xy(p["lat"], p["lon"], lat0, lon0) for p in g]
    frame = box(-pad, -pad, pad, pad)
    coast, areas = [], []
    for el in d["elements"]:
        t = el.get("tags", {})
        if el["type"] == "way" and t.get("natural") == "coastline":
            coast.append(LineString(xy(el["geometry"])))
        elif el["type"] == "way" and len(el.get("geometry", [])) >= 4:
            areas.append(Polygon(xy(el["geometry"])).buffer(0))
        elif el["type"] == "relation":
            outer = [LineString(xy(m["geometry"])) for m in el.get("members", []) if m.get("role") == "outer" and "geometry" in m]
            inner = [LineString(xy(m["geometry"])) for m in el.get("members", []) if m.get("role") == "inner" and "geometry" in m]
            po = unary_union(list(polygonize(linemerge(outer)))) if outer else None
            if po is not None and not po.is_empty:
                pi = unary_union(list(polygonize(linemerge(inner)))) if inner else None
                areas.append(po.difference(pi) if pi is not None and not pi.is_empty else po)
    sea = []
    if coast:
        merged = linemerge(coast)
        lines = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        cut = unary_union([ln.intersection(frame) for ln in lines] + [frame.boundary])
        for face in polygonize(cut):
            p = face.representative_point()
            ln = min(lines, key=lambda L: L.distance(p))
            s = ln.project(p)
            a, b = ln.interpolate(max(s - 2, 0)), ln.interpolate(min(s + 2, ln.length))
            q = ln.interpolate(s)
            cross = (b.x - a.x) * (p.y - q.y) - (b.y - a.y) * (p.x - q.x)
            if cross < 0:  # right of the coastline = water
                sea.append(face)
    wat = unary_union(sea + areas).intersection(box(-half, -half, half, half))
    img = Image.new("L", (px, px), 0)
    dr = ImageDraw.Draw(img)

    def to_px(c):
        return [((x + half) / (2 * half) * px, (half - y) / (2 * half) * px) for x, y in c]
    for g in getattr(wat, "geoms", [wat]):
        if g.is_empty or g.geom_type != "Polygon":
            continue
        dr.polygon(to_px(g.exterior.coords), fill=255)
        for r in g.interiors:
            dr.polygon(to_px(r.coords), fill=0)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    p = CACHE / f"water_{name}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
    record(p, f"https://www.openstreetmap.org/#map=14/{lat0}/{lon0}", "ODbL 1.0 — © OpenStreetMap contributors",
           "https://www.openstreetmap.org/copyright")
    print("water", name, round(wat.area / 4 / half / half * 100, 1), "% of the square")


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
    elif cmd == "copdem":
        copdem(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), *(int(a) for a in sys.argv[6:7]))
    elif cmd == "water":
        water(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), *(int(a) for a in sys.argv[6:7]))
    elif cmd == "textures":
        textures(*sys.argv[2:])
    elif cmd == "nasa":
        nasa(sys.argv[2])
