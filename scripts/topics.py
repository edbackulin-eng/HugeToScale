"""Keep the size-ladder topic queue full (owner 18.11): always 30+ planned topics, only realistic objects with open data,
a topic never repeats. New topics go into data/ladder-topics.json (the owner can review it). Runs on a runner
(topics.yml, weekly) - it downloads DEM tiles.

    python scripts/topics.py            # resolve approved topics, verify summits, add new topics until the queue is full
    python scripts/topics.py --dry      # print what would be added, write nothing

Engines (what can be made automatically today):
  peaks     - real summits (Copernicus DEM relief) - READY: such a topic gets a "spec" and goes into production.
  area-map  - a place dropped onto a country at true size (US states, islands, lakes, deserts) - READY since 19.11
              (scripts/area_topics.py, shorts/areamap.py).
A topic of a non-ready engine waits in the file ("engine" names what it needs) and is never scheduled.

Two sources for every height: Wikidata (best-rank elevation, normalised to metres; the English Wikipedia article is
linked too) and Copernicus DEM GLO-30 measured here: a summit whose DEM top differs by more than 2 % is not used.
Titles come from real YouTube autocomplete (suggestqueries), <= 60 characters, with a number.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shorts"))
sys.path.insert(0, str(ROOT / "scripts"))
TOPICS = ROOT / "data" / "ladder-topics.json"
VERIFIED = ROOT / "data" / "peaks-verified.json"
UA = {"User-Agent": "HugeToScale-topics/1.0 (https://github.com/edbackulin-eng/HugeToScale)"}
MIN_PLANNED = 32          # owner: 30+ topics ahead (margin 2)
MIN_READY = 20            # of them renderable today (20 days of Shorts)
MIN_AREA = 12             # of them area-map topics (owner 19.11: no more than 2 mountain ladders in a row)
MAX_SHARED = 2            # a new topic shares at most 2 objects with any earlier topic
RATIO = 1.18              # each step at least 18 % taller than the one before
VOLCANO = {"Q8072", "Q169358", "Q212057", "Q190869", "Q2120095"}

PEAKS_SPARQL = """
SELECT ?item ?itemLabel ?elev ?coord ?country ?countryLabel ?range ?rangeLabel ?links ?article WHERE {
  ?item wdt:P31 wd:%s; wikibase:sitelinks ?links.
  FILTER(?links >= 12)
  ?item wdt:P625 ?coord; wdt:P17 ?country; p:P2044/psn:P2044/wikibase:quantityAmount ?elev.
  OPTIONAL { ?item wdt:P4552 ?range. }
  ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}"""
PEAK_CLASSES = ["Q8502", "Q8072", "Q169358", "Q212057", "Q207326"]   # mountain, volcano, strato-, shield volcano, summit

def get(url, data=None, tries=4, timeout=120):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:                                       # noqa: BLE001
            if k == tries - 1:
                raise
            print(f"retry {k + 1}: {str(e)[:120]}")
            time.sleep(15 * (k + 1))


def sparql(q):
    body = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    for k in range(4):         # the query service sometimes cuts a long answer off mid-stream (invalid JSON)
        try:
            r = json.loads(get("https://query.wikidata.org/sparql", data=body, timeout=180))
            break
        except json.JSONDecodeError as e:
            if k == 3:
                raise
            print(f"sparql answer cut off ({e}); retry")
            time.sleep(30 * (k + 1))
    return [{k: v["value"] for k, v in b.items()} for b in r["results"]["bindings"]]


def qid(uri):
    return uri.rsplit("/", 1)[-1]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def suggest(q):
    """Real YouTube search suggestions for q."""
    url = "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=" + urllib.parse.quote(q)
    try:
        return json.loads(get(url, tries=2, timeout=30).decode("utf-8", "replace"))[1]
    except Exception as e:                                           # noqa: BLE001
        print("suggest failed:", q, str(e)[:80])
        return []


GOOD = re.compile(r"\b(tallest|highest|biggest|largest|height|heights|size|compar\w*|summits?|peaks?|volcano(es)?|mountains?)\b")
BAD = re.compile(r"\b(feet|ft|biking|bike|ski|skiing|hike|hiking|trail|map|music|song|movie|film|fire|game|drawing|"
                 r"live|news|eruption|erupting|trip|tour|vlog|death|deaths|died|climb|climbing|weather|ranges?|video|view|km|meters?|simulator|tamil|hindi|urdu|telugu|bangla|increasing|measurement|"
                 r"shorts|explained|facts|documentary|names?|list|how|why|what|when)\b")

SMALL = {"a", "an", "and", "of", "in", "on", "the", "to", "vs", "vs.", "at", "by", "for", "from"}


def title_case(s):
    w = s.split()
    return " ".join(x if any(c.isupper() for c in x[1:]) else (x if i and x in SMALL else x[:1].upper() + x[1:])
                    for i, x in enumerate(w)).replace(" Us ", " US ").replace(" Us:", " US:").replace(" Uk ", " UK ").replace(" Uk:", " UK:")


# ------------------------------------------------------------------------------------------------ peaks

def load_peaks():
    seen = {}
    rows = []
    for cls in PEAK_CLASSES:       # one query per class: a single query with all classes times out
        rows += [{**r, "cls": cls} for r in sparql(PEAKS_SPARQL % cls)]
    for r in rows:
        q = qid(r["item"])
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", r["coord"])
        if not m or re.match(r"^Q\d+$", r["itemLabel"]):
            continue
        p = seen.setdefault(q, {"qid": q, "name": r["itemLabel"], "h": round(float(r["elev"]), 2),
                                "lon": float(m.group(1)), "lat": float(m.group(2)), "links": int(r["links"]),
                                "countries": set(), "ranges": set(), "volcano": False, "article": r["article"]})
        p["countries"].add(r["countryLabel"])
        if r.get("rangeLabel") and not re.match(r"^Q\d+$", r["rangeLabel"]):
            p["ranges"].add(r["rangeLabel"])
        p["volcano"] |= r["cls"] in VOLCANO
        v = round(float(r["elev"]), 2)
        prec = lambda x: len(f"{x:g}".split(".")[1]) if "." in f"{x:g}" else -len(f"{x:g}") + len(f"{x:g}".rstrip("0"))
        if prec(v) > prec(p["h"]) or (prec(v) == prec(p["h"]) and v > p["h"]):
            p["h"] = v
    for p in seen.values():
        # Crimea is Ukraine (Wikidata lists Russia too for occupied Crimea): never "mountains of Russia"
        if "Ukraine" in p["countries"] or (44.3 <= p["lat"] <= 46.3 and 32.4 <= p["lon"] <= 36.7):
            p["countries"] = {"Ukraine"}
    return list(seen.values())


def pick_steps(cands, n_max=6, n_min=5):
    """From the tallest down: each next one at most top/RATIO, the most famous in its band; 5-6 steps, wide range."""
    cands = sorted(cands, key=lambda p: -p["h"])
    if not cands:
        return []
    out = [cands[0]]
    while len(out) < n_max:
        lim = out[-1]["h"] / RATIO
        band = [p for p in cands if lim / 1.9 <= p["h"] <= lim]
        if not band:
            break
        out.append(max(band, key=lambda p: (p["links"], p["h"])))
    out = out[::-1]
    return out if len(out) >= n_min and out[-1]["h"] / out[0]["h"] >= 2.0 else []


def dem_check(p, verified):
    """Second source: the Copernicus DEM top within 1.5 km of the Wikidata point, within 2 %."""
    if p["qid"] in verified:
        return verified[p["qid"]]["ok"]
    import data_prep
    try:
        data_prep.copdem(f"v_{p['qid']}", p["lat"], p["lon"], 1600, 128)
        meta = json.loads((data_prep.CACHE / f"dem_v_{p['qid']}.json").read_text())
        dem = round(meta["summit_m"], 1)
        for f in data_prep.CACHE.glob(f"dem_v_{p['qid']}.*"):
            f.unlink()
        ok = abs(dem - p["h"]) / p["h"] <= 0.02
    except Exception as e:                                           # noqa: BLE001
        print("dem check failed", p["name"], str(e)[:120])
        dem, ok = None, False
    verified[p["qid"]] = {"name": p["name"], "wikidata_m": p["h"], "dem_m": dem, "ok": ok, "checked": str(date.today())}
    print(f"  DEM {p['name']}: wikidata {p['h']} m, DEM {dem} m -> {'ok' if ok else 'REJECTED'}")
    return ok


def spec_step(p, verified):
    v = verified[p["qid"]]
    key = slug(p["name"])[:24] + "-" + p["qid"].lower()
    return {"key": key, "qid": p["qid"], "name": p["name"].upper(), "value": f"{round(p['h']):,} m", "h": p["h"],
            "lat": round(p["lat"], 5), "lon": round(p["lon"], 5),
            "sources": [f"https://www.wikidata.org/wiki/{p['qid']} (elevation {p['h']:g} m); {p['article']}",
                        f"Copernicus DEM GLO-30, summit measured {v['dem_m']} m (within 2 %)"]}


def titles_for(seeds, keys, steps):
    """Up to 3 titles: a real YouTube suggestion (for one of the seeds, mentioning one of the keys) + the numbers."""
    top = steps[-1]
    used, sugg = [], []
    keys = {k.lower() for k in keys} | {top["name"].lower()}
    for q in list(seeds) + [f"{top['name'].title()} height"]:
        for s in suggest(q):
            if any(k in s.lower() for k in keys) and len(s) <= 40 and s not in sugg and GOOD.search(s.lower())                     and not BAD.search(s.lower()):
                sugg.append(s)
                if q not in used:
                    used.append(q)
    n = len(steps)
    out = []
    for s in sugg[:8]:
        s = title_case(s)
        for t in (f"{s}: {n} Peaks to {top['value']}", f"{s}: {top['value']} at True Scale",
                  f"{s} ({steps[0]['value']} to {top['value']})"):
            if len(t) <= 60 and t not in out and re.search(r"\d", t):
                out.append(t)
                break
        if len(out) == 3:
            break
    return out, used


def seeds_for(group, kind):
    return {"country": [f"tallest mountains in {group}", f"highest mountains in {group}", f"{group} mountains"],
            "volcano": [f"volcanoes in {group}", f"biggest volcano in {group}", f"{group} volcanoes"],
            "range": [f"{group} highest peaks", f"{group} mountains", f"tallest mountains in the {group}"]}[kind]


def peak_topics(peaks, verified, taken_ids, taken_sets, need):
    groups = []
    by = {}
    for p in peaks:
        for c in p["countries"]:
            # a low summit listed for two countries (Korvatunturi: Finland, also listed for Russia) is not shown as
            # "a mountain of" either; high border summits (Everest, Mont Blanc, Kanchenjunga) stay
            if len(p["countries"]) > 1 and p["h"] < 3000:
                continue
            by.setdefault(("country", c), []).append(p)
            if p["volcano"]:
                by.setdefault(("volcano", c), []).append(p)
        for r in p["ranges"]:
            by.setdefault(("range", r), []).append(p)
    for (kind, g), ps in by.items():
        if len(ps) >= 5:
            groups.append((sum(p["links"] for p in ps), kind, g, ps))
    added = []
    for _, kind, g, ps in sorted(groups, key=lambda x: -x[0]):
        if len(added) >= need:
            break
        tid = {"country": "peaks-", "volcano": "volcanoes-", "range": "range-"}[kind] + slug(g)
        if tid in taken_ids:
            continue
        pool = list(ps)
        for _ in range(4):          # a rejected summit is dropped and the pick repeated
            steps = pick_steps(pool)
            if not steps:
                break
            bad = [p for p in steps if not dem_check(p, verified)]
            if not bad:
                break
            pool = [p for p in pool if p not in bad]
        else:
            steps = []
        if not steps:
            continue
        qs = {p["qid"] for p in steps}
        if any(len(qs & s) > MAX_SHARED for s in taken_sets):
            continue
        sp = [spec_step(p, verified) for p in steps]
        titles, used = titles_for(seeds_for(g, kind), {g}, sp)
        if not titles:
            print("no autocomplete title for", tid)
            continue
        noun = {"country": f"mountains of {g}", "volcano": f"volcanoes of {g}", "range": f"peaks of the {g}"}[kind]
        tp = {"id": tid, "kind": "higher", "engine": "peaks", "status": "planned", "source": "generated",
              "added": str(date.today()), "steps": [f"{s['name'].title()} {s['value']}" for s in sp],
              "data": "Copernicus DEM GLO-30 + Wikidata elevations (two sources, 2 % check)",
              "spec": {"steps": sp, "titles": titles, "queries": used,
                       "hashtags": ["#sizecomparison", "#" + slug(g).replace("-", ""), "#mountains", "#3d", "#scale"],
                       "intro": f"{len(sp)} real {noun}, each taller than the last, side by side at true scale "
                                f"(Copernicus DEM elevation data): " + ", ".join(s["name"].title() for s in sp) + "."}}
        added.append(tp)
        taken_ids.add(tid)
        taken_sets.append(qs)
        print("+", tid, tp["steps"], titles[0])
    return added


def search_peak(name):
    """Wikidata search by name: items with an elevation and coordinates (for summits the class query missed)."""
    url = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&limit=5&search="
           + urllib.parse.quote(name))
    ids = [x["id"] for x in json.loads(get(url))["search"]]
    if not ids:
        return []
    ents = json.loads(get("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=claims|labels|sitelinks"
                          "&ids=" + "|".join(ids)))["entities"]
    out = []
    for q, e in ents.items():
        cl = e.get("claims", {})
        try:
            el = [c for c in cl["P2044"] if c["rank"] != "deprecated"]
            best = [c for c in el if c["rank"] == "preferred"] or el
            amt = best[0]["mainsnak"]["datavalue"]["value"]
            h = float(amt["amount"]) * (0.3048 if amt["unit"].endswith("Q3710") else 1.0)
            co = cl["P625"][0]["mainsnak"]["datavalue"]["value"]
            art = e.get("sitelinks", {}).get("enwiki", {}).get("title")
        except (KeyError, IndexError):
            continue
        if not art:
            continue
        out.append({"qid": q, "name": e["labels"].get("en", {}).get("value", name), "h": round(h, 2),
                    "lat": co["latitude"], "lon": co["longitude"], "links": len(e.get("sitelinks", {})),
                    "countries": set(), "ranges": set(), "volcano": False,
                    "article": "https://en.wikipedia.org/wiki/" + art.replace(" ", "_")})
    return out


def resolve_named(tp, peaks, verified):
    """Approved topics written as names ("Fuji 3,776 m"): matched to Wikidata summits by name and height."""
    sp = []
    for label in tp["steps"]:
        m = re.match(r"(.+?)\s+~?([\d,]+) m$", label)
        if not m:
            return None
        name, h = m.group(1).strip().lower(), float(m.group(2).replace(",", ""))
        c = [p for p in peaks if abs(p["h"] - h) / h <= 0.03 and
             (name in p["name"].lower() or p["name"].lower().replace("mount ", "") in name)]
        if not c:
            c = [p for p in search_peak(m.group(1).strip()) if abs(p["h"] - h) / h <= 0.03]
        if not c:
            print("  not found:", label)
            return None
        p = max(c, key=lambda p: p["links"])
        if not dem_check(p, verified):
            print("  DEM disagrees, step dropped:", label)
            continue
        sp.append(spec_step(p, verified))
    return sp if len(sp) >= 5 else None


def main():
    dry = "--dry" in sys.argv
    doc = json.loads(TOPICS.read_text(encoding="utf-8"))
    topics = doc["topics"]
    verified = json.loads(VERIFIED.read_text(encoding="utf-8")) if VERIFIED.exists() else {}
    peaks = load_peaks()
    print(len(peaks), "Wikidata summits")
    # approved topics of the peaks engine that are still names only
    for tp in topics:
        if tp.get("engine") == "peaks" and not tp.get("spec") and tp["status"] == "planned":
            sp = resolve_named(tp, peaks, verified)
            if sp:
                titles, used = titles_for(tp.get("seeds", []), tp.get("keys", []), sp)
                tp["spec"] = {"steps": sp, "titles": tp.get("titles") or titles, "queries": tp.get("queries") or used,
                              "hashtags": tp.get("hashtags") or ["#sizecomparison", "#mountains", "#3d", "#scale"],
                              "intro": tp.get("intro") or (f"{len(sp)} real mountains, each taller than the last, side "
                                                           "by side at true scale (Copernicus DEM elevation data): "
                                                           + ", ".join(s["name"].title() for s in sp) + ".")}
                print("resolved", tp["id"], tp["spec"]["titles"][:1])
    planned = [t for t in topics if t["status"] == "planned"]
    ready = [t for t in planned if t.get("engine") in ("peaks", "area-map") and t.get("spec")]
    taken_ids = {t["id"] for t in topics}
    taken_sets = [{s["qid"] for s in t["spec"].get("steps", []) if "qid" in s} for t in topics if t.get("spec")]
    need_ready = max(0, MIN_READY - len(ready))
    need_total = max(0, MIN_PLANNED - len(planned))
    # area-map topics (owner 19.11): alternate with the mountain ladders, so about half of the renderable queue
    import area_topics
    area_ready = [t for t in ready if t.get("engine") == "area-map"]
    new_area = area_topics.area_topics(topics, max(0, MIN_AREA - len(area_ready)), sparql, suggest, title_case)
    topics += new_area
    planned = [t for t in topics if t["status"] == "planned"]
    ready = [t for t in planned if t.get("engine") in ("peaks", "area-map") and t.get("spec")]
    need_ready = max(0, MIN_READY - len(ready))
    need_total = max(0, MIN_PLANNED - len(planned))
    new = peak_topics(peaks, verified, taken_ids | {t["id"] for t in new_area}, taken_sets, max(need_ready, need_total))
    topics += new
    new += new_area
    planned = [t for t in topics if t["status"] == "planned"]
    ready = [t for t in planned if t.get("engine") in ("peaks", "area-map") and t.get("spec")]
    doc["queue"] = {"planned": len(planned), "ready_for_production": len(ready), "updated": str(date.today()),
                    "rule": f">= {MIN_PLANNED} planned, >= {MIN_READY} renderable; a topic is used once"}
    print(f"queue: {len(planned)} planned, {len(ready)} renderable, {len(new)} new")
    if not dry:
        TOPICS.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        VERIFIED.write_text(json.dumps(verified, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if len(planned) < 30:
        sys.exit(f"queue below 30: {len(planned)}")


if __name__ == "__main__":
    main()
