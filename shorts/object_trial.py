"""Trial frame of a library object (owner 21.11: every new object gets a trial frame first; toy-like ones are
replaced). Renders the object alone, framed as in a ladder, at full resolution.

    blender -b --factory-startup -P shorts/object_trial.py -- <key> <out_dir>
"""
import json
import sys
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import animate as A  # noqa: E402
import ladders  # noqa: E402
import library  # noqa: E402
import plan as P  # noqa: E402
import test_frame as T  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    key, out = argv[0], Path(argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    o = library.get(key)
    step = {"key": key, "name": o["name"], "h": o["h"], "w": o["w"], "sources": o["sources"]}
    name = "trial_" + key
    P.LADDERS[name] = ladders.ladder_from_spec({"steps": [step]})
    T.render_setup(False)
    sc = bpy.context.scene
    sc.cycles.samples = 32
    import ladder
    t0 = time.time()
    ladder.build(name, False, A.Rig())
    frame = round(P.LADDERS[name]["overview"] * P.FPS)
    sc.frame_set(frame)
    sc.render.filepath = str(out / f"trial_{key}.png")
    bpy.ops.render.render(write_still=True)
    info = {"key": key, "checks": T.CHECKS, "seconds": round(time.time() - t0, 1), "frame": frame,
            "model_w": P.LADDERS[name]["steps"][0].get("model_w")}
    (out / f"trial_{key}.json").write_text(json.dumps(info, indent=1))
    print("TRIAL", json.dumps(info))


main()
