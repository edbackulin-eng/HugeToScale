"""Object library (data/objects.json, owner 21.11): real objects with two-source heights and CC0 / public-domain /
CC BY / own models. Pure Python (used by plan, ladders, data_prep and Blender)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "data" / "objects.json"
MODELS_DIR = ROOT / "assets" / "models"


def load():
    return json.loads(LIB.read_text(encoding="utf-8"))["objects"]


def get(key):
    return load().get(key)


def usable(key, allow_candidates=False):
    o = get(key)
    return bool(o) and (o["status"] == "approved" or (allow_candidates and o["status"] == "candidate"))


def model_path(key):
    o = get(key)
    t = o["model"]["type"]
    if t == "glb":
        return MODELS_DIR / f"{key}.glb"
    if t == "polyhaven":
        return MODELS_DIR / key / f"{o['model']['id']}_{o['model'].get('res', '1k')}.gltf"
    return None
