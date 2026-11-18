"""Measure every music track of data/music-registry.json that has no length/loudness yet (runs on a runner).

Downloads each file from its OpenGameArt url into a temp dir, reads the length (ffprobe) and the integrated
loudness (ffmpeg loudnorm, EBU R128), stores seconds, loudness_lufs, true_peak_db, sha256 and measured_on.
A track that cannot be downloaded or decoded gets status "unavailable" (never used) and a note.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

REG = Path(__file__).resolve().parent.parent / "data" / "music-registry.json"


def measure(path):
    sec = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                               capture_output=True, text=True, check=True).stdout.strip())
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "loudnorm=print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    j = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err).group(0))
    return round(sec, 1), round(float(j["input_i"]), 1), round(float(j["input_tp"]), 1)


def main():
    reg = json.loads(REG.read_text(encoding="utf-8"))
    todo = [t for t in reg["tracks"] if t.get("seconds") is None or t.get("loudness_lufs") is None or "--all" in sys.argv]
    with tempfile.TemporaryDirectory() as tmp:
        for t in todo:
            f = Path(tmp) / ("x" + Path(t["url"]).suffix)
            try:
                req = urllib.request.Request(t["url"], headers={"User-Agent": "Mozilla/5.0 (music licence check)"})
                f.write_bytes(urllib.request.urlopen(req, timeout=120).read())
                sec, lufs, tp = measure(f)
            except Exception as e:                                    # noqa: BLE001
                t["status"] = "unavailable"
                t["note"] = f"measure failed {date.today()}: {str(e)[:120]}"
                print(f"FAIL {t['id']}: {e}")
                continue
            t.update(seconds=sec, loudness_lufs=lufs, true_peak_db=tp,
                     sha256=hashlib.sha256(f.read_bytes()).hexdigest(), measured_on=str(date.today()))
            print(f"{t['id']:34s} {sec:7.1f} s  {lufs:6.1f} LUFS  TP {tp:5.1f} dB")
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
