"""Dataset：TerritoryIR 的数据集对象。

持有一座城市的基础数据（四级路网父地块、区划街道面、OSM 地物、region 围栏）
并派生统一铺盖 U（路网父地块 × 街道面 切片）与词表/地物索引。
所有编译、重演、语义构面都围绕 Dataset 工作。

install(globals()) 把全部公共名拷入调用方全局命名空间——
用于旧代码的薄适配层（兼容 `tc.U`、`tc.compile_fence` 模块属性式访问）。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from shapely import ops, wkt
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from .coords import gcj2wgs, gcj2wgs_vec

def _norm_key(s: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(s).lower())


CLASS_RANK = {"motorway": 0, "motorway_link": 1, "trunk": 1, "trunk_link": 2,
              "primary": 2, "primary_link": 3, "secondary": 3,
              "secondary_link": 4, "tertiary": 4, "tertiary_link": 5,
              "residential": 6, "unclassified": 7, "service": 8}
RIVER_RANK = 3


class Dataset:
    """一座城市的 TerritoryIR 数据集。"""

    def __init__(self, *, data_dir, roadnet_path, streets_path, osm_path,
                 name="default", km2_deg2=12364.0,
                 feat_buf_m=100.0, band_buf_m=150.0):
        self.name = name
        self.data_dir = Path(data_dir)
        self.roadnet_path = str(roadnet_path)
        self.streets_path = str(streets_path)
        self.osm_path = str(osm_path)
        self.KM2 = km2_deg2
        self.FEAT_BUF = feat_buf_m / 111000.0
        self.BAND_BUF = band_buf_m / 111000.0
        self._build()

    # ---------- 构建 ----------
    def _build(self):
        d = json.load(open(self.roadnet_path))
        self.parents, self.pstreet, self.pdistrict = [], [], []
        for f in d["features"]:
            g = f["geometry"]
            if g["type"] != "Polygon":
                continue
            pr = f["properties"]
            self.parents.append(Polygon(g["coordinates"][0], g["coordinates"][1:]))
            self.pstreet.append(pr.get("街道[内置]", ""))
            self.pdistrict.append(pr.get("区[内置]", ""))
        self.pt = STRtree(self.parents)

        sd = json.load(open(self.streets_path))
        self.spoly, self.sname = [], []
        for f in sd["features"]:
            g = f["geometry"]
            try:
                if g["type"] == "Polygon":
                    p = Polygon(g["coordinates"][0], g["coordinates"][1:])
                elif g["type"] == "MultiPolygon":
                    p = ops.unary_union([Polygon(c[0], c[1:])
                                         for c in g["coordinates"]])
                else:
                    continue
            except Exception:  # noqa: BLE001
                continue
            if p.is_empty:
                continue
            if not p.is_valid:
                p = p.buffer(0)
            self.spoly.append(p)
            pr = f["properties"]
            self.sname.append(pr.get("街道[内置]") or pr.get("街道")
                              or pr.get("name") or "")
        self.sst = STRtree(self.spoly)
        self.sbt = ops.unary_union([p.boundary for p in self.spoly])
        self.spoly_by_name = dict(zip(self.sname, self.spoly))

        self.reg = json.load(open(Path(self.data_dir) / "region.json"))
        self.osm = json.load(open(self.osm_path))

        self.feat_geoms, self.feat_names, self.feat_rank = [], [], {}
        for r in self.osm["roads"]:
            nm = r.get("name")
            if not nm:
                continue
            try:
                g = wkt.loads(r["wkt"])
            except Exception:  # noqa: BLE001
                continue
            self._add_feat(nm, g, CLASS_RANK.get(r.get("cls", "unclassified"), 7))
        for r in self.osm.get("rivers", []):
            nm = r.get("name", "")
            if not nm:
                continue
            try:
                g = wkt.loads(r["wkt"])
            except Exception:  # noqa: BLE001
                continue
            self._add_feat(nm, g, RIVER_RANK)
        self.ftt = STRtree(self.feat_geoms)

        self.adm6 = []
        for rr in self.osm["adm6"]:
            try:
                self.adm6.append((rr.get("name", ""),
                                  wkt.loads(rr["wkt"]).boundary))
            except Exception:  # noqa: BLE001
                pass
        self.adm6bt = ops.unary_union([b for _, b in self.adm6])

        # 统一铺盖 U：(几何, 主街道标签, 所在街道面, 父地块号)
        U = []
        for pi, u in enumerate(self.parents):
            cand = [int(j) for j in self.sst.query(u)]
            hits = []
            for j in cand:
                if not self.spoly[j].intersects(u):
                    continue
                inter = self.spoly[j].intersection(u)
                if inter.is_empty or inter.area < 1e-12:
                    continue
                if not inter.is_valid:
                    inter = inter.buffer(0)
                hits.append((j, inter))
            if len(hits) <= 1:
                a = self.sname[hits[0][0]] if hits else ""
                if u.geom_type == "Polygon":
                    U.append((u, self.pstreet[pi], a, pi))
                continue
            for j, part in hits:
                if part.geom_type == "Polygon":
                    U.append((part, self.pstreet[pi], self.sname[j], pi))
                elif part.geom_type == "MultiPolygon":
                    for g2 in part.geoms:
                        U.append((g2, self.pstreet[pi], self.sname[j], pi))
        for k in range(len(U)):
            if not U[k][0].is_valid:
                U[k] = (U[k][0].buffer(0),) + U[k][1:]
        self.U = U
        self.Ut = STRtree([x[0] for x in self.U])

        # 地物贴附（一次性向量化 GCJ→WGS，避免 6261 次逐片 transform）
        import numpy as np
        import shapely
        self._feats = {}
        self.FEATS = defaultdict(set)
        all_geoms = [self.U[k][0] for k in range(len(self.U))]
        coords_arr = shapely.get_coordinates(all_geoms)
        lon2, lat2 = gcj2wgs_vec(coords_arr[:, 0], coords_arr[:, 1])
        self.U_wgs = list(shapely.set_coordinates(
            np.array(all_geoms, dtype=object),
            np.column_stack([lon2, lat2])))
        for _k in range(len(self.U)):
            for _nm in self.feats_of(_k):
                self.FEATS[_nm].add(_k)

        self._river_name_set = {r.get("name", "") for r in self.osm.get("rivers", [])
                                if r.get("name", "")}
        self._VOCAB = None

        # 国道/省道编号 → 几何（来自 fetch_region_osm 的 osm_parsed.refs，WGS）
        self.osm_refs = {}
        for rp in (Path(self.data_dir) / "osm_refs.json",
                   Path(self.data_dir) / "osm_parsed.json"):
            if rp.exists():
                parsed = json.loads(rp.read_text(encoding="utf-8"))
                self.osm_refs = parsed.get("refs", parsed)  # osm_refs.json 或 osm_parsed 格式
                break

        # 道路编号别名（全局映射）：g324 → 广汕公路 等
        self.road_aliases = {}
        ap = Path(self.data_dir) / "road_aliases.json"
        if not ap.exists():
            ap = Path(__file__).resolve().parent / "road_aliases.json"
        if ap.exists():
            raw = json.loads(ap.read_text(encoding="utf-8"))
            for k, v in raw.items():
                if not k.startswith("_"):
                    self.road_aliases[_norm_key(k)] = v

    def _add_feat(self, nm, g, rk_default):
        parts = ([g] if g.geom_type == "LineString"
                 else (list(g.geoms) if g.geom_type == "MultiLineString" else []))
        for pp in parts:
            if pp.length > 1e-5:
                self.feat_geoms.append(pp)
                self.feat_names.append(nm)
        rk = self.feat_rank.get(nm, rk_default)
        if nm not in self.feat_rank or rk < self.feat_rank[nm]:
            self.feat_rank[nm] = rk

    # ---------- 地物贴附 ----------
    def feats_of(self, k):
        if k not in self._feats:
            gw = self.U_wgs[k]
            s = set()
            for j in self.ftt.query(gw.buffer(self.FEAT_BUF)):
                if self.feat_geoms[j].distance(gw) <= self.FEAT_BUF:
                    s.add(self.feat_names[j])
            self._feats[k] = s
        return self._feats[k]

    # ---------- 词表 ----------
    def vocab(self):
        if self._VOCAB is not None:
            return self._VOCAB
        v = []
        byba = defaultdict(list)
        for k in range(len(self.U)):
            byba[(self.U[k][1], self.U[k][2])].append(k)
        for (b, a), ks in byba.items():
            v.append((f"{b}(限{a}内)",
                      {"type": "slice", "street": b, "within": a}, set(ks)))
        byf = defaultdict(set)
        for k in range(len(self.U)):
            for f in self.feats_of(k):
                byf[(self.U[k][1], self.U[k][2], f)].add(k)
        for (b, a, f), ks in byf.items():
            kind = "river" if f in self._river_name_set else "road"
            v.append((f"{b}沿{f}(限{a}内)",
                      {"type": "feat", "street": b, "feat": f,
                       "kind": kind, "within": a}, set(ks)))
        v.append(("零星地块", {"type": "pieces", "ids": []}, set()))
        for k in range(len(self.U)):
            v.append((f"P#{k}", {"type": "pieces", "ids": [k]}, {k}))
        self._VOCAB = v
        return v

    # ---------- 子句解析 ----------
    def clause_pieces(self, clause):
        t = clause["type"]
        if t == "band":
            return set()
        if t == "slice":
            return {k for k, x in enumerate(self.U)
                    if x[1] == clause["street"] and x[2] == clause["within"]}
        if t == "feat":
            return {k for k in self.FEATS.get(clause["feat"], set())
                    if self.U[k][1] == clause["street"]
                    and (not clause.get("within") or self.U[k][2] == clause["within"])}
        if t == "block":
            return {k for k, x in enumerate(self.U) if x[1] == clause["street"]}
        if t == "pieces":
            return set(clause["ids"])
        return set()

    def eval_sir(self, ir):
        S = set()
        bands = []
        for cl in ir["clauses"]:
            S |= self.clause_pieces(cl)
            if cl["type"] == "band":
                nm = cl["ref"].replace("河岸", "")
                g = self.spoly_by_name.get(
                    nm.replace("至", "").split("—")[0] if "—" in nm
                    else nm.replace("至", ""))
                if g is not None:
                    a_ = nm.replace("至", "").split("—")[0] if "—" in nm else nm
                    inside = [x[0] for x in self.U if x[2] == a_]
                    if inside:
                        bands.append(g.difference(ops.unary_union(inside)))
        return S, bands

    # ---------- 贪心合成 ----------
    def synth(self, zg, T):
        T = set(T)
        chosen, cov = [], set()
        V = self.vocab()
        while cov < T:
            best = None
            for label, clause, s in V:
                gain = len((s & T) - cov)
                if gain == 0:
                    continue
                o = len((s - cov) - T)
                salience = 0
                if clause["type"] == "feat":
                    salience = -self.feat_rank.get(clause["feat"], 7)
                key = (o, -gain, salience)
                if best is None or key < best[0]:
                    best = (key, label, clause, s)
            if best is None:
                break
            _, label, clause, s = best
            chosen.append((label, clause))
            cov |= (s & T)
        return chosen

    # ---------- 人话 ----------
    def verbalize(self, chosen, zg_):
        by_street = defaultdict(list)
        bands = []
        for label, cl in chosen:
            if cl["type"] == "band":
                bands.append(cl)
                continue
            if cl["type"] == "pieces":
                continue
            if cl["type"] in ("slice", "feat", "block"):
                by_street[cl["street"]].append(cl)
        parts = []
        for stn, cls in sorted(by_street.items(), key=lambda kv: -len(kv[1])):
            whole = any(c["type"] == "slice" and c["street"] == c["within"]
                        for c in cls) or (
                len(cls) == 1 and cls[0]["type"] == "block")
            feats = sorted({c["feat"] for c in cls if c["type"] == "feat"},
                           key=lambda f: -self.feat_rank.get(f, 7))
            if whole:
                parts.append(stn)
            elif feats:
                parts.append(f"{stn}沿{feats[0]}")
            else:
                parts.append(f"{stn}一带")
        for cl in bands:
            parts.append(f"{cl['side']}至{cl['ref']}")
        return parts

    def band_clause(self, zg, pc):
        c = pc.centroid
        best6 = None
        for n6, b6 in self.adm6:
            dd6 = b6.distance(c) * 111000
            if best6 is None or dd6 < best6[1]:
                best6 = (n6, dd6)
        side = ("西" if c.x < zg.centroid.x else "东" if c.x > zg.centroid.x
                else "南" if pc.centroid.y < zg.centroid.y else "北")
        if best6 and best6[1] < 300:
            return {"type": "band", "side": side, "ref": f"{best6[0]}界"}
        best = None
        for j in range(len(self.spoly)):
            dd = self.spoly[j].boundary.distance(c) * 111000
            if best is None or dd < best[1]:
                best = (j, dd)
        j = best[0]
        cands = sorted(((self.sname[j2],
                         self.spoly[j2].boundary.distance(c) * 111000)
                        for j2 in range(len(self.spoly)) if j2 != j),
                       key=lambda t: t[1])
        return {"type": "band", "side": side,
                "ref": f"{self.sname[j]}—{cands[0][0] if cands else '?'}界"}

    # ---------- 单围栏编译 ----------
    def compile_fence(self, fence):
        zg = Polygon(fence["rings"][0])
        if not zg.is_valid:
            zg = zg.buffer(0)
        if zg.geom_type == "MultiPolygon":
            zg = max(zg.geoms, key=lambda g: g.area)
        fa = zg.area
        T = {k for k in range(len(self.U))
             if self.U[k][0].intersection(zg).area / max(self.U[k][0].area, 1e-12) >= 0.5
             or self.U[k][0].intersection(zg).area / fa >= 0.3}
        psel = {i for i in self.pt.query(zg)
                if self.parents[i].intersection(zg).area / max(self.parents[i].area, 1e-12) >= 0.5
                or self.parents[i].intersection(zg).area / fa >= 0.3}
        if not psel:
            psel = {i for i in self.pt.query(zg)
                    if self.parents[i].intersection(zg).area > 1e-9}
        chosen = self.synth(zg, T)
        if chosen:
            S_syn = set()
            for _, c in chosen:
                S_syn |= self.clause_pieces(c)
            pu = ops.unary_union([self.U[k][0] for k in S_syn])
            strip = zg.difference(pu).intersection(
                ops.unary_union([self.sbt, self.adm6bt]).buffer(self.BAND_BUF))
            if strip.area * self.KM2 > 0.01:
                pieces = (strip.geoms if strip.geom_type == "MultiPolygon"
                          else [strip])
                for pc in pieces:
                    if pc.area * self.KM2 < 0.01:
                        continue
                    chosen.append((f"{pc.centroid.x:.4f}界带",
                                   self.band_clause(zg, pc)))
        clauses = [cl for _, cl in chosen]
        import hashlib
        libhash = hashlib.sha256(
            open(self.roadnet_path, "rb").read()).hexdigest()[:16]
        ir = {"area_id": fence["area_id"], "ir_version": 1,
              "tessellation": "U",
              "unit_library": f"{libhash}+cutv2",
              "clauses": clauses, "annotations": {}}
        S = set()
        bands_g = []
        for cl in clauses:
            s = self.clause_pieces(cl)
            S |= s
            if cl["type"] == "band":
                nm = cl["ref"].replace("界", "")
                a = nm.split("—")[0]
                g = self.spoly_by_name.get(a)
                if g is not None:
                    inside = [x[0] for x in self.U if x[2] == a]
                    if inside:
                        bands_g.append(g.difference(
                            ops.unary_union(inside)))
        full = (ops.unary_union([self.U[k][0] for k in S] + bands_g)
                if (S or bands_g) else None)
        hterms = self.verbalize(chosen, zg)
        hit = len(S & T)
        over = len(S - T)
        miss = len(T - S)
        J = hit / (hit + over + miss) if hit + over + miss else 0
        cov = (zg.intersection(full).area / zg.area * 100
               if full is not None else 0)
        ii = self.iou_v(zg, full) if full is not None else 0
        return {"dealer": fence["dealer"], "area_id": fence["area_id"],
                "km2": fence["area_km2"],
                "human_terms": hterms,
                "engine_terms": [l for l, _ in chosen],
                "ir": ir, "T": sorted(T), "S": sorted(S),
                "engine_J": round(J, 3), "engine_hit": hit,
                "engine_over": over, "engine_miss": miss,
                "truth_pieces": len(T), "iou": round(ii, 3),
                "cover": round(cov, 2)}

    @staticmethod
    def iou_v(a, b):
        i = a.intersection(b).area
        s = a.area + b.area - i
        return i / s if s else 0

    # ---------- 兼容安装 ----------
    def install(self, g: dict) -> None:
        """把全部公共名拷入调用方 globals（旧模块属性式访问的薄适配）。"""
        skip = {"install"}
        for k in list(self.__dict__):
            if not k.startswith("_") and k not in skip:
                g[k] = self.__dict__[k]
        for m in ("feats_of", "vocab", "clause_pieces", "eval_sir", "synth",
                  "verbalize", "band_clause", "compile_fence", "iou_v"):
            g[m] = getattr(self, m)
        g["ds"] = self

    # ---------- 预置数据集 ----------
    @classmethod
    def guangzhou(cls, data_dir):
        here = Path(__file__).resolve().parent
        cfg = Path(data_dir) / "territory_ir_dataset.json"
        if cfg.exists():
            c = json.loads(cfg.read_text(encoding="utf-8"))
            return cls(data_dir=data_dir, **c)
        import os
        import warnings
        home = os.path.expanduser("~")
        # 环境变量优先于 ~/Downloads 硬编码(见 issue #1)
        roadnet = os.environ.get("TIR_GZ_ROADNET") or os.path.join(
            home, "Downloads",
            "边界数据-路网-到区县带海岸线-四级路网-广东省-广州市.geojson")
        streets = os.environ.get("TIR_GZ_STREETS") or os.path.join(
            home, "Downloads", "区划数据-街道-广东省-广州市.geojson")
        warnings.warn(
            "Dataset.guangzhou 回退到硬编码 ~/Downloads/... 路径。"
            "生产请用 <data_dir>/territory_ir_dataset.json 或 "
            "环境变量 TIR_GZ_ROADNET / TIR_GZ_STREETS。",
            stacklevel=2)
        return cls(
            data_dir=data_dir,
            roadnet_path=roadnet,
            streets_path=streets,
            osm_path=os.path.join(data_dir, "gz_osm_full.json"),
            name="guangzhou")
