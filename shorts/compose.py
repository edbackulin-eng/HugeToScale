"""Assemble a Short: rendered chunks -> grade -> captions -> final comparison frame held -> CC0 music -> MP4.
Also writes sources.json, 3 title options (from real YouTube search suggestions) and the description.

    python shorts/compose.py <short> <chunks_dir> <out_dir> [--preview STEP]
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import grade as G  # noqa: E402
import plan as P  # noqa: E402

FONT = str(ROOT / "assets/fonts/Anton-Regular.ttf")
W, H = 1080, 1920
SAFE_X, SAFE_W = 500, 820      # Shorts safe zone: keep clear of the right-hand buttons and the bottom title
STROKE = (12, 14, 30)


def ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def caption_layer(c):
    """One caption block drawn at full size on a transparent canvas (shadow + outline + fill)."""
    fonts = []
    for ln in c["lines"]:
        size = ln["size"]
        while True:
            f = ImageFont.truetype(FONT, size)
            if f.getlength(ln["text"]) <= SAFE_W or size < 30:
                break
            size -= 4
        fonts.append((f, size))
    heights = [s * 1.18 for _, s in fonts]
    total = sum(heights)
    img = Image.new("RGBA", (W, int(total) + 80), (0, 0, 0, 0))
    shadow = Image.new("L", img.size, 0)
    d, sd = ImageDraw.Draw(img), ImageDraw.Draw(shadow)
    y = 40
    for (f, s), hgt, ln in zip(fonts, heights, c["lines"]):
        cy = y + hgt / 2
        sw = max(3, s // 10)
        sd.text((SAFE_X, cy + s * 0.06), ln["text"], font=f, fill=150, stroke_width=sw + 2, anchor="mm")
        d.text((SAFE_X, cy), ln["text"], font=f, fill=(*ln["colour"], 255), stroke_width=sw, stroke_fill=STROKE,
               anchor="mm")
        y += hgt
    shadow = shadow.filter(ImageFilter.GaussianBlur(9))
    base = Image.new("RGBA", img.size, (0, 0, 0, 0))
    base.putalpha(shadow)
    return Image.alpha_composite(base, img)


def nice_step(m_per_px, min_px=170):
    for v in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
        if v / m_per_px >= min_px:
            return v
    return 50000


def fmt_m(v):
    return f"{v / 1000:g} km" if v >= 1000 else f"{v:g} m"


def ladder_overlay(frame, track, t, short):
    """Growing height ruler on the left + small labels on the earlier objects (all of them in the overview)."""
    s = P.SHORTS[short]
    L = P.LADDERS[s["ladder"]]
    row = track["track"][min(len(track["track"]) - 1, int(round(t * P.FPS)))]
    S = row["S"]
    gy = track["ground_y"] * H
    ppm = H / S
    d = ImageDraw.Draw(frame)
    # ruler
    step = nice_step(1 / ppm)
    f_r = ImageFont.truetype(FONT, 30)
    x0 = 46
    d.line([(x0, gy), (x0, 170)], fill=(255, 255, 255, 230), width=4)
    v = 0
    ruler_boxes = []   # tick labels: object labels never cover them (owner 18.11: "Burj Khalifa" over "1 km")
    while gy - v * ppm >= 175:
        y = gy - v * ppm
        d.line([(x0 - 10, y), (x0 + 14, y)], fill=(255, 255, 255, 240), width=4)
        if v:
            d.text((x0 + 22, y), fmt_m(v), font=f_r, fill=(255, 255, 255, 255), stroke_width=4,
                   stroke_fill=STROKE, anchor="lm")
            ruler_boxes.append((x0 - 14, y - 24, x0 + 30 + f_r.getlength(fmt_m(v)), y + 24))
        v += step
    # labels (none during the rewind: the loop starts clean)
    if t >= L["rewind"]:
        return True
    steps = L["steps"]
    cur = max(i for i, st in enumerate(steps) if st["t"] <= t)
    overview = L["overview"] <= t < L["rewind"]
    f_l = ImageFont.truetype(FONT, 36)
    boxes = []
    items = []
    for i, st in enumerate(steps):
        sc = row.get(st["key"], 1.0)
        if sc < 0.6 or (i == cur and not overview):
            continue
        hpx = st["h"] * sc * ppm
        if hpx < 22 and not overview:
            continue
        xp = W / 2 + (st["x"] - row["x"]) * ppm
        yt = gy - hpx
        if not (10 < xp < W - 10):
            continue
        items.append((xp, yt, st))
    for xp, yt, st in sorted(items, key=lambda a: a[0]):
        txt = f"{st['name']}  {st['value']}"
        wl = f_l.getlength(txt)
        bx = min(max(xp - wl / 2, 20), W - 20 - wl)
        by = yt - 70

        def hit(bx, by):
            return next((b for b in boxes + ruler_boxes
                         if bx - 8 < b[2] and bx + wl + 8 > b[0] and by - 4 < b[3] and by + 48 > b[1]), None)
        for _ in range(12):
            b = hit(bx, by)
            if b is None:
                break
            if b in ruler_boxes and b[2] + 10 + wl < W - 20:
                bx = b[2] + 10          # step right of the ruler's tick label
            else:
                by = b[1] - 52          # stack above the earlier label
        boxes.append((bx, by, bx + wl, by + 44))
        lx = min(max(xp, bx + 12), bx + wl - 12)
        d.line([(xp, yt - 4), (lx, by + 44)], fill=(255, 255, 255, 220), width=3)
        d.text((bx, by), st["name"] + "  ", font=f_l, fill=(255, 255, 255, 255), stroke_width=5, stroke_fill=STROKE)
        d.text((bx + f_l.getlength(st["name"] + "  "), by), st["value"], font=f_l, fill=(*P.YELLOW, 255),
               stroke_width=5, stroke_fill=STROKE)
    return True


def caption_frames(short, total, outdir, track=None):
    s = P.SHORTS[short]
    layers = [(c, caption_layer(c)) for c in s["captions"]]
    outdir.mkdir(parents=True, exist_ok=True)
    blank = None
    for i in range(total):
        t = i / P.FPS
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        any_on = bool(track) and ladder_overlay(frame, track, t, short)
        for c, lay in layers:
            if not (c["t0"] <= t <= min(c["t1"], s["seconds"])):
                continue
            k_in = 1.0 if c["t0"] < 0 else ease_out((t - c["t0"]) / 0.22)
            k_out = 1.0 if c["t1"] >= s["seconds"] else min(1.0, (c["t1"] - t) / 0.2)
            alpha = min(k_in, k_out)
            sc = 0.86 + 0.14 * k_in
            lw, lh = int(lay.width * sc), int(lay.height * sc)
            l2 = lay.resize((lw, lh), Image.LANCZOS)
            if alpha < 1:
                l2.putalpha(l2.getchannel("A").point(lambda v, a=alpha: int(v * a)))
            frame.alpha_composite(l2, (int(SAFE_X * (1 - sc)), int(c["y"] - lh / 2)))
            any_on = True
        p = outdir / f"c{i + 1:04d}.png"
        if not any_on:
            if blank is None:
                frame.save(p)
                blank = p
            else:
                p.write_bytes(blank.read_bytes())
        else:
            frame.save(p)


def loudest_start(path, seconds):
    """Start (s) of the loudest window of the Short's length (the climax of the track), not in the first 5 s."""
    import array
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "2000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = array.array("h", raw)
    blk = 1000                                           # 0.5 s blocks
    e = [sum(v * v for v in a[i:i + blk]) / blk for i in range(0, len(a) - blk, blk)]
    n = int(seconds * 2)
    best, arg = -1.0, 10
    for k in range(10, max(11, len(e) - n - 4)):
        w = sum(e[k:k + n])
        if w > best:
            best, arg = w, k
    return arg / 2


TARGET_LUFS = -14.0      # owner 19.11: every Short at YouTube's -14 LUFS, whatever the track's own loudness
TRUE_PEAK = -1.5


def _loudnorm_stats(args):
    """Run ffmpeg with a loudnorm print_format=json pass; returns its JSON."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args + ["-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    return json.loads(err[err.rindex("{"):err.rindex("}") + 1])


def music_chain(path, start, seconds):
    """Two-pass loudnorm: measure the cut (trim + fades) first, then a linear gain to -14 LUFS (no pumping)."""
    cut = (f"atrim=start={start}:duration={seconds},asetpts=PTS-STARTPTS,afade=t=in:d=0.6,"
           f"afade=t=out:st={seconds - 1.8}:d=1.8")
    m = _loudnorm_stats(["-i", str(path), "-af", f"{cut},loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11:print_format=json"])
    return (f"{cut},loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11:measured_I={m['input_i']}:"
            f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
            f"offset={m['target_offset']}:linear=true,aresample=48000")


def measure_mp4(mp4):
    m = _loudnorm_stats(["-i", str(mp4), "-vn", "-af", "loudnorm=print_format=json"])
    return {"integrated_lufs": float(m["input_i"]), "true_peak_db": float(m["input_tp"]),
            "target_lufs": TARGET_LUFS, "ok": abs(float(m["input_i"]) - TARGET_LUFS) <= 1.0}


def music(short, dst):
    m = P.track(short)
    req = urllib.request.Request(m["url"], headers={"User-Agent": "HugeToScale-build/0.1"})
    dst.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    if m["start"] == "auto":
        m = {**m, "start": loudest_start(dst, P.SHORTS[short]["seconds"])}
    return m


def build_text(short, fetched):
    s = P.SHORTS[short]
    m = P.track(short)
    lines = [s["intro"], "", "Facts:"]
    for fact, url, note in s["facts"]:
        lines.append(f"- {fact}" + (f" ({note})" if note else "") + (f" — {url}" if url else ""))
    lines += ["", "Data, images and credits:"]
    seen = set()
    for item in fetched.values():
        key = item["licence"]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {item['licence']}: {item['url']}")
    lines.append(f"- Music: \"{m['title']}\" by {m['creator']}, {m['licence']} — {m['page']}")
    lines.append("- Font: Anton by Vernon Adams, SIL Open Font License 1.1")
    steps = P.LADDERS.get(s.get("ladder"), {}).get("steps", [])
    if short == "saturnv_pyramid" or any(st["key"] in ("saturnv", "pyramid", "burj") for st in steps):
        lines.append("- Saturn V, Great Pyramid, Burj Khalifa: 3D models built for this video from published dimensions")
    import library
    for cr in dict.fromkeys((library.get(st["key"]) or {}).get("credit") for st in steps):
        if cr:
            lines.append(f"- {cr}")
    lines.append("- Map data © OpenStreetMap contributors" if any("OpenStreetMap" in i["licence"] for i in fetched.values())
                 else "")
    # owner 21.11: no hashtags in the description (exactly 3 go into the title, automation/publish.final_title) and
    # no "https://" (the channel has no advanced features: links stay plain text)
    import re
    text = "\n".join(x for x in lines if x is not None).replace("\n\n\n", "\n\n")
    return re.sub(r"https?://", "", text)


def main():
    short, chunks, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    step = int(sys.argv[sys.argv.index("--preview") + 1]) if "--preview" in sys.argv else 1
    out.mkdir(parents=True, exist_ok=True)
    s = P.SHORTS[short]
    total = round(s["seconds"] * P.FPS)
    work = out / "work"
    work.mkdir(exist_ok=True)
    # 1) rendered frames (all chunks unpacked into one folder, named f####.png by frame number)
    frames = sorted(chunks.glob("**/f[0-9][0-9][0-9][0-9].png"))
    if not frames:
        raise SystemExit("no frames")
    seq = work / "seq"
    seq.mkdir(exist_ok=True)
    for i, f in enumerate(frames):
        dst = seq / f"s{i + 1:04d}.png"
        if not dst.exists():
            dst.hardlink_to(f) if hasattr(dst, "hardlink_to") else dst.write_bytes(f.read_bytes())
    rendered = len(frames)
    hold = max(0.0, s["seconds"] - rendered * step / P.FPS)   # a preview (every 3rd frame) can overshoot
    tracks = sorted(chunks.glob("**/ladder_track.json"))
    track = json.loads(tracks[0].read_text()) if tracks else None
    caption_frames(short, total, work / "cap", track)
    track = music(short, work / "music.mp3")
    mp4 = out / f"{short}{'_preview' if step > 1 else ''}.mp4"
    vf = (f"[0:v]scale={W}:{H}:flags=lanczos,fps={P.FPS},{G.GRADE},"
          f"tpad=stop_mode=clone:stop_duration={hold:.3f},trim=duration={s['seconds']}[v];"
          f"[v][1:v]overlay=0:0:format=auto,format=yuv420p[vo];"
          f"[2:a]{music_chain(work / 'music.mp3', track['start'], s['seconds'])}[ao]")
    cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", str(P.FPS / step), "-i", str(seq / "s%04d.png"),
           "-framerate", str(P.FPS), "-i", str(work / "cap/c%04d.png"), "-i", str(work / "music.mp3"),
           "-filter_complex", vf, "-map", "[vo]", "-map", "[ao]", "-r", str(P.FPS),
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k",
           "-t", str(s["seconds"]), "-movflags", "+faststart", str(mp4)]
    subprocess.run(cmd, check=True)
    # phone check on a few finished frames
    checks = {}
    for t in (0.5, 3.0, s["seconds"] / 2, s["seconds"] - 1.0):
        png = work / f"check_{t:.1f}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(mp4), "-frames:v", "1", str(png)],
                       check=True)
        st = G.stats(png)
        checks[f"{t:.1f}s"] = st
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate,codec_name",
                                       "-of", "json", str(mp4)], capture_output=True, text=True, check=True).stdout)
    fetched = {}
    for fj in list(chunks.glob("**/fetched.json")) + list((ROOT / "data/cache").glob("fetched.json")):
        fetched.update(json.loads(fj.read_text()))
    infos = [json.loads(p.read_text()) for p in chunks.glob("**/info_*.json")]
    sources = {
        "short": short, "data": fetched,
        "music": {**track, "registry": P.MUSIC_LIST},
        "font": {"name": "Anton", "licence": "SIL Open Font License 1.1", "file": "assets/fonts/Anton-OFL.txt"},
        "facts": [{"fact": a, "url": b, "note": c} for a, b, c in s["facts"]],
        "size_checks": infos[0]["checks"] if infos else [],
        "containsSyntheticMedia": False, "selfDeclaredMadeForKids": False,
    }
    (out / f"{short}_sources.json").write_text(json.dumps(sources, indent=1, ensure_ascii=False), encoding="utf-8")
    titles = {"search_suggestions_used": s["queries"],
              "titles": [{"title": t, "chars": len(t)} for t in s["titles"]]}
    assert all(len(t) <= 60 for t in s["titles"]), "title over 60 characters"
    (out / f"{short}_titles.json").write_text(json.dumps(titles, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / f"{short}_description.txt").write_text(build_text(short, fetched), encoding="utf-8")
    report = {"short": short, "mp4": mp4.name, "probe": probe, "phone_checks": checks, "loudness": measure_mp4(mp4),
              "phone_ok": all(c["mean_luma"] >= 0.42 for c in checks.values()),
              "rendered_frames": rendered, "step": step, "hold_seconds": round(hold, 2),
              "render": [{k: i.get(k) for k in ("frames", "seconds_per_frame", "probe_full_quality_seconds",
                                                 "build_seconds", "buildings", "crater")} for i in infos]}
    (out / f"{short}_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
