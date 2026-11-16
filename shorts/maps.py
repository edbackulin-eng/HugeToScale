"""True-size map comparisons from Natural Earth (public domain), 1 unit = 1 m.

Each shape is projected with a Lambert azimuthal equal-area projection centred on itself, so its
area and shape are true; then it is moved onto the target. Areas are checked against the source.
"""
import json
import math

import bmesh
import bpy

R = 6371008.8  # mean Earth radius, m


def laea(lon, lat, lon0, lat0):
    lam, phi = math.radians(lon - lon0), math.radians(lat)
    phi0 = math.radians(lat0)
    k = math.sqrt(2 / (1 + math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(lam)))
    x = R * k * math.cos(phi) * math.sin(lam)
    y = R * k * (math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(lam))
    return x, y


def polygons(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return geom["coordinates"]


def find(path, **match):
    data = json.loads(open(path, encoding="utf-8").read())
    for f in data["features"]:
        p = f["properties"]
        if all(str(p.get(k)) == str(v) for k, v in match.items()):
            return f
    raise KeyError(match)


def area(ring):
    return abs(0.5 * sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1] for i in range(len(ring))))


def project(feature, lon0, lat0, min_area=0.0):
    """Outer rings in metres around (lon0, lat0), dropping islands smaller than min_area m²."""
    out = []
    for poly in polygons(feature["geometry"]):
        ring = [laea(lon, lat, lon0, lat0) for lon, lat in poly[0]]
        if area(ring) >= min_area:
            out.append(ring)
    return out


def centroid(rings):
    a = cx = cy = 0.0
    for r in rings:
        for i in range(len(r)):
            x0, y0 = r[i - 1]; x1, y1 = r[i]
            c = x0 * y1 - x1 * y0
            a += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


def slab(name, rings, z0, thick, m, shift=(0.0, 0.0), rot=0.0):
    bm = bmesh.new()
    c, s = math.cos(rot), math.sin(rot)
    for r in rings:
        pts = r[:-1] if r[0] == r[-1] else r
        pts = [(x * c - y * s + shift[0], x * s + y * c + shift[1]) for x, y in pts]
        try:
            f = bm.faces.new([bm.verts.new((x, y, z0)) for x, y in pts])
        except ValueError:
            continue
        if f.normal.z < 0:
            f.normal_flip()
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1.0)
    ext = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, vec=(0, 0, thick), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(m)
    return o


def outline(name, rings, z, width, m, shift=(0.0, 0.0)):
    """Border line as a curve with a round bevel."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = width
    cu.bevel_resolution = 2
    for r in rings:
        sp = cu.splines.new("POLY")
        sp.points.add(len(r) - 1)
        for p, (x, y) in zip(sp.points, r):
            p.co = (x + shift[0], y + shift[1], z, 1)
        sp.use_cyclic_u = True
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(m)
    return o
