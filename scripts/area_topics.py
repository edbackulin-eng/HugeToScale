"""Area-map topics (owner 19.11): a real place dropped onto a country at true size - US states, islands, lakes, deserts.

Called by scripts/topics.py. Every topic has two sources per number:
  official area  - Wikidata, best-rank area (P2046), with the English Wikipedia article;
  outline        - the Natural Earth shape measured on an equal-area projection (shorts/areamap.py), within 3 %.
A pair is used only when the difference is clear (7-45 % bigger or smaller) and the place is not inside that country.
Titles come from real YouTube autocomplete; a "X vs Y" suggestion is used only when it names the same country.
"""
import json
import math
import re
import sys
import urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shorts"))

CATS = {"state": ("adm1", lambda p: p.get("admin") == "United States of America"),
        "island": ("region", lambda p: p.get("FEATURECLA") == "Island"),
        "lake": ("lake", lambda p: True),
        "desert": ("region", lambda p: p.get("FEATURECLA") == "Desert")}
MIN_KM2 = 8000
OUTLINE_TOL = 0.03
RATIO = [(1.07, 1.45), (0.69, 0.93)]
BASE_MAX_USES = 2
AREA_GOOD = re.compile(r"\b(vs|versus|compared|comparison|size|big|bigger|biggest|largest|area|scale)\b")
AREA_BAD = re.compile(r"\b(music|song|movie|film|game|live|news|trip|tour|vlog|death|weather|video|simulator|reaction|"
                      r"population|gdp|military|army|war|football|soccer|economy|flag|language|accent|food|price|cost|"
                      r"tamil|hindi|urdu|telugu|bangla|shorts|explained|facts|documentary|cities|city|rich|poor)\b")


def wikidata(qids, sparql):
    out = {}
    qids = sorted(set(qids))
    for i in range(0, len(qids), 250):
        vals = " ".join("wd:" + q for q in qids[i:i + 250])
        q = f"""SELECT ?i ?iLabel ?a ?links ?article WHERE {{ VALUES ?i {{ {vals} }}
          ?i p:P2046 ?s. ?s a wikibase:BestRank; psn:P2046/wikibase:quantityAmount ?a. ?i wikibase:sitelinks ?links.
          OPTIONAL {{ ?article schema:about ?i; schema:isPartOf <https://en.wikipedia.org/>. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}"""
        for r in sparql(q):
            k = r["i"].rsplit("/", 1)[1]
            a = float(r["a"]) / 1e6
            if k in out and out[k]["km2"] != a:       # two best-rank values that disagree: not trusted
                out[k]["conflict"] = True
                continue
            out[k] = {"km2": a, "links": int(r["links"]), "name": r["iLabel"], "article": r.get("article")}
    return {k: v for k, v in out.items() if not v.get("conflict") and not re.match(r"^Q\d+$", v["name"])}


def bbox(geom):
    import map2d as M
    pts = [c for p in M.polys(geom) for c in p[0]]
    return min(c[0] for c in pts), min(c[1] for c in pts), max(c[0] for c in pts), max(c[1] for c in pts)


def candidates(sparql):
    import areamap as A
    rows = {}
    for cat, (layer, ok) in CATS.items():
        key = A.LAYERS[layer][1]
        for f in A.features(layer):
            p = f["properties"]
            q = p.get(key)
            if q and ok(p):
                rows[(cat, q)] = f
    for f in A.features("adm0"):
        q = f["properties"].get("WIKIDATAID")
        if q and f["properties"].get("TYPE") in ("Sovereign country", "Country"):
            rows[("country", q)] = f
    wd = wikidata([q for _, q in rows], sparql)
    out = []
    for (cat, q), f in rows.items():
        w = wd.get(q)
        if not w or w["km2"] < MIN_KM2 or not w["article"]:
            continue
        b = bbox(f["geometry"])
        if b[2] - b[0] > 180:                                     # crosses the antimeridian
            continue
        s = A.shape(f["geometry"])
        if abs(s["km2"] - w["km2"]) / w["km2"] > OUTLINE_TOL:
            continue
        layer = "adm0" if cat == "country" else CATS[cat][0]
        out.append({"cat": cat, "layer": layer, "qid": q, "name": w["name"], "km2": round(w["km2"]),
                    "outline_km2": round(s["km2"]), "links": w["links"], "article": w["article"], "bbox": b,
                    "centre": (s["lon0"], s["lat0"])})
    return out


FILLER = set("lake island desert the state us usa real really actually size big bigger is how vs versus compared to "
             "comparison area map of in on top true scale and".split())
TRIAL_USED = {"Q1439"}      # Texas: already in the trial Short "Texas on France"


def only_about(s, o, b):
    """The suggestion speaks of this place (and this country) only: no other names in it."""
    allowed = FILLER | set(re.findall(r"[a-z]+", o["name"].lower())) | set(re.findall(r"[a-z]+", b["name"].lower()))
    words = set(re.findall(r"[a-z]+", s.lower()))
    kind = {"lake": "lake", "island": "island", "desert": "desert"}
    for w in kind:                         # "how big is lake michigan" is not about the state of Michigan
        if w in words and o["cat"] != w and w not in o["name"].lower():
            return False
    return words <= allowed


def core(name):
    n = name.lower()
    n = re.sub(r"^(lake|the|isle of)\s+|\s+(desert|island|lake|sea)$", "", n)
    return n.strip()


def titles(o, b, pct, suggest, title_case):
    seeds = [f"{o['name']} vs {b['name']}", f"{o['name']} compared to {b['name']}", f"{o['name']} size comparison",
             f"how big is {o['name']}"]
    oc, bc = core(o["name"]), core(b["name"])
    sugg, used = [], []
    for q in seeds:
        for s in suggest(q.lower()):
            sl = s.lower()
            if (oc in sl and only_about(s, o, b) and len(s) <= 40 and s.isascii() and AREA_GOOD.search(sl) and not AREA_BAD.search(sl)
                    and (bc in sl or not re.search(r"\b(vs|versus|compared)\b", sl)) and s not in sugg):
                sugg.append(s)
                if q not in used:
                    used.append(q)
    verdict = (f"{o['name']} Is {pct}% Bigger" if pct > 0 else f"{o['name']} Is {-pct}% Smaller")
    out = []
    for s in sugg[:8]:
        names_base = bc in s.lower()
        s = title_case(s)
        forms = ((f"{s}: {verdict}",) if names_base else ()) + (
            f"{s}: {o['km2']:,} km² on {b['name']}", f"{s}: Dropped on {b['name']} ({pct:+d}%)",
            f"{s}: {o['km2']:,} km² at True Scale")
        for t in forms:
            if len(t) <= 60 and t not in out and re.search(r"\d", t):
                out.append(t)
                break
        if len(out) == 3:
            break
    return out, used


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def part(c):
    return {"layer": c["layer"], "qid": c["qid"], "name": c["name"], "km2": c["km2"],
            "sources": [f"https://www.wikidata.org/wiki/{c['qid']} (area, best rank); {c['article']}",
                        f"Natural Earth outline on an equal-area projection: {c['outline_km2']:,} km² "
                        f"(within {round(100 * OUTLINE_TOL)} %)"]}


def area_topics(topics, need, sparql, suggest, title_case):
    if need <= 0:
        return []
    cands = candidates(sparql)
    states = {c["name"].lower() for c in cands if c["cat"] == "state"} | {"georgia"}
    bases = sorted([c for c in cands if c["cat"] == "country" and c["name"].lower() not in states],
                   key=lambda c: -c["links"])[:120]           # Georgia the country vs Georgia the state: never
    used_over = TRIAL_USED | {t["spec"]["over"]["qid"] for t in topics if t.get("engine") == "area-map" and t.get("spec")}
    country_names = {c["name"].lower() for c in cands if c["cat"] == "country"}
    base_uses = {}
    for t in topics:
        if t.get("engine") == "area-map" and t.get("spec"):
            base_uses[t["spec"]["base"]["qid"]] = base_uses.get(t["spec"]["base"]["qid"], 0) + 1
    taken_ids = {t["id"] for t in topics}
    queues = {}
    for cat in CATS:
        overs = sorted([c for c in cands if c["cat"] == cat and c["qid"] not in used_over
                        and c["name"].lower() not in country_names], key=lambda c: -c["links"])   # Georgia: no
        queues[cat] = overs[:40]
    added = []
    while len(added) < need and any(queues.values()):
        for cat in CATS:
            if len(added) >= need or not queues[cat]:
                continue
            o = queues[cat].pop(0)
            for b in bases:
                r = o["km2"] / b["km2"]
                if not any(lo <= r <= hi for lo, hi in RATIO) or base_uses.get(b["qid"], 0) >= BASE_MAX_USES:
                    continue
                x0, y0, x1, y1 = b["bbox"]
                if x0 <= o["centre"][0] <= x1 and y0 <= o["centre"][1] <= y1:     # the place lies in that country
                    continue
                if math.hypot(o["centre"][0] - b["centre"][0], o["centre"][1] - b["centre"][1]) < 1:
                    continue
                pct = round(100 * (r - 1))
                tid = f"area-{slug(o['name'])}-vs-{slug(b['name'])}"
                if tid in taken_ids:
                    continue
                tl, used = titles(o, b, pct, suggest, title_case)
                if not tl:
                    continue
                spec = {"over": part(o), "base": part(b), "titles": tl, "queries": used,
                        "hashtags": ["#sizecomparison", "#" + slug(o["name"]).replace("-", ""),
                                     "#" + slug(b["name"]).replace("-", ""), "#maps", "#geography"],
                        "intro": f"{o['name']} dropped onto {b['name']} at true size: both outlines on an equal-area "
                                 f"projection (Natural Earth), both areas official figures."}
                added.append({"id": tid, "kind": "area", "engine": "area-map", "status": "planned",
                              "source": "generated", "added": str(date.today()), "category": o["cat"],
                              "steps": [f"{o['name']} {o['km2']:,} km²", f"{b['name']} {b['km2']:,} km²"],
                              "data": "Wikidata official areas + Natural Earth outlines (within 3 %)", "spec": spec})
                taken_ids.add(tid)
                base_uses[b["qid"]] = base_uses.get(b["qid"], 0) + 1
                print("+", tid, f"{pct:+d}%", tl[0])
                break
    return added
