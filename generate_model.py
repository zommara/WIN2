#!/usr/bin/env python3
"""
Génère l'objet 3D animé du site AR, en deux formats à partir d'une seule description :

  assets/objet-v2.glb   -> Android (WebXR / Scene Viewer) et aperçu 3D dans la page
  assets/objet-v2.usdz  -> iPhone / iPad (AR Quick Look), animation incluse

Animation iPhone : AR Quick Look ne lit que les images clés écrites dans le fichier, sans
interpoler « en pensée » entre deux valeurs. Une rotation écrite « 0° puis 360° » donne donc
deux orientations identiques, c'est-à-dire aucun mouvement. On écrit donc de nombreuses
orientations (quaternions) rapprochées, et la boucle est répétée bout à bout pour que
l'animation dure plusieurs minutes même si Quick Look ne la relance pas.

Aucune dépendance : Python 3 standard uniquement.
Usage : python3 generate_model.py
"""
import json
import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUT, exist_ok=True)

DUREE = 8.0      # durée de la boucle d'animation (secondes)
FPS = 24         # images par seconde (USD)
KEYS = 64        # images clés par boucle (glTF et USD) : au plus ~17° entre deux clés
LOOPS_USD = 24   # nombre de boucles mises bout à bout dans le USDZ (~3 min 12 s)
NOM = "objet-v2" # nom des fichiers (changé pour éviter le cache des anciennes versions)


# --------------------------------------------------------------------------
# 1. Géométrie
# --------------------------------------------------------------------------
def _sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _dot(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _norm(a):
    l = math.sqrt(_dot(a, a)) or 1.0
    return (a[0]/l, a[1]/l, a[2]/l)


def fix_winding(pos, nrm, idx):
    """Oriente chaque triangle dans le sens anti-horaire vu de l'extérieur."""
    out = []
    for i in range(0, len(idx), 3):
        a, b, c = idx[i:i+3]
        n = _cross(_sub(pos[b], pos[a]), _sub(pos[c], pos[a]))
        avg = (nrm[a][0]+nrm[b][0]+nrm[c][0], nrm[a][1]+nrm[b][1]+nrm[c][1], nrm[a][2]+nrm[b][2]+nrm[c][2])
        out += [a, b, c] if _dot(n, avg) >= 0 else [a, c, b]
    return out


def uv_sphere(r, lat=24, lon=36):
    pos, nrm, idx = [], [], []
    for i in range(lat + 1):
        th = math.pi * i / lat
        for j in range(lon + 1):
            ph = 2 * math.pi * j / lon
            n = (math.sin(th)*math.cos(ph), math.cos(th), math.sin(th)*math.sin(ph))
            pos.append((n[0]*r, n[1]*r, n[2]*r)); nrm.append(n)
    for i in range(lat):
        for j in range(lon):
            a = i*(lon+1)+j; b = a+lon+1
            idx += [a, b, a+1, a+1, b, b+1]
    return pos, nrm, fix_winding(pos, nrm, idx)


def torus(R, r, seg=72, sides=20):
    pos, nrm, idx = [], [], []
    for i in range(seg + 1):
        u = 2 * math.pi * i / seg
        for j in range(sides + 1):
            v = 2 * math.pi * j / sides
            n = (math.cos(v)*math.cos(u), math.sin(v), math.cos(v)*math.sin(u))
            pos.append(((R + r*math.cos(v))*math.cos(u), r*math.sin(v), (R + r*math.cos(v))*math.sin(u)))
            nrm.append(n)
    for i in range(seg):
        for j in range(sides):
            a = i*(sides+1)+j; b = a+sides+1
            idx += [a, b, a+1, a+1, b, b+1]
    return pos, nrm, fix_winding(pos, nrm, idx)


def cylinder(r, h, y0=0.0, seg=48):
    pos, nrm, idx = [], [], []
    for j in range(seg + 1):                      # flanc lisse
        a = 2 * math.pi * j / seg
        n = (math.cos(a), 0.0, math.sin(a))
        pos.append((r*n[0], y0, r*n[2])); nrm.append(n)
        pos.append((r*n[0], y0+h, r*n[2])); nrm.append(n)
    for j in range(seg):
        a = 2*j; idx += [a, a+2, a+1, a+1, a+2, a+3]
    for top in (True, False):                      # disques haut et bas
        y = y0 + (h if top else 0.0)
        n = (0.0, 1.0 if top else -1.0, 0.0)
        c = len(pos); pos.append((0.0, y, 0.0)); nrm.append(n)
        for j in range(seg + 1):
            a = 2 * math.pi * j / seg
            pos.append((r*math.cos(a), y, r*math.sin(a))); nrm.append(n)
        for j in range(seg):
            idx += [c, c+1+j, c+2+j]
    return pos, nrm, fix_winding(pos, nrm, idx)


def gem(r=0.05, h=0.075, sides=8):
    """Bipyramide à facettes, ombrage plat."""
    top, bot = (0.0, h, 0.0), (0.0, -h, 0.0)
    ring = [(r*math.cos(2*math.pi*k/sides), 0.0, r*math.sin(2*math.pi*k/sides)) for k in range(sides)]
    pos, nrm, idx = [], [], []
    for k in range(sides):
        p, q = ring[k], ring[(k+1) % sides]
        for tri in ((top, p, q), (bot, q, p)):
            n = _norm(_cross(_sub(tri[1], tri[0]), _sub(tri[2], tri[0])))
            centre = tuple(sum(v[i] for v in tri)/3 for i in range(3))
            if _dot(n, centre) < 0:
                tri = (tri[0], tri[2], tri[1]); n = (-n[0], -n[1], -n[2])
            base = len(pos)
            pos += list(tri); nrm += [n, n, n]; idx += [base, base+1, base+2]
    return pos, nrm, idx


def build_meshes():
    base_bas = cylinder(0.090, 0.012, 0.0)
    base_haut = cylinder(0.058, 0.008, 0.012)
    return {
        "BaseLower": (base_bas, "Slate"),
        "BaseTop": (base_haut, "Gold"),
        "Gem": (gem(), "Teal"),
        "Ring1": (torus(0.100, 0.0060), "Gold"),
        "Ring2": (torus(0.130, 0.0050), "Silver"),
        "Sat1": (uv_sphere(0.015), "Pearl"),
        "Sat2": (uv_sphere(0.012), "Coral"),
    }


MATERIALS = {   # couleur, métal, rugosité, émission
    "Slate":  ((0.10, 0.12, 0.18), 0.55, 0.45, (0.0, 0.0, 0.0)),
    "Gold":   ((1.00, 0.77, 0.34), 1.00, 0.28, (0.0, 0.0, 0.0)),
    "Silver": ((0.90, 0.92, 0.96), 1.00, 0.22, (0.0, 0.0, 0.0)),
    "Teal":   ((0.10, 0.78, 0.72), 0.30, 0.15, (0.02, 0.30, 0.28)),
    "Pearl":  ((0.98, 0.98, 1.00), 0.10, 0.30, (0.45, 0.45, 0.50)),
    "Coral":  ((0.98, 0.42, 0.36), 0.20, 0.35, (0.25, 0.06, 0.05)),
}

# --------------------------------------------------------------------------
# 2. Scène : hiérarchie de nœuds animés
#    t=translation fixe | rot=(axe, degrés) fixe | spin=(axe, tours/boucle)
#    bob=(hauteur, amplitude) : lévitation sinusoïdale
# --------------------------------------------------------------------------
SCENE = {"name": "Scene", "children": [
    {"name": "Base", "children": [
        {"name": "Lower", "mesh": "BaseLower"},
        {"name": "Top", "mesh": "BaseTop"}]},
    {"name": "Floating", "bob": (0.175, 0.018), "children": [
        {"name": "GemSpin", "spin": ("y", 1), "children": [{"name": "Gem", "mesh": "Gem"}]},
        {"name": "Ring1Spin", "spin": ("y", 1), "children": [
            {"name": "Ring1Tilt", "rot": ("x", 68), "children": [{"name": "Ring1", "mesh": "Ring1"}]}]},
        {"name": "Ring2Spin", "spin": ("y", -1), "children": [
            {"name": "Ring2Tilt", "rot": ("z", 62), "children": [{"name": "Ring2", "mesh": "Ring2"}]}]},
        {"name": "Orbit1", "spin": ("y", 2), "children": [
            {"name": "Sat1Pos", "t": (0.165, 0.0, 0.0), "children": [{"name": "Sat1", "mesh": "Sat1"}]}]},
        {"name": "Orbit2Tilt", "rot": ("x", -35), "children": [
            {"name": "Orbit2", "spin": ("y", -3), "children": [
                {"name": "Sat2Pos", "t": (0.115, 0.0, 0.0), "children": [{"name": "Sat2", "mesh": "Sat2"}]}]}]},
    ]},
]}

AXES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}


def quat(axis, deg):
    a = AXES[axis]; s = math.sin(math.radians(deg)/2)
    return (a[0]*s, a[1]*s, a[2]*s, math.cos(math.radians(deg)/2))


def r6(v): return f"{v:.6g}"
def vec(v): return "(" + ", ".join(r6(x) for x in v) + ")"


# --------------------------------------------------------------------------
# 3. Export glTF binaire (.glb)
# --------------------------------------------------------------------------
def export_glb(meshes, path):
    blob = bytearray()
    views, accessors = [], []

    def add_view(data, target=None):
        while len(blob) % 4: blob.append(0)
        v = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target: v["target"] = target
        blob.extend(data); views.append(v); return len(views) - 1

    def add_acc(view, ctype, count, typ, mn=None, mx=None):
        a = {"bufferView": view, "componentType": ctype, "count": count, "type": typ}
        if mn is not None: a["min"], a["max"] = mn, mx
        accessors.append(a); return len(accessors) - 1

    gl_materials, mat_index = [], {}
    for name, (col, met, rou, emi) in MATERIALS.items():
        mat_index[name] = len(gl_materials)
        gl_materials.append({"name": name, "pbrMetallicRoughness": {
            "baseColorFactor": [*col, 1.0], "metallicFactor": met, "roughnessFactor": rou},
            "emissiveFactor": list(emi)})

    gl_meshes, mesh_index = [], {}
    for name, ((pos, nrm, idx), mat) in meshes.items():
        vp = add_view(b"".join(struct.pack("<3f", *p) for p in pos), 34962)
        vn = add_view(b"".join(struct.pack("<3f", *n) for n in nrm), 34962)
        vi = add_view(struct.pack(f"<{len(idx)}I", *idx), 34963)
        mn = [min(p[i] for p in pos) for i in range(3)]; mx = [max(p[i] for p in pos) for i in range(3)]
        prim = {"attributes": {"POSITION": add_acc(vp, 5126, len(pos), "VEC3", mn, mx),
                               "NORMAL": add_acc(vn, 5126, len(nrm), "VEC3")},
                "indices": add_acc(vi, 5125, len(idx), "SCALAR"),
                "material": mat_index[mat], "mode": 4}
        mesh_index[name] = len(gl_meshes)
        gl_meshes.append({"name": name, "primitives": [prim]})

    # Animation : une seule horloge partagée par tous les canaux
    times = [DUREE * i / KEYS for i in range(KEYS + 1)]
    t_view = add_view(struct.pack(f"<{len(times)}f", *times))
    t_acc = add_acc(t_view, 5126, len(times), "SCALAR", [0.0], [DUREE])
    samplers, channels, nodes = [], [], []

    def add_channel(node_idx, path_name, ctype, values):
        v = add_view(b"".join(struct.pack(f"<{len(x)}f", *x) for x in values))
        a = add_acc(v, 5126, len(values), ctype)
        samplers.append({"input": t_acc, "output": a, "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": node_idx, "path": path_name}})

    def add_node(d):
        node = {"name": d["name"]}
        nodes.append(node); idx = len(nodes) - 1
        if "mesh" in d: node["mesh"] = mesh_index[d["mesh"]]
        if "t" in d: node["translation"] = list(d["t"])
        if "rot" in d: node["rotation"] = list(quat(*d["rot"]))
        if "spin" in d:
            axis, revs = d["spin"]
            add_channel(idx, "rotation", "VEC4", [quat(axis, 360.0*revs*i/KEYS) for i in range(KEYS + 1)])
        if "bob" in d:
            y0, amp = d["bob"]
            node["translation"] = [0.0, y0, 0.0]
            add_channel(idx, "translation", "VEC3",
                        [(0.0, y0 + amp*math.sin(2*math.pi*i/KEYS), 0.0) for i in range(KEYS + 1)])
        kids = [add_node(c) for c in d.get("children", [])]
        if kids: node["children"] = kids
        return idx

    root = add_node(SCENE)
    gltf = {"asset": {"version": "2.0", "generator": "generate_model.py"},
            "scene": 0, "scenes": [{"nodes": [root]}], "nodes": nodes, "meshes": gl_meshes,
            "materials": gl_materials, "accessors": accessors, "bufferViews": views,
            "buffers": [{"byteLength": len(blob)}],
            "animations": [{"name": "Loop", "samplers": samplers, "channels": channels}]}

    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON")); f.write(js)
        f.write(struct.pack("<I4s", len(blob), b"BIN\0")); f.write(blob)
    return total


# --------------------------------------------------------------------------
# 4. Export USD (.usda) puis paquet .usdz pour AR Quick Look
# --------------------------------------------------------------------------
def export_usda(meshes):
    boucle = int(round(DUREE * FPS))          # images par boucle
    assert boucle % KEYS == 0
    pas_frame = boucle // KEYS                # images entre deux clés
    n_cles = KEYS * LOOPS_USD                 # nombre de segments sur toute la durée
    end = boucle * LOOPS_USD

    def usd_quat(q):                          # USD écrit (w, x, y, z)
        return "(" + ", ".join(f"{v:.7f}" for v in (q[3], q[0], q[1], q[2])) + ")"

    L = ["#usda 1.0", "(", '    defaultPrim = "Scene"', "    metersPerUnit = 1", '    upAxis = "Y"',
         "    startTimeCode = 0", f"    endTimeCode = {end}", f"    timeCodesPerSecond = {FPS}",
         f"    framesPerSecond = {FPS}", ")", ""]

    def mesh_block(name, ind):
        (pos, nrm, idx), mat = meshes[name]
        mn = [min(p[i] for p in pos) for i in range(3)]; mx = [max(p[i] for p in pos) for i in range(3)]
        p = " " * ind
        return [f'{p}def Mesh "geo" (', f'{p}    prepend apiSchemas = ["MaterialBindingAPI"]', f"{p})", f"{p}{{",
                f"{p}    float3[] extent = [{vec(mn)}, {vec(mx)}]",
                f"{p}    int[] faceVertexCounts = [{', '.join(['3'] * (len(idx)//3))}]",
                f"{p}    int[] faceVertexIndices = [{', '.join(map(str, idx))}]",
                f"{p}    rel material:binding = </Scene/Materials/{mat}>",
                f"{p}    normal3f[] normals = [{', '.join(vec(n) for n in nrm)}] (",
                f'{p}        interpolation = "vertex"', f"{p}    )",
                f"{p}    point3f[] points = [{', '.join(vec(q) for q in pos)}]",
                f'{p}    uniform token subdivisionScheme = "none"', f"{p}}}"]

    def node_block(d, ind, is_root=False):
        p = " " * ind
        head = f'{p}def Xform "{d["name"]}"'
        L.append(head + (' (\n' + p + '    kind = "component"\n' + p + ')' if is_root else ""))
        L.append(f"{p}{{")
        order = []
        if "t" in d:
            L.append(f"{p}    double3 xformOp:translate = {vec(d['t'])}"); order.append('"xformOp:translate"')
        if "rot" in d:
            L.append(f"{p}    quatf xformOp:orient = {usd_quat(quat(*d['rot']))}"); order.append('"xformOp:orient"')
        if "spin" in d:
            ax, revs = d["spin"]
            samples = ", ".join(f"{i*pas_frame}: {usd_quat(quat(ax, 360.0*revs*i/KEYS))}" for i in range(n_cles + 1))
            L.append(f"{p}    quatf xformOp:orient.timeSamples = {{ {samples} }}"); order.append('"xformOp:orient"')
        if "bob" in d:
            y0, amp = d["bob"]
            samples = ", ".join(f"{i*pas_frame}: {vec((0.0, y0 + amp*math.sin(2*math.pi*i/KEYS), 0.0))}" for i in range(n_cles + 1))
            L.append(f"{p}    double3 xformOp:translate.timeSamples = {{ {samples} }}"); order.append('"xformOp:translate"')
        if order:
            L.append(f"{p}    uniform token[] xformOpOrder = [{', '.join(order)}]")
        if "mesh" in d:
            L.extend(mesh_block(d["mesh"], ind + 4))
        for c in d.get("children", []):
            node_block(c, ind + 4)
        if is_root:
            L.append('    def Scope "Materials"'); L.append("    {")
            for name, (col, met, rou, emi) in MATERIALS.items():
                base = f"/Scene/Materials/{name}"
                L.extend([f'        def Material "{name}"', "        {",
                      f"            token outputs:surface.connect = <{base}/PBR.outputs:surface>",
                      '            def Shader "PBR"', "            {",
                      '                uniform token info:id = "UsdPreviewSurface"',
                      f"                color3f inputs:diffuseColor = {vec(col)}",
                      f"                color3f inputs:emissiveColor = {vec(emi)}",
                      f"                float inputs:metallic = {r6(met)}",
                      f"                float inputs:roughness = {r6(rou)}",
                      "                token outputs:surface", "            }", "        }"])
            L.append("    }")
        L.append(f"{p}}}")

    node_block(SCENE, 0, is_root=True)
    return "\n".join(L) + "\n"


def write_usdz(files, path):
    """Archive ZIP non compressée, données alignées sur 64 octets (exigence USDZ)."""
    out = bytearray(); central = []
    for name, data in files:
        nb = name.encode(); crc = zlib.crc32(data) & 0xFFFFFFFF; offset = len(out)
        pad = (-(offset + 30 + len(nb) + 4)) % 64           # 4 = en-tête du champ extra
        extra = struct.pack("<HH", 0x1986, pad) + b"\0" * pad
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 0x21, crc, len(data), len(data), len(nb), len(extra))
        out += nb + extra + data
        central.append((nb, crc, len(data), offset))
    cd_start = len(out)
    for nb, crc, size, offset in central:
        out += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, 0, 0x21, crc, size, size,
                           len(nb), 0, 0, 0, 0, 0, offset) + nb
    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(central), len(central), len(out) - cd_start, cd_start, 0)
    with open(path, "wb") as f:
        f.write(out)
    return len(out)


def verifier_animation():
    """Aucune rotation ne doit sauter de plus de 60° entre deux images clés."""
    def parcourir(d):
        yield d
        for c in d.get("children", []):
            yield from parcourir(c)
    pire = 0.0
    for d in parcourir(SCENE):
        if "spin" in d:
            ax, revs = d["spin"]
            for i in range(KEYS * LOOPS_USD):
                a, b = quat(ax, 360.0*revs*i/KEYS), quat(ax, 360.0*revs*(i+1)/KEYS)
                dot = min(1.0, abs(sum(x*y for x, y in zip(a, b))))
                pire = max(pire, math.degrees(2*math.acos(dot)))
    assert pire < 60, f"écart trop grand entre deux clés : {pire:.1f}°"
    return pire


if __name__ == "__main__":
    print(f"écart max entre deux clés de rotation : {verifier_animation():.1f}°")
    meshes = build_meshes()
    n = export_glb(meshes, os.path.join(OUT, NOM + ".glb"))
    usda = export_usda(meshes)
    if os.environ.get("KEEP_USDA"): open(os.path.join(OUT, NOM + ".usda"), "w").write(usda)  # débogage
    m = write_usdz([(NOM + ".usda", usda.encode())], os.path.join(OUT, NOM + ".usdz"))
    print(f"{NOM}.glb  : {n/1024:.0f} Ko")
    print(f"{NOM}.usdz : {m/1024:.0f} Ko")
