"""Stylised real objects and landmarks, built from primitives in Blender (1 unit = 1 m).

Every builder puts the object's base centre at (x, y, 0) and returns the list of objects.
Heights are the published real figures; shapes are simplified on purpose (channel art).

    Saturn V            110.6 m   NASA (SP-4206 / Apollo by the Numbers)
    Statue of Liberty    93.0 m   ground to torch tip, US National Park Service
    Elizabeth Tower      96.0 m   (Big Ben) UK Parliament
    Taj Mahal            73.0 m   plinth to finial, UNESCO / ASI
    Leaning Tower Pisa   56.7 m   highest side, Opera della Primaziale Pisana
    Great Pyramid       138.5 m   present height, base 230.3 m
    Eiffel Tower        330.0 m   with antennas, Société d'Exploitation de la Tour Eiffel
    Seawise Giant       458.45 m  length (largest ship ever built), beam 68.86 m
    Person                1.8 m
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- materials

_MATS = {}


def mat(name, rgb, rough=0.45, metal=0.0, coat=0.0):
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    _MATS[name] = m
    return m


def quadrant_mat(name, light, dark, z0, z1, rough=0.4):
    """Saturn V style roll pattern: two opposite quadrants dark between z0 and z1 (object space)."""
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = rough
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    xy = nt.nodes.new("ShaderNodeMath"); xy.operation = "MULTIPLY"
    nt.links.new(sep.outputs[0], xy.inputs[0]); nt.links.new(sep.outputs[1], xy.inputs[1])
    q = nt.nodes.new("ShaderNodeMath"); q.operation = "GREATER_THAN"; q.inputs[1].default_value = 0
    nt.links.new(xy.outputs[0], q.inputs[0])
    lo = nt.nodes.new("ShaderNodeMath"); lo.operation = "GREATER_THAN"; lo.inputs[1].default_value = z0
    hi = nt.nodes.new("ShaderNodeMath"); hi.operation = "LESS_THAN"; hi.inputs[1].default_value = z1
    nt.links.new(sep.outputs[2], lo.inputs[0]); nt.links.new(sep.outputs[2], hi.inputs[0])
    a1 = nt.nodes.new("ShaderNodeMath"); a1.operation = "MULTIPLY"
    nt.links.new(lo.outputs[0], a1.inputs[0]); nt.links.new(hi.outputs[0], a1.inputs[1])
    a2 = nt.nodes.new("ShaderNodeMath"); a2.operation = "MULTIPLY"
    nt.links.new(a1.outputs[0], a2.inputs[0]); nt.links.new(q.outputs[0], a2.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (*light, 1); mix.inputs["B"].default_value = (*dark, 1)
    nt.links.new(a2.outputs[0], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    _MATS[name] = m
    return m


# ---------------------------------------------------------------- primitives

def _link(ob, m):
    ob.data.materials.append(m)
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


def cyl(x, y, z0, h, r0, r1=None, m=None, n=48, name="cyl"):
    r1 = r0 if r1 is None else r1
    bpy.ops.mesh.primitive_cone_add(vertices=n, radius1=r0, radius2=r1, depth=h,
                                    location=(x, y, z0 + h / 2))
    ob = bpy.context.object
    ob.name = name
    if n >= 24:
        bpy.ops.object.shade_smooth()
    ob.data.materials.append(m)
    return ob


def box(x, y, z0, sx, sy, h, m, name="box"):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z0 + h / 2))
    ob = bpy.context.object
    ob.scale = (sx, sy, h)
    ob.name = name
    ob.data.materials.append(m)
    bpy.ops.object.transform_apply(scale=True)
    bev = ob.modifiers.new("bev", "BEVEL")
    bev.width = min(sx, sy, h) * 0.04
    bev.segments = 2
    return ob


def frustum(x, y, z0, h, w0, w1, m, d0=None, d1=None, name="frustum"):
    """Square (or rectangular) truncated pyramid."""
    d0 = w0 if d0 is None else d0
    d1 = w1 if d1 is None else d1
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    v = [bm.verts.new((x + sx * w / 2, y + sy * d / 2, z)) for (w, d, z) in ((w0, d0, z0), (w1, d1, z0 + h))
         for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    bm.faces.new(v[0:4][::-1]); bm.faces.new(v[4:8])
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((v[i], v[j], v[4 + j], v[4 + i]))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(m)
    return ob


def sphere(x, y, z, r, m, sz=1.0, name="sphere"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=r, location=(x, y, z))
    ob = bpy.context.object
    ob.scale = (1, 1, sz)
    ob.name = name
    bpy.ops.object.shade_smooth()
    ob.data.materials.append(m)
    return ob


def group(objs, name, x=0, y=0, rot_y=0.0, rot_z=0.0):
    """Parent parts to one empty so the whole object can be moved/tilted."""
    e = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(e)
    for o in objs:
        o.parent = e
    e.location = (x, y, 0)
    e.rotation_euler = (0, rot_y, rot_z)
    return e


# ---------------------------------------------------------------- objects

WHITE = (0.92, 0.92, 0.90)
BLACK = (0.03, 0.03, 0.035)


def saturn_v(x=0.0, y=0.0):
    X, Y = x, y
    x = y = 0.0
    w = mat("sv_white", WHITE, 0.35)
    k = mat("sv_black", BLACK, 0.4)
    silver = mat("sv_silver", (0.75, 0.77, 0.8), 0.25, 0.9)
    eng = mat("sv_engine", (0.12, 0.12, 0.13), 0.3, 0.8)
    s1 = quadrant_mat("sv_sic", WHITE, BLACK, 18.0, 36.0)
    r = 5.05
    parts = [
        cyl(x, y, 6, 36.1, r, m=s1, name="S-IC"),
        cyl(x, y, 42.1, 1.6, r, m=k, name="interstage1"),
        cyl(x, y, 43.7, 23.1, r, m=w, name="S-II"),
        cyl(x, y, 66.8, 5.8, r, 3.3, m=w, name="taper"),
        cyl(x, y, 72.6, 4.0, 3.3, m=k, name="S-IVB aft"),
        cyl(x, y, 76.6, 9.0, 3.3, m=quadrant_mat("sv_s4", WHITE, BLACK, -4.5, 4.5), name="S-IVB"),
        cyl(x, y, 85.6, 0.9, 3.3, m=k, name="IU"),
        cyl(x, y, 86.5, 8.5, 3.3, 1.95, m=w, name="SLA"),
        cyl(x, y, 95.0, 3.0, 1.95, m=silver, name="SM"),
        cyl(x, y, 98.0, 3.5, 1.95, 0.45, m=w, name="CM"),
        cyl(x, y, 101.5, 4.5, 0.55, 0.35, m=k, n=8, name="LES truss"),
        cyl(x, y, 106.0, 3.6, 0.35, 0.35, m=w, name="LES motor"),
        cyl(x, y, 109.6, 1.0, 0.35, 0.02, m=k, name="LES tip"),
        cyl(x, y, 0, 6, r * 0.95, r, m=k, name="skirt"),
    ]
    for i in range(4):  # fins and engine fairings
        a = math.pi / 4 + i * math.pi / 2
        fx, fy = x + math.cos(a) * (r + 1.6), y + math.sin(a) * (r + 1.6)
        f = box(fx, fy, 0, 3.2, 0.5, 9, w, name="fin")
        f.rotation_euler.z = a
        parts.append(f)
        parts.append(cyl(x + math.cos(a) * r * 0.85, y + math.sin(a) * r * 0.85, 0, 8, 1.5, 1.2, m=k, name="fairing"))
        parts.append(cyl(x + math.cos(a) * r * 0.55, y + math.sin(a) * r * 0.55, -0.01, 3.5, 1.9, 1.1, m=eng, name="F-1"))
    return group(parts, "Saturn V", X, Y)


def statue_of_liberty(x=0.0, y=0.0):
    X, Y = x, y
    x = y = 0.0
    copper = mat("liberty_copper", (0.24, 0.72, 0.58), 0.45)
    granite = mat("liberty_granite", (0.86, 0.80, 0.70), 0.6)
    fort = mat("liberty_fort", (0.70, 0.66, 0.60), 0.7)
    gold = mat("liberty_gold", (1.0, 0.70, 0.12), 0.25, 1.0)
    p = [
        frustum(x, y, 0, 6, 40, 37, fort, name="fort"),
        frustum(x, y, 6, 14, 27, 23, granite, name="foundation"),
        frustum(x, y, 20, 27, 19.8, 14.0, granite, name="pedestal"),
        box(x, y, 44.5, 15.2, 15.2, 2.5, granite, name="pedestal cap"),
        cyl(x, y, 47, 30, 5.8, 3.0, m=copper, name="robe"),
        cyl(x, y, 77, 3.5, 3.0, 1.6, m=copper, name="shoulders"),
        cyl(x, y, 80.5, 1.2, 1.1, m=copper, name="neck"),
        sphere(x, y, 83.2, 2.0, copper, 1.15, name="head"),
        cyl(x + 2.2, y, 78, 11.5, 1.1, 0.9, m=copper, name="arm"),
        cyl(x + 2.6, y, 89.5, 1.6, 0.9, 1.4, m=copper, name="torch"),
        cyl(x + 2.6, y, 91.1, 1.9, 1.0, 0.05, m=gold, name="flame"),
        box(x - 3.6, y - 0.5, 70, 1.2, 4.0, 7.0, copper, name="tablet"),
    ]
    p[-4].rotation_euler.y = math.radians(-8)
    for i in range(7):  # crown rays
        a = math.radians(-60 + i * 20)
        ray = cyl(0, 0, 0, 2.6, 0.32, 0.02, m=copper, n=8, name="ray")
        ray.location = (x + math.sin(a) * 1.6, y - math.cos(a) * 0.6, 84.6)
        ray.rotation_euler = (math.radians(-35), math.radians(math.degrees(a) * 0.9), 0)
        p.append(ray)
    return group(p, "Statue of Liberty", X, Y)


def big_ben(x=0.0, y=0.0):
    X, Y = x, y
    x = y = 0.0
    stone = mat("bb_stone", (0.93, 0.70, 0.36), 0.55)
    roof = mat("bb_roof", (0.10, 0.16, 0.30), 0.4, 0.3)
    gold = mat("bb_gold", (1.0, 0.72, 0.15), 0.25, 1.0)
    face = mat("bb_face", (0.98, 0.97, 0.92), 0.3)
    p = [
        box(x, y, 0, 12.0, 12.0, 55, stone, name="shaft"),
        box(x, y, 55, 12.8, 12.8, 15, stone, name="clock stage"),
        box(x, y, 70, 11.6, 11.6, 7, stone, name="belfry"),
        frustum(x, y, 77, 15, 11.6, 1.4, roof, name="spire roof"),
        cyl(x, y, 92, 4, 0.5, 0.05, m=gold, n=8, name="finial"),
    ]
    for i in range(4):
        a = i * math.pi / 2
        d = 6.45
        c = cyl(0, 0, 0, 0.4, 3.4, m=face, name="clock")
        c.rotation_euler = (math.pi / 2, 0, a + math.pi / 2)
        c.location = (x + math.cos(a) * d, y + math.sin(a) * d, 62.5)
        rim = cyl(0, 0, 0, 0.3, 3.8, m=gold, name="rim")
        rim.rotation_euler = c.rotation_euler
        rim.location = (x + math.cos(a) * (d - 0.15), y + math.sin(a) * (d - 0.15), 62.5)
        p += [c, rim]
        for s in (-1, 1):  # corner pinnacles
            p.append(cyl(x + 6.2 * math.cos(a) - s * 6.2 * math.sin(a),
                         y + 6.2 * math.sin(a) + s * 6.2 * math.cos(a), 70, 9, 0.6, 0.05, m=gold, n=8, name="pinnacle"))
    return group(p, "Elizabeth Tower", X, Y)


def taj_mahal(x=0.0, y=0.0):
    X, Y = x, y
    x = y = 0.0
    marble = mat("taj_marble", (0.97, 0.94, 0.92), 0.3)
    shade = mat("taj_arch", (0.55, 0.62, 0.78), 0.4)
    gold = mat("taj_gold", (1.0, 0.72, 0.15), 0.25, 1.0)
    p = [box(x, y, 0, 95, 95, 6.7, marble, name="plinth")]
    main = cyl(x, y, 6.7, 30, 40.0, m=marble, n=8, name="main hall")
    main.rotation_euler.z = math.pi / 8
    p.append(main)
    for i in range(4):  # big iwan arches as recessed dark panels
        a = i * math.pi / 2
        arch = box(x + math.cos(a) * 36.6, y + math.sin(a) * 36.6, 9, 1.2 if i % 2 == 0 else 17,
                   17 if i % 2 == 0 else 1.2, 24, shade, name="iwan")
        p.append(arch)
    p.append(cyl(x, y, 36.7, 8, 13.5, m=marble, name="drum"))
    p.append(sphere(x, y, 53.5, 14.5, marble, 1.12, name="dome"))
    p.append(cyl(x, y, 68.5, 4.5, 1.6, 0.1, m=gold, n=12, name="finial"))
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        cx, cy = x + sx * 22, y + sy * 22
        p.append(cyl(cx, cy, 36.7, 6, 3.6, m=marble, n=8, name="chhatri base"))
        p.append(sphere(cx, cy, 43.5, 3.8, marble, 1.1, name="chhatri dome"))
        mx, my = x + sx * 44, y + sy * 44
        p.append(cyl(mx, my, 6.7, 33, 2.8, 2.1, m=marble, name="minaret"))
        p.append(cyl(mx, my, 39.7, 3.5, 3.0, m=marble, n=8, name="minaret gallery"))
        p.append(sphere(mx, my, 44.8, 2.6, marble, 1.15, name="minaret dome"))
    return group(p, "Taj Mahal", X, Y)


def pisa(x=0.0, y=0.0):
    X, Y = x, y
    x = y = 0.0
    stone = mat("pisa_stone", (0.97, 0.93, 0.84), 0.45)
    band = mat("pisa_band", (0.80, 0.74, 0.62), 0.5)
    p = [cyl(x, y, 0, 49, 7.75, m=stone, name="shaft")]
    for k in range(1, 8):
        p.append(cyl(x, y, k * 6.4 - 0.4, 0.8, 8.15, m=band, name="gallery"))
    p.append(cyl(x, y, 49, 7.7, 5.2, m=stone, name="belfry"))
    return group(p, "Leaning Tower of Pisa", X, Y, rot_y=math.radians(3.97))


def pyramid(x=0.0, y=0.0):
    X, Y = x, y
    x = y = 0.0
    sand = mat("pyr_sand", (0.98, 0.70, 0.30), 0.75)
    return group([frustum(x, y, 0, 138.5, 230.3, 9.0, sand, name="pyramid")], "Great Pyramid", X, Y)


def eiffel(x=0.0, y=0.0):
    X, Y = x, y
    x = y = 0.0
    iron = mat("eiffel_iron", (0.62, 0.30, 0.16), 0.5, 0.35)
    deck = mat("eiffel_deck", (0.50, 0.24, 0.13), 0.5, 0.35)

    def half(z):  # half-width of the tower's outline at height z (fits 62.5 m at base, ~5 m at 276 m)
        return 3.0 + 59.5 * math.exp(-z / 62.0)

    parts = []
    me = bpy.data.meshes.new("eiffel_legs")
    bm = bmesh.new()
    zs = [0, 10, 20, 30, 45, 57, 70, 85, 100, 115.7]
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        rings = []
        for z in zs:
            h = half(z)
            s = 0.30 * h if z < 115 else h
            cx, cy = sx * (h - s / 2), sy * (h - s / 2)
            rings.append([bm.verts.new((x + cx + dx * s / 2, y + cy + dy * s / 2, z))
                          for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        bm.faces.new(rings[0][::-1])
        for a, b in zip(rings, rings[1:]):
            for i in range(4):
                j = (i + 1) % 4
                bm.faces.new((a[i], a[j], b[j], b[i]))
        bm.faces.new(rings[-1])
    bm.to_mesh(me); bm.free()
    legs = bpy.data.objects.new("eiffel legs", me)
    bpy.context.collection.objects.link(legs)
    legs.data.materials.append(iron)
    parts.append(legs)
    # upper shaft
    me2 = bpy.data.meshes.new("eiffel_shaft")
    bm = bmesh.new()
    zs2 = [115.7, 140, 170, 200, 230, 260, 276]
    rings = [[bm.verts.new((x + dx * half(z), y + dy * half(z), z)) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
             for z in zs2]
    bm.faces.new(rings[0][::-1])
    for a, b in zip(rings, rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(rings[-1])
    bm.to_mesh(me2); bm.free()
    shaft = bpy.data.objects.new("eiffel shaft", me2)
    bpy.context.collection.objects.link(shaft)
    shaft.data.materials.append(iron)
    parts.append(shaft)
    # lattice look: wireframe skin over both
    for o in (legs, shaft):
        sub = o.modifiers.new("sub", "SUBSURF"); sub.subdivision_type = "SIMPLE"; sub.levels = 2
        tri = o.modifiers.new("tri", "TRIANGULATE")
        wf = o.modifiers.new("wf", "WIREFRAME"); wf.thickness = 1.1; wf.use_replace = False
    # inner solid core so the lattice reads as a mass from far away
    parts.append(frustum(x, y, 115.7, 160, 2 * half(115.7) * 0.8, 2 * half(276) * 0.8, deck, name="core"))
    for z, hgt in ((57, 5), (115.7, 3.5), (276, 6)):
        w = 2 * half(z) + 4
        parts.append(box(x, y, z - hgt / 2, w, w, hgt, deck, name="platform"))
    parts.append(cyl(x, y, 279, 12, 3.2, 1.6, m=deck, n=8, name="cupola"))
    parts.append(cyl(x, y, 291, 39, 0.9, 0.3, m=deck, n=8, name="antenna"))
    return group(parts, "Eiffel Tower", X, Y)


def seawise_giant(x=0.0, y=0.0, upright=False):
    """Hull 458.45 x 68.86 m, depth 29.8 m. Lying along X; upright=True stands it on its stern."""
    L, B, D = 458.45, 68.86, 29.8
    red = mat("ship_red", (0.80, 0.07, 0.06), 0.5)
    hull = mat("ship_hull", (0.02, 0.05, 0.20), 0.35)
    deckm = mat("ship_deck", (0.06, 0.32, 0.14), 0.6)
    white = mat("ship_white", (0.95, 0.95, 0.93), 0.35)
    funnel = mat("ship_funnel", (0.95, 0.55, 0.05), 0.4)
    # stations along the length: (x, half-beam factor, keel z, deck z) — raked bow, forecastle, cut-up stern
    st = [(-L / 2, 0.80, 7.0, D), (-L / 2 + 14, 1.0, 0.0, D), (L / 2 - 45, 1.0, 0.0, D),
          (L / 2 - 28, 0.85, 0.5, D + 3), (L / 2 - 10, 0.45, 4.0, D + 3), (L / 2, 0.10, 11.0, D + 3)]
    h = _hull("hull", st, B, hull, 0.0)
    skin = _hull("antifouling", [(x_, f, z0, min(z1, 11.0)) for x_, f, z0, z1 in st], B, red, 0.25)
    parts = [h, skin, box(0, 0, D, L - 70, B - 8, 0.6, deckm, name="deck"),
             box(25, 0, D, L - 150, 3, 2.5, white, name="catwalk"),
             box(10, 0, D, 8, B - 14, 3.5, white, name="manifold")]
    for k in range(9):  # hatches along the deck
        parts.append(box(-150 + k * 40, 0, D, 10, B * 0.45, 1.5, mat("ship_hatch", (0.85, 0.15, 0.10), 0.5), name="hatch"))
    parts.append(box(-L / 2 + 30, 0, D, 30, B * 0.70, 32, white, name="accommodation"))
    parts.append(box(-L / 2 + 34, 0, D + 32, 20, B * 0.92, 3.5, white, name="bridge wings"))
    parts.append(box(-L / 2 + 12, 0, D, 12, 10, 42, funnel, name="funnel"))
    g = group(parts, "Seawise Giant")
    if upright:  # stood on its stern, deck facing the camera (-Y): bow points up
        g.rotation_euler = Matrix(((0, -1, 0), (0, 0, -1), (1, 0, 0))).to_euler()
        g.location = (x, y, L / 2)
    else:
        g.location = (x, y, 0)
    return g


def _hull(name, st, B, m, pad):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for i, (sx, f, z0, z1) in enumerate(st):
        hb = B / 2 * f + pad
        sx += (-pad if i == 0 else pad if i == len(st) - 1 else 0)
        rings.append([bm.verts.new((sx, sy * hb, z)) for sy, z in ((-1, z0 - 0.01), (1, z0 - 0.01), (1, z1), (-1, z1))])
    bm.faces.new(rings[0][::-1])
    for a, b in zip(rings, rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(rings[-1])
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(m)
    return o


def person(x=0.0, y=0.0, color=(1.0, 0.15, 0.05)):
    X, Y = x, y
    x = y = 0.0
    m = mat("person", color, 0.5)
    p = [cyl(x - 0.09, y, 0, 0.85, 0.08, 0.1, m=m, n=12, name="leg"),
         cyl(x + 0.09, y, 0, 0.85, 0.08, 0.1, m=m, n=12, name="leg"),
         cyl(x, y, 0.85, 0.65, 0.2, 0.22, m=m, n=16, name="torso"),
         sphere(x, y, 1.66, 0.13, m, 1.1, name="head")]
    return group(p, "Person", X, Y)


def bounds(ob):
    """World-space min/max z and x of an object hierarchy (for the size self-check)."""
    bpy.context.view_layer.update()
    pts = []
    for o in [ob] + list(ob.children_recursive):
        if o.type != "MESH":
            continue
        dg = bpy.context.evaluated_depsgraph_get()
        e = o.evaluated_get(dg)
        mw = e.matrix_world
        pts += [mw @ Vector(c) for c in e.bound_box]
    xs, ys, zs = [p.x for p in pts], [p.y for p in pts], [p.z for p in pts]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))
