"""Final colour grade (ffmpeg) and a brightness check for phones.

    python shorts/grade.py <in.png> <out.png>

Grade (owner 17.11): + contrast, + saturation, light vibrance, slight lift of mid-tones, no clipping.
Check: mean luma (should be light), clipped pixels, sky saturation — written to <out>.json.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat

GRADE = "eq=contrast=1.10:saturation=1.28:gamma=1.06:brightness=0.015,vibrance=intensity=0.16"


def stats(path):
    im = Image.open(path).convert("RGB")
    luma = im.convert("L")
    hist = luma.histogram()
    n = sum(hist)
    top = im.crop((0, 0, im.width, im.height // 5)).convert("HSV")
    return {"mean_luma": round(ImageStat.Stat(luma).mean[0] / 255, 3),
            "clipped_pct": round(100 * sum(hist[250:]) / n, 2),
            "crushed_pct": round(100 * sum(hist[:6]) / n, 2),
            "top_saturation": round(ImageStat.Stat(top).mean[1] / 255, 3)}


def main(src, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", GRADE, dst], check=True)
    info = {"grade": GRADE, "before": stats(src), "after": stats(dst)}
    a = info["after"]
    info["phone_ok"] = a["mean_luma"] >= 0.42 and a["clipped_pct"] <= 2.0
    Path(dst).with_suffix(".json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
