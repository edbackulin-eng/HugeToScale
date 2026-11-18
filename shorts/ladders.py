"""Size ladders built from data/ladder-topics.json (owner 18.11: the topic queue fills itself, a topic is never repeated).

A topic with a "spec" is renderable by the ladder engine (shorts/ladder.py). Engines:
  peaks  - every step is a real summit (Copernicus DEM GLO-30) or one of the simple models
           saturnv / pyramid / burj (own models from official dimensions).
Topics of other kinds (deeper / longer / area) wait in the file with "engine" naming what they need.

Every step of a spec: key, name, value ("3,776 m"), h (metres), sources (two: Wikidata/official + the DEM measured on
the runner, which must agree within 2 % before a step is used), and lat/lon for a summit.
Layout and timing are computed here, so a spec holds only facts.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ROOT / "data" / "ladder-topics.json"
STATE = ROOT / "state" / "episodes.json"
MODELS = {"saturnv": 110.6, "pyramid": 138.5, "burj": 828.0}


def fmt_value(h):
    return f"{round(h):,} m"


def timing(n):
    """15-20 s: first object at 0 s, the second at 2 s, then one every dt; the whole ladder, then the rewind."""
    dt = 2.6 if n <= 6 else 2.3
    t = [0.0] + [round(2.0 + dt * i, 2) for i in range(n - 1)]
    overview = round(t[-1] + dt, 2)
    rewind = round(overview + 2.2, 2)
    return t, overview, rewind, round(rewind + 0.8, 2)


def layout(steps):
    """Models stand in front (y = 0) on the left; summits stand further back, each taller one behind and to the right of
    the last, their footprints never touching (ortho camera: depth never changes a size)."""
    out = []
    x = y = 0.0
    prev_r = 0.0
    models = [s for s in steps if s["key"] in MODELS]
    mx = -4460.0 if models else 0.0
    for s in steps:
        s = dict(s)
        h = s["h"]
        if s["key"] in MODELS:
            s["x"], s["y"] = mx, 0
            mx += {"saturnv": 160, "pyramid": 210, "burj": 0}[s["key"]]
        else:
            r_in, r_out = max(0.7 * h, 1500.0), max(1.25 * h, 3500.0)
            half = r_out + 500.0
            px = int(min(720, max(400, 2 * half / 25)))
            if not out or all(o["key"] in MODELS for o in out):
                x = (mx + 1500.0 + 0.3 * h) if models else 0.0
                y = r_out + (2500.0 if models else 0.0)
            else:
                x += 0.42 * h
                y += prev_r + r_out
            prev_r = r_out
            s.update(x=round(x), y=round(y), r_in=round(r_in), r_out=round(r_out), half_w=round(0.25 * h),
                     dem=[s["key"], f"{s['lat']:.5f}", f"{s['lon']:.5f}", str(int(half)), str(px)])
        out.append(s)
    return out


def ladder_from_spec(spec):
    steps = layout(spec["steps"])
    t, overview, rewind, seconds = timing(len(steps))
    for s, ti in zip(steps, t):
        s["t"] = ti
        s.setdefault("value", fmt_value(s["h"]))
    return {"steps": steps, "overview": overview, "rewind": rewind, "seconds": seconds}


def load_topics():
    return json.loads(TOPICS.read_text(encoding="utf-8"))["topics"]


def episode_music(short):
    """Music the production run assigned to this episode (state/episodes.json), else None."""
    if not STATE.exists():
        return None
    for e in json.loads(STATE.read_text(encoding="utf-8"))["episodes"]:
        if e["short"] == short and e.get("music"):
            return e["music"]
    return None


def km2_to_sqmi(k):
    return round(k / 2.589988110336)


def fit(text, size, width=980):
    return min(size, int(width / (0.47 * max(1, len(text)))))


def area_short(tp):
    """'Texas on France' format for an area-map topic: the base country, the place dropped onto it, both numbers,
    the difference in %, the final frame with both areas (official figures, sq mi converted)."""
    from plan import cap, WHITE, YELLOW
    sp = tp["spec"]
    o, b = sp["over"], sp["base"]
    O, B = o["name"].upper(), b["name"].upper()
    pct = round(100 * (o["km2"] / b["km2"] - 1))
    verdict = (f"{pct}% BIGGER" if pct >= 5 else f"{-pct}% SMALLER" if pct <= -5 else "ALMOST THE SAME")
    caps = [cap(0.15, 1.2, 250, (B, fit(B, 96), WHITE)),
            cap(2.0, 6.6, 250, (O, fit(O, 120), YELLOW), (f"{o['km2']:,} km²", 96, WHITE)),
            cap(7.0, 11.6, 250, (B, fit(B, 110), WHITE), (f"{b['km2']:,} km²", 96, YELLOW)),
            cap(12.0, 17.2, 250, (f"{O} IS", fit(O + " IS", 90), WHITE), (verdict, fit(verdict, 130), YELLOW)),
            cap(18.0, 99, 250, (f"{O}  {o['km2']:,} km²", fit(O + "  000,000 km²", 78), YELLOW),
                (f"{km2_to_sqmi(o['km2']):,} sq mi", 58, WHITE)),
            cap(18.0, 99, 1340, (f"{B}  {b['km2']:,} km²", fit(B + "  000,000 km²", 70), WHITE),
                (f"{km2_to_sqmi(b['km2']):,} sq mi", 54, WHITE))]
    return {"renderer": "map2d", "seconds": 22.0, "hold": 4.0, "appear": 1.2, "area": sp,
            "data": [["borders"], ["ne", "ne_10m_lakes"], ["ne", "ne_10m_geography_regions_polys"]],
            "captions": caps, "queries": sp["queries"], "titles": sp["titles"], "hashtags": sp["hashtags"],
            "intro": sp["intro"],
            "facts": [[f"{o['name']} area {o['km2']:,} km²", o["sources"][0], "outline: " + o["sources"][1]],
                      [f"{b['name']} area {b['km2']:,} km²", b["sources"][0], "outline: " + b["sources"][1]],
                      [f"{o['km2']:,} / {b['km2']:,} = {o['km2'] / b['km2']:.2f}", None, "computed"],
                      ["sq mi converted from km² (1 sq mi = 2.589988 km²)", None, "computed"]],
            "topic": tp["id"]}


def short_name(tp):
    return {"peaks": "ladder_", "area-map": "map_"}[tp["engine"]] + tp["id"].replace("-", "_")


def register(shorts, ladders, ladder_short):
    for tp in load_topics():
        spec = tp.get("spec")
        if spec and tp.get("engine") == "area-map":
            name = short_name(tp)
            if name not in shorts:
                shorts[name] = {**area_short(tp), "music": episode_music(name) or {"id": "auto", "start": "auto"}}
            continue
        if not spec or tp.get("engine") != "peaks":
            continue
        name = "ladder_" + tp["id"].replace("-", "_")
        if name in shorts:
            continue
        ladders[name] = ladder_from_spec(spec)
        sh = ladder_short(name)
        sh.update(queries=spec["queries"], titles=spec["titles"], hashtags=spec["hashtags"], intro=spec["intro"],
                  music=episode_music(name) or {"id": "auto", "start": "auto"}, topic=tp["id"])
        shorts[name] = sh
