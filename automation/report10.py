"""Report after the first 10 published Shorts (owner 19.11), in Ukrainian.

Per Short: views, average % viewed (retention), subscribers gained, average view duration; then the topics ranked.
YouTube Analytics needs ~2 days to settle, so the report is made once the 10th Short has been public for 3 days.

    python automation/report10.py            # makes reports/report-10.md once (state/report10.json marks it done)
    python automation/report10.py --force    # makes it now with what is published so far (a test)
Needs YT_TOKEN_JSON with the yt-analytics.readonly scope (scripts/youtube_auth.py).
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
STATE = ROOT / "state" / "episodes.json"
TOPICS = ROOT / "data" / "ladder-topics.json"
DONE = ROOT / "state" / "report10.json"
OUT = ROOT / "reports" / "report-10.md"
N = 10
SETTLE = timedelta(days=3)
TYPES = {"mountains": "гори", "volcanoes": "вулкани", "craters": "кратер", "structures": "споруди", "mixed": "мікс"}


def published(now):
    eps = json.loads(STATE.read_text(encoding="utf-8"))["episodes"]
    out = [e for e in eps if e.get("video_id") and e.get("publish_at")
           and datetime.fromisoformat(e["publish_at"].replace("Z", "+00:00")) <= now]
    return sorted(out, key=lambda e: e["publish_at"])


def analytics(cred_json, ids, start):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    d = json.loads(cred_json)
    cred = Credentials(token=None, refresh_token=d["refresh_token"], client_id=d["client_id"],
                       client_secret=d["client_secret"], token_uri=d.get("token_uri", "https://oauth2.googleapis.com/token"),
                       scopes=d.get("scopes"))
    ya = build("youtubeAnalytics", "v2", credentials=cred, cache_discovery=False)
    yt = build("youtube", "v3", credentials=cred, cache_discovery=False)
    res = ya.reports().query(ids="channel==MINE", startDate=start, endDate=str(date.today()),
                             metrics="views,averageViewPercentage,averageViewDuration,subscribersGained,likes",
                             dimensions="video", filters="video==" + ",".join(ids), maxResults=50).execute()
    cols = [c["name"] for c in res["columnHeaders"]]
    rows = {r[0]: dict(zip(cols, r)) for r in res.get("rows", [])}
    stats = {}
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="statistics", id=",".join(ids[i:i + 50])).execute()["items"]:
            stats[v["id"]] = v["statistics"]
    return rows, stats


def topic_type(e, topics):
    from automation import episodes as E
    return E.type_of(e, topics)


def build_report(eps, rows, stats, topics):
    lines = [f"# Huge To Scale — звіт після {len(eps)} Shorts ({date.today():%d.%m.%Y})", "",
             "| # | Дата | Short | Тип | Перегляди | Досмотр, % | Сер. час, с | Підписники |",
             "|---|---|---|---|---|---|---|---|"]
    data = []
    for i, e in enumerate(eps, 1):
        r = rows.get(e["video_id"], {})
        views = int(stats.get(e["video_id"], {}).get("viewCount", r.get("views", 0)) or 0)
        pct = float(r.get("averageViewPercentage") or 0)
        dur = float(r.get("averageViewDuration") or 0)
        subs = int(r.get("subscribersGained") or 0)
        kind = TYPES.get(topic_type(e, topics), "?")
        day = datetime.fromisoformat(e["publish_at"].replace("Z", "+00:00")).astimezone().strftime("%d.%m")
        data.append((e, views, pct, subs, kind))
        lines.append(f"| {i} | {day} | {e.get('title', e['slug'])} | {kind} | {views:,} | {pct:.0f} | {dur:.0f} | {subs} |")
    tot_v = sum(d[1] for d in data)
    tot_s = sum(d[3] for d in data)
    lines += ["", f"**Разом:** {tot_v:,} переглядів, {tot_s} підписників."]
    if data:
        best_v = max(data, key=lambda d: d[1])
        best_p = max(data, key=lambda d: d[2])
        best_s = max(data, key=lambda d: d[3])
        lines += ["", "**Що зайшло найкраще:**",
                  f"- перегляди: {best_v[0].get('title', best_v[0]['slug'])} ({best_v[1]:,});",
                  f"- досмотр: {best_p[0].get('title', best_p[0]['slug'])} ({best_p[2]:.0f}%);",
                  f"- підписники: {best_s[0].get('title', best_s[0]['slug'])} ({best_s[3]})."]
        by = {}
        for _, v, p, s, k in data:
            by.setdefault(k, []).append((v, p, s))
        lines += ["", "**За типом (у середньому на Short):**"]
        for k, xs in sorted(by.items(), key=lambda kv: -sum(x[0] for x in kv[1]) / len(kv[1])):
            n = len(xs)
            lines.append(f"- {k}: {sum(x[0] for x in xs) / n:,.0f} переглядів, досмотр {sum(x[1] for x in xs) / n:.0f}%, "
                         f"{sum(x[2] for x in xs) / n:.1f} підписника ({n} Shorts)")
    lines += ["", "_Дані: YouTube Analytics (досмотр, підписники, час) і YouTube Data API (перегляди). "
                  "Аналітика YouTube оновлюється із затримкою до 2–3 днів._"]
    return "\n".join(lines) + "\n"


def main():
    force = "--force" in sys.argv
    if DONE.exists() and not force:
        print("report already made:", json.loads(DONE.read_text())["made"])
        return 0
    now = datetime.now(timezone.utc)
    eps = published(now)
    if not force:
        if len(eps) < N:
            print(f"{len(eps)} of {N} published: not yet")
            return 0
        eps = eps[:N]
        tenth = datetime.fromisoformat(eps[-1]["publish_at"].replace("Z", "+00:00"))
        if now - tenth < SETTLE:
            print(f"10th Short public since {tenth:%Y-%m-%d %H:%M} UTC: waiting for analytics until {tenth + SETTLE:%Y-%m-%d}")
            return 0
    if not eps:
        print("nothing published yet")
        return 0
    first = datetime.fromisoformat(eps[0]["publish_at"].replace("Z", "+00:00")).date()
    rows, stats = analytics(os.environ["YT_TOKEN_JSON"], [e["video_id"] for e in eps], str(first))
    topics = {t["id"]: t for t in json.loads(TOPICS.read_text(encoding="utf-8"))["topics"]}
    text = build_report(eps, rows, stats, topics)
    print(text)
    if force:
        return 0
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    DONE.write_text(json.dumps({"made": str(date.today()), "shorts": [e["slug"] for e in eps]}, indent=1) + "\n")
    from core import ytguard
    ytguard.persist([str(OUT.relative_to(ROOT)), str(DONE.relative_to(ROOT))], "report after 10 Shorts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
