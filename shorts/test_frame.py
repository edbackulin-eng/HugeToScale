"""Render one test frame of a trial Short and time it (Blender scenes; maps are 2D, see map2d.py).

    blender -b --factory-startup -P shorts/test_frame.py -- <scene> <out.png> [--preview]

Scenes: titanic_aerial (drone view over USGS NAIP orthophoto of Times Square),
        titanic_pitch (fallback: beside a FIFA-size football pitch),
        saturnv_pyramid (Saturn V beside the Great Pyramid of Giza).
Style (owner 17.11): bright daytime sun only, crisp shadows, light haze, AgX Punchy; grade.py finishes the colour.
Budget: 40 samples + OpenImageDenoise, simple materials, 24 fps, <= 30 s a frame.
Size check: every real object must match its source within 1 % or the frame is not rendered.
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
sys.path.insert(0, str(ROOT / "branding3d"))
import objects as O  # noqa: E402
import models as BM  # noqa: E402

CACHE = ROOT / "data/cache"
HDRI = ROOT / "assets/hdri"
TEX = ROOT / "assets/textures"
FPS = 24
CHECKS = []


def check(name, model, real, unit="m", tol=0.01, note=None):
    err = abs(model - real) / real
    CHECKS.append({"object": name, "model": round(model, 2), "source": real, "unit": unit,
                   "error_pct": round(100 * err, 3), "ok": err <= tol, "tolerance_pct": tol * 100, "note": note})
    print("SIZE", CHECKS[-1])


# ------------------------------------------------------------------------------------------- common

def render_setup(preview):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 12 if preview else int(os.environ.get("SAMPLES", 24))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = float(os.environ.get("ADAPTIVE", 0.05))
    sc.render.use_persistent_data = True  # animation: scene/BVH kept between frames
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.volume_bounces = 0
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    sc.render.fps = FPS
    sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
    sc.render.resolution_percentage = 40 if preview else 100
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sc.view_settings.exposure = 0.35
    sc.render.image_settings.file_format = "PNG"
    sc.frame_set(1)


def sunny_world(hdri="kloofendal_43d_clear_puresky", strength=1.4, rot=0.0):
    """Clear-sky HDRI (Poly Haven CC0): its sun disk gives crisp shadows, the sky stays saturated blue."""
    w = bpy.data.worlds.new("world")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(HDRI / f"{hdri}_2k.hdr"))
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(rot))
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    # deepen the blue of the sky a little (camera rays only; lighting keeps the HDRI's real colour)
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = 1.6
    nt.links.new(env.outputs["Color"], hsv.inputs["Color"])
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(hsv.outputs["Color"], bg_cam.inputs["Color"])
    bg_cam.inputs["Strength"].default_value = strength
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(bg_cam.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes["World Output"].inputs[0])


def sun(elev, azim, strength=4.0, angle=1.2):
    """Sun lamp: azim is the compass direction the light comes FROM (0 = north, 90 = east)."""
    d = bpy.data.lights.new("sun", "SUN")
    d.energy = strength
    d.angle = math.radians(angle)
    o = bpy.data.objects.new("sun", d)
    bpy.context.collection.objects.link(o)
    o.rotation_euler = (math.radians(90 - elev), 0, math.radians(180 - azim))
    return o


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


def haze(start, depth, colour=(0.72, 0.84, 0.98), amount=0.22):
    """Light aerial perspective: the mist pass blends far things toward a bright sky blue."""
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


def pbr(name, tid, scale, bump=0.6, tint=None):
    """Poly Haven CC0 texture set, box-projected in object space so no UVs are needed."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / scale, 1 / scale, 1 / scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def img(kind, colour):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(TEX / f"{tid}_{kind}_2k.jpg"))
        t.image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
        t.projection = "BOX"
        t.projection_blend = 0.25
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t

    d = img("diff", True)
    if tint:
        mixc = nt.nodes.new("ShaderNodeMix"); mixc.data_type = "RGBA"; mixc.blend_type = "MULTIPLY"
        mixc.inputs["Factor"].default_value = 1.0
        mixc.inputs["B"].default_value = (*tint, 1)
        nt.links.new(d.outputs["Color"], mixc.inputs["A"])
        nt.links.new(mixc.outputs["Result"], b.inputs["Base Color"])
    else:
        nt.links.new(d.outputs["Color"], b.inputs["Base Color"])
    r = img("rough", False)
    nt.links.new(r.outputs["Color"], b.inputs["Roughness"])
    n = img("nor", False)
    nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = bump
    nt.links.new(n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def plane(name, size, m, loc=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(m)
    return o


# ------------------------------------------------------------------------------------------- scenes

def titanic_aerial(preview):
    """Drone view over the real Times Square (NAIP orthophoto); the ship casts its shadow on the photo."""
    meta = json.loads((CACHE / "naip_times_square.json").read_text())
    half = meta["half_m"]
    sunny_world(strength=1.2)
    m = bpy.data.materials.new("naip")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(str(CACHE / "naip_times_square.jpg"))
    t.interpolation = "Linear"
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.9
    b.inputs["Specular IOR Level"].default_value = 0.2
    plane("NAIP Times Square", 2 * half, m)  # default plane UVs cover the image exactly
    ship = O.titanic()
    check("Titanic length overall", O.local_extent(ship, 0), 269.1)
    check("Titanic beam", O.local_extent(ship, 1), 28.2)
    check("Titanic keel to funnel tops", O.top_of(ship, "funnel top"), 53.3)
    bearing = 29.0  # Manhattan's avenue grid, along 7th Avenue through the square
    d = Vector((math.sin(math.radians(bearing)), math.cos(math.radians(bearing)), 0))
    ship.rotation_euler.z = math.atan2(d.y, d.x)
    ship.location = (0, 0, 0)
    # the photo's own shadows fall to the north-west: the sun stands in the south-east
    sun(58, 150, strength=4.5)
    n = Vector((d.y, -d.x, 0))
    cam = d * 250 + n * 110 + Vector((0, 0, 380))
    camera(cam, d * 10, lens=30, fstop=11, focus=(cam - d * 10).length)
    haze(250, 2500, amount=0.15)
    return {"aerial": "USGS NAIP Plus orthoimagery, public domain", "bearing_deg": bearing}


def pbr_or_flat():
    m = bpy.data.materials.new("park grass")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 0.05
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.10, 0.30, 0.05, 1)
    ramp.color_ramp.elements[1].color = (0.20, 0.42, 0.08, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.9
    return m


def titanic_pitch(preview):
    """Fallback: Titanic lying beside a FIFA-standard football pitch (105 x 68 m) on open grass."""
    sunny_world(strength=1.3, rot=40)
    grass = bpy.data.materials.new("pitch grass")
    grass.use_nodes = True
    nt = grass.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    stripe = nt.nodes.new("ShaderNodeMath"); stripe.operation = "PINGPONG"; stripe.inputs[1].default_value = 5.25
    nt.links.new(sep.outputs[0], stripe.inputs[0])
    st = nt.nodes.new("ShaderNodeMath"); st.operation = "GREATER_THAN"; st.inputs[1].default_value = 2.625
    nt.links.new(stripe.outputs[0], st.inputs[0])
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 0.6
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (0.10, 0.36, 0.06, 1)
    mix.inputs["B"].default_value = (0.16, 0.48, 0.09, 1)
    nt.links.new(st.outputs[0], mix.inputs["Factor"])
    mix2 = nt.nodes.new("ShaderNodeMix"); mix2.data_type = "RGBA"; mix2.blend_type = "MULTIPLY"
    mix2.inputs["Factor"].default_value = 0.25
    nt.links.new(mix.outputs["Result"], mix2.inputs["A"])
    nt.links.new(noise.outputs["Color"], mix2.inputs["B"])
    nt.links.new(mix2.outputs["Result"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.85
    pitch = plane("pitch", 1, grass)
    pitch.scale = (111, 74, 1)
    pitch.location.z = 0.004
    plane("park grass", 4000, pbr_or_flat())
    white = O.mat("lines", (0.95, 0.95, 0.95), 0.6)
    L_, W_ = 105.0, 68.0
    lw = 0.12
    lines = [((0, W_ / 2), (L_, lw)), ((0, -W_ / 2), (L_, lw)), ((L_ / 2, 0), (lw, W_)), ((-L_ / 2, 0), (lw, W_)),
             ((0, 0), (lw, W_))]
    for sx in (1, -1):  # penalty and goal areas
        lines += [((sx * (L_ / 2 - 16.5), 0), (lw, 40.32)), ((sx * (L_ / 2 - 8.25), 20.16), (16.5, lw)),
                  ((sx * (L_ / 2 - 8.25), -20.16), (16.5, lw)), ((sx * (L_ / 2 - 5.5), 0), (lw, 18.32)),
                  ((sx * (L_ / 2 - 2.75), 9.16), (5.5, lw)), ((sx * (L_ / 2 - 2.75), -9.16), (5.5, lw))]
    for (x, y), (sx_, sy_) in lines:
        O.box("line", (x, y, 0.01), (sx_, sy_, 0.02), white)
    O.cylinder("centre circle", (0, 0, 0.0), 9.15, 0.02, white, n=96)
    O.cylinder("centre grass", (0, 0, 0.005), 9.15 - lw, 0.03, grass, n=96)
    for sx in (1, -1):  # goals 7.32 x 2.44 m
        for y in (-3.66, 3.66):
            O.cylinder("post", (sx * L_ / 2, y, 0), 0.06, 2.44, white, n=12)
        O.box("bar", (sx * L_ / 2, 0, 2.44), (0.12, 7.44, 0.12), white)
    check("pitch length", L_, 105.0)
    ship = O.titanic()
    check("Titanic length overall", O.local_extent(ship, 0), 269.1)
    check("Titanic beam", O.local_extent(ship, 1), 28.2)
    ship.location = (25, 62, 0)
    cam = Vector((150, -190, 70))
    camera(cam, Vector((10, 30, 10)), lens=28, fstop=11)
    haze(300, 3000, amount=0.18)
    return {"pitch": "FIFA Laws of the Game: 105 x 68 m"}


def saturnv_pyramid(preview):
    """Saturn V (110.6 m) beside the Great Pyramid (138.5 m now, base 230.3 m) in the desert."""
    sunny_world(strength=1.5, rot=float(os.environ.get("HDRI_ROT", 0)))
    sand = pbr("sand", "aerial_sand", 6.0, bump=0.4, tint=(1.0, 0.78, 0.52))
    stone = pbr("limestone blocks", "large_sandstone_blocks", 3.2, bump=1.0, tint=(1.0, 0.80, 0.52))
    plane("desert", 20000, sand)
    pyr = BM.frustum(0, 0, 0, 138.5, 230.3, 9.0, stone, name="Great Pyramid")
    check("Great Pyramid height (present)", O.world_bounds(pyr)[2][1], 138.5)
    check("Great Pyramid base side", O.world_bounds(pyr)[0][1] - O.world_bounds(pyr)[0][0], 230.3)
    sv = BM.saturn_v(150, -95)
    check("Saturn V height", O.world_bounds(sv)[2][1] - O.world_bounds(sv)[2][0], 110.6)
    cam = Vector((260, -340, 1.8))
    camera(cam, Vector((70, -40, 95)), lens=24, fstop=11)
    haze(400, 5000, colour=(0.78, 0.86, 0.98), amount=0.25)
    return {"pyramid": "present height 138.5 m, base 230.3 m"}


SCENES = {"titanic_aerial": titanic_aerial, "titanic_pitch": titanic_pitch, "saturnv_pyramid": saturnv_pyramid}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    name, out = argv[0], Path(argv[1]).resolve()
    preview = "--preview" in argv
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
    first = time.time() - t1
    # steady state, as in a real animation: frame 2 with the camera moved, scene kept in memory
    cam = sc.camera
    cam.location.x += 1.5
    sc.frame_set(2)
    sc.render.filepath = str(out.with_name(out.stem + "_f2.png"))
    t2 = time.time()
    bpy.ops.render.render(write_still=True)
    secs = time.time() - t2
    info["first_frame_seconds"] = round(first, 1)
    info.update({"status": "rendered", "build_seconds": round(build_s, 1), "render_seconds": round(secs, 1),
                 "resolution": [sc.render.resolution_x * sc.render.resolution_percentage // 100,
                                sc.render.resolution_y * sc.render.resolution_percentage // 100],
                 "samples": sc.cycles.samples, "threads": os.cpu_count(), "fps": FPS})
    for sec in (20, 30, 45):
        frames = sec * FPS
        hours = frames * secs / 3600
        info[f"estimate_{sec}s_short"] = {"frames": frames, "cpu_hours": round(hours, 1),
                                          "jobs_at_4h": max(1, math.ceil(hours / 4))}
    out.with_suffix(".json").write_text(json.dumps(info, indent=1))
    print("RENDER", name, round(secs, 1), "s")


main()
