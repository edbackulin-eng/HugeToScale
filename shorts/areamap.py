"""Area map engine (owner 19.11): one real place dropped onto a country at true size, like "Texas on France".

    python shorts/areamap.py still <short> <out.png> [--t 0..1]   # one frame (preview)

A topic spec (data/ladder-topics.json, engine "area-map", written by scripts/topics.py):
  over / base: {"layer": adm0|adm1|lake|region, "qid", "name", "km2", "sources": [official, outline]}
The base is always a country. Shapes are Natural Earth (public domain) outlines, each projected with a Lambert
azimuthal equal-area projection centred on itself, so area and shape are true, then the "over" shape is moved onto
the base's centre. The numbers in the captions are the official areas (Wikidata, best rank, with its reference);
the outline must agree with them within 3 % (two sources). Checks written for the Short's sources.json:
  - each outline vs its official area (<= 3 %)
  - the drawn pixel area ratio vs the true outline ratio (<= 1 %)
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import map2d as M  # noqa: E402

W, H, SS = M.W, M.H, M.SS
LAYERS = {"adm0": ("ne_50m_admin_0_countries.geojson", "WIKIDATAID"),
          "adm1": ("ne_10m_admin_1_states_provinces.geojson", "wikidataid"),
          "lake": ("ne_10m_lakes.geojson", "wikidataid"),
          "region": ("ne_10m_geography_regions_polys.geojson", "WIKIDATAID")}
CY = H * 0.5          # map centre on screen
_cache = {}


def features(layer):
    if layer not in _cache:
        f, _ = LAYERS[layer]
        path = M.CACHE / f
        if not path.exists() and (M.CACHE / f.replace("_10m_", "_50m_")).exists():   # local previews only
            path = M.CACHE / f.replace("_10m_", "_50m_")
        _cache[layer] = json.loads(path.read_text(encoding="utf-8"))["features"]
    return _cache[layer]


def feature(layer, qid):
    key = LAYERS[layer][1]
    return next(f for f in features(layer) if f["properties"].get(key) == qid)


def ring_xy(ring, lon0, lat0):
    return [M.laea(lo, la, lon0, lat0) for lo, la in ring]


def shape(geom):
    """Main cluster of a (multi)polygon: the largest part plus the parts near it (far islands / overseas parts dropped).
    Returns rings projected around the cluster's own centre, holes, the outline area (km²) and the kept share."""
    parts = []
    for p in M.polys(geom):
        lo = sum(c[0] for c in p[0]) / len(p[0])
        la = sum(c[1] for c in p[0]) / len(p[0])
        a = M.area(ring_xy(p[0], lo, la)) - sum(M.area(ring_xy(h, lo, la)) for h in p[1:])
        parts.append((a, lo, la, p))
    parts.sort(key=lambda x: -x[0])
    a0, lon0, lat0, _ = parts[0]
    reach = 2.5 * math.sqrt(a0)
    keep, total = [], sum(x[0] for x in parts)
    for a, lo, la, p in parts:
        x, y = M.laea(lo, la, lon0, lat0)
        if math.hypot(x, y) <= reach and a >= 0.0005 * a0:
            keep.append((a, p))
    # re-centre on the kept parts' area centroid
    rings = [ring_xy(p[0], lon0, lat0) for _, p in keep]
    cx, cy = M.centroid(rings)
    kept = sum(a for a, _ in keep)
    return {"outer": [[(x - cx, y - cy) for x, y in r] for r in rings],
            "holes": [[(x - cx, y - cy) for x, y in ring_xy(h, lon0, lat0)] for _, p in keep for h in p[1:]],
            "km2": kept / 1e6, "kept_share": kept / total, "lon0": lon0, "lat0": lat0, "shift": (cx, cy)}


def load(spec_part):
    return shape(feature(spec_part["layer"], spec_part["qid"])["geometry"])


def fit_scale(a, b):
    """px per metre so that both shapes fit: 86 % of the width, 48 % of the height."""
    pts = [p for s in (a, b) for r in s["outer"] for p in r]
    mx = max(abs(x) for x, _ in pts)
    my = max(abs(y) for _, y in pts)
    return min(0.43 * W / mx, 0.24 * H / my)


def _poly(draw, ring, scale, dx=0.0, dy=0.0, **kw):
    draw.polygon([((W / 2 + (x + dx) * scale) * SS, (CY - (y + dy) * scale) * SS) for x, y in ring], **kw)


def frame(spec, t=1.0, scale=None, show_over=True, shapes=None):
    base, over = shapes or (load(spec["base"]), load(spec["over"]))
    scale = scale or fit_scale(base, over)
    img = Image.new("RGB", (W * SS, H * SS))
    top, bot = (18, 120, 215), (8, 70, 165)
    g = Image.new("RGB", (1, 256))
    for i in range(256):
        g.putpixel((0, i), tuple(int(a + (b - a) * i / 255) for a, b in zip(top, bot)))
    img.paste(g.resize((W * SS, H * SS)))
    d = ImageDraw.Draw(img, "RGBA")
    lon0, lat0, (sx, sy) = base["lon0"], base["lat0"], base["shift"]
    view = max(W, H) / scale * 0.75                               # metres from the centre that can be on screen
    for f in features("adm0"):
        if f["properties"]["WIKIDATAID"] == spec["base"]["qid"]:
            continue
        for p in M.polys(f["geometry"]):
            lo = sum(c[0] for c in p[0]) / len(p[0])
            la = sum(c[1] for c in p[0]) / len(p[0])
            cosd = (math.sin(math.radians(la)) * math.sin(math.radians(lat0)) +
                    math.cos(math.radians(la)) * math.cos(math.radians(lat0)) * math.cos(math.radians(lo - lon0)))
            if cosd < 0.5:                                         # > 60° away: off screen, projection unsafe
                continue
            r = [(x - sx, y - sy) for x, y in ring_xy(p[0], lon0, lat0)]
            if min(math.hypot(x, y) for x, y in r) > view:
                continue
            _poly(d, r, scale, fill=(118, 196, 92), outline=(245, 245, 235), width=2 * SS)
    for r in base["outer"]:
        _poly(d, r, scale, fill=(52, 120, 245), outline=(255, 214, 10), width=4 * SS)
    for r in base["holes"]:
        _poly(d, r, scale, fill=(18, 110, 210))
    if show_over:
        off = (1 - t) * 1.6 * H / scale
        shadow = Image.new("L", img.size, 0)
        sd = ImageDraw.Draw(shadow)
        for r in over["outer"]:
            _poly(sd, r, scale, 18 / scale, -26 / scale + off, fill=140)
        shadow = shadow.filter(ImageFilter.GaussianBlur(14 * SS))
        img.paste((10, 20, 40), (0, 0), shadow)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(lay)
        for r in over["outer"]:
            pts = [((W / 2 + x * scale) * SS, (CY - (y + off) * scale) * SS) for x, y in r]
            od.polygon(pts, fill=(255, 112, 10, 205))
            od.line(pts + [pts[0]], fill=(255, 236, 120, 255), width=5 * SS, joint="curve")
        img.paste(lay, (0, 0), lay)
    return img.resize((W, H), Image.LANCZOS)


def checks(spec, shapes):
    base, over = shapes
    out = []
    for role, s in (("over", over), ("base", base)):
        part = spec[role]
        diff = (s["km2"] - part["km2"]) / part["km2"]
        out.append({"object": f"{part['name'].title()} outline {s['km2']:,.0f} km² (Natural Earth) vs official "
                              f"{part['km2']:,} km²", "ok": abs(diff) <= 0.03, "diff_pct": round(100 * diff, 2),
                    "kept_share": round(s["kept_share"], 4)})
    k = 4 * fit_scale(base, over)                                  # raster at 4x the screen: edges count little
    masks = []
    for s in (over, base):
        m = Image.new("L", (W * 4, H * 4), 0)
        md = ImageDraw.Draw(m)
        for r in s["outer"]:
            md.polygon([(2 * W + x * k, 2 * H - y * k) for x, y in r], fill=255)
        for r in s["holes"]:
            md.polygon([(2 * W + x * k, 2 * H - y * k) for x, y in r], fill=0)
        masks.append(sum(m.histogram()[128:]))
    drawn = masks[0] / masks[1]
    true = over["km2"] / base["km2"]
    out.append({"object": f"drawn area ratio {drawn:.4f} vs true outline ratio {true:.4f}",
                "ok": abs(drawn / true - 1) <= 0.01, "diff_pct": round(100 * (drawn / true - 1), 2)})
    return out


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def anim(short, outdir, a, b, step=1):
    import time
    import plan as P
    s = P.SHORTS[short]
    spec = s["area"]
    shapes = (load(spec["base"]), load(spec["over"]))
    final = fit_scale(*shapes)
    t_a, t_land = s["appear"], s["appear"] + 0.7
    t_end = s["seconds"] - s["hold"]
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    t0, n = time.time(), 0
    for f in range(a, b + 1, step):
        t = (f - 1) / P.FPS
        zoom = final * (1.29 + (1 - 1.29) * ease(t / (t_end - 0.6)))
        drop = 0.0 if t < t_a else min(1.0, ((t - t_a) / (t_land - t_a)) ** 2)
        frame(spec, drop, zoom, show_over=t >= t_a, shapes=shapes).save(outdir / f"f{f:04d}.png")
        n += 1
    spf = round((time.time() - t0) / max(n, 1), 2)
    info = {"short": short, "frames": [a, b, step], "checks": checks(spec, shapes), "seconds_per_frame": spf}
    (outdir / f"info_{a:04d}.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    print("area frames", n, spf, "s/frame", json.dumps(info["checks"], ensure_ascii=False))


if __name__ == "__main__" and sys.argv[1] == "still":
    import plan as P
    sp = P.SHORTS[sys.argv[2]]["area"]
    t = float(sys.argv[sys.argv.index("--t") + 1]) if "--t" in sys.argv else 1.0
    sh = (load(sp["base"]), load(sp["over"]))
    frame(sp, t, shapes=sh).save(sys.argv[3])
    print(json.dumps(checks(sp, sh), indent=1, ensure_ascii=False))
