"""Comparison maps drawn in 2D (Pillow): seconds per frame instead of a 3D render.

    python shorts/map2d.py texas_france <out.png> [--t 0..1]

Natural Earth (public domain) outlines; each shape is projected with a Lambert azimuthal equal-area
projection centred on itself, so area and shape are true, then moved onto the target.
Areas in captions are the official totals (owner 17.11): Texas 695,662 km² (US Census), France
(metropolitan) 543,940 km² (Wikidata Q212429; second official source still to confirm).
"""
import json
import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
CACHE = ROOT / "data/cache"
FONT = str(ROOT / "assets/fonts/Anton-Regular.ttf")
W, H, SS = 1080, 1920, 2
KM2_PER_SQMI = 2.589988110336

R = 6371008.8


def laea(lon, lat, lon0, lat0):
    lam, phi, phi0 = math.radians(lon - lon0), math.radians(lat), math.radians(lat0)
    k = math.sqrt(2 / (1 + math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(lam)))
    return (R * k * math.cos(phi) * math.sin(lam),
            R * k * (math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(lam)))


def polys(geom):
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]


def area(r):
    return abs(0.5 * sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r))))


def centroid(rings):
    a = cx = cy = 0.0
    for r in rings:
        for i in range(len(r)):
            x0, y0 = r[i - 1]; x1, y1 = r[i]
            c = x0 * y1 - x1 * y0
            a += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c
    return cx / (3 * a), cy / (3 * a)


def find(path, **m):
    for f in json.loads(Path(path).read_text(encoding="utf-8"))["features"]:
        if all(str(f["properties"].get(k)) == str(v) for k, v in m.items()):
            return f
    raise KeyError(m)


def text(d, xy, s, size, fill=(255, 255, 255), stroke=(12, 14, 30), anchor="mm"):
    f = ImageFont.truetype(FONT, size * SS)
    d.text((xy[0] * SS, xy[1] * SS), s, font=f, fill=fill, stroke_width=max(2, size * SS // 9),
           stroke_fill=stroke, anchor=anchor)


def texas_france(t=1.0):
    adm0 = CACHE / "ne_50m_admin_0_countries.geojson"
    adm1 = CACHE / "ne_10m_admin_1_states_provinces.geojson"
    lon0, lat0 = 2.4, 46.6
    fr = find(adm0, ADMIN="France")
    tx = find(adm1, name="Texas", admin="United States of America")
    fr_rings = [r for r in ([laea(lo, la, lon0, lat0) for lo, la in p[0]] for p in polys(fr["geometry"]))
                if area(r) > 2e8 and max(abs(x) for x, _ in r) < 1.2e6]
    tx_rings = [r for r in ([laea(lo, la, -99.3, 31.4) for lo, la in p[0]] for p in polys(tx["geometry"]))
                if area(r) > 1e7]
    cfr, ctx = centroid(fr_rings), centroid(tx_rings)
    scale = 1 / 1450.0  # px per metre: Texas (~1,240 km wide) fills ~85 % of the width
    cx, cy = W / 2, H * 0.47

    def px(x, y, dx=0.0, dy=0.0):
        return ((cx + (x - cfr[0] + dx) * scale) * SS, (cy - (y - cfr[1] + dy) * scale) * SS)

    img = Image.new("RGB", (W * SS, H * SS))
    # sea: saturated vertical gradient
    top, bot = (18, 120, 215), (8, 70, 165)
    g = Image.new("RGB", (1, 256))
    for i in range(256):
        g.putpixel((0, i), tuple(int(a + (b - a) * i / 255) for a, b in zip(top, bot)))
    img.paste(g.resize((W * SS, H * SS)))
    d = ImageDraw.Draw(img, "RGBA")
    # neighbouring countries
    for f in json.loads(adm0.read_text(encoding="utf-8"))["features"]:
        if f["properties"]["ADMIN"] == "France":
            continue
        for p in polys(f["geometry"]):
            ll = p[0]
            if not all(-25 < lo < 40 and 30 < la < 72 for lo, la in ll):
                continue
            pts = [px(*laea(lo, la, lon0, lat0)) for lo, la in ll]
            d.polygon(pts, fill=(118, 196, 92), outline=(245, 245, 235), width=2 * SS)
    for r in fr_rings:
        d.polygon([px(x, y) for x, y in r], fill=(52, 120, 245), outline=(255, 214, 10), width=4 * SS)
    # Texas slides in from the top (t: 0 -> 1) and settles on France with a soft shadow
    off = (1 - t) * 900e3
    shadow = Image.new("L", img.size, 0)
    sd = ImageDraw.Draw(shadow)
    for r in tx_rings:
        sd.polygon([px(x, y, cfr[0] - ctx[0] + 25e3, cfr[1] - ctx[1] - 35e3 + off) for x, y in r], fill=140)
    shadow = shadow.filter(ImageFilter.GaussianBlur(14 * SS))
    img.paste((10, 20, 40), (0, 0), shadow)
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    for r in tx_rings:
        pts = [px(x, y, cfr[0] - ctx[0], cfr[1] - ctx[1] + off) for x, y in r]
        od.polygon(pts, fill=(255, 112, 10, 205))
        od.line(pts + [pts[0]], fill=(255, 236, 120, 255), width=5 * SS, joint="curve")
    img.paste(over, (0, 0), over)
    d = ImageDraw.Draw(img)
    tx_km, tx_mi = 695662, 268596  # US Census Bureau, total area (official sq mi figure, not a conversion)
    fr_km = 543940
    fr_mi = round(fr_km / KM2_PER_SQMI)
    if t >= 1.0:
        text(d, (W / 2, 250), "TEXAS", 120, (255, 214, 10))
        text(d, (W / 2, 360), f"{tx_km:,} km²  ·  {tx_mi:,} sq mi", 52)
        text(d, (W / 2, 1330), "FRANCE", 96, (255, 255, 255))
        text(d, (W / 2, 1425), f"{fr_km:,} km²  ·  {fr_mi:,} sq mi", 46)
    out = img.resize((W, H), Image.LANCZOS)
    return out, {"texas_km2": tx_km, "texas_sqmi": tx_mi, "france_km2": fr_km,
                 "france_sqmi": fr_mi,
                 "outline_area_km2": {"texas_ne10m": round(sum(area(r) for r in tx_rings) / 1e6),
                                      "france_ne50m": round(sum(area(r) for r in fr_rings) / 1e6)}}


if __name__ == "__main__":
    name, out = sys.argv[1], Path(sys.argv[2])
    t = float(sys.argv[sys.argv.index("--t") + 1]) if "--t" in sys.argv else 1.0
    t0 = time.time()
    img, info = {"texas_france": texas_france}[name](t)
    img.save(out)
    secs = time.time() - t0
    info.update({"scene": name, "status": "rendered", "render_seconds": round(secs, 2), "fps": 24,
                 "estimate_30s_short": {"frames": 720, "cpu_hours": round(720 * secs / 3600, 2), "jobs_at_4h": 1}})
    out.with_suffix(".json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    print("RENDER", name, round(secs, 2), "s")
