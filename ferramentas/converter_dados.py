"""Converte MDT (GeoTIFF), nuvem de solo (LAS) e curvas de nível (SHP) nos arquivos do visualizador.

Uso:
    python converter_dados.py PASTA_ENTRADA PASTA_SAIDA

A pasta de entrada deve ter:
    MDT_Vocoroca.tif        MDT exportado do Cyclone 3DR / QGIS
    Nuvem_Solo_Unida.las    nuvem de pontos de solo (classe 2), com RGB
    Curvas.shp (+ .shx .dbf .prj)   curvas de nível com o campo "Elevation"

Saída: meta.json, mdt.json, nuvem.json e curvas.json (copiar para a pasta data/).
Dependências: pip install numpy rasterio laspy pyshp
"""
import json, base64, sys
import numpy as np, rasterio, laspy, shapefile

RAW, OUT = sys.argv[1], sys.argv[2]
b64 = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()

# ---- MDT
r = rasterio.open(f"{RAW}/MDT_Vocoroca.tif")
z = r.read(1).astype("float64")
nod = (z == r.nodata) | ~np.isfinite(z)
zmin, zmax = float(z[~nod].min()), float(z[~nod].max())
las = laspy.read(f"{RAW}/Nuvem_Solo_Unida.las")
E0 = float(np.floor(min(r.bounds.left, las.header.mins[0]) * 10) / 10)
N0 = float(np.floor(min(r.bounds.bottom, las.header.mins[1]) * 10) / 10)
Z0 = float(np.floor(min(zmin, las.header.mins[2])))
q = np.round((z - Z0) * 1000).clip(0, 65534).astype("<u2")   # mm acima de Z0
q[nod] = 65535
t = r.transform
mdt = dict(w=r.width, h=r.height, dx=t.a, dy=-t.e, left=t.c, top=t.f, data=b64(q))
cell = t.a * -t.e
valid = int((~nod).sum())

# ---- Nuvem
x, y, zz = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
pq = np.stack([(x - E0), (y - N0), (zz - Z0)], 1)
pq = np.round(pq / 0.002).clip(0, 65535).astype("<u2")       # unidade de 2 mm
rgb = np.stack([las.red, las.green, las.blue], 1).astype("float64")
if rgb.max() > 255: rgb = rgb / 256
rgb = rgb.clip(0, 255).astype("u1")
nuvem = dict(n=len(x), unit=0.002, xyz=b64(pq), rgb=b64(rgb))

# ---- Curvas
sf = shapefile.Reader(f"{RAW}/Curvas.shp")
elevs, starts, verts = [], [], []
for sr in sf.iterShapeRecords():
    shp, el = sr.shape, float(sr.record["Elevation"])
    parts = list(shp.parts) + [len(shp.points)]
    for a, b in zip(parts[:-1], parts[1:]):
        pts = np.array(shp.points[a:b])
        if len(pts) < 2: continue
        starts.append(sum(len(v) for v in verts)); elevs.append(el)
        verts.append(np.column_stack([pts[:, 0] - E0, pts[:, 1] - N0, np.full(len(pts), el - Z0)]))
V = np.concatenate(verts).astype("<f4")
curvas = dict(n_lines=len(elevs), elev=elevs, start=starts, n_verts=len(V), xyz=b64(V))

meta = dict(nome="Voçoroca Monjolo", epsg=31981, src="SIRGAS 2000 / UTM zona 21S",
            E0=E0, N0=N0, Z0=Z0, zmin=zmin, zmax=zmax,
            largura=r.bounds.right - r.bounds.left, altura=r.bounds.top - r.bounds.bottom,
            res=t.a, area_mdt=valid * cell, n_pontos=len(x),
            curvas_eq=0.2, curvas_n=len(set(elevs)))
for k, v in dict(mdt=mdt, nuvem=nuvem, curvas=curvas, meta=meta).items():
    json.dump(v, open(f"{OUT}/{k}.json", "w"))
print(json.dumps(meta, ensure_ascii=False, indent=1))
print("verts curvas", len(V), "rgb range", rgb.min(), rgb.max(), rgb.mean(0))
