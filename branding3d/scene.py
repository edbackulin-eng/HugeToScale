"""Render channel art in Blender (Cycles, CPU).

    blender -b -P branding3d/scene.py -- <variant> <out.png> [--preview]

Variants: banner_A banner_B banner_C avatar_A avatar_B avatar_C.
Writes <out>.png and <out>.json (pixel positions for the 2D text overlay + size self-check).
"""
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import models as M  # noqa: E402

ROOT = HERE.parent
HDRI = ROOT / "assets/hdri"

SKIES = {  # zenith, horizon (linear-ish RGB), hdri, sun elevation/azimuth (deg), floor tint
    "blue": ((0.01, 0.16, 0.80), (0.12, 0.62, 0.95), "kloofendal_48d_partly_cloudy_puresky_2k.hdr", 34, -62,
             (0.42, 0.68, 0.98)),
    "dawn": ((0.12, 0.42, 1.00), (1.00, 0.42, 0.08), "spruit_sunrise_2k.hdr", 20, 65, (1.00, 0.45, 0.18)),
    "teal": ((0.00, 0.30, 0.75), (0.05, 0.85, 0.75), "kloofendal_48d_partly_cloudy_puresky_2k.hdr", 36, 60,
             (0.35, 0.85, 0.80)),
}

# heights the models must reproduce (m) — checked within 1 % before rendering
EXPECTED = {"Saturn V": 110.6, "Statue of Liberty": 93.0, "Elizabeth Tower": 96.0, "Taj Mahal": 73.0,
            "Leaning Tower of Pisa": 56.7, "Great Pyramid": 138.5, "Eiffel Tower": 330.0,
            "Seawise Giant": 458.45, "Person": 1.8}

# layout: res, sky, giant, tallest height -> pixel height, base line px, scene centre x (m),
# objects as (builder, x, y)
VARIANTS = {
    "banner_A": dict(res=(2560, 1440), sky="blue", giant="Saturn V", px=405, base=918, cx=-87, objs=[
        ("saturn_v", -120, 0), ("person", -106, -14), ("statue_of_liberty", -52, 10), ("big_ben", 8, 0),
        ("taj_mahal", 82, 40)]),
    "banner_B": dict(res=(2560, 1440), sky="dawn", giant="Seawise Giant", px=405, base=918, cx=430, objs=[
        ("seawise_giant_up", 300, 0), ("eiffel", 95, 40), ("pyramid", -130, 120), ("big_ben", -300, 0),
        ("statue_of_liberty", -385, 10), ("person", 240, -30)]),
    "banner_C": dict(res=(2560, 1440), sky="teal", giant="Eiffel Tower", px=405, base=918, cx=22, objs=[
        ("eiffel", 0, 0), ("person", 70, -60), ("statue_of_liberty", 110, 0), ("big_ben", 160, -10),
        ("taj_mahal", 245, 30), ("pisa", 320, -10), ("pyramid", 460, 160)]),
    "avatar_A": dict(res=(800, 800), sky="blue", giant="Saturn V", px=560, base=690, cx=4, objs=[
        ("saturn_v", 0, 0), ("person", 14, -12)]),
    "avatar_B": dict(res=(800, 800), sky="dawn", giant="Seawise Giant", px=560, base=690, cx=-60, objs=[
        ("seawise_giant_up", 25, 0), ("eiffel", -150, 60)]),
    "avatar_C": dict(res=(800, 800), sky="teal", giant="Eiffel Tower", px=560, base=690, cx=55, objs=[
        ("eiffel", 0, 0), ("big_ben", 115, -20)]),
}


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def world(sky):
    zen, hor, hdri, *_ = SKIES[sky]
    w = bpy.data.worlds.new("sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    # lighting: CC0 HDRI from Poly Haven
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(HDRI / hdri))
    bg_l = nt.nodes.new("ShaderNodeBackground")
    bg_l.inputs["Strength"].default_value = 0.6
    nt.links.new(env.outputs[0], bg_l.inputs[0])
    # what the camera and reflections see: a saturated gradient by ray elevation
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -0.02
    mr.inputs["From Max"].default_value = 0.07
    nt.links.new(sep.outputs[2], mr.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*hor, 1)
    ramp.color_ramp.elements[1].color = (*zen, 1)
    ramp.color_ramp.interpolation = "EASE"
    nt.links.new(mr.outputs[0], ramp.inputs[0])
    bg_s = nt.nodes.new("ShaderNodeBackground")
    bg_s.inputs["Strength"].default_value = 1.0
    nt.links.new(ramp.outputs[0], bg_s.inputs[0])
    lp = nt.nodes.new("ShaderNodeLightPath")
    mx = nt.nodes.new("ShaderNodeMath"); mx.operation = "MAXIMUM"
    nt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0])
    nt.links.new(lp.outputs["Is Glossy Ray"], mx.inputs[1])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mx.outputs[0], mix.inputs[0])
    nt.links.new(bg_l.outputs[0], mix.inputs[1])
    nt.links.new(bg_s.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])


def floor(sky):
    tint = SKIES[sky][5]
    bpy.ops.mesh.primitive_plane_add(size=60000, location=(0, 0, 0))
    f = bpy.context.object
    f.name = "floor"
    m = bpy.data.materials.new("glossy floor")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*tint, 1)
    b.inputs["Roughness"].default_value = 0.22
    b.inputs["Coat Weight"].default_value = 0.35
    b.inputs["Coat Roughness"].default_value = 0.08
    f.data.materials.append(m)


def sun(sky):
    elev, azim = SKIES[sky][3], SKIES[sky][4]
    d = bpy.data.lights.new("sun", "SUN")
    d.energy = 4.5
    d.angle = math.radians(3.5)
    o = bpy.data.objects.new("sun", d)
    bpy.context.collection.objects.link(o)
    # camera looks along +Y; light comes from the camera side, rotated by azimuth
    o.rotation_euler = (math.radians(90 - elev), 0, math.radians(azim) + math.pi)
    o.rotation_euler = (math.radians(90 - elev), 0, math.radians(180 + azim))


def camera(v):
    rx, ry = v["res"]
    tall = EXPECTED[v["giant"]]
    k = v["px"] / tall  # pixels per metre on the object plane
    lens = 135.0
    full_w = rx / k
    dist = full_w * lens / 36.0
    h = tall * 0.035
    cam = bpy.data.cameras.new("cam")
    cam.lens = lens
    cam.sensor_width = 36
    cam.sensor_fit = "HORIZONTAL"
    cam.shift_y = (v["base"] - h * k - ry / 2) / rx
    cam.clip_end = 100000
    cam.dof.use_dof = False
    o = bpy.data.objects.new("cam", cam)
    bpy.context.collection.objects.link(o)
    o.location = (v["cx"], -dist, h)
    o.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.scene.camera = o
    return o


def build(v):
    made = {}
    for name, x, y in v["objs"]:
        if name == "seawise_giant_up":
            g = M.seawise_giant(x, y, upright=True)
        else:
            g = getattr(M, name)(x, y)
        made[g.name] = g
    return made


def self_check(made):
    rows = []
    ok = True
    for name, g in made.items():
        base = name.split(".")[0]
        (_, _), (_, _), (z0, z1) = M.bounds(g)
        want = EXPECTED[base]
        err = abs((z1 - max(z0, 0)) - want) / want
        rows.append({"object": base, "model_height_m": round(z1 - max(z0, 0), 2), "real_height_m": want,
                     "error_pct": round(100 * err, 2)})
        ok &= err <= 0.01
    return ok, rows


def screen(cam, p):
    sc = bpy.context.scene
    c = world_to_camera_view(sc, cam, Vector(p))
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    return [round(c.x * rx, 1), round((1 - c.y) * ry, 1)]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    key, out = argv[0], Path(argv[1])
    preview = "--preview" in argv
    v = VARIANTS[key]
    clear()
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    world(v["sky"])
    floor(v["sky"])
    sun(v["sky"])
    cam = camera(v)
    made = build(v)
    ok, rows = self_check(made)
    for r in rows:
        print("SIZE", r)
    if not ok:
        raise SystemExit("size self-check failed (>1 %)")
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 24 if preview else 160
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 6
    sc.render.resolution_x, sc.render.resolution_y = v["res"]
    sc.render.resolution_percentage = 50 if preview else 100
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "Medium High Contrast"
    sc.view_settings.exposure = -0.55
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(out)
    # pixel anchors for the overlay (at 100 % resolution)
    sc.render.resolution_percentage = 100
    g = made[v["giant"]]
    (x0, x1), (y0, y1), (z0, z1) = M.bounds(g)
    info = {"variant": key, "giant": v["giant"], "giant_height_m": EXPECTED[v["giant"]],
            "giant_top": screen(cam, ((x0 + x1) / 2, (y0 + y1) / 2, z1)),
            "giant_base": screen(cam, ((x0 + x1) / 2, (y0 + y1) / 2, 0)),
            "giant_left": screen(cam, (x0, (y0 + y1) / 2, 0)),
            "giant_right": screen(cam, (x1, (y0 + y1) / 2, 0)),
            "objects": {n: {"top": screen(cam, ((M.bounds(o)[0][0] + M.bounds(o)[0][1]) / 2, 0, M.bounds(o)[2][1])),
                            "left": screen(cam, (M.bounds(o)[0][0], 0, 0)),
                            "right": screen(cam, (M.bounds(o)[0][1], 0, 0))} for n, o in made.items()},
            "size_check": rows}
    sc.render.resolution_percentage = 50 if preview else 100
    out.with_suffix(".json").write_text(json.dumps(info, indent=1))
    bpy.ops.render.render(write_still=True)


main()
