"""会话围栏仓：导入/描述/文字建围栏/沿路拆分/合并。

所有围栏 = {id, name, rings:[[环]...], pieces:set|None, terms, km2, color}
pieces 非空时按片运算（可拆可并）；为空（库外导入）时仅几何视图。
"""
from __future__ import annotations

import json
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
            self.fences = [{**r, "pieces": set(r["pieces"]) if r["pieces"] else None}
                           for r in rows]

    # ---------- 基础 ----------
    def _color(self):
        return PALETTE[len(self.fences) % len(PALETTE)]

    def _by_id(self, fid):
        for f in self.fences:
            if f["id"] == fid:
                return f
        raise KeyError(fid)

    def find(self, name_substr):
        exact = [f for f in self.fences if f["name"] == name_substr]
        hits = [f for f in self.fences if name_substr in f["name"]]
        if len(hits) > 1 and not exact:
            raise ValueError(f"「{name_substr}」匹配到 {len(hits)} 个围栏，请用更完整的名字")
        return exact[0] if exact else hits[0]

    def public(self):
        return [{"id": f["id"], "name": f["name"], "rings": f["rings"],
                 "km2": f["km2"], "terms": f["terms"], "pieces": len(f["pieces"] or []),
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
            w = [[gcj2wgs(x, y)[0], gcj2wgs(x, y)[1]]
                 for x, y in poly.exterior.coords]
            tot += Polygon(w).area
        return round(tot * 111.32 ** 2 * 0.92, 2)

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
        self.compile(fence)
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
            ring = (g["coordinates"][0] if g["type"] == "Polygon"
                    else max(g["coordinates"], key=len)[0])
            nm = f"{name}" if len(geoms) == 1 else f"{name}-{n}"
            out.append(self.import_ring(nm, ring))
        if not out:
            raise ValueError("GeoJSON 中没有可用的 Polygon")
        return out

    # ---------- 编译/描述 ----------
    def compile(self, fence) -> dict:
        row = self.ds.compile_fence(
            {"area_id": fence["id"], "dealer": fence["name"],
             "rings": fence["rings"], "area_km2": fence["km2"]})
        fence["pieces"] = set(row["T"])
        fence["terms"] = row["human_terms"]
        fence["j"] = row["engine_J"]
        return {"fence": self.pub(fence), "row": row}

    def describe(self, name_substr) -> dict:
        f = self.find(name_substr)
        row = self.compile(f)["row"]
        return {"fence": self.pub(f), "terms": row["human_terms"],
                "j": row["engine_J"], "pieces": len(row["T"])}

    def pub(self, fence) -> dict:
        return {"id": fence["id"], "name": fence["name"], "rings": fence["rings"],
                "km2": fence["km2"], "terms": fence["terms"],
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

    # ---------- 3. 沿路拆分 ----------
    def split(self, name_substr, road, side) -> tuple[dict, dict]:
        f = self.find(name_substr)
        if not f["pieces"]:
            raise ValueError(f"「{f['name']}」不在单元库覆盖内（无片），无法按片拆分")
        line = road_line_gcj(self.ds, road)
        chosen, other = split_pieces_by_road(self.ds, f["pieces"], line, side)
        if not chosen or not other:
            raise ValueError(f"切分结果有一侧为空（整块都在一侧），无法拆分")
        self.fences.remove(f)
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
            row = self.ds.compile_fence(
                {"area_id": nf["id"], "dealer": nf["name"],
                 "rings": [nf["rings"][0]], "area_km2": nf["km2"]})
            nf["terms"] = row["human_terms"]
        self.fences += [f1, f2]
        self.save()
        return f1, f2

    # ---------- 4. 合并 ----------
    def merge(self, name_substrings) -> dict:
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
        for f in fs:
            self.fences.remove(f)
        merged = {"id": uuid.uuid4().hex[:8],
                  "name": "+".join(f["name"] for f in fs)[:24],
                  "rings": self._rings_of(geom), "pieces": pieces,
                  "terms": [], "km2": self._km2(self.ds, geom),
                  "color": fs[0]["color"]}
        row = self.ds.compile_fence(
            {"area_id": merged["id"], "dealer": merged["name"],
             "rings": [merged["rings"][0]], "area_km2": merged["km2"]})
        merged["terms"] = row["human_terms"]
        self.fences.append(merged)
        self.save()
        return merged

    # ---------- GeoJSON 导出 ----------
    def to_geojson(self, fence) -> dict:
        polys = ([{"type": "Polygon", "coordinates": [r]} for r in fence["rings"]])
        feats = [{"type": "Feature",
                  "properties": {"name": fence["name"], "km2": fence["km2"]},
                  "geometry": p} for p in polys]
        return {"type": "FeatureCollection", "features": feats}
