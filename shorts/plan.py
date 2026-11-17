"""Trial Shorts: timeline, captions, music, titles and sources (pure Python, shared by Blender and compose).

    python shorts/plan.py matrix <shorts,comma> <mode preview|full> <chunks>   # GitHub matrix JSON
    python shorts/plan.py data <short>                                        # fetch the open data

Structure of every Short (owner spec): 1-2 s familiar place -> the object appears at true size before 2 s
-> camera flies around / pulls back -> captions with numbers -> final comparison frame (held, no render).
"""
import json
import subprocess
import sys
from pathlib import Path

FPS = 24
YELLOW = (255, 214, 10)
WHITE = (255, 255, 255)
MUSIC_LIST = "data/music-registry.json"


def track(short):
    """Registry entry of the Short's music (CC0, licence checked on the source page) + start offset."""
    reg = json.loads((Path(__file__).resolve().parents[1] / MUSIC_LIST).read_text(encoding="utf-8"))
    m = SHORTS[short]["music"]
    t = next(x for x in reg["tracks"] if x["id"] == m["id"])
    assert t["status"] == "active", "track removed from rotation"
    return {**t, "start": m["start"]}


def cap(t0, t1, y, *lines):
    """A caption block: lines = (text, size_px, colour); y = centre of the block in the 1080x1920 frame."""
    return {"t0": t0, "t1": t1, "y": y, "lines": [{"text": a, "size": b, "colour": c} for a, b, c in lines]}


SHORTS = {
    "crater_manhattan": {
        "renderer": "blender",
        "seconds": 26.0, "hold": 3.5,        # last 3.5 s = the final comparison frame, held
        "appear": 1.2,                        # the crater forms 1.2 -> 1.9 s
        "data": [["hdri"], ["dem", "meteor_crater", "35.0275", "-111.0225", "1300", "1000"],
                 ["naip", "meteor_crater", "35.0275", "-111.0225", "1300", "2600"],
                 ["naip", "manhattan", "40.7577", "-73.9857", "1500", "3000"],
                 ["naip", "manhattan_wide", "40.7577", "-73.9857", "6000", "3000"],
                 ["water", "manhattan_wide", "40.7577", "-73.9857", "6000", "4000"],
                 ["osm", "midtown", "40.7577", "-73.9857", "2600"]],
        "captions": [
            cap(0.15, 1.15, 330, ("MIDTOWN MANHATTAN", 72, WHITE)),
            cap(2.0, 6.6, 330, ("METEOR CRATER, ARIZONA", 78, WHITE), ("1.2 km WIDE", 120, YELLOW)),
            cap(7.0, 11.6, 330, ("170 m DEEP", 130, YELLOW), ("RIM TO FLOOR", 64, WHITE)),
            cap(12.0, 16.8, 330, ("MADE ABOUT", 70, WHITE), ("50,000 YEARS AGO", 104, YELLOW)),
            cap(22.5, 99, 300, ("WIDER THAN", 84, WHITE), ("CENTRAL PARK", 112, YELLOW),
                ("1.2 km  vs  0.8 km", 70, WHITE)),
        ],
        "music": {"id": "oga-eclipse-legion", "start": 58},
        "queries": ["meteor crater size comparison", "meteor crater arizona", "barringer crater",
                    "new york city size comparison"],
        "titles": ["Meteor Crater Size Comparison: a 1.2 km Hole in Manhattan",
                   "Meteor Crater Arizona Dropped Into New York: 170 m Deep",
                   "Barringer Crater in NYC: 1.2 km Wide, 170 m Deep"],
        "facts": [
            ["Barringer (Meteor) Crater diameter about 1.2 km (1.186 km)",
             "https://www.usgs.gov/centers/astrogeo-sc/science/meteor-crater-sample-collection",
             "measured here on USGS 3DEP: 1,198 m rim crest"],
            ["Depth about 170 m rim to floor", "https://en.wikipedia.org/wiki/Meteor_Crater",
             "measured here on USGS 3DEP: 170 m (USGS gives ~180 m from the highest rim point)"],
            ["Formed about 50,000 years ago",
             "https://www.usgs.gov/centers/astrogeo-sc/science/meteor-crater-sample-collection", None],
            ["Central Park is about 0.8 km (0.5 mi) wide", "https://en.wikipedia.org/wiki/Central_Park", None],
        ],
        "hashtags": ["#sizecomparison", "#meteorcrater", "#newyork", "#3d", "#scale"],
        "intro": "Barringer Meteor Crater from Arizona, placed into Midtown Manhattan at its true size, "
                 "using real elevation data and aerial photos.",
    },
    "saturnv_pyramid": {
        "renderer": "blender",
        "seconds": 24.0, "hold": 3.5,
        "appear": 1.25,                      # Saturn V lands 1.25 -> 1.85 s
        "data": [["hdri"], ["textures", "large_sandstone_blocks", "aerial_sand"]],
        "captions": [
            cap(0.15, 1.2, 330, ("GREAT PYRAMID OF GIZA", 74, WHITE)),
            cap(2.0, 6.4, 330, ("SATURN V", 120, WHITE), ("110.6 m TALL", 104, YELLOW)),
            cap(6.8, 11.4, 330, ("GREAT PYRAMID", 104, WHITE), ("138.5 m TODAY", 104, YELLOW)),
            cap(11.8, 16.6, 330, ("ORIGINALLY", 70, WHITE), ("146.6 m", 130, YELLOW),
                ("BEFORE IT LOST ITS TOP", 60, WHITE)),
            cap(20.0, 99, 300, ("THE PYRAMID IS", 80, WHITE), ("28 m TALLER", 124, YELLOW),
                ("138.5 m  vs  110.6 m", 70, WHITE)),
        ],
        "music": {"id": "oga-the-ancient-legend", "start": 151},
        "queries": ["saturn v size comparison", "great pyramid of giza size comparison", "how big are the pyramids",
                    "great pyramid scale"],
        "titles": ["Saturn V Size Comparison: 110.6 m Next to the Great Pyramid",
                   "How Big Are the Pyramids? 138.5 m vs the Saturn V Rocket",
                   "Great Pyramid Scale: Saturn V Is 28 m Shorter"],
        "facts": [
            ["Saturn V height 110.6 m (363 ft)", "https://www.space.com/saturn-v-rocket-guide-apollo",
             "Wikidata / Wikipedia: 110.6 m"],
            ["Great Pyramid present height 138.5 m, original 146.6 m",
             "https://en.wikipedia.org/wiki/Great_Pyramid_of_Giza",
             "Britannica: originally about 147 m, base about 230 m"],
            ["Great Pyramid base side about 230 m", "https://www.britannica.com/place/Great-Pyramid-of-Giza", None],
        ],
        "hashtags": ["#sizecomparison", "#saturnv", "#pyramid", "#3d", "#scale"],
        "intro": "The Saturn V Moon rocket landed next to the Great Pyramid of Giza, both at true size "
                 "and at the same distance from the camera.",
    },
    "texas_france": {
        "renderer": "map2d",
        "seconds": 22.0, "hold": 4.0,
        "appear": 1.2,                       # Texas drops onto France 1.2 -> 1.9 s
        "data": [["borders"]],
        "captions": [
            cap(0.15, 1.2, 250, ("FRANCE", 96, WHITE)),
            cap(2.0, 6.6, 250, ("TEXAS", 120, YELLOW), ("695,662 km²", 96, WHITE)),
            cap(7.0, 11.6, 250, ("FRANCE", 110, WHITE), ("551,500 km²", 96, YELLOW)),
            cap(12.0, 17.2, 250, ("TEXAS IS", 90, WHITE), ("26% BIGGER", 130, YELLOW)),
            cap(18.0, 99, 250, ("TEXAS  695,662 km²", 78, YELLOW), ("268,596 sq mi", 58, WHITE)),
            cap(18.0, 99, 1340, ("FRANCE  551,500 km²", 70, WHITE), ("212,935 sq mi", 54, WHITE)),
        ],
        "music": {"id": "oga-inevitable", "start": 119},
        "queries": ["texas vs france", "how big is texas compared to europe", "texas compared to other countries",
                    "how big is texas really"],
        "titles": ["Texas vs France: Texas Is 26% Bigger",
                   "How Big Is Texas Really? 695,662 km² on Top of France",
                   "Texas Compared to Europe: Dropped on France (+26%)"],
        "facts": [
            ["Texas total area 695,662 km² (268,596 sq mi)",
             "https://www.census.gov/geographies/reference-files/2010/geo/state-area.html", None],
            ["Metropolitan France 551,500 km² (land + inland waters)",
             "https://unstats.un.org/UNSD/demographic/products/dyb/dyb2013/Table03.pdf", "UN Demographic Yearbook 2013, table 3"],
            ["695,662 / 551,500 = 1.26: Texas is 26% bigger", None, "computed"],
        ],
        "hashtags": ["#sizecomparison", "#texas", "#france", "#maps", "#geography"],
        "intro": "Texas dropped onto France with both shapes in an equal-area projection, so the sizes are true.",
    },
}


# ------------------------------------------------------------------ "size ladder" format (owner 17.11)
# 15-20 s: first object with its number -> every 2-3 s a taller one appears beside it, the camera pulls back
# so all fit -> final: the largest + the whole ladder -> rewind into the first frame (seamless loop).
# Orthographic side view: every object is compared at true scale wherever it stands; a height ruler grows.
LADDERS = {
    "ladder_heights": {
        "steps": [
            {"key": "saturnv", "name": "SATURN V", "value": "111 m", "h": 110.6, "x": -4460, "y": 0, "t": 0.0,
             "sources": ["https://www.space.com/saturn-v-rocket-guide-apollo", "https://en.wikipedia.org/wiki/Saturn_V"]},
            {"key": "pyramid", "name": "GREAT PYRAMID", "value": "139 m", "h": 138.5, "x": -4300, "y": 0, "t": 2.0,
             "sources": ["https://en.wikipedia.org/wiki/Great_Pyramid_of_Giza",
                         "https://www.britannica.com/place/Great-Pyramid-of-Giza"]},
            {"key": "burj", "name": "BURJ KHALIFA", "value": "828 m", "h": 828.0, "x": -4090, "y": 0, "t": 4.6,
             "sources": ["https://burjkhalifa.ae/en/the-tower/facts-figures",
                         "https://www.skyscrapercenter.com/building/burj-khalifa/3"]},
            {"key": "fuji", "name": "MOUNT FUJI", "value": "3,776 m", "h": 3776.0, "x": -2600, "y": 8000, "t": 7.2,
             "dem": ["fuji", "35.3606", "138.7274", "7000", "560"], "r_in": 3500, "r_out": 6500,
             "sources": ["https://www.nippon.com/en/japan-data/h01233/ (GSI data)", "https://en.wikipedia.org/wiki/Mount_Fuji"]},
            {"key": "kili", "name": "KILIMANJARO", "value": "5,895 m", "h": 5895.0, "x": -500, "y": 22000, "t": 9.8,
             "dem": ["kilimanjaro", "-3.0758", "37.3533", "9500", "620"], "r_in": 5000, "r_out": 9000,
             "sources": ["https://en.wikipedia.org/wiki/Mount_Kilimanjaro (TANAPA figure)",
                         "https://worldheritageoutlook.iucn.org/node/1030"]},
            {"key": "everest", "name": "EVEREST", "value": "8,849 m", "h": 8848.86, "x": 3400, "y": 40000, "t": 12.4,
             "dem": ["everest", "27.9881", "86.9250", "11500", "720"], "r_in": 6000, "r_out": 11000,
             "sources": ["https://kathmandupost.com/national/2020/12/08/it-s-official-mount-everest-is-8-848-86-metres-tall",
                         "https://en.wikipedia.org/wiki/Mount_Everest"]},
        ],
        "overview": 15.0,     # the whole ladder, all labelled
        "rewind": 17.2,       # quick rewind into the first frame
        "seconds": 18.0,
        "replaced": {"Olympus Mons (~22 km)": "In a vertical 9:16 frame at true scale it is a 600 km wide, very flat "
                     "shield: framed for its height it fills the frame as a flat wall, framed whole it is a sliver. "
                     "Kept for a wide map-format Short (Olympus Mons over a country); Kilimanjaro takes its step."},
    },
}


def ladder_short(name):
    L = LADDERS[name]
    st = L["steps"]
    caps = []
    for i, s in enumerate(st):
        t1 = st[i + 1]["t"] - 0.12 if i + 1 < len(st) else L["overview"] - 0.1
        caps.append(cap(-1.0 if i == 0 else s["t"] + 0.12, t1, 280, (s["name"], 104, WHITE), (s["value"], 124, YELLOW)))
    s0 = st[0]
    caps.append(cap(L["rewind"] + 0.5, 99, 280, (s0["name"], 104, WHITE), (s0["value"], 124, YELLOW)))
    return {
        "renderer": "blender", "seconds": L["seconds"], "hold": 0.0, "appear": 0.0, "ladder": name,
        "data": [["hdri"]] + [["copdem", *s["dem"]] for s in st if "dem" in s],
        "captions": caps,
        "music": {"id": "oga-inevitable", "start": 119},
        "queries": ["size comparison", "mountain size comparison", "everest size comparison", "burj khalifa vs everest"],
        "titles": ["Size Comparison: 111 m Rocket to 8,849 m Everest",
                   "Burj Khalifa vs Everest: 828 m Next to 8,849 m",
                   "Taller and Taller: Saturn V to Everest in 6 Steps"],
        "facts": [[f"{s['name'].title()}: {s['value']}", s["sources"][0], "second source: " + s["sources"][1]] for s in st],
        "hashtags": ["#sizecomparison", "#everest", "#burjkhalifa", "#3d", "#scale"],
        "intro": "Six real things, each taller than the last, side by side at true scale: Saturn V, the Great "
                 "Pyramid, Burj Khalifa, Mount Fuji, Kilimanjaro and Mount Everest (real elevation data).",
    }


SHORTS["ladder_heights"] = ladder_short("ladder_heights")


def frames(short):
    s = SHORTS[short]
    return round((s["seconds"] - s["hold"]) * FPS)   # rendered frames; the hold is the last frame, repeated


def matrix(names, mode, chunks):
    out = []
    for n in names:
        total = frames(n)
        k = 1 if (mode == "preview" or SHORTS[n]["renderer"] == "map2d") else chunks
        size = -(-total // k)
        for i in range(k):
            a, b = 1 + i * size, min(total, (i + 1) * size)
            out.append({"short": n, "chunk": i, "start": a, "end": b, "renderer": SHORTS[n]["renderer"]})
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "matrix":
        print(json.dumps({"include": matrix([x for x in sys.argv[2].split(",") if x], sys.argv[3], int(sys.argv[4]))}))
    elif cmd == "data":
        for step in SHORTS[sys.argv[2]]["data"]:
            subprocess.run([sys.executable, "shorts/data_prep.py", *step], check=True)
