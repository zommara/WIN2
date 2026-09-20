#!/usr/bin/env python3
"""
Génère une méduse 3D avec animation squelettique intégrée, dans les deux formats AR :

  assets/meduse.glb   -> Android (WebXR / Scene Viewer) et aperçu 3D dans la page
  assets/meduse.usdz  -> iPhone / iPad (AR Quick Look)

Les deux fichiers viennent du même squelette (20 os) et de la même animation :
  glTF : « skin » + « animation » (rotation / translation / échelle des os)
  USD  : UsdSkel (Skeleton + SkelAnimation), le format d'animation que Quick Look lit nativement.
La boucle dure 3 s ; dans le USDZ elle est répétée 20 fois bout à bout (1 min) au cas où
Quick Look ne la relancerait pas seul.

Aucune dépendance : Python 3 standard uniquement.   Usage : python3 generate_model.py
"""
import json
import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUT, exist_ok=True)

NOM = "meduse"
P = 3.0            # durée d'une boucle (s)
K = 36             # images clés par boucle (12 par seconde)
FPS = 24
LOOPS_USD = 20     # boucles mises bout à bout dans le USDZ
assert (FPS * P / K) == int(FPS * P / K)
FRAMES_PAR_CLE = int(FPS * P / K)

# --------------------------------------------------------------------------
# 1. Petites fonctions de calcul
# --------------------------------------------------------------------------
def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def dot(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def norm(a):
    l = math.sqrt(dot(a, a))
    return (a[0]/l, a[1]/l, a[2]/l) if l > 1e-12 else (0.0, 1.0, 0.0)


def qaxis(axis, ang):
    s = math.sin(ang / 2)
    return (axis[0]*s, axis[1]*s, axis[2]*s, math.cos(ang / 2))


def qmul(a, b):   # produit de quaternions (x, y, z, w) : applique b puis a
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return (aw*bx + ax*bw + ay*bz - az*by,
            aw*by - ax*bz + ay*bw + az*bx,
            aw*bz + ax*by - ay*bx + az*bw,
            aw*bw - ax*bx - ay*by - az*bz)


# --------------------------------------------------------------------------
# 2. Squelette : Root -> Bell (ombrelle) et 6 tentacules de 3 os
# --------------------------------------------------------------------------
Y0 = 0.20          # hauteur du centre de l'ombrelle au-dessus du socle (m)
N_TENT = 6
SEG = 0.045        # longueur d'un segment de tentacule
R_ATT = 0.05       # rayon d'attache des tentacules

JOINTS = []        # {name, parent, t}


def add_joint(name, parent, t):
    JOINTS.append({"name": name, "parent": parent, "t": t})
    return len(JOINTS) - 1


def build_rig():
    root = add_joint("Root", -1, (0.0, Y0, 0.0))
    add_joint("Bell", root, (0.0, 0.0, 0.0))
    for i in range(N_TENT):
        phi = 2 * math.pi * i / N_TENT
        a = add_joint(f"T{i}_0", root, (R_ATT*math.cos(phi), -0.010, R_ATT*math.sin(phi)))
        b = add_joint(f"T{i}_1", a, (0.0, -SEG, 0.0))
        add_joint(f"T{i}_2", b, (0.0, -SEG, 0.0))


build_rig()


def joint_path(i):
    parts = []
    while i >= 0:
        parts.append(JOINTS[i]["name"]); i = JOINTS[i]["parent"]
    return "/".join(reversed(parts))


def world_bind(i):
    x = y = z = 0.0
    while i >= 0:
        t = JOINTS[i]["t"]; x += t[0]; y += t[1]; z += t[2]; i = JOINTS[i]["parent"]
    return (x, y, z)


def joint_index(name):
    return next(i for i, j in enumerate(JOINTS) if j["name"] == name)


# --------------------------------------------------------------------------
# 3. Animation : pose locale de chaque os à l'instant t (périodique, période P)
# --------------------------------------------------------------------------
MOY_FLARE = [math.radians(a) for a in (5, 5, 4)]     # ouverture moyenne des tentacules
AMP_FLARE = [math.radians(a) for a in (7, 14, 16)]   # battement vers l'extérieur
AMP_TOURB = [math.radians(a) for a in (3, 9, 12)]    # ondulation latérale


def pose(t):
    """Renvoie [(translation, quaternion xyzw, échelle)] pour chaque os."""
    w = 2 * math.pi * t / P
    out = []
    for j in JOINTS:
        tr, q, sc = j["t"], (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0)
        name = j["name"]
        if name == "Root":                                   # lévitation
            tr = (0.0, Y0 + 0.013 * math.sin(w - 0.8), 0.0)
        elif name == "Bell":                                 # pulsation de l'ombrelle
            c = math.sin(w)
            sc = (1 + 0.08*c, 1 - 0.10*c, 1 + 0.08*c)
        else:                                                # tentacules : onde qui descend
            i, k = int(name[1]), int(name[3])
            phi = 2 * math.pi * i / N_TENT
            tangent = (-math.sin(phi), 0.0, math.cos(phi))
            radial = (math.cos(phi), 0.0, math.sin(phi))
            alpha = MOY_FLARE[k] + AMP_FLARE[k] * math.sin(w - 1.0*k + 0.5*i)
            beta = AMP_TOURB[k] * math.cos(w - 1.0*k + 0.5*i)
            q = qmul(qaxis(tangent, alpha), qaxis(radial, beta))
            if q[3] < 0: q = tuple(-v for v in q)
        out.append((tr, q, sc))
    return out


# --------------------------------------------------------------------------
# 4. Géométrie
# --------------------------------------------------------------------------
def fix_winding(pos, prov, idx):
    """Oriente chaque triangle vers l'extérieur d'après des normales provisoires."""
    out = []
    for i in range(0, len(idx), 3):
        a, b, c = idx[i:i+3]
        n = cross(sub(pos[b], pos[a]), sub(pos[c], pos[a]))
        avg = tuple(prov[a][k] + prov[b][k] + prov[c][k] for k in range(3))
        out += [a, b, c] if dot(n, avg) >= 0 else [a, c, b]
    return out


def smooth_normals(pos, idx):
    acc = [[0.0, 0.0, 0.0] for _ in pos]
    for i in range(0, len(idx), 3):
        a, b, c = idx[i:i+3]
        n = cross(sub(pos[b], pos[a]), sub(pos[c], pos[a]))
        for v in (a, b, c):
            for k in range(3): acc[v][k] += n[k]
    return [norm(tuple(a)) for a in acc]


def cylinder(r, h, y0=0.0, seg=48):
    pos, nrm, idx = [], [], []
    for j in range(seg + 1):
        a = 2 * math.pi * j / seg
        n = (math.cos(a), 0.0, math.sin(a))
        pos.append((r*n[0], y0, r*n[2])); nrm.append(n)
        pos.append((r*n[0], y0+h, r*n[2])); nrm.append(n)
    for j in range(seg):
        a = 2*j; idx += [a, a+2, a+1, a+1, a+2, a+3]
    for top in (True, False):
        y = y0 + (h if top else 0.0)
        n = (0.0, 1.0 if top else -1.0, 0.0)
        c = len(pos); pos.append((0.0, y, 0.0)); nrm.append(n)
        for j in range(seg + 1):
            a = 2 * math.pi * j / seg
            pos.append((r*math.cos(a), y, r*math.sin(a))); nrm.append(n)
        for j in range(seg):
            idx += [c, c+1+j, c+2+j]
    return pos, nrm, fix_winding(pos, nrm, idx)


def sphere(r, centre, lat=16, lon=24):
    pos, nrm, idx = [], [], []
    for i in range(lat + 1):
        th = math.pi * i / lat
        for j in range(lon + 1):
            ph = 2 * math.pi * j / lon
            n = (math.sin(th)*math.cos(ph), math.cos(th), math.sin(th)*math.sin(ph))
            pos.append((centre[0]+n[0]*r, centre[1]+n[1]*r, centre[2]+n[2]*r)); nrm.append(n)
    for i in range(lat):
        for j in range(lon):
            a = i*(lon+1)+j; b = a+lon+1
            idx += [a, b, a+1, a+1, b, b+1]
    return pos, nrm, fix_winding(pos, nrm, idx)


def bell_geometry():
    """Ombrelle : dôme + jupe festonnée, calé autour de l'os « Bell »."""
    R, H, n_th, n_ph = 0.072, 0.056, 14, 48
    profil = []                                          # (rayon, hauteur, fraction)
    for i in range(n_th + 1):
        th = (math.pi / 2) * i / n_th
        profil.append((R*math.sin(th), H*math.cos(th), i / n_th))
    profil += [(R*1.035, -0.006, 1.0), (R*1.02, -0.012, 1.0), (R*0.94, -0.018, 1.0)]
    pos, prov = [], []
    centre = (0.0, Y0 + 0.010, 0.0)
    for (r, y, f) in profil:
        for j in range(n_ph):
            ph = 2 * math.pi * j / n_ph
            rr = r * (1 + 0.045 * (f ** 3) * math.cos(8 * ph))
            p = (rr*math.cos(ph), Y0 + y, rr*math.sin(ph))
            pos.append(p); prov.append(norm(sub(p, centre)))
    idx = []
    for i in range(len(profil) - 1):
        for j in range(n_ph):
            a = i*n_ph + j; b = i*n_ph + (j+1) % n_ph
            c = (i+1)*n_ph + j; d = (i+1)*n_ph + (j+1) % n_ph
            idx += [a, c, b, b, c, d]
    idx = fix_winding(pos, prov, idx)
    return pos, smooth_normals(pos, idx), idx


def tentacle_geometry(i):
    phi = 2 * math.pi * i / N_TENT
    bx, by, bz = R_ATT*math.cos(phi), Y0 - 0.010, R_ATT*math.sin(phi)
    n_r, sides, D = 30, 8, 3 * SEG
    j0 = joint_index(f"T{i}_0")
    pos, prov, jid, wgt = [], [], [], []
    for r in range(n_r + 1):
        d = D * r / n_r
        rad = 0.0068 * (1 - 0.7 * d / D)
        if d <= SEG:
            f = d / SEG; ji, wi = (j0, j0+1, 0, 0), (1-f, f, 0.0, 0.0)
        elif d <= 2*SEG:
            f = (d - SEG) / SEG; ji, wi = (j0+1, j0+2, 0, 0), (1-f, f, 0.0, 0.0)
        else:
            ji, wi = (j0+2, 0, 0, 0), (1.0, 0.0, 0.0, 0.0)
        for s in range(sides):
            a = 2 * math.pi * s / sides
            pos.append((bx + rad*math.cos(a), by - d, bz + rad*math.sin(a)))
            prov.append((math.cos(a), 0.0, math.sin(a)))
            jid.append(ji); wgt.append(wi)
    centre = len(pos)                                    # bouchon à l'extrémité
    pos.append((bx, by - D, bz)); prov.append((0.0, -1.0, 0.0))
    jid.append((j0+2, 0, 0, 0)); wgt.append((1.0, 0.0, 0.0, 0.0))
    idx = []
    for r in range(n_r):
        for s in range(sides):
            a = r*sides + s; b = r*sides + (s+1) % sides
            c = (r+1)*sides + s; d = (r+1)*sides + (s+1) % sides
            idx += [a, c, b, b, c, d]
    base = n_r * sides
    for s in range(sides):
        idx += [base + s, centre, base + (s+1) % sides]
    idx = fix_winding(pos, prov, idx)
    return pos, smooth_normals(pos, idx), idx, jid, wgt


def merge(parts):
    pos, nrm, idx, jid, wgt = [], [], [], [], []
    for p, n, ix, ji, wi in parts:
        off = len(pos)
        pos += p; nrm += n; idx += [k + off for k in ix]; jid += ji; wgt += wi
    return pos, nrm, idx, jid, wgt


def build_meshes():
    bell_id = joint_index("Bell")
    bp, bn, bi = bell_geometry()
    cp, cn, ci = sphere(0.022, (0.0, Y0 + 0.024, 0.0))
    tent = merge([tentacle_geometry(i) for i in range(N_TENT)])
    n = lambda k: [(bell_id, 0, 0, 0)] * k
    w = lambda k: [(1.0, 0.0, 0.0, 0.0)] * k
    skinned = {
        "Bell": (bp, bn, bi, n(len(bp)), w(len(bp)), "Bell"),
        "Core": (cp, cn, ci, n(len(cp)), w(len(cp)), "Core"),
        "Tentacles": (*tent, "Tentacle"),
    }
    static = {
        "BaseLower": (*cylinder(0.090, 0.012, 0.0), "Slate"),
        "BaseTop": (*cylinder(0.058, 0.008, 0.012), "Gold"),
    }
    return skinned, static


MATERIALS = {   # couleur, métal, rugosité, émission, opacité, double face
    "Slate":    dict(col=(0.10, 0.12, 0.18), met=0.55, rou=0.45, emi=(0.00, 0.00, 0.00), alpha=1.0, double=False),
    "Gold":     dict(col=(1.00, 0.77, 0.34), met=1.00, rou=0.28, emi=(0.00, 0.00, 0.00), alpha=1.0, double=False),
    "Bell":     dict(col=(0.78, 0.58, 1.00), met=0.00, rou=0.18, emi=(0.20, 0.09, 0.34), alpha=0.72, double=True),
    "Core":     dict(col=(0.45, 1.00, 0.92), met=0.00, rou=0.30, emi=(0.35, 0.95, 0.85), alpha=1.0, double=False),
    "Tentacle": dict(col=(1.00, 0.62, 0.86), met=0.00, rou=0.40, emi=(0.30, 0.10, 0.25), alpha=1.0, double=False),
}


# --------------------------------------------------------------------------
# 5. Export glTF binaire (.glb) : skin + animation squelettique
# --------------------------------------------------------------------------
def export_glb(skinned, static, path):
    blob = bytearray(); views, accessors = [], []

    def add_view(data, target=None):
        while len(blob) % 4: blob.append(0)
        v = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target: v["target"] = target
        blob.extend(data); views.append(v); return len(views) - 1

    def add_acc(view, ctype, count, typ, mn=None, mx=None):
        a = {"bufferView": view, "componentType": ctype, "count": count, "type": typ}
        if mn is not None: a["min"], a["max"] = mn, mx
        accessors.append(a); return len(accessors) - 1

    gl_mats, mat_idx = [], {}
    for name, m in MATERIALS.items():
        mat_idx[name] = len(gl_mats)
        d = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": [*m["col"], m["alpha"]],
             "metallicFactor": m["met"], "roughnessFactor": m["rou"]}, "emissiveFactor": list(m["emi"])}
        if m["alpha"] < 1: d["alphaMode"] = "BLEND"
        if m["double"]: d["doubleSided"] = True
        gl_mats.append(d)

    def geometry_attrs(pos, nrm, idx):
        vp = add_view(b"".join(struct.pack("<3f", *p) for p in pos), 34962)
        vn = add_view(b"".join(struct.pack("<3f", *n) for n in nrm), 34962)
        vi = add_view(struct.pack(f"<{len(idx)}I", *idx), 34963)
        mn = [min(p[i] for p in pos) for i in range(3)]; mx = [max(p[i] for p in pos) for i in range(3)]
        return ({"POSITION": add_acc(vp, 5126, len(pos), "VEC3", mn, mx),
                 "NORMAL": add_acc(vn, 5126, len(nrm), "VEC3")},
                add_acc(vi, 5125, len(idx), "SCALAR"))

    gl_meshes, skinned_meshes, static_meshes = [], [], []
    for name, (pos, nrm, idx, jid, wgt, mat) in skinned.items():
        attrs, ind = geometry_attrs(pos, nrm, idx)
        vj = add_view(b"".join(struct.pack("<4H", *j) for j in jid), 34962)
        vw = add_view(b"".join(struct.pack("<4f", *w) for w in wgt), 34962)
        attrs["JOINTS_0"] = add_acc(vj, 5123, len(jid), "VEC4")
        attrs["WEIGHTS_0"] = add_acc(vw, 5126, len(wgt), "VEC4")
        gl_meshes.append({"name": name, "primitives": [{"attributes": attrs, "indices": ind,
                          "material": mat_idx[mat], "mode": 4}]})
        skinned_meshes.append((name, len(gl_meshes) - 1))
    for name, (pos, nrm, idx, mat) in static.items():
        attrs, ind = geometry_attrs(pos, nrm, idx)
        gl_meshes.append({"name": name, "primitives": [{"attributes": attrs, "indices": ind,
                          "material": mat_idx[mat], "mode": 4}]})
        static_meshes.append((name, len(gl_meshes) - 1))

    # nœuds : 0 = scène, 1..n = os, puis maillages
    nodes = [{"name": "Scene", "children": []}]
    for j in JOINTS:
        nodes.append({"name": j["name"], "translation": list(j["t"])})
    for i, j in enumerate(JOINTS):
        parent = nodes[0] if j["parent"] < 0 else nodes[j["parent"] + 1]
        parent.setdefault("children", []).append(i + 1)
    for name, m in skinned_meshes:
        nodes.append({"name": name, "mesh": m, "skin": 0}); nodes[0]["children"].append(len(nodes) - 1)
    for name, m in static_meshes:
        nodes.append({"name": name, "mesh": m}); nodes[0]["children"].append(len(nodes) - 1)

    ibm = b"".join(struct.pack("<16f", 1,0,0,0, 0,1,0,0, 0,0,1,0, *(-c for c in world_bind(i)), 1)
                   for i in range(len(JOINTS)))
    skin = {"joints": [i + 1 for i in range(len(JOINTS))], "skeleton": 1,
            "inverseBindMatrices": add_acc(add_view(ibm), 5126, len(JOINTS), "MAT4")}

    # animation : uniquement les canaux qui varient réellement
    poses = [pose(P * i / K) for i in range(K + 1)]
    times = [P * i / K for i in range(K + 1)]
    t_acc = add_acc(add_view(struct.pack(f"<{len(times)}f", *times)), 5126, len(times), "SCALAR", [0.0], [P])
    samplers, channels = [], []
    for ji in range(len(JOINTS)):
        for comp, cible, typ in ((0, "translation", "VEC3"), (1, "rotation", "VEC4"), (2, "scale", "VEC3")):
            vals = [p[ji][comp] for p in poses]
            if all(max(abs(a - b) for a, b in zip(v, vals[0])) < 1e-9 for v in vals): continue
            out = add_acc(add_view(b"".join(struct.pack(f"<{len(v)}f", *v) for v in vals)), 5126, len(vals), typ)
            samplers.append({"input": t_acc, "output": out, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": ji + 1, "path": cible}})

    gltf = {"asset": {"version": "2.0", "generator": "generate_model.py"}, "scene": 0,
            "scenes": [{"nodes": [0]}], "nodes": nodes, "meshes": gl_meshes, "skins": [skin],
            "materials": gl_mats, "accessors": accessors, "bufferViews": views,
            "buffers": [{"byteLength": len(blob)}],
            "animations": [{"name": "Nage", "samplers": samplers, "channels": channels}]}
    js = json.dumps(gltf, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON")); f.write(js)
        f.write(struct.pack("<I4s", len(blob), b"BIN\0")); f.write(blob)
    return total, len(channels)


# --------------------------------------------------------------------------
# 6. Export USD (UsdSkel) puis paquet .usdz pour AR Quick Look
# --------------------------------------------------------------------------
def n5(v):
    s = f"{v:.5f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def v3(v): return "(" + ", ".join(n5(x) for x in v) + ")"
def qw(q): return "(" + ", ".join(n5(x) for x in (q[3], q[0], q[1], q[2])) + ")"   # USD : (w, x, y, z)


def export_usda(skinned, static):
    end = FRAMES_PAR_CLE * K * LOOPS_USD
    joints_tok = ", ".join(f'"{joint_path(i)}"' for i in range(len(JOINTS)))
    L = ["#usda 1.0", "(", '    defaultPrim = "Scene"', "    metersPerUnit = 1", '    upAxis = "Y"',
         "    startTimeCode = 0", f"    endTimeCode = {end}", f"    timeCodesPerSecond = {FPS}",
         f"    framesPerSecond = {FPS}", ")", "",
         'def Xform "Scene" (', '    kind = "component"', ")", "{"]

    def mat_binding(mat): return f"        rel material:binding = </Scene/Materials/{mat}>"

    # --- socle (statique)
    L += ['    def Xform "Base"', "    {"]
    for name, (pos, nrm, idx, mat) in static.items():
        mn = [min(p[i] for p in pos) for i in range(3)]; mx = [max(p[i] for p in pos) for i in range(3)]
        L += [f'        def Mesh "{name}" (', '            prepend apiSchemas = ["MaterialBindingAPI"]', "        )", "        {",
              f"            float3[] extent = [{v3(mn)}, {v3(mx)}]",
              f"            int[] faceVertexCounts = [{', '.join(['3'] * (len(idx)//3))}]",
              f"            int[] faceVertexIndices = [{', '.join(map(str, idx))}]",
              f"            rel material:binding = </Scene/Materials/{mat}>",
              f"            normal3f[] normals = [{', '.join(v3(x) for x in nrm)}] (",
              '                interpolation = "vertex"', "            )",
              f"            point3f[] points = [{', '.join(v3(p) for p in pos)}]",
              '            uniform token subdivisionScheme = "none"', "        }"]
    L += ["    }"]

    # --- méduse : SkelRoot, squelette, animation, maillages skinnés
    L += ['    def SkelRoot "Jelly"', "    {",
          '        def Skeleton "Skel" (', '            prepend apiSchemas = ["SkelBindingAPI"]', "        )", "        {",
          f"            uniform token[] joints = [{joints_tok}]"]
    bind = ", ".join(f"( (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), {v3(world_bind(i))[:-1]}, 1) )"
                     for i in range(len(JOINTS)))
    rest = ", ".join(f"( (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), {v3(JOINTS[i]['t'])[:-1]}, 1) )"
                     for i in range(len(JOINTS)))
    L += [f"            uniform matrix4d[] bindTransforms = [{bind}]",
          f"            uniform matrix4d[] restTransforms = [{rest}]",
          "            rel skel:animationSource = </Scene/Jelly/Skel/Anim>",
          '            def SkelAnimation "Anim"', "            {",
          f"                uniform token[] joints = [{joints_tok}]"]
    tr_s, ro_s, sc_s = [], [], []
    for i in range(K * LOOPS_USD + 1):
        frame = i * FRAMES_PAR_CLE
        ps = pose(P * i / K)
        tr_s.append(f"{frame}: [{', '.join(v3(p[0]) for p in ps)}]")
        ro_s.append(f"{frame}: [{', '.join(qw(p[1]) for p in ps)}]")
        sc_s.append(f"{frame}: [{', '.join(v3(p[2]) for p in ps)}]")
    L += [f"                float3[] translations.timeSamples = {{ {', '.join(tr_s)} }}",
          f"                quatf[] rotations.timeSamples = {{ {', '.join(ro_s)} }}",
          f"                half3[] scales.timeSamples = {{ {', '.join(sc_s)} }}",
          "            }", "        }"]

    for name, (pos, nrm, idx, jid, wgt, mat) in skinned.items():
        flat_j = [k for j in jid for k in j]; flat_w = [n5(k) for w in wgt for k in w]
        L += [f'        def Mesh "{name}" (', '            prepend apiSchemas = ["SkelBindingAPI", "MaterialBindingAPI"]', "        )", "        {",
              f"            uniform bool doubleSided = {'true' if MATERIALS[mat]['double'] else 'false'}",
              f"            int[] faceVertexCounts = [{', '.join(['3'] * (len(idx)//3))}]",
              f"            int[] faceVertexIndices = [{', '.join(map(str, idx))}]",
              "            matrix4d primvars:skel:geomBindTransform = ( (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1) )",
              f"            int[] primvars:skel:jointIndices = [{', '.join(map(str, flat_j))}] (",
              "                elementSize = 4", '                interpolation = "vertex"', "            )",
              f"            float[] primvars:skel:jointWeights = [{', '.join(flat_w)}] (",
              "                elementSize = 4", '                interpolation = "vertex"', "            )",
              f"            rel material:binding = </Scene/Materials/{mat}>",
              "            rel skel:skeleton = </Scene/Jelly/Skel>",
              f"            normal3f[] normals = [{', '.join(v3(x) for x in nrm)}] (",
              '                interpolation = "vertex"', "            )",
              f"            point3f[] points = [{', '.join(v3(p) for p in pos)}]",
              '            uniform token subdivisionScheme = "none"', "        }"]
    L += ["    }"]

    # --- matériaux
    L += ['    def Scope "Materials"', "    {"]
    for name, m in MATERIALS.items():
        base = f"/Scene/Materials/{name}"
        L += [f'        def Material "{name}"', "        {",
              f"            token outputs:surface.connect = <{base}/PBR.outputs:surface>",
              '            def Shader "PBR"', "            {",
              '                uniform token info:id = "UsdPreviewSurface"',
              f"                color3f inputs:diffuseColor = {v3(m['col'])}",
              f"                color3f inputs:emissiveColor = {v3(m['emi'])}",
              f"                float inputs:metallic = {n5(m['met'])}",
              f"                float inputs:roughness = {n5(m['rou'])}",
              f"                float inputs:opacity = {n5(m['alpha'])}",
              "                token outputs:surface", "            }", "        }"]
    L += ["    }", "}"]
    return "\n".join(L) + "\n"


def write_usdz(files, path):
    """Archive ZIP non compressée, données alignées sur 64 octets (exigence USDZ)."""
    out = bytearray(); central = []
    for name, data in files:
        nb = name.encode(); crc = zlib.crc32(data) & 0xFFFFFFFF; offset = len(out)
        pad = (-(offset + 30 + len(nb) + 4)) % 64
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


if __name__ == "__main__":
    skinned, static = build_meshes()
    n, nch = export_glb(skinned, static, os.path.join(OUT, NOM + ".glb"))
    usda = export_usda(skinned, static)
    if os.environ.get("KEEP_USDA"):
        open(os.path.join(OUT, NOM + ".usda"), "w").write(usda)
    m = write_usdz([(NOM + ".usda", usda.encode())], os.path.join(OUT, NOM + ".usdz"))
    print(f"{len(JOINTS)} os, {nch} canaux d'animation")
    print(f"{NOM}.glb  : {n/1024:.0f} Ko")
    print(f"{NOM}.usdz : {m/1024:.0f} Ko")
