"""OpenStreetMap city blocks for Blender: buildings / building parts extruded to their tagged heights,
roads as ribbons, water as glossy surfaces. Data © OpenStreetMap contributors (ODbL).

Facades get a window grid from UVs (u = metres along the wall, v = metres up), so no textures are needed.
"""
import json
import math
import random

import bmesh
import bpy
from mathutils import Vector

ROAD_W = {"motorway": 16, "trunk": 16, "primary": 15, "secondary": 13, "tertiary": 11,
          "residential": 9, "unclassified": 8, "service": 5, "living_street": 6}


def facade_mat(name, wall, glass=(0.05, 0.07, 0.09), win_w=1.6, bay=2.6, floor=3.4, glassy=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    uv = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs[0], sep.inputs[0])

    def frac_mask(src, period, lo, hi):
        d = nt.nodes.new("ShaderNodeMath"); d.operation = "DIVIDE"; d.inputs[1].default_value = period
        nt.links.new(src, d.inputs[0])
        f = nt.nodes.new("ShaderNodeMath"); f.operation = "FRACT"
        nt.links.new(d.outputs[0], f.inputs[0])
        a = nt.nodes.new("ShaderNodeMath"); a.operation = "GREATER_THAN"; a.inputs[1].default_value = lo
        c = nt.nodes.new("ShaderNodeMath"); c.operation = "LESS_THAN"; c.inputs[1].default_value = hi
        nt.links.new(f.outputs[0], a.inputs[0]); nt.links.new(f.outputs[0], c.inputs[0])
        mm = nt.nodes.new("ShaderNodeMath"); mm.operation = "MULTIPLY"
        nt.links.new(a.outputs[0], mm.inputs[0]); nt.links.new(c.outputs[0], mm.inputs[1])
        return mm.outputs[0]

    mu = frac_mask(sep.outputs[0], bay, (1 - win_w / bay) / 2, 1 - (1 - win_w / bay) / 2)
    mv = frac_mask(sep.outputs[1], floor, 0.22, 0.88)
    win = nt.nodes.new("ShaderNodeMath"); win.operation = "MULTIPLY"
    nt.links.new(mu, win.inputs[0]); nt.links.new(mv, win.inputs[1])
    if glassy:  # curtain wall: mostly glass with thin mullions
        mx = nt.nodes.new("ShaderNodeMath"); mx.operation = "MAXIMUM"; mx.inputs[1].default_value = 0.85
        nt.links.new(win.outputs[0], mx.inputs[0])
        win = mx
    # per-window variation (some lit/brighter panes, blinds)
    noise = nt.nodes.new("ShaderNodeTexWhiteNoise"); noise.noise_dimensions = "2D"
    snap = nt.nodes.new("ShaderNodeVectorMath"); snap.operation = "SNAP"
    snap.inputs[1].default_value = (bay, floor, 1)
    nt.links.new(uv.outputs[0], snap.inputs[0])
    nt.links.new(snap.outputs[0], noise.inputs["Vector"])
    gl = nt.nodes.new("ShaderNodeMix"); gl.data_type = "RGBA"
    gl.inputs["A"].default_value = (*glass, 1)
    gl.inputs["B"].default_value = (glass[0] * 3 + 0.08, glass[1] * 3 + 0.08, glass[2] * 3 + 0.08, 1)
    nt.links.new(noise.outputs["Value"], gl.inputs["Factor"])
    col = nt.nodes.new("ShaderNodeMix"); col.data_type = "RGBA"
    col.inputs["A"].default_value = (*wall, 1)
    nt.links.new(win.outputs[0], col.inputs["Factor"])
    nt.links.new(gl.outputs["Result"], col.inputs["B"])
    nt.links.new(col.outputs["Result"], b.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.8; rough.inputs["To Max"].default_value = 0.06
    nt.links.new(win.outputs[0], rough.inputs[0])
    nt.links.new(rough.outputs[0], b.inputs["Roughness"])
    met = nt.nodes.new("ShaderNodeMath"); met.operation = "MULTIPLY"; met.inputs[1].default_value = 0.4
    nt.links.new(win.outputs[0], met.inputs[0])
    nt.links.new(met.outputs[0], b.inputs["Metallic"])
    return m


def flat_mat(name, rgb, rough=0.6, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat
    return m


def _area(pts):
    return 0.5 * sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))


def point_in(pt, poly):
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def load(path):
    return json.loads(open(path, encoding="utf-8").read())


def footprints(data, kinds=("building", "part")):
    return [f for f in data["features"] if f["kind"] in kinds and len(f["pts"]) >= 4]


def build(data, skip=lambda f: False, radius=None, palette=None, seed=3):
    """Create one mesh for all buildings (material per style), roads and water. Returns the objects."""
    rnd = random.Random(seed)
    palette = palette or [((0.62, 0.58, 0.52), False), ((0.45, 0.42, 0.40), False), ((0.70, 0.66, 0.58), False),
                          ((0.38, 0.40, 0.44), True), ((0.55, 0.36, 0.27), False), ((0.30, 0.36, 0.42), True)]
    mats = [facade_mat(f"facade {i}", w, glassy=g) for i, (w, g) in enumerate(palette)]
    roof = flat_mat("roof", (0.22, 0.22, 0.23), 0.85)
    feats = footprints(data)
    # a building outline that has parts inside is drawn by its parts only
    parts = [f for f in feats if f["kind"] == "part"]
    part_centres = [(sum(p[0] for p in f["pts"]) / len(f["pts"]), sum(p[1] for p in f["pts"]) / len(f["pts"]))
                    for f in parts]
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    count = 0
    for f in feats:
        pts = [tuple(p) for p in f["pts"]]
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3 or skip(f):
            continue
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        if radius and math.hypot(cx, cy) > radius:
            continue
        if f["kind"] == "building" and any(point_in(c, pts) for c in part_centres):
            continue
        h = f["height"] or rnd.uniform(12, 24)
        z0 = f["min_height"] or 0.0
        if h <= z0 + 0.5:
            continue
        if _area(pts) < 0:
            pts = pts[::-1]
        mi = rnd.randrange(len(mats))
        bottom = [bm.verts.new((x, y, z0)) for x, y in pts]
        top = [bm.verts.new((x, y, h)) for x, y in pts]
        try:
            ft = bm.faces.new(top); ft.material_index = len(mats)
            fb = bm.faces.new(bottom[::-1]); fb.material_index = len(mats)
        except ValueError:
            continue
        u = 0.0
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            seg = math.dist(pts[i], pts[j])
            fw = bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
            fw.material_index = mi
            for loop, (uu, vv) in zip(fw.loops, ((u, z0), (u + seg, z0), (u + seg, h), (u, h))):
                loop[uv].uv = (uu, vv)
            u += seg
        count += 1
    me = bpy.data.meshes.new("osm buildings")
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new("OSM buildings", me)
    bpy.context.collection.objects.link(ob)
    for m in mats + [roof]:
        ob.data.materials.append(m)
    out = [ob]
    # roads as flat ribbons
    asphalt = flat_mat("asphalt", (0.035, 0.035, 0.038), 0.7)
    bm = bmesh.new()
    for f in data["features"]:
        if f["kind"] != "road" or f.get("highway") not in ROAD_W:
            continue
        w = ROAD_W[f["highway"]] / 2
        pts = f["pts"]
        for a, b in zip(pts, pts[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dx, dy)
            if ln < 0.1:
                continue
            nx, ny = -dy / ln * w, dx / ln * w
            vs = [bm.verts.new((a[0] + nx, a[1] + ny, 0.03)), bm.verts.new((a[0] - nx, a[1] - ny, 0.03)),
                  bm.verts.new((b[0] - nx, b[1] - ny, 0.03)), bm.verts.new((b[0] + nx, b[1] + ny, 0.03))]
            bm.faces.new(vs[::-1] if (dx * ny - dy * nx) > 0 else vs)
    me = bpy.data.meshes.new("roads"); bm.to_mesh(me); bm.free()
    ro = bpy.data.objects.new("OSM roads", me)
    bpy.context.collection.objects.link(ro)
    ro.data.materials.append(asphalt)
    out.append(ro)
    # water
    water = flat_mat("water", (0.03, 0.10, 0.14), 0.03, coat=1.0)
    bm = bmesh.new()
    for f in data["features"]:
        if f["kind"] != "water":
            continue
        pts = [tuple(p) for p in f["pts"]]
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3:
            continue
        try:
            bm.faces.new([bm.verts.new((x, y, 0.06)) for x, y in pts])
        except ValueError:
            pass
    me = bpy.data.meshes.new("water"); bm.to_mesh(me); bm.free()
    wo = bpy.data.objects.new("OSM water", me)
    bpy.context.collection.objects.link(wo)
    wo.data.materials.append(water)
    out.append(wo)
    print("city:", count, "buildings")
    return out


def ground(size=6000, rgb=(0.32, 0.31, 0.29)):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    g = bpy.context.object
    g.name = "ground"
    g.data.materials.append(flat_mat("pavement", rgb, 0.85))
    return g


def free_spot(feats, footprint_fn, candidates):
    """Pick the placement whose footprint overlaps the fewest building samples."""
    polys = [[tuple(p) for p in f["pts"]] for f in feats]
    boxes = [(min(p[0] for p in q), max(p[0] for p in q), min(p[1] for p in q), max(p[1] for p in q)) for q in polys]
    best = None
    for cand in candidates:
        pts = footprint_fn(*cand)
        hits = 0
        for x, y in pts:
            for q, (a, b, c, d) in zip(polys, boxes):
                if a <= x <= b and c <= y <= d and point_in((x, y), q):
                    hits += 1
                    break
        if best is None or hits < best[0]:
            best = (hits, cand)
    return best
