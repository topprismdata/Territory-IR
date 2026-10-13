"""WP12 Layer API：类型化纯函数入口（无 HTTP、无 LLM、无持久会话）。

面向集成方（SRP 后端 / SRAF 引擎 / module2-e2e）的稳定门面：
    api = TerritoryAPI(ds)
    ir   = api.compile(name, ring)          # 几何 → IR（片集合+条款+J/IoU）
    text = api.render(ir)                    # IR → 人话条款
    ir2  = api.fence_from_text(...)          # 结构化语义 → IR
    rep  = api.validate(ring)                # 连续性/自交/空集/覆盖体检
    rt   = api.roundtrip(name, ring)         # 编译→渲染→重解析 闭环一致性

纪律：本模块只做编排与类型收口；几何/语义算法一律走 dataset/session/semantics。
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from typing import Any

from .dataset import Dataset
from .session import Session


@dataclass(frozen=True)
class Issue:
    code: str  # SELF_INTERSECT | EMPTY_RING | DISCONTINUOUS | NO_COVERAGE | DEGENERATE
    severity: str  # "error" | "warning"
    message: str


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[Issue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity == "warning")


@dataclass(frozen=True)
class RoundtripResult:
    iou: float  # 重解析几何 vs 原几何
    j_exact: bool  # 片集合恒等（T == S'）
    terms: list  # 渲染出的人话条款
    issues: tuple[Issue, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return self.j_exact and not self.issues


def _poly(ring: list):
    from shapely.geometry import Polygon

    return Polygon(ring)


def _ir_of(sess: Session, res: dict) -> dict[str, Any]:
    """pub 投影 + 原始片集（pub 只给计数，IR 必须携带片集合与 J）。"""
    pub = dict(res["fence"])
    row = res["row"]
    pub["pieces"] = sorted(row["T"])
    pub["j"] = row.get("engine_J")
    return pub


class TerritoryAPI:
    """一个 Dataset 一个门面；每次调用内部用一次性 Session（不落盘）。"""

    def __init__(self, ds: Dataset):
        self.ds = ds

    # ---------- 编译与渲染 ----------
    def compile(self, name: str, ring: list[list[float]]) -> dict[str, Any]:
        """几何 → IR。返回 {name, rings, pieces, terms, engine_terms, j, km2}。"""
        with tempfile.TemporaryDirectory() as td:
            sess = Session(self.ds, persist_dir=td)
            fence = sess.import_ring(name, ring)
            return _ir_of(sess, sess.compile(fence))

    def render(self, ir: dict[str, Any]) -> list:
        """IR → 人话条款列表（compile 的 terms 投影；纯函数）。"""
        return list(ir.get("terms") or [])

    def fence_from_text(self, name: str, areas: list, bounds: dict) -> dict[str, Any]:
        """结构化语义（街道 areas + 方向界 bounds）→ IR。确定性，无 LLM。"""
        with tempfile.TemporaryDirectory() as td:
            sess = Session(self.ds, persist_dir=td)
            fence = sess.fence_from_text(name, areas, bounds)
            return _ir_of(sess, sess.compile(fence))

    # ---------- 体检 ----------
    def validate(self, ring: list[list[float]]) -> ValidationReport:
        """围栏几何体检：自交/退化/空 → error；不连续（MultiPolygon）→ warning。"""
        issues: list[Issue] = []
        if not ring or len(ring) < 4:
            return ValidationReport((Issue("EMPTY_RING", "error", "环点数不足 4"),))
        p = _poly(ring)
        if not p.is_valid:
            issues.append(Issue("SELF_INTERSECT", "error", "多边形自交或非法"))
            p = p.buffer(0)
        if p.is_empty or p.area <= 0:
            issues.append(Issue("DEGENERATE", "error", "面积为零/退化几何"))
            return ValidationReport(tuple(issues))
        if p.geom_type == "MultiPolygon":
            issues.append(
                Issue(
                    "DISCONTINUOUS",
                    "warning",
                    f"不连续：{len(p.geoms)} 块（多连通片区须显式声明）",
                )
            )
        # 覆盖体检：IR 片集合非空
        try:
            ir = self.compile("validate-probe", ring)
            if not ir.get("pieces"):
                issues.append(Issue("NO_COVERAGE", "error", "单元库无覆盖片"))
        except Exception as e:  # noqa: BLE001
            issues.append(Issue("NO_COVERAGE", "error", f"编译失败：{e}"))
        return ValidationReport(tuple(issues))

    # ---------- 闭环一致性 ----------
    def roundtrip(self, name: str, ring: list[list[float]]) -> RoundtripResult:
        """compile → terms → fence_from_terms → S' 与 T 对比（论文 J/IoU 口径）。

        条款含「界/沿…(限…内)」等无独立片集类型时由 fence_from_terms 跳过，
        此时 J 允许 False 并给出 warning（与论文 42/43 口径一致）。"""
        ir = self.compile(name, ring)
        terms = self.render(ir)
        with tempfile.TemporaryDirectory() as td:
            sess = Session(self.ds, persist_dir=td)
            try:
                f2 = sess.fence_from_terms(name, terms)
            except ValueError as e:
                return RoundtripResult(
                    iou=0.0,
                    j_exact=False,
                    terms=terms,
                    issues=(Issue("NO_COVERAGE", "error", f"条款重解析失败：{e}"),),
                )
            out = _ir_of(sess, sess.compile(f2))
        t0 = set(ir["pieces"])
        t1 = set(out["pieces"])
        a, b = _poly(ir["rings"][0]), _poly(out["rings"][0])
        union = a.union(b).area
        iou = (a.intersection(b).area / union) if union > 0 else 0.0
        issues: list[Issue] = []
        if t0 != t1:
            issues.append(
                Issue(
                    "DISCONTINUOUS",
                    "warning",
                    f"片集差异：丢 {sorted(t0 - t1)} / 增 {sorted(t1 - t0)}",
                )
            )
        return RoundtripResult(
            iou=iou, j_exact=t0 == t1, terms=terms, issues=tuple(issues)
        )
