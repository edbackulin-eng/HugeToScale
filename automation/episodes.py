"""Episode queue of Huge To Scale (owner 18.11): the trial Shorts first, then size ladders from the topic queue.

state/episodes.json holds every episode in publishing order:
  queued   -> picked, music assigned, waits for the render (produce.yml)
  ready    -> rendered and checked; the MP4 + texts sit in the DRAFT release ep-<slug> (not public)
  uploaded -> on YouTube (private + publishAt), video_id and publish_at recorded

    python automation/episodes.py next      # the episode to render now (prints its short name, or nothing)
    python automation/episodes.py store <short> <dir>   # checks the composed Short, makes the draft release, marks it ready
"""
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "shorts"))
STATE = ROOT / "state" / "episodes.json"
TOPICS = ROOT / "data" / "ladder-topics.json"
MUSIC = ROOT / "data" / "music-registry.json"
READY_AHEAD = 2           # rendered and waiting, on top of the 2 scheduled on YouTube (owner: buffer 2)


def load():
    return json.loads(STATE.read_text(encoding="utf-8"))


def save(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def slug_of(short):
    return short.replace("_", "-")


def previous_music(st):
    used = [e for e in st["episodes"] if e.get("music")]
    return used[-1]["music"]["id"] if used else None


def assign_music(st, e):
    import plan as P
    reg = json.loads(MUSIC.read_text(encoding="utf-8"))
    t = P.pick_music(reg, previous_music(st))
    e["music"] = {"id": t["id"], "start": "auto"}
    t["last_used"] = str(date.today())
    MUSIC.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def next_topic():
    doc = json.loads(TOPICS.read_text(encoding="utf-8"))
    for tp in doc["topics"]:
        if tp["status"] == "planned" and tp.get("engine") == "peaks" and tp.get("spec"):
            tp["status"] = "scheduled"
            TOPICS.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            return tp
    return None


def cmd_next():
    st = load()
    ready = [e for e in st["episodes"] if e["status"] == "ready"]
    queued = [e for e in st["episodes"] if e["status"] == "queued"]
    if len(ready) >= READY_AHEAD and not os.environ.get("FORCE"):
        print(f"{len(ready)} ready: nothing to render", file=sys.stderr)
        return ""
    if queued:
        e = queued[0]
    else:
        tp = next_topic()
        if not tp:
            from core import ytguard
            ytguard.notify("Huge To Scale: no renderable topic left", "The topic queue has no planned topic with a "
                           "ready engine. topics.yml refills it weekly; run it by hand.")
            return ""
        e = {"slug": "ladder-" + tp["id"], "short": "ladder_" + tp["id"].replace("-", "_"), "topic": tp["id"],
             "status": "queued", "added": str(date.today())}
        st["episodes"].append(e)
    if not e.get("music") and e["short"].startswith("ladder_") and e["short"] != "ladder_heights":
        assign_music(st, e)
    save(st)
    return e["short"]


def check_composed(short, d):
    """The composed Short must be 1080x1920, <= 60 s, phone-bright, every size check ok, titles <= 60 with a number."""
    d = Path(d)
    rep = json.loads((d / f"{short}_report.json").read_text())
    src = json.loads((d / f"{short}_sources.json").read_text(encoding="utf-8"))
    tit = json.loads((d / f"{short}_titles.json").read_text(encoding="utf-8"))
    v = next(s for s in rep["probe"]["streams"] if s["codec_name"] == "h264")
    problems = []
    if (v["width"], v["height"]) != (1080, 1920):
        problems.append(f"size {v['width']}x{v['height']}")
    if float(rep["probe"]["format"]["duration"]) > 60:
        problems.append("longer than 60 s")
    if not rep.get("phone_ok"):
        problems.append("too dark for a phone")
    if rep.get("loudness") and not rep["loudness"].get("ok"):
        problems.append(f"loudness {rep['loudness']['integrated_lufs']} LUFS, not -14")
    bad = [c["object"] for c in src.get("size_checks", []) if not c.get("ok")]
    if bad:
        problems.append("size checks failed: " + ", ".join(bad))
    if src.get("containsSyntheticMedia") is not False or src.get("selfDeclaredMadeForKids") is not False:
        problems.append("flags")
    if not tit["titles"] or any(t["chars"] > 60 or not re.search(r"\d", t["title"]) for t in tit["titles"][:1]):
        problems.append("title")
    return problems


def cmd_store(short, d):
    from core import ytguard
    st = load()
    e = next(x for x in st["episodes"] if x["short"] == short)
    problems = check_composed(short, d)
    if problems:
        ytguard.notify(f"Huge To Scale: {short} not stored", "\n".join(problems))
        raise SystemExit("; ".join(problems))
    tag = "ep-" + e["slug"]
    files = [str(Path(d) / f"{short}{x}") for x in (".mp4", "_titles.json", "_description.txt", "_sources.json",
                                                     "_report.json")]
    subprocess.run(["gh", "release", "delete", tag, "--yes"], capture_output=True)
    subprocess.run(["gh", "release", "create", tag, "--draft", "--title", tag, "--notes",
                    f"Rendered {date.today()}; uploaded by upload.yml (private + publishAt)."] + files, check=True)
    e.update(status="ready", release=tag, rendered=str(date.today()))
    save(st)
    print("stored", tag)


if __name__ == "__main__":
    if sys.argv[1] == "next":
        print(cmd_next())
    elif sys.argv[1] == "store":
        cmd_store(sys.argv[2], sys.argv[3])
