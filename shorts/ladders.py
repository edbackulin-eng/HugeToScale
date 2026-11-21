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
    """Owner 21.11: 15-20 s, a new object every 1-2 s: the first at 0 s, the second at 1.5 s, then one every dt;
    the whole ladder held, then the rewind into the first frame (seamless loop)."""
    dt = 1.9 if n <= 6 else 1.7
    t = [0.0] + [round(1.5 + dt * i, 2) for i in range(n - 1)]
    overview = round(t[-1] + dt, 2)
    rewind = round(max(overview + 2.2, 14.2), 2)
    return t, overview, rewind, round(rewind + 0.8, 2)


def is_object(s):
    """A modelled object (library), not a summit from the DEM."""
    return "lat" not in s


def layout(steps):
    """Objects stand in front (y = 0) from the left, side by side with a gap; summits stand further back, each taller
    one behind and to the right of the last, their footprints never touching (ortho camera: depth never changes a
    size). The approved trio Saturn V / pyramid / Burj keeps its original spacing."""
    import library
    out = []
    x = y = 0.0
    prev_r = 0.0
    objs = [s for s in steps if is_object(s)]
    trio = {"saturnv": 160, "pyramid": 210, "burj": 0}
    mx = -4460.0 if objs and all(s["key"] in trio for s in objs) else 0.0
    prev = None
    for s in steps:
        s = dict(s)
        h = s["h"]
        if is_object(s):
            lib = library.get(s["key"]) or {}
            s.setdefault("w", lib.get("w", 0.2 * h))
            if s["key"] in trio and mx < 0:
                s["x"], s["y"] = mx, 0
                mx += trio[s["key"]]
            else:
                if prev is not None:
                    mx += prev["w"] / 2 + s["w"] / 2 + 0.15 * max(h, prev["h"])
                s["x"], s["y"] = round(mx, 2), 0
            prev = s
        else:
            r_in, r_out = max(0.7 * h, 1500.0), max(1.25 * h, 3500.0)
            half = r_out + 500.0
            px = int(min(720, max(400, 2 * half / 25)))
            if not out or all(is_object(o) for o in out):
                x = (mx + 1500.0 + 0.3 * h) if objs else 0.0
                y = r_out + (2500.0 if objs else 0.0)
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


def short_name(tp):
    return "ladder_" + tp["id"].replace("-", "_")


def register(shorts, ladders, ladder_short):
    for tp in load_topics():
        spec = tp.get("spec")
        if not spec or tp.get("engine") != "peaks":
            continue
        name = "ladder_" + tp["id"].replace("-", "_")
        if name in shorts:
            continue
        ladders[name] = ladder_from_spec(spec)
        if tp.get("type") == "volcanoes":           # dark basalt rock (shorts/ladder.generic_zones)
            for st in ladders[name]["steps"]:
                st["volcanic"] = not is_object(st)
        sh = ladder_short(name)
        sh.update(queries=spec["queries"], titles=spec["titles"], hashtags=spec["hashtags"], intro=spec["intro"],
                  music=episode_music(name) or {"id": "auto", "start": "auto"}, topic=tp["id"])
        shorts[name] = sh
