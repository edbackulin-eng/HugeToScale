"""Render a range of frames of a trial Short (Blender, Cycles CPU).

    blender -b --factory-startup -P shorts/animate.py -- <short> <outdir> <start> <end> [--preview] [--step N]
                                                          [--probe F]

Scenes, timeline and captions come from plan.py (captions are drawn later by compose.py, not here).
--preview: 30 % resolution, few samples (owner rule: quick previews only), every N-th frame.
--probe F: after the range, render frame F once at full quality to measure the real per-frame cost.
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
import plan as P  # noqa: E402
import test_frame as T  # noqa: E402  (render setup, world, sun, PBR, size checks)
import objects as O  # noqa: E402
import models as BM  # noqa: E402

CACHE = ROOT / "data/cache"
FPS = P.FPS


def F(sec):
    return int(round(sec * FPS)) + 1


# ------------------------------------------------------------------------------------------- helpers

def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        if k.startswith("_"):
            setattr(n, k[1:], v)
        else:
            n.inputs[k].default_value = v
    return n


def math_node(nt, op, a, b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def maprange(nt, v, a, b, smooth=True):
    n = nt.nodes.new("ShaderNodeMapRange")
    if smooth:
        n.interpolation_type = "SMOOTHSTEP"
    n.inputs["From Min"].default_value = a
    n.inputs["From Max"].default_value = b
    nt.links.new(v, n.inputs["Value"])
    return n.outputs[0]


def mix_rgb(nt, fac, a, b):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "RGBA"
    for sock, v in (("Factor", fac), ("A", a), ("B", b)):
        if isinstance(v, (int, float)):
            n.inputs[sock].default_value = v
        elif isinstance(v, tuple):
            n.inputs[sock].default_value = (*v, 1) if len(v) == 3 else v
        else:
            nt.links.new(v, n.inputs[sock])
    return n.outputs["Result"]


def mix_val(nt, fac, a, b):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "FLOAT"
    for sock, v in (("Factor", fac), ("A", a), ("B", b)):
        if isinstance(v, (int, float)):
            n.inputs[sock].default_value = v
        else:
            nt.links.new(v, n.inputs[sock])
    return n.outputs["Result"]


def aerial(m, start, depth, most, hdri, strength, rot=0.0, sat=1.6):
    """Aerial perspective inside the material: far surfaces fade into the colour of the sky just above the
    horizon in their own direction (same HDRI, same camera-ray saturation as the background), so the ground
    melts into a real hazy horizon with no visible edge. Camera rays only; lighting is unchanged."""
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
    if not out.inputs["Surface"].links:
        return
    surf = out.inputs["Surface"].links[0].from_socket
    camd = nt.nodes.new("ShaderNodeCameraData")
    d = math_node(nt, "SUBTRACT", camd.outputs["View Distance"], start)
    d = math_node(nt, "MAXIMUM", d, 0.0)
    d = math_node(nt, "DIVIDE", d, depth)
    e = math_node(nt, "EXPONENT", math_node(nt, "MULTIPLY", d, -1.0))
    f = math_node(nt, "MULTIPLY", math_node(nt, "SUBTRACT", 1.0, e), most)
    lp = nt.nodes.new("ShaderNodeLightPath")
    f = math_node(nt, "MULTIPLY", f, lp.outputs["Is Camera Ray"])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    neg = nt.nodes.new("ShaderNodeVectorMath"); neg.operation = "SCALE"; neg.inputs["Scale"].default_value = -1.0
    nt.links.new(geo.outputs["Incoming"], neg.inputs[0])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(neg.outputs[0], sep.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs[0], comb.inputs[0]); nt.links.new(sep.outputs[1], comb.inputs[1])
    nt.links.new(math_node(nt, "MAXIMUM", sep.outputs[2], 0.035), comb.inputs[2])
    nrm = nt.nodes.new("ShaderNodeVectorMath"); nrm.operation = "NORMALIZE"
    nt.links.new(comb.outputs[0], nrm.inputs[0])
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Rotation"].default_value = (0, 0, math.radians(rot))
    nt.links.new(nrm.outputs[0], mp.inputs["Vector"])
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(T.HDRI / f"{hdri}_2k.hdr"), check_existing=True)
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    hs = nt.nodes.new("ShaderNodeHueSaturation"); hs.inputs["Saturation"].default_value = sat
    nt.links.new(env.outputs["Color"], hs.inputs["Color"])
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Strength"].default_value = strength
    nt.links.new(hs.outputs["Color"], em.inputs["Color"])
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(f, mx.inputs[0]); nt.links.new(surf, mx.inputs[1]); nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])


class Rig:
    """Camera that tracks an empty; both keyed, smooth Bezier path."""

    def __init__(self, fstop=11.0, clip=200000):
        cd = bpy.data.cameras.new("cam")
        cd.sensor_fit = "AUTO"
        cd.sensor_width = 36
        cd.clip_start = 1.0
        cd.clip_end = clip
        self.cam = bpy.data.objects.new("cam", cd)
        bpy.context.collection.objects.link(self.cam)
        self.tgt = bpy.data.objects.new("target", None)
        bpy.context.collection.objects.link(self.tgt)
        c = self.cam.constraints.new("TRACK_TO")
        c.target = self.tgt
        c.track_axis = "TRACK_NEGATIVE_Z"
        c.up_axis = "UP_Y"
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.focus_object = self.tgt
        bpy.context.scene.camera = self.cam

    def key(self, f, loc, tgt, lens):
        self.cam.location = loc
        self.tgt.location = tgt
        self.cam.data.lens = lens
        self.cam.keyframe_insert("location", frame=f)
        self.tgt.keyframe_insert("location", frame=f)
        self.cam.data.keyframe_insert("lens", frame=f)

    def shake(self, f0, f1, metres):
        """Impact shake: noise on the camera position, faded in and out."""
        for fc in self.cam.animation_data.action.fcurves:
            if fc.data_path != "location":
                continue
            mod = fc.modifiers.new("NOISE")
            mod.scale = 2.2
            mod.strength = metres * 2
            mod.phase = 7.0 * (fc.array_index + 1)
            mod.use_restricted_range = True
            mod.frame_start, mod.frame_end = f0, f1
            mod.blend_in, mod.blend_out = 1, (f1 - f0) * 0.7


def polar(c, a_deg, r, z):
    a = math.radians(a_deg)
    return Vector((c[0] + r * math.cos(a), c[1] + r * math.sin(a), z))


def set_interp(obj_or_data, path, index, interp, easing="AUTO"):
    fc = obj_or_data.animation_data.action.fcurves.find(path, index=index)
    for kp in fc.keyframe_points:
        kp.interpolation = interp
        kp.easing = easing


# ------------------------------------------------------------------------------------------- crater

def photo(nt, pos, name, half_m, sat, val):
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.vector_type = "POINT"
    mp.inputs["Scale"].default_value = (1 / (2 * half_m), 1 / (2 * half_m), 1)
    mp.inputs["Location"].default_value = (0.5, 0.5, 0)
    nt.links.new(pos, mp.inputs["Vector"])
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(str(CACHE / name), check_existing=True)
    t.extension = "EXTEND"
    t.interpolation = "Cubic" if half_m < 2000 else "Linear"
    nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
    if name.endswith(".png"):
        t.image.colorspace_settings.name = "Non-Color"
        return t.outputs["Color"]
    hs = nt.nodes.new("ShaderNodeHueSaturation")
    hs.inputs["Saturation"].default_value = sat
    hs.inputs["Value"].default_value = val
    nt.links.new(t.outputs["Color"], hs.inputs["Color"])
    return hs.outputs["Color"]


def image_mean(name):
    import numpy as np
    im = bpy.data.images.load(str(CACHE / name), check_existing=True)
    px = np.empty(len(im.pixels), dtype=np.float32)
    im.pixels.foreach_get(px)
    return tuple(float(v) for v in px.reshape(-1, 4)[:, :3].mean(axis=0))


def ground_material(name, crater=None, mean=(0.2, 0.2, 0.2)):
    """Manhattan photos (3000 m sharp + 12 km wide), OSM water as real water (blue, glossy, small waves),
    far edge fading into the photo's mean colour; optional crater photo revealed by an animated value."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(pos, sep.inputs[0])
    ax = math_node(nt, "ABSOLUTE", sep.outputs[0]); ay = math_node(nt, "ABSOLUTE", sep.outputs[1])
    near = math_node(nt, "LESS_THAN", math_node(nt, "MAXIMUM", ax, ay), 1495.0)
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs[0], comb.inputs[0]); nt.links.new(sep.outputs[1], comb.inputs[1])
    ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; nt.links.new(comb.outputs[0], ln.inputs[0])
    r = ln.outputs["Value"]
    city = mix_rgb(nt, near, photo(nt, pos, "naip_manhattan_wide.jpg", 6000, 1.4, 1.18),
                   photo(nt, pos, "naip_manhattan.jpg", 1500, 1.4, 1.18))
    fade = maprange(nt, r, 4300, 5900)
    city = mix_rgb(nt, fade, city, mean)
    wmask = maprange(nt, photo(nt, pos, "water_manhattan_wide.png", 6000, 1, 1), 0.3, 0.7)
    wmask = math_node(nt, "MULTIPLY", wmask, math_node(nt, "SUBTRACT", 1.0, fade))
    col = city
    if crater:
        r_in, r_out, reveal = crater
        cr = photo(nt, pos, "naip_meteor_crater.jpg", 1300, 1.15, 1.05)
        # soften the pale desert ring: towards the lip the crater photo takes the city's grey stone tone
        grey = nt.nodes.new("ShaderNodeHueSaturation")
        grey.inputs["Saturation"].default_value = 0.45
        grey.inputs["Value"].default_value = 0.78
        nt.links.new(cr, grey.inputs["Color"])
        cr = mix_rgb(nt, math_node(nt, "MULTIPLY", maprange(nt, r, 560, 720), 0.75), cr, grey.outputs["Color"])
        nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.004
        nz.inputs["Detail"].default_value = 6
        nt.links.new(pos, nz.inputs["Vector"])
        jit = math_node(nt, "MULTIPLY_ADD", nz.outputs["Fac"], 140.0)
        jit.node.inputs[2].default_value = -70.0
        rr = math_node(nt, "ADD", r, jit)
        to_city = maprange(nt, rr, r_in - 70, r_out - 30)
        fc = math_node(nt, "MULTIPLY", math_node(nt, "SUBTRACT", 1.0, to_city), reveal(nt))
        col = mix_rgb(nt, fc, city, cr)
        wmask = math_node(nt, "MULTIPLY", wmask, math_node(nt, "SUBTRACT", 1.0, fc))
    water_col = (0.016, 0.075, 0.19)
    nt.links.new(mix_rgb(nt, wmask, col, water_col), b.inputs["Base Color"])
    nt.links.new(mix_val(nt, wmask, 0.92, 0.07), b.inputs["Roughness"])
    nt.links.new(mix_val(nt, wmask, 0.15, 0.5), b.inputs["Specular IOR Level"])
    waves = nt.nodes.new("ShaderNodeTexNoise"); waves.inputs["Scale"].default_value = 0.09
    waves.inputs["Detail"].default_value = 8; waves.inputs["Roughness"].default_value = 0.6
    nt.links.new(pos, waves.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Distance"].default_value = 0.4
    nt.links.new(math_node(nt, "MULTIPLY", wmask, 0.35), bump.inputs["Strength"])
    nt.links.new(waves.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def strips(name, inner, outer, z, m):
    """A square frame of four planes between |xy| = inner and outer (leaves the crater uncovered)."""
    for cx, cy, sx, sy in ((0, (outer + inner) / 2, 2 * outer, outer - inner), (0, -(outer + inner) / 2, 2 * outer, outer - inner),
                           ((outer + inner) / 2, 0, outer - inner, 2 * inner), (-(outer + inner) / 2, 0, outer - inner, 2 * inner)):
        p = T.plane(name, 1.0, m, loc=(cx, cy, z))
        p.scale = (sx, sy, 1)


WALLS = [((0.50, 0.45, 0.38), 0.8, 0.0), ((0.42, 0.42, 0.42), 0.8, 0.0), ((0.36, 0.20, 0.14), 0.85, 0.0),
         ((0.60, 0.59, 0.56), 0.75, 0.0), ((0.10, 0.14, 0.19), 0.12, 0.6), ((0.13, 0.20, 0.28), 0.10, 0.5)]


def buildings(data, r_cut, roof):
    """OSM footprints extruded to their tagged heights (NYC import has heights for nearly all).
    Returns (outer, inner): inner = everything that touches the crater (it collapses when the crater forms)."""
    import random
    import bmesh
    rnd = random.Random(11)
    walls = []
    for i, (c, rough, metal) in enumerate(WALLS):
        w = bpy.data.materials.new(f"wall {i}")
        w.use_nodes = True
        bb = w.node_tree.nodes["Principled BSDF"]
        bb.inputs["Base Color"].default_value = (*c, 1)
        bb.inputs["Roughness"].default_value = rough
        bb.inputs["Metallic"].default_value = metal
        walls.append(w)
    feats = [f for f in data["features"] if f["kind"] in ("building", "part") and len(f["pts"]) >= 4]
    # outlines that have parts are drawn by their parts (grid lookup of part centres)
    grid = {}
    for f in feats:
        if f["kind"] == "part":
            cx = sum(p[0] for p in f["pts"]) / len(f["pts"]); cy = sum(p[1] for p in f["pts"]) / len(f["pts"])
            grid.setdefault((int(cx // 60), int(cy // 60)), []).append((cx, cy))
    import city as C
    meshes = {"outer": bmesh.new(), "inner": bmesh.new()}
    n = {"outer": 0, "inner": 0}
    for f in feats:
        pts = [tuple(p) for p in f["pts"]]
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3:
            continue
        if f["kind"] == "building":
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            hit = False
            for gx in range(int(min(xs) // 60), int(max(xs) // 60) + 1):
                for gy in range(int(min(ys) // 60), int(max(ys) // 60) + 1):
                    if any(C.point_in(c, pts) for c in grid.get((gx, gy), [])):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                continue
        h = f["height"] or rnd.uniform(10, 24)
        z0 = f["min_height"] or -2.0
        if h <= z0 + 0.5 or h > 560:
            continue
        if C._area(pts) < 0:
            pts = pts[::-1]
        key = "inner" if min(math.hypot(x, y) for x, y in pts) < r_cut else "outer"
        bm = meshes[key]
        tall = h > 110
        mi = rnd.choice((4, 5, 4, 0)) if tall else rnd.choice((0, 1, 2, 3, 0, 1, 3))
        bottom = [bm.verts.new((x, y, z0)) for x, y in pts]
        top = [bm.verts.new((x, y, h)) for x, y in pts]
        try:
            bm.faces.new(top).material_index = len(walls)
        except ValueError:
            continue
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            try:
                bm.faces.new((bottom[i], bottom[j], top[j], top[i])).material_index = mi
            except ValueError:
                pass
        n[key] += 1
    out = []
    for key in ("outer", "inner"):
        me = bpy.data.meshes.new(f"buildings {key}")
        meshes[key].to_mesh(me); meshes[key].free()
        ob = bpy.data.objects.new(f"OSM buildings {key}", me)
        bpy.context.collection.objects.link(ob)
        for w in walls + [roof]:
            ob.data.materials.append(w)
        out.append(ob)
    print("buildings", n)
    return out, n


def crater_manhattan(preview, rig):
    import array

    import numpy as np
    meta = json.loads((CACHE / "dem_meteor_crater.json").read_text())
    n_px, half_d = meta["px"], meta["half_m"]
    z = np.frombuffer((CACHE / "dem_meteor_crater.f32").read_bytes(), dtype="<f4").reshape(n_px, n_px)

    def h(x, y):
        u = np.clip((x + half_d) / (2 * half_d) * (n_px - 1), 0, n_px - 1.001)
        v = np.clip((half_d - y) / (2 * half_d) * (n_px - 1), 0, n_px - 1.001)
        i, j = v.astype(int), u.astype(int)
        fu, fv = u - j, v - i
        return ((z[i, j] * (1 - fu) + z[i, j + 1] * fu) * (1 - fv) + (z[i + 1, j] * (1 - fu) + z[i + 1, j + 1] * fu) * fv)

    t = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    plain = float(np.median(np.concatenate([h(r * np.cos(t), r * np.sin(t)) for r in (1000, 1150, 1250)])))
    rr = np.arange(400, 800, 5.0)
    rim_v, rim_r = [], []
    for a in t:
        hv = h(rr * np.cos(a), rr * np.sin(a))
        k = int(np.argmax(hv)); rim_v.append(hv[k]); rim_r.append(rr[k])
    rim_h = float(np.mean(rim_v)) - plain
    floor_z = float(z.min()) - plain
    diameter = 2 * float(np.mean(rim_r))
    T.check("Barringer Crater rim-crest diameter (3DEP) vs 1186 m", diameter, 1186.0, tol=0.03,
            note="published ~1.19 km; measured on the DEM rim crest")
    T.check("Barringer Crater depth rim to floor (3DEP) vs 170 m", rim_h - floor_z, 170.0, tol=0.08,
            note="published ~170 m; DEM floor lowest point")

    half, N = 1500.0, (300 if preview else 640)
    r_in, r_out = 650.0, 780.0
    g = np.linspace(-half, half, N + 1)
    X, Y = np.meshgrid(g, g)
    R = np.hypot(X, Y)
    w = np.where(R <= r_in, 1.0, np.where(R >= r_out, 0.0, 0.5 + 0.5 * np.cos(np.pi * (R - r_in) / (r_out - r_in))))
    Z = (h(X, Y) - plain) * w
    me = bpy.data.meshes.new("terrain")
    verts = np.stack([X.ravel(), Y.ravel(), np.zeros(X.size)], axis=1)
    idx = np.arange((N + 1) * (N + 1)).reshape(N + 1, N + 1)
    quads = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], axis=1)
    me.from_pydata(verts.tolist(), [], quads.tolist())
    me.shade_smooth()
    terrain = bpy.data.objects.new("Manhattan with Meteor Crater", me)
    bpy.context.collection.objects.link(terrain)
    terrain.shape_key_add(name="Basis", from_mix=False)
    kb = terrain.shape_key_add(name="crater", from_mix=False)
    kb.data.foreach_set("co", np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1).astype(np.float32).ravel())

    fa = F(P.SHORTS["crater_manhattan"]["appear"])
    reveal_nodes = []

    def reveal(nt):
        v = nt.nodes.new("ShaderNodeValue")
        reveal_nodes.append(v)
        return v.outputs[0]

    mean = image_mean("naip_manhattan_wide.jpg")
    mean = tuple(min(1.0, c * 1.18) for c in mean)
    ground = ground_material("ground", crater=(r_in, r_out, reveal), mean=mean)
    terrain.data.materials.append(ground)
    roof = ground_material("roofs", mean=mean)
    strips("Manhattan wide", half, 6000.0, -0.3, roof)
    far = bpy.data.materials.new("far land")
    far.use_nodes = True
    far.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*mean, 1)
    far.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.95
    strips("far land", 5990.0, 120000.0, -0.6, far)

    data = json.loads((CACHE / "osm_midtown.json").read_text(encoding="utf-8"))
    (outer, inner), counts = buildings(data, r_out + 10, roof)

    # --- appearance: the city block collapses, the crater opens, its photo replaces the streets
    kb.value = 0.0; kb.keyframe_insert("value", frame=fa + 1)
    kb.value = 1.0; kb.keyframe_insert("value", frame=fa + 15)
    for v in reveal_nodes:
        v.outputs[0].default_value = 0.0; v.outputs[0].keyframe_insert("default_value", frame=fa + 2)
        v.outputs[0].default_value = 1.0; v.outputs[0].keyframe_insert("default_value", frame=fa + 16)
    inner.location.z = 0.0; inner.scale.z = 1.0
    inner.keyframe_insert("location", index=2, frame=fa)
    inner.keyframe_insert("scale", index=2, frame=fa)
    inner.location.z = -260.0; inner.scale.z = 0.25
    inner.keyframe_insert("location", index=2, frame=fa + 12)
    inner.keyframe_insert("scale", index=2, frame=fa + 12)
    set_interp(inner, "location", 2, "QUAD", "EASE_IN")
    inner.hide_render = False; inner.keyframe_insert("hide_render", frame=fa + 12)
    inner.hide_render = True; inner.keyframe_insert("hide_render", frame=fa + 13)
    fc =inner.animation_data.action.fcurves.find("hide_render")
    for kp in fc.keyframe_points:
        kp.interpolation = "CONSTANT"

    T.sunny_world(strength=1.2)
    T.sun(38, 125, strength=4.5)
    for mtl in (ground, roof, far, *[m for m in bpy.data.materials if m.name.startswith("wall")]):
        aerial(mtl, 1200, 16000, 0.97, "kloofendal_43d_clear_puresky", 1.2)

    # --- camera: drone over intact Midtown -> impact -> orbit on the sunlit side -> pull back over Central Park
    end = P.frames("crater_manhattan")
    C0 = (0, 0)
    rig.key(1, Vector((330, -1560, 690)), Vector((0, 160, 0)), 24)
    rig.key(fa, Vector((280, -1400, 720)), Vector((0, 110, -20)), 24)
    rig.key(fa + 30, Vector((220, -1290, 780)), Vector((0, 60, -60)), 22)
    rig.key(F(8.0), polar(C0, -64, 1240, 700), Vector((0, 20, -80)), 21)
    rig.key(F(13.5), polar(C0, -42, 1130, 560), Vector((0, 0, -90)), 20)
    d = Vector((math.sin(math.radians(29)), math.cos(math.radians(29)), 0))   # Manhattan grid bearing
    final_cam = -d * 1950 + Vector((0, 0, 2450))
    final_tgt = d * 1250
    rig.key(F(17.5), polar(C0, -95, 1700, 1500), d * 500 + Vector((0, 0, -40)), 22)
    rig.key(end - 12, final_cam, final_tgt, 24)
    rig.key(end, final_cam, final_tgt, 24)
    rig.shake(fa + 3, fa + 34, 5.0)
    rig.cam.data.dof.aperture_fstop = 16
    return {"crater": {"diameter_m_dem": round(diameter), "depth_m_dem": round(rim_h - floor_z),
                       "rim_above_plain_m": round(rim_h)}, "buildings": counts}


# ------------------------------------------------------------------------------------------- pyramid

def saturnv_pyramid(preview, rig):
    info = T.saturnv_pyramid(preview)
    # the test scene added its own fixed camera: drop it, the rig drives the shot
    for ob in list(bpy.data.objects):
        if ob.type == "CAMERA" and ob is not rig.cam:
            bpy.data.objects.remove(ob)
    bpy.context.scene.camera = rig.cam
    sand = bpy.data.materials["sand"]
    T.plane("far desert", 240000, sand, loc=(0, 0, -1.2))
    # owner 18.11 (ladder fix carried over): no black face - a soft fill light from the orbit's side (south), no
    # shadows of its own (rotating the sky's sun behind the camera washed the whole frame out), and the warm
    # sandstone courses of the ladder Short
    import ladder
    fill = T.sun(30, 190, strength=1.6, angle=8.0)
    fill.data.cycles.cast_shadow = False
    pyr = bpy.data.objects["Great Pyramid"]
    pyr.data.materials.clear()
    pyr.data.materials.append(ladder.sandstone())
    sv = next(o for o in bpy.data.objects if o.name.startswith("Saturn V") and o.parent is None)
    fa = F(P.SHORTS["saturnv_pyramid"]["appear"])
    land = fa + 14
    sv.location.z = 330.0
    sv.keyframe_insert("location", index=2, frame=1)
    sv.keyframe_insert("location", index=2, frame=fa)
    sv.location.z = 0.0
    sv.keyframe_insert("location", index=2, frame=land)
    fc = sv.animation_data.action.fcurves.find("location", index=2)
    fc.keyframe_points[0].interpolation = "CONSTANT"
    fc.keyframe_points[1].interpolation = "QUAD"
    fc.keyframe_points[1].easing = "EASE_IN"
    sv.hide_render = True; sv.keyframe_insert("hide_render", frame=1)
    sv.hide_render = False; sv.keyframe_insert("hide_render", frame=fa - 1)
    for kp in sv.animation_data.action.fcurves.find("hide_render").keyframe_points:
        kp.interpolation = "CONSTANT"
    for ch in sv.children_recursive:
        ch.hide_render = True; ch.keyframe_insert("hide_render", frame=1)
        ch.hide_render = False; ch.keyframe_insert("hide_render", frame=fa - 1)
        for kp in ch.animation_data.action.fcurves.find("hide_render").keyframe_points:
            kp.interpolation = "CONSTANT"

    end = P.frames("saturnv_pyramid")
    C0 = (64, 0)
    rig.key(1, polar(C0, -58, 390, 42), Vector((40, 0, 62)), 30)
    rig.key(fa, polar(C0, -60, 360, 46), Vector((44, 0, 62)), 30)
    rig.key(land + 20, polar(C0, -66, 380, 55), Vector((50, 0, 58)), 30)
    rig.key(F(9.0), polar(C0, -84, 450, 120), Vector((40, 0, 50)), 30)
    rig.key(F(14.5), polar(C0, -102, 500, 170), Vector((40, 0, 45)), 30)
    rig.key(end - 14, Vector((64, -420, 70)), Vector((64, 0, 56)), 40)
    rig.key(end, Vector((64, -420, 70)), Vector((64, 0, 56)), 40)
    rig.shake(land, land + 24, 1.6)
    return info


def ladder_heights(preview, rig):
    import ladder
    return ladder.build("ladder_heights", preview, rig)


SCENES = {"crater_manhattan": crater_manhattan, "saturnv_pyramid": saturnv_pyramid, "ladder_heights": ladder_heights}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    name, out, a, b = argv[0], Path(argv[1]).resolve(), int(argv[2]), int(argv[3])
    preview = "--preview" in argv
    step = int(argv[argv.index("--step") + 1]) if "--step" in argv else 1
    probe = int(argv[argv.index("--probe") + 1]) if "--probe" in argv else None
    out.mkdir(parents=True, exist_ok=True)
    T.render_setup(preview)
    sc = bpy.context.scene
    if preview:
        sc.render.resolution_percentage = 30
        sc.cycles.samples = 8
    rig = Rig()
    t0 = time.time()
    extra = SCENES[name](preview, rig)
    build_s = time.time() - t0
    info = {"short": name, "preview": preview, "frames": [a, b, step], "checks": T.CHECKS, **extra,
            "build_seconds": round(build_s, 1)}
    bad = [c for c in T.CHECKS if not c["ok"]]
    if bad:
        info["status"] = "size check failed — not rendered"
        (out / f"info_{name}_{a}.json").write_text(json.dumps(info, indent=1))
        raise SystemExit("SIZE CHECK FAILED: " + ", ".join(c["object"] for c in bad))
    sc.frame_start, sc.frame_end, sc.frame_step = a, b, step
    sc.render.filepath = str(out / "f####")
    t1 = time.time()
    bpy.ops.render.render(animation=True)
    n = len(range(a, b + 1, step))
    info["seconds_per_frame"] = round((time.time() - t1) / n, 1)
    if probe:
        sc.render.resolution_percentage = 100
        sc.cycles.samples = int(os.environ.get("SAMPLES", 24))
        sc.frame_set(probe)
        sc.render.filepath = str(out / f"probe_{probe:04d}.png")
        t2 = time.time()
        bpy.ops.render.render(write_still=True)
        info["probe_full_quality_seconds"] = round(time.time() - t2, 1)
    tr = CACHE.parent / "ladder_track.json"
    if tr.exists():
        (out / "ladder_track.json").write_bytes(tr.read_bytes())
    info["status"] = "rendered"
    (out / f"info_{name}_{a}.json").write_text(json.dumps(info, indent=1))
    print("DONE", json.dumps({k: info[k] for k in ("seconds_per_frame", "build_seconds")}))


if __name__ == "__main__":
    main()
