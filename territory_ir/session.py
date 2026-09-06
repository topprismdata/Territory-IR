"""会话围栏仓：导入/描述/文字建围栏/沿路拆分/合并。

所有围栏 = {id, name, rings:[[环]...], pieces:set|None, terms, km2, color}
pieces 非空时按片运算（可拆可并）；为空（库外导入）时仅几何视图。

★ 核心不变量：不存在物理切割。切分/合并/扩展全部是【片归属变更】——
  片是原子，任何操作只增删改「片属于哪个围栏」，永不修改片几何。
  围栏环(rings)永远是所属片并集的派生视图。
"""
from __future__ import annotations

import json
import math
import uuid
from pathlib import Path

from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union

from .dataset import Dataset
from .semantics import (ir_fence_from_semantics, pieces_union,
                        road_line_gcj, split_pieces_by_road)

PALETTE = ["#1e88e5", "#43a047", "#e53935", "#fb8c00", "#8e24aa",
           "#00897b", "#6d4c41", "#f4511e"]


class Session:
    def __init__(self, ds: Dataset, persist_dir="sessions"):
        self.ds = ds
        self.fences: list[dict] = []
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(exist_ok=True)

    # ---------- 持久化 ----------
    def save(self, sid="default"):
        out = [{**f, "pieces": sorted(f["pieces"]) if f["pieces"] else None}
               for f in self.fences]
        (self.persist_dir / f"{sid}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    def load(self, sid="default"):
        p = self.persist_dir / f"{sid}.json"
        if p.exists():
            rows = json.loads(p.read_text(encoding="utf-8"))
            self.fences = [{**r, "pieces": set(r["pieces"]) if r["pieces"] else None,
                            "clauses": r.get("clauses", [])}
                           for r in rows]

    _line_cache: dict = {}

    def road_line(self, road):
        """路折线（GCJ，进程级缓存）。"""
        if road not in self._line_cache:
            from territory_ir.semantics import road_line_gcj
            self._line_cache[road] = road_line_gcj(self.ds, road)
        return self._line_cache[road]

    # ---------- 基础 ----------
    def _color(self):
        return PALETTE[len(self.fences) % len(PALETTE)]

    def _by_id(self, fid):
        for f in self.fences:
            if f["id"] == fid:
                return f
        raise KeyError(fid)

    def find_exact(self, name: str):
        hits = [f for f in self.fences if f["name"] == name]
        if len(hits) != 1:
            raise ValueError(f"精确名「{name}」匹配到 {len(hits)} 个围栏")
        return hits[0]

    def find(self, name_substr):
        exact = [f for f in self.fences if f["name"] == name_substr]
        hits = [f for f in self.fences if name_substr in f["name"]]
        if exact:
            return exact[0]
        if len(hits) == 1:
            return hits[0]
        raise ValueError(f"「{name_substr}」匹配到 {len(hits)} 个围栏，请用更完整的名字")

    def public(self):
        return [{"id": f["id"], "name": f["name"], "rings": f["rings"],
                 "km2": f["km2"], "terms": f["terms"],
                 "engine_terms": f.get("engine_terms", []),
                 "pieces": len(f["pieces"] or []),
                 "color": f["color"]} for f in self.fences]

    @staticmethod
    def _rings_of(geom) -> list:
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        out = []
        for p in sorted(polys, key=lambda g: -g.area):
            out.append([[round(x, 6), round(y, 6)] for x, y in p.exterior.coords])
        return out

    @staticmethod
    def _km2(ds, geom) -> float:
        from .coords import gcj2wgs
        tot = 0.0
        for poly in (geom.geoms if geom.geom_type == "MultiPolygon" else [geom]):
            w = [gcj2wgs(x, y) for x, y in poly.exterior.coords]
            lat = sum(p[1] for p in w) / len(w)
            # 平面近似:纬度 km/deg 固定 111.32,经度 km/deg = 111.32·cos(lat)。
            # 旧实现硬编码广州纬度因子 0.92,换城市即错(审计 B1)。
            tot += Polygon(w).area * 111.32 * 111.32 * math.cos(math.radians(lat))
        return round(tot, 2)

    # ---------- 1. 导入 ----------
    def import_ring(self, name, ring) -> dict:
        """单环导入 → 编译（真值片+人话）。"""
        poly = Polygon(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        fence = {"id": uuid.uuid4().hex[:8], "name": name,
                 "rings": [[[round(x, 6), round(y, 6)]
                            for x, y in poly.exterior.coords]],
                 "pieces": None, "terms": [],
                 "km2": self._km2(self.ds, poly), "color": self._color()}
        self.fences.append(fence)
        self.compile(fence)   # ★ 全生命周期唯一一次编译
        self.save()
        return fence

    def import_geojson(self, name, geo: dict) -> list[dict]:
        """GeoJSON FeatureCollection/Feature/geometry 导入（取 Polygon 部分）。"""
        geoms = []
        if geo.get("type") == "FeatureCollection":
            geoms = [f["geometry"] for f in geo["features"]]
        elif geo.get("type") == "Feature":
            geoms = [geo["geometry"]]
        elif geo.get("type"):
            geoms = [geo]
        out = []
        n = 0
        for g in geoms:
            if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            n += 1
            # MultiPolygon 不再只取最大部分(审计 B2 静默丢几何):
            # 每个部分独立成围栏,符合"多连通分量合法"的业务约定。
            parts = ([g["coordinates"]] if g["type"] == "Polygon"
                     else list(g["coordinates"]))
            for pi, part in enumerate(parts, 1):
                if len(geoms) == 1 and len(parts) == 1:
                    nm = name
                elif len(parts) == 1:
                    nm = f"{name}-{n}"
                else:
                    nm = f"{name}-{n}.{pi}"
                out.append(self.import_ring(nm, part[0]))
        if not out:
            raise ValueError("GeoJSON 中没有可用的 Polygon")
        return out

    def describe_pieces(self, pieces) -> list[str]:
        """轻量人话：片集合的街道构成统计（毫秒级，无编译）。"""
        from collections import Counter
        pieces = set(pieces)
        cnt = Counter(self.ds.U[k][1] for k in pieces)
        totals = Counter(self.ds.U[k][1] for k in range(len(self.ds.U)))
        feats_by = {k: self.ds.feats_of(k) for k in pieces}
        parts = []
        for st, n in cnt.most_common():
            st_pieces = {k for k in pieces if self.ds.U[k][1] == st}
            if st in totals and n == totals[st]:
                parts.append(st)          # 全域
                continue
            best_fm, best_c = None, 1
            for k in st_pieces:
                for fm in feats_by[k]:
                    c = sum(1 for kk in st_pieces if fm in feats_by[kk])
                    if c > best_c:
                        best_fm, best_c = fm, c
            parts.append(f"{st}沿{best_fm}" if best_fm else f"{st}一带")
        return parts

    # ---------- 编译/描述 ----------
    def compile(self, fence) -> dict:
        row = self.ds.compile_fence(
            {"area_id": fence["id"], "dealer": fence["name"],
             "rings": fence["rings"], "area_km2": fence["km2"]})
        fence["pieces"] = set(row["T"])
        fence["clauses"] = row["ir"]["clauses"]
        fence["terms"] = row["human_terms"]
        fence["engine_terms"] = row["engine_terms"]
        fence["j"] = row["engine_J"]
        return {"fence": self.pub(fence), "row": row}

    def describe(self, name_substr) -> dict:
        f = self.find(name_substr)
        return {"fence": self.pub(f), "terms": f["terms"],
                "j": f.get("j"), "pieces": len(f["pieces"] or [])}

    def pub(self, fence) -> dict:
        return {"id": fence["id"], "name": fence["name"], "rings": fence["rings"],
                "km2": fence["km2"], "terms": fence["terms"],
                "engine_terms": fence.get("engine_terms", []),
                "pieces": len(fence["pieces"] or []), "color": fence["color"]}

    # ---------- 2. 文字建围栏 ----------
    def fence_from_text(self, name, areas, bounds) -> dict:
        pieces = ir_fence_from_semantics(self.ds, areas, bounds, None)
        if not pieces:
            raise ValueError("语义未命中单元库片（请核对街道名/界路名，或该区域不在覆盖范围）")
        geom = pieces_union(self.ds, pieces)
        rings = self._rings_of(geom)
        fence = {"id": uuid.uuid4().hex[:8], "name": name,
                 "rings": rings, "pieces": pieces,
                 "terms": [], "km2": self._km2(self.ds, geom),
                 "color": self._color()}
        # 人话：从真值即片集合反推（T=S 场景直接用 compile 的 verbalize 产物）
        row = self.ds.compile_fence({"area_id": fence["id"], "dealer": name,
                                     "rings": [rings[0]], "area_km2": fence["km2"]})
        fence["terms"] = row["human_terms"]
        self.fences.append(fence)
        self.save()
        return fence

    def fence_from_terms(self, name, terms) -> dict:
        """条款（| 分隔）→ 片集合 → 围栏（确定性，无LLM）。

        支持引擎格式：`新塘街道沿天顺路(限新塘街道内)`、`P#1473`、
        `联和街道(限凤凰街道内)`；界带/东至类条款无独立片集，跳过。"""
        import re as _re
        clauses = []
        skipped = []
        for term in terms:
            term = term.strip().strip("|").strip()
            if not term:
                continue
            if "界带" in term or _re.match(r"^[东南西北]至", term):
                skipped.append(term)
                continue
            m = _re.match(r"^P#(\d+)$", term)
            if m:
                clauses.append({"type": "pieces", "ids": [int(m.group(1))]})
                continue
            within = ""
            mw = _re.search(r"\(限(.+?)内\)", term)
            if mw:
                within = mw.group(1)
                term = term[:mw.start()].strip()
            if "沿" in term:
                st, road = [x.strip() for x in term.split("沿", 1)]
                clauses.append({"type": "feat", "street": st,
                                "feat": road, "within": within})
            elif within and within != term:
                clauses.append({"type": "slice", "street": term,
                                "within": within})
            else:
                clauses.append({"type": "block", "street": term})
        S = set()
        for cl in clauses:
            S |= self.ds.clause_pieces(cl)
        if not S and all(_re.search(r"(高速|公路|大道|快速|国道|省道)", term) for term in terms):
            # 道路名走廊兜底：沿路取 3km 走廊带
            return self.corridor([_re.sub(r"\(限.+?内\)", "", tm).strip() for tm in terms], 3.0, name)
        if not S:
            raise ValueError("条款未命中任何单元片（请核对街道/路名）")
        geom = pieces_union(self.ds, S)
        rings = self._rings_of(geom)
        fence = {"id": uuid.uuid4().hex[:8], "name": name,
                 "rings": rings, "pieces": S, "terms": terms,
                 "km2": self._km2(self.ds, geom), "color": self._color()}
        self.fences.append(fence)
        self.save()
        fence["_skipped"] = skipped
        fence["_clauses"] = clauses
        return fence

    # ---------- 扩展到界路 ----------
    def expand(self, name_substr, direction, road) -> tuple[dict, int]:
        """沿方向扩展围栏直到界路（片归属变更，新增相邻片）。"""
        side = {"west": "east", "east": "west",
                "south": "north", "north": "south"}[direction]
        f = self.find(name_substr)
        if not f["pieces"]:
            raise ValueError(f"「{f['name']}」不在单元库覆盖内，无法按片扩展")
        line = road_line_gcj(self.ds, road)
        allp = set(range(len(self.ds.U)))
        side_pieces, _ = split_pieces_by_road(self.ds, allp, line, side)
        geom = pieces_union(self.ds, f["pieces"])
        adj = {k for k in side_pieces
               if self.ds.U[k][0].distance(geom) <= 0.045}  # ≈5km 邻接带
        added = adj - set(f["pieces"])
        if not added:
            raise ValueError(f"没有可扩展的相邻片（可能已到达「{road}」）")
        f["pieces"] = set(f["pieces"]) | added
        geom2 = pieces_union(self.ds, f["pieces"])
        f["rings"] = self._rings_of(geom2)
        f["km2"] = self._km2(self.ds, geom2)
        f["clauses"] = f.get("clauses", []) + [
            {"type": "pieces", "ids": sorted(added)}]
        f["terms"] = self.describe_pieces(f["pieces"])
        self.save()
        return f, len(added)

    def corridor(self, roads, km=3.0, name="走廊围栏") -> dict:
        """沿多条路取走廊带内的片 → 建围栏（片归属变更语义同导入）。"""
        from shapely.geometry import Point
        from shapely.ops import unary_union as _uu
        buf_deg = km / 111.0
        bands = []
        for rd in roads:
            line = self.road_line(rd)
            bands.append(line.buffer(buf_deg))
        band = _uu(bands)
        pieces = {k for k in range(len(self.ds.U))
                  if band.covers(self.ds.U[k][0].centroid)}
        if not pieces:
            raise ValueError(f"这些路（{'、'.join(roads)}）周边 {km}km 内没有单元片")
        geom = pieces_union(self.ds, pieces)
        fence = {"id": uuid.uuid4().hex[:8], "name": name,
                 "rings": self._rings_of(geom), "pieces": pieces,
                 "clauses": [{"type": "pieces", "ids": sorted(pieces)}],
                 "terms": self.describe_pieces(pieces),
                 "km2": self._km2(self.ds, geom), "color": self._color()}
        self.fences.append(fence)
        self.save()
        return fence

    def enclosed_region(self, roads, name="多路围合") -> dict:
        """N（3-5）条互交道路围合区域：两两交点聚类 → 凸包 → 质心落内的片。

        ★ 纯片归属：片原子不切割。"""
        from itertools import combinations
        from shapely.geometry import Point, MultiPoint
        if not 3 <= len(roads) <= 5:
            raise ValueError("围合区域支持 3-5 条互交道路")
        lines = [self.road_line(r) for r in roads]
        pair_pts = []
        for i, j in combinations(range(len(lines)), 2):
            inter = lines[i].intersection(lines[j])
            pts = []
            def _collect(g):
                if g.is_empty:
                    return
                if g.geom_type == "Point":
                    pts.append(g)
                elif g.geom_type in ("MultiPoint", "GeometryCollection"):
                    for gg in g.geoms:
                        _collect(gg)
                elif g.geom_type == "LineString":
                    pts.extend([Point(g.coords[0]), Point(g.coords[-1])])
            _collect(inter)
            pair_pts.append(pts)
        all_pts = [p for pts in pair_pts for p in pts]
        if len(all_pts) < 3:
            raise ValueError("道路交点不足，无法围合")
        import statistics
        cx = statistics.median(p.x for p in all_pts)
        cy = statistics.median(p.y for p in all_pts)
        ordered = sorted(all_pts, key=lambda p: (p.x - cx) ** 2 + (p.y - cy) ** 2)
        near = [p for p in ordered if p.distance(ordered[0]) <= 0.30] or ordered[:3]
        hull = MultiPoint(near).convex_hull
        if hull.geom_type != "Polygon" or hull.area < 1e-6:
            raise ValueError("交点无法构成围合区域（近似共线？）")
        pieces = {k for k in range(len(self.ds.U))
                  if hull.covers(self.ds.U[k][0].centroid)}
        if not pieces:
            raise ValueError("围合区域内没有单元片")
        geom = pieces_union(self.ds, pieces)
        fence = {"id": uuid.uuid4().hex[:8], "name": name,
                 "rings": self._rings_of(geom), "pieces": pieces,
                 "clauses": [{"type": "pieces", "ids": sorted(pieces)}],
                 "terms": self.describe_pieces(pieces),
                 "km2": self._km2(self.ds, geom), "color": self._color()}
        self.fences.append(fence)
        self.save()
        return fence, hull

    # ---------- 3. 沿路拆分 ----------
    def split_preview(self, name_substr, road, side=None) -> dict:
        """预览沿路切分（零副作用）：片分堆出两个子围栏，存入 pending。"""
        side = side or "north"
        f = self.find(name_substr)
        if not f["pieces"]:
            raise ValueError(f"「{f['name']}」不在单元库覆盖内（无片），无法按片拆分")
        line = self.road_line(road)
        chosen, other = split_pieces_by_road(self.ds, f["pieces"], line, side)
        if not chosen or not other:
            fp = Polygon(f["rings"][0])
            if not fp.is_valid:
                fp = fp.buffer(0)
            cands = {n for j, n in enumerate(self.ds.feat_names)
                     if self.ds.feat_geoms[j].intersects(fp)}
            good = []
            for n in cands:
                try:
                    ln = self.road_line(n)
                    a, b = split_pieces_by_road(self.ds, f["pieces"], ln, "north")
                except Exception:  # noqa: BLE001
                    continue
                if a and b and min(len(a), len(b)) >= max(1, len(f["pieces"]) // 5):
                    good.append(n)
            hint = ("；该围栏可被这些路切分："
                    + "、".join(sorted(good)[:6])) if good else ""
            raise ValueError(f"「{road}」分不开这个围栏（整块在一侧）{hint}")
        side_cn = {"west": "西", "east": "东", "south": "南", "north": "北"}[side]
        g1 = pieces_union(self.ds, chosen)
        g2 = pieces_union(self.ds, other)
        f1 = {"id": uuid.uuid4().hex[:8], "name": f"{f['name']}·{side_cn}",
              "rings": self._rings_of(g1), "pieces": chosen, "terms": [],
              "km2": self._km2(self.ds, g1), "color": f["color"]}
        f2 = {"id": uuid.uuid4().hex[:8], "name": f["name"],
              "rings": self._rings_of(g2), "pieces": other, "terms": f["terms"],
              "km2": self._km2(self.ds, g2), "color": self._color()}
        for nf in (f1, f2):
            nf["terms"] = self.describe_pieces(nf["pieces"])
        self.pending = {"kind": "split", "parent": f["name"],
                        "children": [f1, f2]}
        return f1, f2

    def split_commit(self) -> None:
        """切分预览落地：移除父围栏，加入两个子围栏。"""
        p = self.pending
        if not p or p["kind"] != "split":
            return
        parent = self.find_exact(p["parent"])
        if parent in self.fences:
            self.fences.remove(parent)
        self.fences += p["children"]
        self.pending = None
        self.save()

    # ---------- 4. 合并 ----------
    def merge_preview(self, name_substrings) -> dict:
        """预览合并（零副作用）。"""
        fs = [self.find(s) for s in name_substrings]
        if len(fs) < 2:
            raise ValueError("合并至少需要两个围栏")
        pieces = set()
        for f in fs:
            pieces |= (f["pieces"] or set())
        if pieces:
            geom = pieces_union(self.ds, pieces)
        else:
            geom = unary_union([Polygon(f["rings"][0]) for f in fs])
            if geom.geom_type == "MultiPolygon":
                geom = max(geom.geoms, key=lambda g: g.area)
        merged = {"id": uuid.uuid4().hex[:8],
                  "name": "+".join(f["name"] for f in fs)[:24],
                  "rings": self._rings_of(geom), "pieces": pieces,
                  "clauses": [cl for f in fs for cl in f.get("clauses", [])],
                  "terms": self.describe_pieces(pieces),
                  "km2": self._km2(self.ds, geom),
                  "color": fs[0]["color"]}
        self.pending = {"kind": "merge", "parents": [f["name"] for f in fs],
                        "merged": merged}
        return merged

    def merge_commit(self) -> None:
        p = self.pending
        if not p or p["kind"] != "merge":
            return
        for nm in p["parents"]:
            f = self.find_exact(nm)
            if f in self.fences:
                self.fences.remove(f)
        self.fences.append(p["merged"])
        self.pending = None
        self.save()

    # ---------- 清空/删除 ----------
    def clear(self, name_substr=None) -> int:
        if name_substr:
            f = self.find(name_substr)
            self.fences.remove(f)
            n = 1
        else:
            n = len(self.fences)
            self.fences = []
        self.save()
        return n

    # ---------- GeoJSON 导出 ----------
    def to_geojson(self, fence) -> dict:
        polys = ([{"type": "Polygon", "coordinates": [r]} for r in fence["rings"]])
        feats = [{"type": "Feature",
                  "properties": {"name": fence["name"], "km2": fence["km2"]},
                  "geometry": p} for p in polys]
        return {"type": "FeatureCollection", "features": feats}
