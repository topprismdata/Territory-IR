"""重演与语义构面：片集合 ⇄ 几何；自然语言语义 → 片集合。

★ 核心不变量：split_pieces_by_road 等全部分堆/判侧操作只改变片归属，
  永不切割片几何（路仅作判侧依据）。
"""
from __future__ import annotations

from collections import Counter

from shapely.geometry import Point
from shapely.ops import unary_union

from .coords import wgs2gcj
from .dataset import Dataset

_SIDE_MAP = {"west": "西", "east": "东", "south": "南", "north": "北"}
_DIR_SIDE = {"北": "south", "南": "north", "西": "east", "东": "west"}


def pieces_union(ds: Dataset, pieces) -> "Polygon | MultiPolygon":
    """S 片并集（保留 MultiPolygon——不连续领地不能截成最大块）。"""
    geoms = [ds.U[k][0] for k in sorted(pieces)]
    return unary_union(geoms)


def osm_catalog(ds: Dataset) -> dict:
    """地物/街道面 → osm_parsed 兼容目录（LLM 语义与 lookup 用）。

    roads 值取自 OSM 地物（WGS）；districts = 街道面（GCJ）。"""
    roads = {}
    for i, nm in enumerate(ds.feat_names):
        if nm not in roads:
            seg = [[round(x, 6), round(y, 6)]
                   for x, y in ds.feat_geoms[i].coords][:64]
            if len(seg) >= 2:
                roads.setdefault(nm, [seg])
    districts = {}
    for nm, g in ds.spoly_by_name.items():
        try:
            ring = [[round(x, 6), round(y, 6)] for x, y in g.exterior.coords]
            districts[nm] = {"polys": [ring]}
        except Exception:  # noqa: BLE001
            pass
    return {"roads": roads, "rivers": {}, "refs": {}, "districts": districts}


def _norm_name(s: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(s).lower())


_line_cache: dict = {}


def road_line_gcj(ds: Dataset, name: str):
    """OSM 地物(WGS) → GCJ 折线集（不做 union，project 直接支持）。

    名称匹配大小写/分隔符不敏感 + 编号别名；进程级缓存。"""
    key = _norm_name(name)
    if key in _line_cache:
        return _line_cache[key]
    from shapely.geometry import LineString
    from shapely import ops as _ops

    norm = _norm_name(name)

    # ① refs：国道/省道编号（WGS）
    for ref, segs in getattr(ds, "osm_refs", {}).items():
        if norm == _norm_name(ref):
            lines = [LineString(seg) for seg in segs if len(seg) >= 2]
            line = unary_union(lines)
            break
    else:
        # ② 地物名子串（WGS）
        matched = [g for g, n in zip(ds.feat_geoms, ds.feat_names)
                   if norm and norm in _norm_name(n)]
        if not matched:
            # ③ 别名映射（G324→广汕公路 等）
            resolved = getattr(ds, "road_aliases", {}).get(norm)
            if resolved:
                matched = [g for g, n in zip(ds.feat_geoms, ds.feat_names)
                           if _norm_name(resolved) in _norm_name(n)]
        if not matched:
            import difflib
            cands = sorted({n for n in ds.feat_names if n},
                           key=lambda n: -difflib.SequenceMatcher(
                               None, norm, _norm_name(n)).ratio())[:5]
            raise ValueError(f"路网中找不到「{name}」。相近路名：{'、'.join(cands)}")
        line = unary_union(matched)

    line = _ops.transform(lambda x, y: tuple(wgs2gcj(x, y)), line)
    _line_cache[key] = line
    return line


def split_pieces_by_road(ds: Dataset, pieces, line, side: str) -> tuple[set, set]:
    """按路的方位把片集合分两堆（片原子，不做几何切割）。

    每片取质心，找最近路段方向向量 d，法向统一指向 side 一侧，
    dot(质心-最近点, n) > 0 即命中。"""
    segs = (list(line.geoms) if line.geom_type in
            ("MultiLineString", "MultiPolygon") else [line])
    chosen, other = set(), set()
    for k in pieces:
        c = ds.U[k][0].centroid
        best_d = 1e18
        best_p = None
        best_dv = None
        for seg in segs:
            if seg.distance(c) >= best_d:
                continue
            coords = list(seg.coords)
            for a, b in zip(coords, coords[1:]):
                ax, ay = a
                bx, by = b
                ex, ey = bx - ax, by - ay
                L2 = ex * ex + ey * ey
                if L2 <= 0:
                    continue
                t = max(0.0, min(1.0, ((c.x - ax) * ex + (c.y - ay) * ey) / L2))
                px, py = ax + t * ex, ay + t * ey
                d2 = (c.x - px) ** 2 + (c.y - py) ** 2
                if d2 < best_d:
                    best_d = d2
                    best_p = (px, py)
                    best_dv = (ex, ey)
        if best_p is None:
            other.add(k)
            continue
        dx, dy = best_dv
        L = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx, ny = -dy / L, dx / L
        if (side == "west" and nx > 0) or (side == "east" and nx < 0):
            nx, ny = -nx, -ny
        if (side == "south" and ny > 0) or (side == "north" and ny < 0):
            nx, ny = -nx, -ny
        hit = (c.x - best_p[0]) * nx + (c.y - best_p[1]) * ny > 0
        (chosen if hit else other).add(k)
    return chosen, other


def select_pieces(ds: Dataset, pieces, selector: str) -> tuple[set, str]:
    """在给定片集合内按选择器分堆：全部/东南西北半区/街道名/区名。

    返回 (命中片集合, 语义名)；选择器不识别时抛 ValueError。"""
    allp = set(pieces)
    sel = (selector or "全部").strip()
    if sel in ("全部", "整体", "所有", "", "不做了", "退出", "整个区域", "整个"):
        return allp, "整个区域"
    half = {"东": "east", "南": "south", "西": "west", "北": "north",
            "东边": "east", "南边": "south", "西边": "west", "北边": "north",
            "东部": "east", "南部": "south", "西部": "west", "北部": "north",
            "东侧": "east", "南侧": "south", "西侧": "west", "北侧": "north",
            "东半区": "east", "南半区": "south", "西半区": "west",
            "北半区": "north"}.get(sel)
    if half:
        fp = pieces_union(ds, allp)
        c = fp.centroid
        picked = set()
        for k in allp:
            pc = ds.U[k][0].centroid
            if half == "east" and pc.x >= c.x:
                picked.add(k)
            elif half == "west" and pc.x < c.x:
                picked.add(k)
            elif half == "north" and pc.y >= c.y:
                picked.add(k)
            elif half == "south" and pc.y < c.y:
                picked.add(k)
        if not picked:
            raise ValueError(f"「{sel}」没有命中任何单元片")
        return picked, f"{sel[:1]}部半区"
    hit_street = {k for k in allp
                  if ds.U[k][1] == sel or ds.U[k][2] == sel}
    if hit_street:
        return hit_street, f"{sel}片区"
    sd = street_district_map(ds)
    streets = [st for st, d in sd.items() if d == sel or d == sel.replace("区", "")]
    if streets:
        ss = set(streets)
        hit = {k for k in allp if ds.U[k][1] in ss or ds.U[k][2] in ss}
        if hit:
            return hit, f"{sel}片区"
    raise ValueError(
        f"无法识别片区「{sel}」。可用：整个区域 / 东南西北半区 / 街道名 / 区名")


def street_district_map(ds: Dataset) -> dict:
    """street → district（单元属性众数）。"""
    m = {}
    path = ds.data_dir / "unit_attributes.json"
    if path.exists():
        import json
        attrs = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(attrs, dict):
            attrs = attrs.get("units", [])
        cnt = {}
        for a in attrs:
            if isinstance(a, dict) and a.get("street") and a.get("district"):
                cnt.setdefault(a["street"], Counter())[a["district"]] += 1
        m = {k: v.most_common(1)[0][0] for k, v in cnt.items()}
    return m


def ir_fence_from_semantics(ds: Dataset, areas: list, bounds: dict,
                            center) -> set:
    """自然语言语义结构 → IR 片集合（新建合同构面的 IR 路径）。

    areas: 街道/区名列表；bounds: {"北": "路名"}（北界=片在路南）；
    center: 无 areas 时的 6km 半径兜底。空集 = 语义未命中单元库。"""
    sd = street_district_map(ds)
    base: set = set()
    for a in areas or []:
        a = str(a).strip()
        base |= {k for k in range(len(ds.U))
                 if ds.U[k][1] == a or ds.U[k][2] == a
                 or sd.get(ds.U[k][1], "") == a
                 or sd.get(ds.U[k][2], "") == a}
    if not base and center:
        c = Point(float(center[0]), float(center[1]))
        base = {k for k in range(len(ds.U))
                if ds.U[k][0].distance(c) <= 0.06}  # ≈6km
    for d, nm in (bounds or {}).items():
        side = _DIR_SIDE.get(str(d)[:1])
        if not side:
            continue
        try:
            line = road_line_gcj(ds, str(nm))
        except ValueError:
            continue
        chosen, _ = split_pieces_by_road(ds, base, line, side)
        if chosen:
            base = chosen
    return base
