"""Upload Huge To Scale Shorts (owner 18.11): 1 Short a day at 19:00 Europe/Kyiv, 2 scheduled ahead.

Every run (upload.yml):
  1. the token must open the channel YT_CHANNEL_ID (core/ytguard.check_channel), else nothing is uploaded;
  2. the channel's COMPLETE video list is read (ytguard.all_uploads); a Short whose description carries
     "[ref: hugetoscale/<slug>]" (or has the same title) is never uploaded again - the state is repaired instead;
  3. while fewer than 2 Shorts are scheduled ahead, the next "ready" episode (draft release ep-<slug>) is uploaded
     PRIVATE with publishAt = the next free 19:00 Kyiv day (one video per day, days taken on YouTube are skipped);
  4. state/episodes.json is committed right after each upload (ytguard.persist), a failed commit stops the run.
Every video: category 28 (Science & Technology), selfDeclaredMadeForKids=false, containsSyntheticMedia=false,
English, title = the first autocomplete title (<= 60 chars), description with sources + credits + the marker.
DRY_RUN=1: reads the channel and prints the plan, uploads nothing.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from automation import episodes as E  # noqa: E402
from core import ytguard  # noqa: E402

CHANNEL = "hugetoscale"
TZ = ZoneInfo("Europe/Kyiv")
LOCAL_TIME = (19, 0)
AHEAD = 2
MIN_LEAD = timedelta(hours=2)
CATEGORY = "28"


def next_slot(taken_days, now):
    d = now.astimezone(TZ).date()
    for _ in range(400):
        slot = datetime(d.year, d.month, d.day, *LOCAL_TIME, tzinfo=TZ)
        if d not in taken_days and slot.astimezone(timezone.utc) - now >= MIN_LEAD:
            return slot.astimezone(timezone.utc)
        d += timedelta(days=1)
    raise RuntimeError("no free day")


def scheduled_ahead(videos, now):
    return sum(1 for v in videos if v["publish_at"] and
               datetime.fromisoformat(v["publish_at"].replace("Z", "+00:00")) > now)


def fetch_release(tag, short, d):
    subprocess.run(["gh", "release", "download", tag, "-D", str(d), "--clobber"], check=True)
    meta = {"mp4": Path(d) / f"{short}.mp4",
            "titles": json.loads((Path(d) / f"{short}_titles.json").read_text(encoding="utf-8")),
            "description": (Path(d) / f"{short}_description.txt").read_text(encoding="utf-8")}
    return meta


def preflight(short, meta, d):
    problems = E.check_composed(short, d)
    if not meta["mp4"].exists():
        problems.append("no mp4")
    return problems


GENERIC_TAGS = {"#sizecomparison", "#3d", "#scale", "#shorts"}
TYPE_TAG = {"volcanoes": "#volcano", "mountains": "#mountains"}


def final_title(short, base):
    """Owner 21.11: the text of a real search query + exactly 3 hashtags at the end: #shorts, #sizecomparison and one
    for this video (its type, or the first specific hashtag of the Short); the whole title <= 100 characters."""
    import plan as P
    s = P.SHORTS.get(short, {})
    base = re.sub(r"\s*#\S+", "", base).strip()
    kind = None
    if s.get("topic"):
        topics = json.loads((ROOT / "data" / "ladder-topics.json").read_text(encoding="utf-8"))["topics"]
        kind = next((t.get("type") for t in topics if t["id"] == s["topic"]), None)
    tag = s.get("title_tag") or TYPE_TAG.get(kind) or next(
        (h for h in s.get("hashtags", []) if h.lower() not in GENERIC_TAGS), "#scale")
    return f"{base} #shorts #sizecomparison {tag.lower()}"


def title_problems(title):
    out = []
    if len(title) > 100:
        out.append(f"title over 100 characters ({len(title)})")
    tags = re.findall(r"#\S+", title)
    if len(tags) != 3 or tags[0] != "#shorts" or not re.search(r"( #\S+){3}$", title):
        out.append("the title must end with exactly 3 hashtags, #shorts first")
    return out


def clean_description(desc):
    """No hashtag lines (the 3 hashtags are in the title) and no https:// (links stay plain text)."""
    desc = re.sub(r"https?://", "", desc)
    return "\n".join(ln for ln in desc.splitlines() if not re.fullmatch(r"\s*(#\S+\s*)+", ln)).strip()


def tags_for(short, meta):
    import plan as P
    s = P.SHORTS.get(short, {})
    tags = [h.lstrip("#") for h in s.get("hashtags", [])] + list(s.get("queries", []))
    tags += ["size comparison", "scale comparison", "3d", "huge to scale"]
    out, n = [], 0
    for t in tags:
        if t and t not in out and n + len(t) + 1 < 450:
            out.append(t)
            n += len(t) + 1
    return out


def upload(yt, meta, title, description, tags, publish_at):
    from googleapiclient.http import MediaFileUpload
    body = {"snippet": {"title": title, "description": description[:4900], "tags": tags, "categoryId": CATEGORY,
                        "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": "private", "publishAt": publish_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False,
                       "embeddable": True, "license": "youtube"}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(meta["mp4"]), chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    got = resp.get("status", {})
    if got.get("selfDeclaredMadeForKids") is True or got.get("containsSyntheticMedia") is True:
        ytguard.notify("Huge To Scale: a flag came back wrong", f"{resp['id']}: {got}")
    return resp["id"]


def main():
    dry = bool(os.environ.get("DRY_RUN"))
    if not os.environ.get("YT_TOKEN_JSON"):
        print("no YT_TOKEN_JSON: nothing to do")
        return 0
    yt = ytguard.service_from_env()
    ch = ytguard.check_channel(yt, os.environ.get("YT_CHANNEL_ID", "").strip())
    print(f"channel ok: {ch['id']} {ch['snippet']['title']}")
    st = E.load()
    known = [e["video_id"] for e in st["episodes"] if e.get("video_id")]
    videos = ytguard.all_uploads(yt, known)
    now = datetime.now(timezone.utc)
    print(f"{len(videos)} videos on the channel, {scheduled_ahead(videos, now)} scheduled ahead")
    # repair: an episode already on the channel is never uploaded again
    for e in st["episodes"]:
        if e["status"] != "uploaded":
            same = ytguard.find_existing(videos, ytguard.ref(CHANNEL, e["slug"]))
            if same:
                print(f"{e['slug']} is already on the channel ({same['id']}): state repaired")
                e.update(status="uploaded", video_id=same["id"], publish_at=same["publish_at"])
                if not dry:
                    E.save(st)
                    ytguard.persist(["state/episodes.json"], f"state: {e['slug']} found on the channel")
    while scheduled_ahead(videos, now) < AHEAD:
        e = next((x for x in st["episodes"] if x["status"] == "ready"), None)
        if not e:
            print("no ready episode")
            if scheduled_ahead(videos, now) == 0:
                ytguard.notify("Huge To Scale: nothing scheduled", "No Short is scheduled ahead and none is ready.")
            break
        days = ytguard.taken_days(videos, [x.get("publish_at") for x in st["episodes"]], tz=TZ)
        when = next_slot(days, now)
        with tempfile.TemporaryDirectory() as d:
            meta = fetch_release(e["release"], e["short"], d)
            problems = preflight(e["short"], meta, d)
            if problems:
                ytguard.notify(f"Huge To Scale: {e['slug']} failed the preflight", "\n".join(problems))
                raise SystemExit("; ".join(problems))
            title = final_title(e["short"], meta["titles"]["titles"][0]["title"])
            if title_problems(title):
                ytguard.notify(f"Huge To Scale: {e['slug']} title", "; ".join(title_problems(title)))
                raise SystemExit("; ".join(title_problems(title)))
            if ytguard.find_existing(videos, None, title):
                if dry:
                    raise SystemExit(f"duplicate title: {title}")
                ytguard.notify("Huge To Scale: same title already on the channel", f"{e['slug']}: {title}")
                raise SystemExit("duplicate title")
            desc = clean_description(meta["description"]) + "\n\n" + ytguard.ref(CHANNEL, e["slug"])
            tags = tags_for(e["short"], meta)
            print(f"-> {e['slug']}: '{title}' at {when.astimezone(TZ):%Y-%m-%d %H:%M} Kyiv")
            if dry:
                videos.append({"id": "dry", "title": title, "description": desc, "privacy": "private",
                               "publish_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "published_at": None, "tags": []})
                e.update(status="dry-run", publish_at=when.strftime("%Y-%m-%dT%H:%M:%SZ"))   # in memory only
                continue
            vid = upload(yt, meta, title, desc, tags, when)
        e.update(status="uploaded", video_id=vid, publish_at=when.strftime("%Y-%m-%dT%H:%M:%SZ"), title=title)
        E.save(st)
        ytguard.persist(["state/episodes.json"], f"state: {e['slug']} uploaded ({vid}), public {when:%Y-%m-%d %H:%M} UTC")
        videos.append({"id": vid, "title": title, "description": desc, "privacy": "private",
                       "publish_at": e["publish_at"], "published_at": None, "tags": []})
        print(f"uploaded {vid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
