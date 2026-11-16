"""Render one test frame of a trial Short and time it.

    blender -b --factory-startup -P shorts/test_frame.py -- <scene> <out.png> [--preview]

Scenes: titanic_times_square, texas_france, saturnv_bigben.
Writes <out>.png and <out>.json: render seconds, settings, size checks, and the estimate for a whole Short.
Real lens (focal length, aperture), Cycles CPU, adaptive sampling, OpenImageDenoise, mist for aerial
perspective. Size check: every real object must match its source within 1 % or the frame is not rendered.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import city  # noqa: E402
import maps  # noqa: E402
import objects as O  # noqa: E402

CACHE = ROOT / "data/cache"
HDRI = ROOT / "assets/hdri"
CHECKS = []


def check(name, model, real, unit="m", tol=0.01, note=None):
    err = abs(model - real) / real
    CHECKS.append({"object": name, "model": round(model, 2), "source": real, "unit": unit,
                   "error_pct": round(100 * err, 3), "ok": err <= tol, "tolerance_pct": tol * 100, "note": note})
    print("SIZE", CHECKS[-1])


# ------------------------------------------------------------------------------------------- common

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def render_setup(preview):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 16 if preview else 128
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03 if preview else 0.01
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 6
    sc.cycles.glossy_bounces = 3
    sc.cycles.transparent_max_bounces = 8
    sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
    sc.render.resolution_percentage = 40 if preview else 100
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sc.render.image_settings.file_format = "PNG"
    sc.frame_set(1)


def world_hdri(name, strength=1.0, rot=0.0):
    w = bpy.data.worlds.new("world")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(HDRI / f"{name}_2k.hdr"))
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(rot))
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength


def camera(loc, target, lens, fstop=8.0, focus=None, clip=20000):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cd.sensor_fit = "AUTO"
    cd.sensor_width = 36
    cd.clip_start = 0.5
    cd.clip_end = clip
    o = bpy.data.objects.new("cam", cd)
    bpy.context.collection.objects.link(o)
    o.location = loc
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = fstop
    cd.dof.focus_distance = focus or d.length
    bpy.context.scene.camera = o
    return o


def aerial_perspective(start, depth, colour, amount=0.35):
    """Mist pass blended toward the sky colour: distant buildings fade like in real air."""
    sc = bpy.context.scene
    sc.view_layers[0].use_pass_mist = True
    sc.world.mist_settings.start = start
    sc.world.mist_settings.depth = depth
    sc.world.mist_settings.falloff = "QUADRATIC"
    sc.use_nodes = True
    nt = sc.node_tree
    rl = nt.nodes.get("Render Layers") or nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.get("Composite") or nt.nodes.new("CompositorNodeComposite")
    mul = nt.nodes.new("CompositorNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = amount
    nt.links.new(rl.outputs["Mist"], mul.inputs[0])
    mix = nt.nodes.new("CompositorNodeMixRGB")
    mix.inputs[2].default_value = (*colour, 1)
    nt.links.new(mul.outputs[0], mix.inputs[0])
    nt.links.new(rl.outputs["Image"], mix.inputs[1])
    nt.links.new(mix.outputs[0], comp.inputs["Image"])


# ------------------------------------------------------------------------------------------- scenes

def titanic_times_square(preview):
    data = city.load(CACHE / "osm_times_square.json")
    world_hdri("kloofendal_48d_partly_cloudy_puresky", 1.0, rot=float(os.environ.get("HDRI_ROT", 270)))
    city.ground()
    city.build(data, radius=430)
    ship = O.titanic()
    check("Titanic length overall", O.local_extent(ship, 0), 269.1)
    check("Titanic beam", O.local_extent(ship, 1), 28.2)
    check("Titanic keel to funnel tops", O.top_of(ship, "funnel top"), 53.3)
    # place it in the square along the avenue grid, where it hits the fewest buildings
    feats = [f for f in city.footprints(data) if math.hypot(*f["pts"][0]) < 450]

    def fp(b, a, p):
        d = (math.sin(math.radians(b)), math.cos(math.radians(b)))
        n = (d[1], -d[0])
        cx, cy = d[0] * a + n[0] * p, d[1] * a + n[1] * p
        return [(cx + d[0] * s + n[0] * w, cy + d[1] * s + n[1] * w)
                for s in range(-130, 131, 10) for w in (-13, 0, 13)]

    cands = [(b, a, p) for b in (27.5, 29, 30.5) for a in range(-80, 81, 20) for p in range(-40, 41, 5)]
    hits, (b, a, p) = city.free_spot(feats, fp, cands)
    print("ship placement", b, a, p, "overlap samples", hits)
    d = Vector((math.sin(math.radians(b)), math.cos(math.radians(b)), 0))
    n = Vector((d.y, -d.x, 0))
    centre = d * a + n * p
    ship.location = centre
    ship.rotation_euler.z = math.atan2(d.y, d.x)
    bow = centre + d * (O.L / 2)
    for along, side in ((18, 34), (18, -34), (26, 24), (26, -24), (35, 14), (35, -14), (50, 6)):
        cam_pos = bow + d * along + n * side + Vector((0, 0, 1.7))
        if not any(city.point_in((cam_pos.x, cam_pos.y), [tuple(q) for q in f["pts"]])
                   for f in feats if (f["min_height"] or 0) < 3):
            break
    print("camera", along, side)
    target = centre + d * 35 + Vector((0, 0, 26))
    camera(cam_pos, target, lens=20, fstop=5.6, focus=(bow - cam_pos).length)
    aerial_perspective(120, 1800, (0.62, 0.72, 0.85), 0.3)
    return {"placement": {"bearing_deg": b, "along_m": a, "across_m": p, "overlap_samples": hits}}


def texas_france(preview):
    adm0 = CACHE / "ne_50m_admin_0_countries.geojson"
    adm1 = CACHE / "ne_10m_admin_1_states_provinces.geojson"
    fr = maps.find(adm0, ADMIN="France")
    tx = maps.find(adm1, name="Texas", admin="United States of America")
    lon0, lat0 = 2.4, 46.6  # metropolitan France
    fr_rings = [r for r in maps.project(fr, lon0, lat0, 2e8) if max(abs(x) for x, _ in r) < 1.2e6]
    tx_rings = maps.project(tx, -99.3, 31.4, 1e7)
    a_fr = sum(maps.area(r) for r in fr_rings) / 1e6
    a_tx = sum(maps.area(r) for r in tx_rings) / 1e6
    # Natural Earth 1:50m is generalised: its area must still be within 2 % of the official land area
    check("France (metropolitan) area, Natural Earth 1:50m vs INSEE 543 940 km²", a_fr, 543940, "km2")
    check("Texas area, Natural Earth 1:10m vs US Census total 695 662 km²", a_tx, 695662, "km2", tol=0.02,
          note="outline covers land + bays/lakes but not coastal sea: lies between Census land (676 587) and "
               "total (695 662); FOR OWNER REVIEW before the full Short")
    cfr = maps.centroid(fr_rings)
    ctx = maps.centroid(tx_rings)
    sea = city.flat_mat("sea", (0.01, 0.10, 0.32), 0.15, coat=0.6)
    land = city.flat_mat("land", (0.20, 0.50, 0.18), 0.8)
    france = city.flat_mat("france", (0.05, 0.25, 0.85), 0.6)
    texas = bpy.data.materials.new("texas")
    texas.use_nodes = True
    tb = texas.node_tree.nodes["Principled BSDF"]
    tb.inputs["Base Color"].default_value = (1.0, 0.38, 0.02, 1)
    tb.inputs["Alpha"].default_value = 0.78
    tb.inputs["Roughness"].default_value = 0.35
    tb.inputs["Emission Color"].default_value = (1.0, 0.35, 0.0, 1)
    tb.inputs["Emission Strength"].default_value = 0.4
    white = city.flat_mat("border", (0.95, 0.95, 0.95), 0.4)
    yellow = city.flat_mat("outline", (1.0, 0.85, 0.05), 0.3)
    bpy.ops.mesh.primitive_plane_add(size=2.0e7, location=(0, 0, 0))
    bpy.context.object.data.materials.append(sea)
    # neighbours for context
    data = json.loads(open(adm0, encoding="utf-8").read())
    for f in data["features"]:
        if f["properties"]["ADMIN"] == "France":
            continue
        rings = []
        for poly in maps.polygons(f["geometry"]):
            ll = poly[0]
            if all(-25 < lo < 40 and 30 < la < 72 for lo, la in ll):
                rings.append([maps.laea(lo, la, lon0, lat0) for lo, la in ll])
        if rings:
            maps.slab(f["properties"]["ADMIN"], rings, 0, 4000, land)
            maps.outline(f["properties"]["ADMIN"] + " border", rings, 4100, 1500, white)
    maps.slab("France", fr_rings, 0, 6000, france)
    maps.outline("France border", fr_rings, 6100, 2500, yellow)
    t = maps.slab("Texas", tx_rings, 0, 5000, texas, shift=(cfr[0] - ctx[0], cfr[1] - ctx[1]))
    t.location.z = 30000
    maps.outline("Texas outline", tx_rings, 35200, 3000, yellow, shift=(cfr[0] - ctx[0], cfr[1] - ctx[1]))
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 4.0; sun.angle = math.radians(2)
    so = bpy.data.objects.new("sun", sun); bpy.context.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), 0, math.radians(-35))
    world_hdri("kloofendal_48d_partly_cloudy_puresky", 0.6)
    tgt = Vector((cfr[0], cfr[1] - 60000, 0))
    cam = tgt + Vector((0, -1.05e6, 2.45e6))
    camera(cam, tgt, lens=35, fstop=64, clip=2.0e7)
    return {"area_km2": {"france_ne50m": round(a_fr), "texas_ne50m": round(a_tx)}}


def saturnv_bigben(preview):
    data = city.load(CACHE / "osm_westminster.json")
    lat0, lon0 = data["origin"]
    tpos = ((-0.12461 - lon0) * math.cos(math.radians(lat0)) * 111320, (51.50073 - lat0) * 110574)
    et = next(f for f in data["features"] if f["id"] == "way/123557148")
    pts = et["pts"]
    edges = [(math.dist(a, b), math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in zip(pts, pts[1:])]
    rot = max(edges)[1]

    def near_tower(f):
        cx = sum(p[0] for p in f["pts"]) / len(f["pts"]); cy = sum(p[1] for p in f["pts"]) / len(f["pts"])
        return math.hypot(cx - tpos[0], cy - tpos[1]) < 9.5

    world_hdri("kloppenheim_06_puresky", 1.0, rot=60)
    city.ground()
    city.build(data, skip=near_tower, radius=400)
    tower = O.elizabeth_tower()
    tower.location = (tpos[0], tpos[1], 0)
    tower.rotation_euler.z = rot
    check("Elizabeth Tower height", O.world_bounds(tower)[2][1], 96.0)
    # Saturn V: own model from NASA's published stage dimensions (branding3d/models.py). The NASA 3D Resources
    # .glb was tried first: low-poly, renders semi-transparent and has a navy band on the S-II stage.
    sys.path.insert(0, str(ROOT / "branding3d"))
    import models as BM  # noqa: E402
    sv = BM.saturn_v(0, 0)
    raw_h, s = 110.6, 1.0
    feats = [f for f in city.footprints(data) if not near_tower(f)]

    def fp(x, y):
        return [(x + r * math.cos(k * math.pi / 6), y + r * math.sin(k * math.pi / 6)) for r in (0, 6, 11) for k in range(12)]

    cands = sorted([(tpos[0] + dx, tpos[1] + dy) for dx in range(-120, 121, 8) for dy in range(-120, 121, 8)
                    if 40 < math.hypot(dx, dy) < 120 and dy > -20],
                   key=lambda c: math.hypot(c[0] - tpos[0] - 25, c[1] - tpos[1] - 55))
    hits, (sx, sy) = city.free_spot(feats, fp, cands)
    sv.location = (sx, sy, 0)
    bpy.context.view_layer.update()
    print("SV bounds", [tuple(round(v, 1) for v in ax) for ax in O.world_bounds(sv)], "cam will look at", tpos)
    check("Saturn V height", O.world_bounds(sv)[2][1] - O.world_bounds(sv)[2][0], 110.6)
    mid = Vector(((tpos[0] + sx) / 2, (tpos[1] + sy) / 2, 0))
    away = Vector((-1.0, -0.45, 0)).normalized()
    cam = mid + away * 165 + Vector((0, 0, 1.7))
    camo = camera(cam, mid + Vector((0, 0, 44)), lens=24, fstop=8, focus=(cam - mid).length)
    from bpy_extras.object_utils import world_to_camera_view
    bpy.context.view_layer.update()
    for nm, p3 in (("rocket base", (sx, sy, 0)), ("rocket top", (sx, sy, 110)), ("tower top", (tpos[0], tpos[1], 96))):
        print("VIEW", nm, [round(v, 3) for v in world_to_camera_view(bpy.context.scene, camo, Vector(p3))])
    aerial_perspective(150, 2500, (0.70, 0.78, 0.88), 0.3)
    return {"saturn_v_spot": [round(sx, 1), round(sy, 1)], "overlap_samples": hits,
            "saturn_v_model": "own (branding3d/models.py), NASA dimensions", "tower_rotation_deg": round(math.degrees(rot), 1)}


SCENES = {"titanic_times_square": titanic_times_square, "texas_france": texas_france,
          "saturnv_bigben": saturnv_bigben}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    name, out = argv[0], Path(argv[1]).resolve()
    preview = "--preview" in argv
    reset()
    render_setup(preview)
    t0 = time.time()
    extra = SCENES[name](preview)
    build_s = time.time() - t0
    bad = [c for c in CHECKS if not c["ok"]]
    info = {"scene": name, "preview": preview, "checks": CHECKS, **extra}
    if bad:
        info["status"] = "size check failed — not rendered"
        out.with_suffix(".json").write_text(json.dumps(info, indent=1))
        raise SystemExit("SIZE CHECK FAILED: " + ", ".join(c["object"] for c in bad))
    sc = bpy.context.scene
    sc.render.filepath = str(out)
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    secs = time.time() - t1
    info.update({"status": "rendered", "build_seconds": round(build_s, 1), "render_seconds": round(secs, 1),
                 "resolution": [sc.render.resolution_x * sc.render.resolution_percentage // 100,
                                sc.render.resolution_y * sc.render.resolution_percentage // 100],
                 "samples": sc.cycles.samples, "threads": os.cpu_count()})
    for sec in (20, 30, 45):
        frames = sec * 30
        info[f"estimate_{sec}s_short"] = {"frames": frames, "cpu_hours": round(frames * secs / 3600, 1),
                                          "jobs_at_4h": math.ceil(frames * secs / 3600 / 4)}
    out.with_suffix(".json").write_text(json.dumps(info, indent=1))
    print("RENDER", name, round(secs, 1), "s")


main()
