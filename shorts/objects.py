"""Real objects modelled in Blender from official dimensions (1 unit = 1 m).

RMS Titanic (Harland & Wolff, 1912): length overall 269.1 m, beam 28.2 m, keel to funnel tops 53.3 m,
  draught 10.5 m. Hull lofted from stations: straight stem, counter stern, sheer, flat-bottom midbody.
Elizabeth Tower (Big Ben): 96 m, shaft 12 m square, clock dials 7 m across.
Every builder returns the root empty; dimensions are verified in test_frame.py before rendering.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

_M = {}


def mat(name, rgb, rough=0.5, metal=0.0, coat=0.0, bump=0.0):
    if name in _M:
        return _M[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    if bump:
        n = nt.nodes.new("ShaderNodeTexNoise"); n.inputs["Scale"].default_value = 3.0
        n.inputs["Detail"].default_value = 8
        bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.05
        nt.links.new(n.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
        # subtle colour variation (weathering) so large surfaces are not flat
        n2 = nt.nodes.new("ShaderNodeTexNoise"); n2.inputs["Scale"].default_value = 0.08
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
        mix.inputs["Factor"].default_value = 0.25
        mix.inputs["A"].default_value = (*rgb, 1)
        mix.inputs["B"].default_value = (rgb[0] * 0.75, rgb[1] * 0.75, rgb[2] * 0.75, 1)
        nt.links.new(n2.outputs["Fac"], mix.inputs["Factor"])
        nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    _M[name] = m
    return m


def _obj(name, bm, m, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    if isinstance(m, (list, tuple)):
        for mm in m:
            o.data.materials.append(mm)
    else:
        o.data.materials.append(m)
    return o


def box(name, c, size, m, rot_z=0.0, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(rot_z, 3, "Z"), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(c), verts=bm.verts)
    o = _obj(name, bm, m)
    if bevel:
        b = o.modifiers.new("bev", "BEVEL"); b.width = bevel; b.segments = 2
    return o


def cylinder(name, c, r, h, m, n=32, r2=None, sx=1.0, sy=1.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=n, radius1=r, radius2=r if r2 is None else r2, depth=h)
    bmesh.ops.scale(bm, vec=Vector((sx, sy, 1)), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector((c[0], c[1], c[2] + h / 2)), verts=bm.verts)
    return _obj(name, bm, m, smooth=n >= 16)


def root(name, parts, loc=(0, 0, 0), rot_z=0.0):
    e = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(e)
    for p in parts:
        p.parent = e
    e.location = loc
    e.rotation_euler.z = rot_z
    return e


# ----------------------------------------------------------------------------------------- Titanic

L, B = 269.1, 28.2
X_BOW, X_STERN = L / 2, -L / 2


def _half_beam(x):
    if x > 72:  # fine bow, straight stem
        t = (x - 72) / (X_BOW - 72)
        return max(0.15, B / 2 * max(0.0, 1 - t ** 1.9))
    if x < -92:  # rounded counter stern
        t = (-92 - x) / (-92 - X_STERN)
        return max(0.4, B / 2 * math.sqrt(max(0.0, 1 - t ** 2.4)))
    return B / 2


def _deck(x):  # sheer line of the shelter deck (C deck), keel = 0
    t = x / X_BOW
    return 19.6 + (2.9 * t * t if t > 0 else 1.5 * t * t)


def _keel(x):  # keel rises at the stern (rudder cut-up) and slightly at the forefoot
    if x < -118:
        return min(8.5, (-118 - x) / (X_STERN + 118) * -8.5)
    if x > 128:
        return (x - 128) / (X_BOW - 128) * 3.0
    return 0.0


def titanic():
    black = mat("ti_black", (0.015, 0.015, 0.017), 0.35, coat=0.4, bump=0.15)
    red = mat("ti_red", (0.42, 0.04, 0.03), 0.6, bump=0.2)
    white = mat("ti_white", (0.86, 0.85, 0.80), 0.45, bump=0.1)
    buff = mat("ti_buff", (0.78, 0.48, 0.16), 0.5, bump=0.1)
    wood = mat("ti_deck", (0.55, 0.40, 0.25), 0.7, bump=0.2)
    gold = mat("ti_gold", (0.9, 0.65, 0.2), 0.3, 0.8)
    glass = mat("ti_porthole", (0.03, 0.04, 0.05), 0.08, 0.5)
    parts = []

    # hull: stations x sections, mirrored. material 0 black above waterline, 1 red below.
    xs = [X_STERN + 0.01] + [X_STERN + (L - 0.02) * i / 120 for i in range(1, 120)] + [X_BOW - 0.01]
    bm = bmesh.new()
    rings = []
    for x in xs:
        hb, zt, zk = _half_beam(x), _deck(x), _keel(x)
        r = min(2.2, hb * 0.5)
        # fullness of the bottom: flat midbody, V-shaped forward
        flat = hb - r if -92 < x < 72 else (hb - r) * (0.55 if x < 0 else max(0.0, 1 - (x - 72) / 50))
        pts = [(0.0, zk), (flat, zk)]
        for k in range(1, 5):
            a = k / 4 * math.pi / 2
            pts.append((flat + r * math.sin(a), zk + r * (1 - math.cos(a))))
        pts += [(hb, zk + r + (zt - zk - r) * f) for f in (0.25, 0.5, 0.75, 1.0)]
        pts += [(0.0, zt)]
        ring = [bm.verts.new((x, y, z)) for y, z in pts]
        ring += [bm.verts.new((x, -y, z)) for y, z in reversed(pts[1:-1])]
        rings.append(ring)
    n = len(rings[0])
    for a, b2 in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((a[i], a[j], b2[j], b2[i]))
            zc = sum(v.co.z for v in f.verts) / 4
            f.material_index = 1 if zc < 10.5 else 0
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    hull = _obj("Titanic hull", bm, [black, red], smooth=True)
    parts.append(hull)

    # open decks (pine planking) following the sheer, seen from above
    bm = bmesh.new()
    prev = None
    for x in xs[1:-1]:
        hb = max(0.05, _half_beam(x) - 0.35)
        z = _deck(x) + 0.06
        pair = (bm.verts.new((x, -hb, z)), bm.verts.new((x, hb, z)))
        if prev:
            bm.faces.new((prev[0], pair[0], pair[1], prev[1]))
        prev = pair
    parts.append(_obj("open deck", bm, wood))
    # gold sheer line along the top of the black hull
    for side in (1, -1):
        bm = bmesh.new()
        prev = None
        for x in xs[2:-2]:
            hb = _half_beam(x) + 0.03
            z = _deck(x) - 0.9
            pair = (bm.verts.new((x, side * hb, z)), bm.verts.new((x, side * hb, z + 0.35)))
            if prev:
                bm.faces.new((prev[0], pair[0], pair[1], prev[1]))
            prev = pair
        parts.append(_obj("sheer line", bm, gold))

    # portholes: two rows along the straight midbody, both sides
    for side in (1, -1):
        for z in (13.0, 16.2):
            ph = cylinder("porthole", (0, 0, 0), 0.32, 0.08, glass, n=12)
            ph.rotation_euler.x = math.pi / 2
            ph.location = (-90, side * (B / 2 + 0.02), z)
            arr = ph.modifiers.new("arr", "ARRAY")
            arr.fit_type = "FIXED_COUNT"; arr.count = 66
            arr.use_relative_offset = False; arr.use_constant_offset = True
            arr.constant_offset_displace = (2.4, 0, 0)
            parts.append(ph)

    # superstructure decks (white): B deck house, A deck, boat deck house; forecastle and poop decks
    def deckhouse(name, x0, x1, z0, h, inset):
        hb = min(_half_beam(x0), _half_beam(x1)) - inset
        return box(name, ((x0 + x1) / 2, 0, z0 + h / 2), (x1 - x0, 2 * hb, h), white, bevel=0.15)

    zc = _deck(0)
    _planks(wood)
    roof = mat("ti_roof", (0.80, 0.80, 0.77), 0.5, bump=0.1)
    parts += [deckhouse("B deck", -95, 66, zc, 3.0, 0.3),
              deckhouse("A deck", -86, 60, zc + 3.0, 3.0, 0.6),
              deckhouse("bridge", 46, 54, zc + 6.0, 2.6, 2.0)]
    # boat deck: pine planking, with separate white deckhouses between the funnels (gaps show the deck)
    parts.append(box("boat deck", (-13, 0, zc + 6.02), (146, B - 1.4, 0.06), wood))
    for k, (x0, x1) in enumerate(((40, 46), (18, 32), (-6, 8), (-30, -17), (-60, -42), (-77, -64))):
        h = deckhouse(f"boat deckhouse {k}", x0, x1, zc + 6.0, 2.8, 6.5)
        parts.append(h)
        parts.append(box("deckhouse roof", ((x0 + x1) / 2, 0, zc + 8.85), (x1 - x0 - 0.6, B - 13.6, 0.08), roof))
    # first-class grand staircase skylight (glass dome) and the forward/aft cargo cranes
    parts.append(cylinder("skylight", (27.0, 0, zc + 8.8), 3.0, 1.4, mat("ti_glass", (0.45, 0.55, 0.6), 0.1, 0.3), n=24, r2=1.2))
    crane = mat("ti_crane", (0.85, 0.85, 0.82), 0.5)
    for x in (110.0, 100.0, -108.0, -118.0):
        for side in (1, -1):
            parts.append(box("crane post", (x, side * 4.5, _deck(x) + 2.5), (0.8, 0.8, 5.0), crane))
            c = box("crane jib", (x + 2.0, side * 4.5, _deck(x) + 5.2), (6.0, 0.4, 0.4), crane)
            c.rotation_euler.y = math.radians(-18)
            parts.append(c)
    # hatch covers on the fore and aft decks
    for x in (118.0, 104.0, 86.0, -104.0, -118.0):
        parts.append(box("hatch", (x, 0, _deck(x) + 0.35), (5.5, 7.0, 0.7), mat("ti_hatch", (0.30, 0.22, 0.14), 0.7)))
    # lifeboats along the boat deck, 8 per side
    for side in (1, -1):
        for k in range(8):
            x = 44 - k * 9.0 - (24 if k >= 4 else 0)
            parts.append(box("lifeboat", (x, side * (B / 2 - 2.2), zc + 6.9), (8.5, 2.5, 1.2), white, bevel=0.4))
    # four funnels: elliptical, buff with black tops, raked aft; tops at 53.3 m above keel
    for k, x in enumerate((38.0, 13.5, -11.0, -35.5)):
        base = zc + 6.0
        hgt = 53.3 - base
        f = cylinder(f"funnel {k + 1}", (0, 0, 0), 3.65, hgt - 4.0, buff, n=32, sx=1.0, sy=0.82)
        top = cylinder(f"funnel top {k + 1}", (0, 0, hgt - 4.0), 3.65, 4.0, black, n=32, sx=1.0, sy=0.82)
        for o in (f, top):
            o.location = (x, 0, base)
            o.rotation_euler.y = math.radians(-2.5)
        parts += [f, top]
    # masts and rigging lines (thin), cranes omitted
    mast_m = mat("ti_mast", (0.75, 0.62, 0.42), 0.6)
    for x, top in ((96.0, 62.0), (-96.0, 60.0)):
        parts.append(cylinder("mast", (x, 0, _deck(x)), 0.45, top - _deck(x), mast_m, n=12, r2=0.2))
    # wireless aerial strung between the mast heads
    span = 96.0 * 2
    w = cylinder("aerial wire", (0, 0, 0), 0.06, span, mat("ti_wire", (0.1, 0.1, 0.1), 0.5), n=6)
    w.rotation_euler.y = -math.pi / 2
    w.location = (96.0, 0, 61.0)
    parts.append(w)
    return root("RMS Titanic", parts)


def _planks(m):
    """Turn a plain wood material into deck planking (bands along the ship, light seams)."""
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    if any(n.type == "TEX_WAVE" for n in nt.nodes):
        return
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"; wv.bands_direction = "Y"; wv.wave_profile = "SAW"
    wv.inputs["Scale"].default_value = 0.0  # set below via mapping
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1 / 0.14, 1.0)  # 14 cm planks
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    wv.inputs["Scale"].default_value = 1.0
    nt.links.new(mp.outputs["Vector"], wv.inputs["Vector"])
    seam = nt.nodes.new("ShaderNodeMath"); seam.operation = "GREATER_THAN"; seam.inputs[1].default_value = 0.93
    nt.links.new(wv.outputs["Fac"], seam.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (0.72, 0.55, 0.36, 1)
    mix.inputs["B"].default_value = (0.35, 0.26, 0.18, 1)
    nt.links.new(seam.outputs[0], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])


# ---------------------------------------------------------------------------------- Elizabeth Tower

def elizabeth_tower():
    stone = mat("et_stone", (0.80, 0.63, 0.40), 0.75, bump=0.35)
    stone_d = mat("et_stone_dark", (0.55, 0.40, 0.24), 0.8, bump=0.35)
    iron = mat("et_iron", (0.10, 0.13, 0.20), 0.45, 0.6)
    gilt = mat("et_gilt", (0.95, 0.68, 0.18), 0.25, 1.0)
    dial = mat("et_dial", (0.92, 0.90, 0.82), 0.3)
    glass = mat("et_slit", (0.04, 0.05, 0.07), 0.2)
    p = []
    w = 12.0
    p.append(box("shaft", (0, 0, 27.5), (w, w, 55), stone))
    # corner buttresses and vertical panel ribs (Perpendicular Gothic)
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        p.append(box("buttress", (sx * (w / 2 - 0.4), sy * (w / 2 - 0.4), 32), (1.6, 1.6, 64), stone))
    for face in range(4):
        a = face * math.pi / 2
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -ny, nx
        for k in range(-2, 3):
            c = (nx * (w / 2 + 0.12) + tx * k * 2.0, ny * (w / 2 + 0.12) + ty * k * 2.0, 27.5)
            p.append(box("rib", c, (0.35 if nx else 0.25, 0.25 if nx else 0.35, 55), stone_d))
        for z in range(6, 54, 7):  # slit windows between ribs
            for k in (-1.5, -0.5, 0.5, 1.5):
                c = (nx * (w / 2 + 0.05) + tx * k * 2.0, ny * (w / 2 + 0.05) + ty * k * 2.0, z + 1.6)
                p.append(box("slit", c, (0.12 if nx else 0.7, 0.7 if nx else 0.12, 3.2), glass))
        for z in (14, 28, 42, 54):  # string courses
            p.append(box("course", (nx * (w / 2 + 0.2), ny * (w / 2 + 0.2), z), (0.5 if nx else w, w if nx else 0.5, 0.45), stone_d))
    # clock stage: overhanging, dials 7 m across, centres ~58 m
    p.append(box("clock stage", (0, 0, 58.5), (13.0, 13.0, 9.0), stone, bevel=0.1))
    for face in range(4):
        a = face * math.pi / 2
        nx, ny = math.cos(a), math.sin(a)
        frame = cylinder("dial frame", (0, 0, 0), 3.9, 0.35, gilt, n=48)
        d = cylinder("dial", (0, 0, 0), 3.5, 0.4, dial, n=48)
        for o, off in ((frame, 6.55), (d, 6.62)):
            o.rotation_euler = (math.pi / 2, 0, a + math.pi / 2)
            o.location = (nx * off, ny * off, 58.0)
        p += [frame, d]
        for hand, ang, ln in (("hour", 0.9, 2.0), ("minute", -0.7, 3.0)):
            h = box("hand", (0, 0, 0), (0.25, 0.12, ln), iron)
            h.location = (nx * 6.86 + 0, ny * 6.86, 58.0)
            h.rotation_euler = (0, 0, a)
            h.rotation_mode = "XYZ"
            p.append(h)
    # belfry with arched openings, then the iron spire with lucarnes and the gilded lantern
    p.append(box("belfry", (0, 0, 67.0), (11.6, 11.6, 8.0), stone))
    for face in range(4):
        a = face * math.pi / 2
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -ny, nx
        for k in (-1, 0, 1):
            c = (nx * 5.85 + tx * k * 3.2, ny * 5.85 + ty * k * 3.2, 67.0)
            p.append(box("bell opening", c, (0.2 if nx else 2.0, 2.0 if nx else 0.2, 5.5), glass))
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        p.append(cylinder("pinnacle", (sx * 6.0, sy * 6.0, 63.0), 0.55, 12.0, gilt, n=8, r2=0.05))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=8.2, radius2=1.4, depth=17.0)
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 4, 3, "Z"), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector((0, 0, 71.0 + 8.5)), verts=bm.verts)
    p.append(_obj("spire", bm, iron))
    for face in range(4):  # lucarnes on the spire
        a = face * math.pi / 2
        p.append(box("lucarne", (math.cos(a) * 4.4, math.sin(a) * 4.4, 76.5), (2.0, 2.0, 3.2), iron, rot_z=a))
        p.append(box("lucarne gilt", (math.cos(a) * 4.5, math.sin(a) * 4.5, 76.8), (0.6, 0.6, 2.2), gilt, rot_z=a))
    p.append(cylinder("lantern", (0, 0, 88.0), 1.3, 3.0, gilt, n=8))
    p.append(cylinder("finial", (0, 0, 91.0), 0.5, 5.0, gilt, n=8, r2=0.03))
    return root("Elizabeth Tower", p)


# --------------------------------------------------------------------------------------------- tools

def world_bounds(ob):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in [ob] + list(ob.children_recursive):
        if o.type != "MESH":
            continue
        e = o.evaluated_get(dg)
        pts += [e.matrix_world @ Vector(c) for c in e.bound_box]
    return [(min(p[i] for p in pts), max(p[i] for p in pts)) for i in range(3)]


def top_of(ob, prefix):
    """Highest world z of the parts whose name starts with prefix (e.g. funnel tops)."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    zs = []
    for o in ob.children_recursive:
        if o.type == "MESH" and o.name.startswith(prefix):
            e = o.evaluated_get(dg)
            zs += [(e.matrix_world @ v.co).z for v in e.data.vertices]
    return max(zs)


def local_extent(ob, axis):
    """Extent of the object along its own axis (for length checks when rotated)."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    inv = ob.matrix_world.inverted()
    vals = []
    for o in ob.children_recursive:
        if o.type != "MESH" or "porthole" in o.name:
            continue
        e = o.evaluated_get(dg)
        m = inv @ e.matrix_world
        vals += [(m @ v.co)[axis] for v in e.data.vertices]
    return max(vals) - min(vals)
