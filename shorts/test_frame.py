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


def pbr(name, tid, scale, bump=0.6, tint=None, disp=0.0, sand_tid=None, sand_height=0.0):
    """Poly Haven CC0 texture set, box-projected in object space so no UVs are needed."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / scale, 1 / scale, 1 / scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    # anti-tiling: warp the texture space with low-frequency noise so repeats never line up
    warp_n = nt.nodes.new("ShaderNodeTexNoise")
    warp_n.inputs["Scale"].default_value = 0.35
    warp_n.inputs["Detail"].default_value = 1.0
    nt.links.new(mp.outputs["Vector"], warp_n.inputs["Vector"])
    centre = nt.nodes.new("ShaderNodeVectorMath"); centre.operation = "SUBTRACT"
    centre.inputs[1].default_value = (0.5, 0.5, 0.5)
    nt.links.new(warp_n.outputs["Color"], centre.inputs[0])
    amt = nt.nodes.new("ShaderNodeVectorMath"); amt.operation = "SCALE"
    amt.inputs["Scale"].default_value = 0.22
    nt.links.new(centre.outputs[0], amt.inputs[0])
    warped = nt.nodes.new("ShaderNodeVectorMath"); warped.operation = "ADD"
    nt.links.new(mp.outputs["Vector"], warped.inputs[0])
    nt.links.new(amt.outputs[0], warped.inputs[1])
    vec = warped.outputs[0]

    def img(kind, colour, vector=None):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(TEX / f"{tid}_{kind}_2k.jpg"))
        t.image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
        t.projection = "BOX"
        t.projection_blend = 0.25
        nt.links.new(vector or vec, t.inputs["Vector"])
        return t

    d1 = img("diff", True)
    # a second sample, rotated and rescaled, blended in by a large soft mask: breaks the remaining repeats
    rot = nt.nodes.new("ShaderNodeMapping")
    rot.inputs["Rotation"].default_value = (0, 0, 0.65)
    rot.inputs["Scale"].default_value = (0.71, 0.71, 0.71)
    rot.inputs["Location"].default_value = (0.37, 0.11, 0.0)
    nt.links.new(vec, rot.inputs["Vector"])
    d2 = img("diff", True, rot.outputs["Vector"])
    mask_n = nt.nodes.new("ShaderNodeTexNoise")
    mask_n.inputs["Scale"].default_value = 0.12
    nt.links.new(mp.outputs["Vector"], mask_n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.42
    ramp.inputs["From Max"].default_value = 0.58
    nt.links.new(mask_n.outputs["Fac"], ramp.inputs["Value"])
    dmix = nt.nodes.new("ShaderNodeMix"); dmix.data_type = "RGBA"
    nt.links.new(ramp.outputs[0], dmix.inputs["Factor"])
    nt.links.new(d1.outputs["Color"], dmix.inputs["A"])
    nt.links.new(d2.outputs["Color"], dmix.inputs["B"])
    # broad tonal variation (weathering, wind-blown dust)
    tone_n = nt.nodes.new("ShaderNodeTexNoise")
    tone_n.inputs["Scale"].default_value = 0.05
    nt.links.new(mp.outputs["Vector"], tone_n.inputs["Vector"])
    tone = nt.nodes.new("ShaderNodeMix"); tone.data_type = "RGBA"; tone.blend_type = "OVERLAY"
    tone.inputs["Factor"].default_value = 0.35
    nt.links.new(dmix.outputs["Result"], tone.inputs["A"])
    nt.links.new(tone_n.outputs["Color"], tone.inputs["B"])

    class _D:  # keep the rest of the function unchanged: d.outputs["Color"] is the blended colour
        outputs = {"Color": tone.outputs["Result"]}
    d = _D()
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
    if disp:  # real relief of the blocks (needs a subdivided mesh)
        dimg = img("disp", False)
        dn = nt.nodes.new("ShaderNodeDisplacement")
        dn.inputs["Scale"].default_value = disp
        dn.inputs["Midlevel"].default_value = 0.5
        nt.links.new(dimg.outputs["Color"], dn.inputs["Height"])
        nt.links.new(dn.outputs["Displacement"], nt.nodes["Material Output"].inputs["Displacement"])
        m.displacement_method = "BOTH"
    if sand_tid:  # windblown sand banked against the lowest courses
        st = nt.nodes.new("ShaderNodeTexImage")
        st.image = bpy.data.images.load(str(TEX / f"{sand_tid}_diff_2k.jpg"))
        st.projection = "BOX"
        nt.links.new(mp.outputs["Vector"], st.inputs["Vector"])
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 0.08
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        hz = nt.nodes.new("ShaderNodeMath"); hz.operation = "MULTIPLY"
        hz.inputs[1].default_value = sand_height * 1.6
        nt.links.new(nz.outputs["Fac"], hz.inputs[0])
        lt = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(sep.outputs[2], lt.inputs["Value"])
        nt.links.new(hz.outputs[0], lt.inputs["From Min"])
        lt.inputs["From Max"].default_value = 0.0
        tint_s = nt.nodes.new("ShaderNodeMix"); tint_s.data_type = "RGBA"; tint_s.blend_type = "MULTIPLY"
        tint_s.inputs["Factor"].default_value = 1.0
        tint_s.inputs["B"].default_value = (1.0, 0.78, 0.52, 1)
        nt.links.new(st.outputs["Color"], tint_s.inputs["A"])
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"
        cur = b.inputs["Base Color"].links[0].from_socket
        nt.links.new(lt.outputs[0], mx.inputs["Factor"])
        nt.links.new(cur, mx.inputs["A"])
        nt.links.new(tint_s.outputs["Result"], mx.inputs["B"])
        nt.links.new(mx.outputs["Result"], b.inputs["Base Color"])
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
    # grade the photo itself: lighter, more saturated, not grey
    hs = nt.nodes.new("ShaderNodeHueSaturation")
    hs.inputs["Saturation"].default_value = 1.4
    hs.inputs["Value"].default_value = 1.18
    bc = nt.nodes.new("ShaderNodeBrightContrast")
    bc.inputs["Bright"].default_value = 0.04
    bc.inputs["Contrast"].default_value = 0.12
    nt.links.new(t.outputs["Color"], hs.inputs["Color"])
    nt.links.new(hs.outputs["Color"], bc.inputs["Color"])
    nt.links.new(bc.outputs["Color"], b.inputs["Base Color"])
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
    sun(float(os.environ.get("SUN_EL", 22)), float(os.environ.get("SUN_AZ", 140)), strength=5.0)  # low morning sun
    contact_shadow(ship, O.L + 24, O.B + 18)
    # almost straight down, like the photo itself, so its leaning towers are not seen from the side
    # 3/4 view from the sunlit side, 32 degrees off vertical: side, red bottom and funnels all show
    n = Vector((d.y, -d.x, 0))
    off = 300 * math.tan(math.radians(32))
    cam = Vector((0, 0, 300)) + (n * 0.5 - d * 0.87).normalized() * off
    camera(cam, Vector((0, 0, 8)), lens=30, fstop=16, focus=350)
    veil(0.04)
    return {"aerial": "USGS NAIP Plus orthoimagery, public domain", "bearing_deg": bearing}


def contact_shadow(parent, length, width):
    """Soft dark ellipse under a hull: the ship sits on the photo instead of floating over it."""
    m = bpy.data.materials.new("contact shadow")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (2.0, 2.0, 1.0)
    mp.inputs["Location"].default_value = (-1.0, -1.0, 0)
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    g = nt.nodes.new("ShaderNodeTexGradient")
    g.gradient_type = "SPHERICAL"
    nt.links.new(mp.outputs["Vector"], g.inputs["Vector"])
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 1.6
    nt.links.new(g.outputs["Fac"], pw.inputs[0])
    k = nt.nodes.new("ShaderNodeMath"); k.operation = "MULTIPLY"; k.inputs[1].default_value = 0.55
    nt.links.new(pw.outputs[0], k.inputs[0])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    dk = nt.nodes.new("ShaderNodeBsdfDiffuse")
    dk.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(k.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(dk.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    p = plane("contact shadow", 1, m, loc=(0, 0, 0.08))
    p.scale = (length, width, 1)
    p.parent = parent
    p.visible_shadow = False
    return p


def veil(amount, colour=(0.80, 0.88, 1.0)):
    """Very light atmospheric veil over the whole frame: photo and model share the same air."""
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    rl = nt.nodes.get("Render Layers") or nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.get("Composite") or nt.nodes.new("CompositorNodeComposite")
    mix = nt.nodes.new("CompositorNodeMixRGB")
    mix.inputs[0].default_value = amount
    mix.inputs[2].default_value = (*colour, 1)
    nt.links.new(rl.outputs["Image"], mix.inputs[1])
    nt.links.new(mix.outputs[0], comp.inputs["Image"])


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
    sand = pbr("sand", "aerial_sand", 22.0, bump=0.4, tint=(1.0, 0.78, 0.52))  # large scale: no visible tiling at long lens
    stone = pbr("limestone blocks", "large_sandstone_blocks", 5.0, bump=0.8, tint=(1.0, 0.80, 0.52),
                disp=0.45, sand_tid="aerial_sand", sand_height=7.0)
    plane("desert", 20000, sand)
    dunes = plane("dunes", 3000, sand, loc=(0, 0, -0.6))
    sub = dunes.modifiers.new("sub", "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = sub.render_levels = 7
    tex = bpy.data.textures.new("dunes", "CLOUDS")
    tex.noise_scale = 160
    dsp = dunes.modifiers.new("dsp", "DISPLACE")
    dsp.texture = tex
    dsp.strength = 4.0
    dsp.texture_coords = "GLOBAL"
    pyr = BM.frustum(0, 0, 0, 138.5, 230.3, 9.0, stone, name="Great Pyramid")
    ps = pyr.modifiers.new("sub", "SUBSURF")
    ps.subdivision_type = "SIMPLE"
    ps.levels = 2
    ps.render_levels = 8
    check("Great Pyramid height (present)", O.world_bounds(pyr)[2][1], 138.5)
    check("Great Pyramid base side", O.world_bounds(pyr)[0][1] - O.world_bounds(pyr)[0][0], 230.3)
    sv = BM.saturn_v(128, 0)  # same depth as the apex, so perspective does not cheat the comparison
    check("Saturn V height", O.world_bounds(sv)[2][1] - O.world_bounds(sv)[2][0], 110.6)
    cam = Vector((64, -420, 70))  # drone height, long lens: apex and rocket equally far, a fair comparison
    camera(cam, Vector((64, 0, 56)), lens=50, fstop=11)
    haze(400, 5000, colour=(0.78, 0.86, 0.98), amount=0.25)
    return {"pyramid": "present height 138.5 m, base 230.3 m"}


def crater_manhattan(preview):
    """Barringer (Meteor) Crater, Arizona, set into Midtown Manhattan at true size.
    Relief: USGS 3DEP; imagery: USGS NAIP of the crater and of Manhattan (all public domain).
    One terrain mesh: crater relief and crater photo inside, city photo outside, soft transition at the ejecta."""
    import array
    meta = json.loads((CACHE / "dem_meteor_crater.json").read_text())
    n_px, half_d = meta["px"], meta["half_m"]
    z = array.array("f")
    z.frombytes((CACHE / "dem_meteor_crater.f32").read_bytes())

    def h(x, y):  # bilinear sample of the DEM at local metres (x east, y north)
        u = (x + half_d) / (2 * half_d) * (n_px - 1)
        v = (half_d - y) / (2 * half_d) * (n_px - 1)
        u = min(max(u, 0), n_px - 1.001); v = min(max(v, 0), n_px - 1.001)
        i, j = int(v), int(u); fu, fv = u - j, v - i
        a = z[i * n_px + j]; b = z[i * n_px + j + 1]
        c = z[(i + 1) * n_px + j]; d = z[(i + 1) * n_px + j + 1]
        return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv

    # level of the surrounding plain = median height on a ring well outside the rim
    ring = sorted(h(r * math.cos(t), r * math.sin(t)) for r in (1000, 1150, 1250) for t in
                  [k * math.pi / 36 for k in range(72)])
    plain = ring[len(ring) // 2]
    floor_z = min(z) - plain
    rims = []
    for k in range(72):
        t = k * math.pi / 36
        best = max(((h(r * math.cos(t), r * math.sin(t)), r) for r in range(400, 800, 5)))
        rims.append(best)
    rim_h = sum(v for v, _ in rims) / len(rims) - plain
    diameter = 2 * sum(r for _, r in rims) / len(rims)
    check("Barringer Crater rim-crest diameter (3DEP) vs 1186 m", diameter, 1186.0, tol=0.03,
          note="published ~1.19 km; measured on the DEM rim crest")
    check("Barringer Crater depth rim to floor (3DEP) vs 170 m", rim_h - floor_z, 170.0, tol=0.08,
          note="published ~170 m; DEM floor lowest point")

    half = 1500.0
    N = 340 if preview else 620
    step = 2 * half / N
    r_in, r_out = 690.0, 860.0  # crater relief (rim crest ~600 m) fades into the flat city between these radii
    import bmesh as _bm
    bm = _bm.new()
    verts = []
    for iy in range(N + 1):
        y = -half + iy * step
        row = []
        for ix in range(N + 1):
            x = -half + ix * step
            r = math.hypot(x, y)
            w = 1.0 if r <= r_in else 0.0 if r >= r_out else 0.5 + 0.5 * math.cos(math.pi * (r - r_in) / (r_out - r_in))
            row.append(bm.verts.new((x, y, (h(x, y) - plain) * w if w else 0.0)))
        verts.append(row)
    for iy in range(N):
        for ix in range(N):
            bm.faces.new((verts[iy][ix], verts[iy][ix + 1], verts[iy + 1][ix + 1], verts[iy + 1][ix]))
    me = bpy.data.meshes.new("terrain")
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    terrain = bpy.data.objects.new("Manhattan with Meteor Crater", me)
    bpy.context.collection.objects.link(terrain)

    m = bpy.data.materials.new("photos")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.92
    b.inputs["Specular IOR Level"].default_value = 0.15
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])

    def photo(name, half_m, sat, val):
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.vector_type = "POINT"
        mp.inputs["Scale"].default_value = (1 / (2 * half_m), 1 / (2 * half_m), 1)
        mp.inputs["Location"].default_value = (0.5, 0.5, 0)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(CACHE / f"naip_{name}.jpg"))
        t.extension = "EXTEND"
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        hs = nt.nodes.new("ShaderNodeHueSaturation")
        hs.inputs["Saturation"].default_value = sat
        hs.inputs["Value"].default_value = val
        nt.links.new(t.outputs["Color"], hs.inputs["Color"])
        return hs.outputs["Color"]

    city_c = photo("manhattan", half, 1.4, 1.18)
    crater_c = photo("meteor_crater", half_d, 1.15, 1.05)
    # photo blend: same radii as the relief, with a ragged noisy edge so no circle shows
    ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"
    cx = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs[0], cx.inputs[0]); nt.links.new(sep.outputs[1], cx.inputs[1])
    nt.links.new(cx.outputs[0], ln.inputs[0])
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.004
    nz.inputs["Detail"].default_value = 6
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    jit = nt.nodes.new("ShaderNodeMath"); jit.operation = "MULTIPLY_ADD"
    jit.inputs[1].default_value = 160.0; jit.inputs[2].default_value = -80.0
    nt.links.new(nz.outputs["Fac"], jit.inputs[0])
    rr = nt.nodes.new("ShaderNodeMath"); rr.operation = "ADD"
    nt.links.new(ln.outputs["Value"], rr.inputs[0]); nt.links.new(jit.outputs[0], rr.inputs[1])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = r_in - 60
    mr.inputs["From Max"].default_value = r_out - 40
    mr.interpolation_type = "SMOOTHSTEP"
    nt.links.new(rr.outputs[0], mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    nt.links.new(mr.outputs[0], mix.inputs["Factor"])
    nt.links.new(crater_c, mix.inputs["A"])
    nt.links.new(city_c, mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    terrain.data.materials.append(m)
    # wider Manhattan around it (lower resolution, 4 m/px) so the frame never shows the edge of the photo
    wm = bpy.data.materials.new("photo wide")
    wm.use_nodes = True
    wn = wm.node_tree
    wb = wn.nodes["Principled BSDF"]
    wb.inputs["Roughness"].default_value = 0.92
    wt = wn.nodes.new("ShaderNodeTexImage")
    wt.image = bpy.data.images.load(str(CACHE / "naip_manhattan_wide.jpg"))
    whs = wn.nodes.new("ShaderNodeHueSaturation")
    whs.inputs["Saturation"].default_value = 1.4
    whs.inputs["Value"].default_value = 1.18
    wn.links.new(wt.outputs["Color"], whs.inputs["Color"])
    wn.links.new(whs.outputs["Color"], wb.inputs["Base Color"])
    # a frame of four strips around the 3 km terrain, so nothing covers the crater
    W = 12000.0
    for cx_, cy_, sx_, sy_ in ((0, (W / 2 + half) / 2, W, W / 2 - half), (0, -(W / 2 + half) / 2, W, W / 2 - half),
                               ((W / 2 + half) / 2, 0, W / 2 - half, 2 * half), (-(W / 2 + half) / 2, 0, W / 2 - half, 2 * half)):
        strip = plane("Manhattan wide", 1.0, wm, loc=(cx_, cy_, -0.3))
        strip.scale = (sx_, sy_, 1)
        # UVs of the strip must address the 12 km photo at its own place
        for loop in strip.data.loops:
            co = strip.data.vertices[loop.vertex_index].co
            strip.data.uv_layers.active.data[loop.index].uv = ((cx_ + co.x * sx_) / W + 0.5, (cy_ + co.y * sy_) / W + 0.5)

    sunny_world(strength=1.2)
    sun(38, 125, strength=4.5)  # morning sun from the south-east, as in both photos
    # drone: 45 degrees off vertical from the south-south-east, crater and Midtown in one frame
    tgt = Vector((0, 60, -60))
    cam = Vector((420, -1250, 1150))
    camera(cam, tgt, lens=22, fstop=16, focus=(cam - tgt).length, clip=30000)
    haze(900, 6000, colour=(0.76, 0.86, 1.0), amount=0.18)
    return {"crater": {"diameter_m_dem": round(diameter), "depth_m_dem": round(rim_h - floor_z),
                       "rim_above_plain_m": round(rim_h), "plain_level_m": round(plain)},
            "sources": "USGS 3DEP elevation; USGS NAIP orthoimagery of Meteor Crater AZ and Midtown Manhattan (public domain)"}


SCENES = {"titanic_aerial": titanic_aerial, "titanic_pitch": titanic_pitch, "saturnv_pyramid": saturnv_pyramid,
          "crater_manhattan": crater_manhattan}


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
