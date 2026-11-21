"""Blender scene of a "size ladder" Short (imported by animate.py).

Orthographic side view, camera looking north (+y), pitch 0: every object is compared at true scale wherever
it stands, so smaller things can stand in front of bigger ones (like a long-lens panorama). Heights:
plan.LADDERS; mountains are Copernicus DEM GLO-30 summits (real relief) whose far flanks fade into the plain.
The sky and the ground band are a camera-locked backdrop (same HDRI and colour pipeline as the haze), so
the horizon is always at the same screen line and the objects' bases sit on it.
"""
import json
import math

import bpy
import numpy as np

import animate as A
import models as BM
import objects as O
import plan as P
import test_frame as T

FPS = P.FPS
GROUND_Y = 1350 / 1920       # base line of every object, fraction of the frame from the top
TOP_FILL = 2.1               # frame height = 2.1 x the current object's height
MIN_FILL = 2.05              # never less: the top stays below the caption band (ground at 1350 px, caption to ~420 px)
HDRI_ID = "kloofendal_43d_clear_puresky"
CAM_DIST = 60000.0


def hdri_sun_azimuth():
    """Horizontal angle (radians, atan2(y, x)) of the brightest pixel of the HDRI = its sun."""
    im = bpy.data.images.load(str(T.HDRI / f"{HDRI_ID}_2k.hdr"), check_existing=True)
    w, h = im.size
    px = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(px)
    lum = px.reshape(h, w, 4)[:, :, :3].sum(axis=2)
    r, c = np.unravel_index(int(np.argmax(lum)), lum.shape)
    u = (c + 0.5) / w
    phi = (u - 0.5) * 2 * math.pi            # Blender equirect: u = atan2(y, -x) / 2pi + 0.5
    x, y = -math.cos(phi), math.sin(phi)
    elev = ((r + 0.5) / h - 0.5) * math.pi    # row 0 = bottom in Blender's pixel buffer
    return math.atan2(y, x), math.degrees(elev)


# ------------------------------------------------------------------------------------------- materials

def sandstone():
    """Limestone courses without repeats: Blender brick texture (1 m courses, random block lengths and
    tones) laid along each face, weathering noise and a light bump. Warm sandstone, not olive."""
    m = bpy.data.materials.new("pyramid sandstone")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nsep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(geo.outputs["Normal"], nsep.inputs[0])
    ax = A.math_node(nt, "ABSOLUTE", nsep.outputs[0]); ay = A.math_node(nt, "ABSOLUTE", nsep.outputs[1])
    wx = A.math_node(nt, "DIVIDE", ay, A.math_node(nt, "ADD", A.math_node(nt, "ADD", ax, ay), 1e-4))
    # along a north/south face the course runs in x, along an east/west face in y
    u = A.math_node(nt, "ADD", A.math_node(nt, "MULTIPLY", sep.outputs[0], wx),
                    A.math_node(nt, "MULTIPLY", sep.outputs[1], A.math_node(nt, "SUBTRACT", 1.0, wx)))
    vec = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(u, vec.inputs[0]); nt.links.new(sep.outputs[2], vec.inputs[1])
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.5
    br.squash = 1.0
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 1.7
    br.inputs["Row Height"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.09
    br.inputs["Mortar Smooth"].default_value = 0.4
    br.inputs["Bias"].default_value = 0.0
    br.inputs["Color1"].default_value = (0.86, 0.62, 0.34, 1)
    br.inputs["Color2"].default_value = (0.95, 0.75, 0.46, 1)
    br.inputs["Mortar"].default_value = (0.55, 0.38, 0.21, 1)
    nt.links.new(vec.outputs[0], br.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.05
    nz.inputs["Detail"].default_value = 6
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    # weathering changes brightness only (mixing grey noise colour turned the stone grey)
    fine = nt.nodes.new("ShaderNodeTexNoise"); fine.inputs["Scale"].default_value = 2.5
    nt.links.new(tc.outputs["Object"], fine.inputs["Vector"])
    shade = A.math_node(nt, "ADD", A.math_node(nt, "MULTIPLY", nz.outputs["Fac"], 0.22), 0.90)
    shade = A.math_node(nt, "ADD", shade, A.math_node(nt, "MULTIPLY", fine.outputs["Fac"], 0.12))
    mul = nt.nodes.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(br.outputs["Color"], mul.inputs["A"])
    gray = nt.nodes.new("ShaderNodeCombineXYZ")
    for k in range(3):
        nt.links.new(shade, gray.inputs[k])
    nt.links.new(gray.outputs[0], mul.inputs["B"])
    nt.links.new(mul.outputs["Result"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.9
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.45
    bump.inputs["Distance"].default_value = 0.08
    hgt = A.math_node(nt, "ADD", A.math_node(nt, "MULTIPLY", br.outputs["Fac"], -1.0), fine.outputs["Fac"])
    nt.links.new(hgt, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


ZONES = {  # (height m, colour) bands for real-looking mountains, plus snow line and max snow slope
    "fuji": ([(0, (0.07, 0.12, 0.05)), (1500, (0.09, 0.13, 0.06)), (2100, (0.16, 0.13, 0.08)),
              (2600, (0.20, 0.11, 0.08)), (3300, (0.14, 0.09, 0.07))], 3350, 0.55),
    "kili": ([(0, (0.08, 0.13, 0.05)), (2700, (0.10, 0.14, 0.06)), (3300, (0.20, 0.18, 0.10)),
              (4200, (0.26, 0.22, 0.18)), (5200, (0.30, 0.27, 0.24))], 5650, 0.40),
    "everest": ([(0, (0.16, 0.15, 0.11)), (4300, (0.22, 0.20, 0.17)), (5200, (0.20, 0.19, 0.18)),
                 (6500, (0.17, 0.16, 0.16))], 5600, 0.52),
}


def generic_zones(lat, top, volcanic=False):
    """Bands for any summit from its latitude: forest up to the tree line, then scrub, bare rock (dark basalt for a
    volcano), snow above the climatic snow line (tropics ~4,900 m, 45 deg ~2,700 m, 65 deg ~900 m)."""
    a = abs(lat or 30.0)
    tree = max(300.0, 3800.0 - max(0.0, a - 20) * 62)
    snow = max(500.0, 4900.0 - max(0.0, a - 20) * 90)
    rock = (0.12, 0.11, 0.10) if volcanic else (0.20, 0.18, 0.15)
    bands = [(0, (0.07, 0.12, 0.05)), (0.6 * tree, (0.09, 0.13, 0.06)), (tree, (0.16, 0.14, 0.09)),
             (tree + 0.35 * max(300.0, snow - tree), rock), (max(top, tree + 600.0), tuple(c * 0.9 for c in rock))]
    return bands, snow, 0.5


def mountain_material(key, top, lat=None, volcanic=False):
    bands, snow_line, max_slope = ZONES[key] if key in ZONES else generic_zones(lat, top, volcanic)
    m = bpy.data.materials.new(f"{key} relief")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.0012
    nz.inputs["Detail"].default_value = 8
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    h = A.math_node(nt, "ADD", sep.outputs[2], A.math_node(nt, "MULTIPLY", A.math_node(nt, "SUBTRACT", nz.outputs["Fac"], 0.5), 500.0))
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*bands[0][1], 1)
    els[1].position, els[1].color = min(1.0, bands[-1][0] / top), (*bands[-1][1], 1)
    for z, c in bands[1:-1]:
        e = els.new(min(0.999, z / top)); e.color = (*c, 1)
    nt.links.new(A.math_node(nt, "DIVIDE", h, top), ramp.inputs["Fac"])
    nsep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(geo.outputs["Normal"], nsep.inputs[0])
    slope = A.math_node(nt, "SUBTRACT", 1.0, nsep.outputs[2])
    snow = A.math_node(nt, "MULTIPLY", A.maprange(nt, h, snow_line - 120, snow_line + 120),
                       A.math_node(nt, "SUBTRACT", 1.0, A.maprange(nt, slope, max_slope - 0.12, max_slope + 0.08)))
    rock_n = nt.nodes.new("ShaderNodeTexNoise"); rock_n.inputs["Scale"].default_value = 0.02
    rock_n.inputs["Detail"].default_value = 10
    nt.links.new(tc.outputs["Object"], rock_n.inputs["Vector"])
    base = A.mix_rgb(nt, 0.18, ramp.outputs["Color"], rock_n.outputs["Color"])
    nt.links.new(A.mix_rgb(nt, snow, base, (0.86, 0.88, 0.92)), b.inputs["Base Color"])
    nt.links.new(A.mix_val(nt, snow, 0.92, 0.45), b.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 6.0
    nt.links.new(rock_n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def backdrop_material(rot_deg, strength):
    """Camera-locked sky + ground band: sky from the same HDRI looking north, 2 -> 32 degrees up the frame;
    below the horizon line a sunlit plain fading into the horizon haze."""
    m = bpy.data.materials.new("backdrop")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["UV"], sep.inputs[0])
    v = sep.outputs[1]
    vg = 1 - GROUND_Y
    e = A.maprange(nt, v, vg, 1.0, smooth=False)
    e = A.math_node(nt, "ADD", A.math_node(nt, "MULTIPLY", e, math.radians(30)), math.radians(2))
    dirv = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(A.math_node(nt, "COSINE", e), dirv.inputs[1])
    nt.links.new(A.math_node(nt, "SINE", e), dirv.inputs[2])
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Rotation"].default_value = (0, 0, math.radians(rot_deg))
    nt.links.new(dirv.outputs[0], mp.inputs["Vector"])
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(T.HDRI / f"{HDRI_ID}_2k.hdr"), check_existing=True)
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    hs = nt.nodes.new("ShaderNodeHueSaturation"); hs.inputs["Saturation"].default_value = 1.6
    nt.links.new(env.outputs["Color"], hs.inputs["Color"])
    sky = A.math_node(nt, "GREATER_THAN", v, vg)
    # ground: sunlit desert plain, haze towards the horizon line
    gf = A.maprange(nt, v, 0.0, vg)
    gf = A.math_node(nt, "POWER", gf, 6.0)
    ground = A.mix_rgb(nt, gf, (0.50, 0.38, 0.25), hs.outputs["Color"])
    col = A.mix_rgb(nt, sky, ground, hs.outputs["Color"])
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Strength"].default_value = strength
    nt.links.new(col, em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


# ------------------------------------------------------------------------------------------- objects

def burj_khalifa(x, y):
    """Simple form of Burj Khalifa: Y-shaped plan (three wings around a hexagonal core) stepping back in a
    spiral, core to 585 m, spire to 828 m (official height). No facade detail."""
    glass = BM.mat("burj glass", (0.60, 0.66, 0.74), 0.12, 0.85)
    parts = [BM.cyl(0, 0, 0, 585, 17.0, 9.0, m=glass, n=6, name="core"),
             BM.cyl(0, 0, 585, 243, 6.5, 0.4, m=glass, n=12, name="spire")]
    for i in range(3):
        a = math.radians(90 + 120 * i)
        for k in range(26):
            z0 = k * 22.0
            zz = z0 + i * 7.5
            if zz > 560:
                break
            L = 56 * (1 - zz / 600) ** 0.85 + 4
            cx, cy = math.cos(a) * (14 + L / 2), math.sin(a) * (14 + L / 2)
            bx = BM.box(cx, cy, z0, L, 30, 22.0, glass, name="wing")
            bx.rotation_euler.z = a
            parts.append(bx)
    return BM.group(parts, "Burj Khalifa", x, y)


def lib_object(step):
    """A library object (data/objects.json): the model imported, joined into one mesh, stood upright with its base
    at z = 0 (origin at the base centre, so the ladder can grow it with scale.z), scaled to the sourced height."""
    import library
    o = library.get(step["key"])
    path = library.model_path(step["key"])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [ob for ob in bpy.data.objects if ob not in before]
    meshes = [ob for ob in new if ob.type == "MESH"]
    for ob in new:                                  # bake parents' transforms, drop empties / cameras / lights
        if ob.type == "MESH":
            mw = ob.matrix_world.copy()
            ob.parent = None
            ob.matrix_world = mw
    for ob in new:
        if ob.type != "MESH":
            bpy.data.objects.remove(ob)
    bpy.ops.object.select_all(action="DESELECT")
    for ob in meshes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    rx, ry, rz = (math.radians(a) for a in o["model"].get("rot", (0, 0, 0)))
    ob.rotation_euler = (ob.rotation_euler.x + rx, ob.rotation_euler.y + ry, ob.rotation_euler.z + rz)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    (x0, x1), (y0, y1), (z0, z1) = O.world_bounds(ob)
    for v in ob.data.vertices:                      # origin at the base centre
        v.co.x -= (x0 + x1) / 2
        v.co.y -= (y0 + y1) / 2
        v.co.z -= z0
    k = step["h"] / (z1 - z0)
    ob.scale = (k, k, k)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.location = (step["x"], step["y"], 0)
    ob.name = o["name"].title()
    T.check(f"{o['name'].title()} height", O.world_bounds(ob)[2][1], step["h"])
    (x0, x1), (y0, y1), _ = O.world_bounds(ob)
    step["model_w"] = round(x1 - x0, 2)
    return ob


def mountain(step):
    name = step["dem"][0]
    meta = json.loads((A.CACHE / f"dem_{name}.json").read_text())
    n, half = meta["px"], meta["half_m"]
    z = np.frombuffer((A.CACHE / f"dem_{name}.f32").read_bytes(), dtype="<f4").reshape(n, n).astype(np.float64)
    g = np.linspace(-half, half, n)
    X, Y = np.meshgrid(g, -g)                    # row 0 = north
    sx, sy = meta["summit_xy"]
    R = np.hypot(X - sx, Y - sy)
    r_in, r_out = step["r_in"], step["r_out"]
    w = np.where(R <= r_in, 1.0, np.where(R >= r_out, 0.0, 0.5 + 0.5 * np.cos(np.pi * (R - r_in) / (r_out - r_in))))
    Z = np.maximum(z, 0.0) * w
    # a 30 m DEM averages a sharp summit (Everest's cell is ~112 m below the surveyed point): restore the
    # surveyed summit with a 300 m taper; the raw DEM figure is reported next to the check
    raw = float(Z.max())
    if raw < step["h"]:
        Z = Z + (step["h"] - raw) * np.clip(1 - R / 300.0, 0, 1) ** 2
    T.check(f"{step['name'].title()} summit raw DEM (30 m grid) vs {step['h']} m", raw, step["h"], tol=0.02,
            note="before restoring the surveyed summit point")
    me = bpy.data.meshes.new(name)
    verts = np.stack([(X - sx).ravel(), (Y - sy).ravel(), Z.ravel()], axis=1)
    idx = np.arange(n * n).reshape(n, n)
    quads = np.stack([idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()], axis=1)
    me.from_pydata(verts.tolist(), [], quads.tolist())
    me.shade_smooth()
    ob = bpy.data.objects.new(step["name"].title(), me)
    bpy.context.collection.objects.link(ob)
    ob.location = (step["x"], step["y"], 0)
    ob.data.materials.append(mountain_material(step["key"], meta["summit_m"], step.get("lat"), step.get("volcanic")))
    T.check(f"{step['name'].title()} summit in the scene vs {step['h']} m", float(Z.max()), step["h"], tol=0.01,
            note="Copernicus DEM relief, summit point restored to the surveyed height")
    return ob


# ------------------------------------------------------------------------------------------- camera plan

def framings(L):
    """Frame (centre x, ortho height S) for every step: the newest object fills ~half the frame height and
    everything so far stays in frame (left-aligned ladder growing to the right)."""
    out = []
    left = None
    for s in L["steps"]:
        half_w = s.get("half_w") or {"saturnv": 8, "pyramid": 116, "burj": 75}.get(s["key"]) or             (0.5 * s["w"] if s.get("w") else 900)
        lo, hi = s["x"] - half_w, s["x"] + half_w
        left = lo if left is None else min(left, lo)
        S = TOP_FILL * s["h"]
        W = S * 1080 / 1920
        need = (hi - left) / 0.86
        if need > W:
            S, W = need * 1920 / 1080, need
        xc = left - 0.07 * W + W / 2
        out.append((xc, S))
    return out


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def camera_track(L, total):
    fr = framings(L)
    st = L["steps"]
    track = []
    for f in range(1, total + 1):
        t = (f - 1) / FPS
        k = max(i for i, s in enumerate(st) if s["t"] <= t)
        xc, S = fr[k]
        if k > 0:  # move from the previous framing: 0.95 s, log-space zoom (feels like a steady pull-back)
            a = ease((t - st[k]["t"]) / 0.95)
            x0, S0 = fr[k - 1]
            S1_ = S
            S = math.exp(math.log(S0) + (math.log(S1_) - math.log(S0)) * a)
            # x follows the zoom (not the clock): the ladder stays put on screen while the camera pulls back
            xc = x0 + (xc - x0) * (S - S0) / (S1_ - S0) if abs(S1_ - S0) > 1e-6 else x0 + (xc - x0) * a
        # slow drift while holding
        hold_end = st[k + 1]["t"] if k + 1 < len(st) else L["overview"]
        S *= 1 + 0.035 * ease((t - st[k]["t"] - 0.95) / max(0.1, hold_end - st[k]["t"] - 0.95))
        if t >= L["overview"]:
            a = ease((t - L["overview"]) / 0.8)
            S *= 1 + 0.10 * a
        if t >= L["rewind"]:
            # rewind into frame 1, then 3 still frames identical to the start: a seamless loop
            a = ease((t - L["rewind"]) / (L["seconds"] - 4 / FPS - L["rewind"]))
            x1, S1 = fr[0]
            xe, Se = track[int(L["rewind"] * FPS) - 1]["x"], track[int(L["rewind"] * FPS) - 1]["S"]
            S = math.exp(math.log(Se) + (math.log(S1) - math.log(Se)) * a)
            xc = x1 + (xe - x1) * (S - S1) / (Se - S1)
        track.append({"f": f, "x": xc, "S": S})
    return track


def scale_at(L, i, t, S=None):
    """Height scale of step i at time t: rises in 0.4 s (slight overshoot), sinks back during the rewind.
    With the frame height S: never taller than the frame allows (owner 18.11: a rising object is not cut at the
    top) - a tall object rises together with the camera's pull-back, its top just under the caption band."""
    v = _scale_at(L, i, t)
    if S is not None and t < L["rewind"] and i > 0:
        v = min(v, S / (MIN_FILL * L["steps"][i]["h"]))
    return v


def _scale_at(L, i, t):
    s = L["steps"][i]
    if i == 0:
        return 1.0
    if t < s["t"]:
        return 0.0
    a = min(1.0, (t - s["t"]) / 0.4)
    up = 1 + 0.04 * math.sin(math.pi * a) if a < 1 else 1.0
    v = (1 - (1 - a) ** 3) * up
    if t >= L["rewind"]:
        n = len(L["steps"])
        r0 = L["rewind"] + 0.06 * (n - 1 - i)
        v *= 1 - ease((t - r0) / 0.3)
    return v


# ------------------------------------------------------------------------------------------- scene

def build(name, preview, rig):
    L = P.LADDERS[name]
    total = round(L["seconds"] * FPS)
    az, el = hdri_sun_azimuth()
    # rotate the sky so its sun shines from behind the camera, front-left: every face we see is lit
    want = math.atan2(-0.80, -0.60)
    rot = math.degrees(az - want)
    T.sunny_world(HDRI_ID, strength=1.2, rot=rot)
    sand = BM.mat("plain", (0.45, 0.34, 0.22), 0.95)
    T.plane("plain", 600000, sand)
    objs = []
    for s in L["steps"]:
        k = s["key"]
        if k == "saturnv":
            ob = BM.saturn_v(s["x"], s["y"])
            T.check("Saturn V height", O.world_bounds(ob)[2][1], s["h"])
        elif k == "pyramid":
            ob = BM.frustum(0, 0, 0, 138.5, 230.3, 9.0, sandstone(), name="Great Pyramid")
            ob.location = (s["x"], s["y"], 0)
            T.check("Great Pyramid height (present)", O.world_bounds(ob)[2][1], s["h"])
        elif k == "burj":
            ob = burj_khalifa(s["x"], s["y"])
            T.check("Burj Khalifa height", O.world_bounds(ob)[2][1], s["h"])
        elif "dem" in s:
            ob = mountain(s)
        else:
            ob = lib_object(s)
        objs.append(ob)
    for m in bpy.data.materials:
        if m.name.endswith("relief"):
            A.aerial(m, CAM_DIST, max(120000.0, 1.6 * max(st["y"] for st in L["steps"])), 0.5, HDRI_ID, 1.2, rot=rot)
    # camera: orthographic, looking north, pitch 0
    cam = rig.cam
    for c in list(cam.constraints):
        cam.constraints.remove(c)
    bpy.data.objects.remove(rig.tgt)
    cam.data.type = "ORTHO"
    cam.data.dof.use_dof = False
    cam.data.clip_start = 10.0
    cam.data.clip_end = 400000.0
    cam.rotation_euler = (math.radians(90), 0, 0)
    bd = T.plane("backdrop", 1.0, backdrop_material(rot, 1.2))
    bd.parent = cam
    bd.location = (0, 0, -300000.0)
    bd.rotation_euler = (0, 0, 0)
    for attr in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter", "visible_shadow"):
        setattr(bd, attr, False)
    track = camera_track(L, total)
    for row in track:
        f, S = row["f"], row["S"]
        zc = (GROUND_Y - 0.5) * S
        cam.location = (row["x"], -CAM_DIST, zc)
        cam.data.ortho_scale = S
        bd.scale = (S * 1080 / 1920 * 1.02, S * 1.02, 1)
        cam.keyframe_insert("location", frame=f)
        cam.data.keyframe_insert("ortho_scale", frame=f)
        bd.keyframe_insert("scale", frame=f)
        row["zc"] = zc
        for i, ob in enumerate(objs):
            v = scale_at(L, i, (f - 1) / FPS, S)
            row[L["steps"][i]["key"]] = round(v, 4)
            if i == 0:
                continue
            ob.scale.z = max(v, 1e-4)
            ob.keyframe_insert("scale", index=2, frame=f)
            ob.hide_render = v < 1e-3
            ob.keyframe_insert("hide_render", frame=f)
    for ob in [cam, cam.data, bd] + objs[1:]:
        if ob.animation_data and ob.animation_data.action:
            for fc in ob.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR" if fc.data_path != "hide_render" else "CONSTANT"
    (A.CACHE.parent / "ladder_track.json").write_text(json.dumps(
        {"track": track, "steps": L["steps"], "ground_y": GROUND_Y, "sun": {"azimuth": math.degrees(az), "elev": el,
                                                                             "world_rot": rot}}))
    return {"ladder": name, "sun_elevation_deg": round(el, 1)}
