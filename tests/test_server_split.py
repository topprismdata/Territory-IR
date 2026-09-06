"""A1 回归：Copilot 沿路切分的预览/提交接线（issue #4 Critical 项）。

历史缺陷：chat() 调用不存在的 Session.split → UI 一点切分必抛 AttributeError；
apply() 只追加子围栏不移除父围栏 → 区域重复。修复后走 split_preview/split_commit。

需要本机存在广州数据源（同 test_gz_smoke），缺数据自动跳过。
"""
import os
import tempfile
from pathlib import Path

import pytest

from server import Copilot

REPO = Path(__file__).resolve().parent.parent
GZ = Path(os.environ.get("TIR_GZ_DATA",
                         REPO.parent / "sales-resource-allocation-framework" / "data" / "gz"))
HOME = os.path.expanduser("~")
NEED = [GZ / "region.json", GZ / "gz_osm_full.json",
        Path(HOME) / "Downloads" / "边界数据-路网-到区县带海岸线-四级路网-广东省-广州市.geojson",
        Path(HOME) / "Downloads" / "区划数据-街道-广东省-广州市.geojson"]

# 天河中心一个横跨多条主干道的围栏，保证存在可切分的路
RING = [[113.30, 23.10], [113.36, 23.10], [113.36, 23.15], [113.30, 23.15]]
NAME = "测试围栏"


@pytest.fixture(scope="module")
def cp():
    if not all(p.exists() for p in NEED):
        pytest.skip("广州数据源不齐全，跳过")
    with tempfile.TemporaryDirectory() as td:
        c = Copilot(GZ, persist_dir=Path(td) / "sess")   # 隔离会话，不碰 sessions/
        c.sess.import_ring(NAME, RING)
        yield c


def test_split_wiring(cp):
    """split 预览：不再 AttributeError，产出预览与 pending。"""
    # 候选路：取与围栏相交的地物名（与 split_preview 内部兜底同源），
    # 逐个尝试直到切开——不假设某条具体路一定分得开。
    from shapely.geometry import Polygon
    fp = Polygon(RING)
    cands = [nm for j, nm in enumerate(cp.ds.feat_names)
             if cp.ds.feat_geoms[j].intersects(fp)]
    assert cands, "围栏未贴附任何地物，测试环境异常"
    reply = None
    for nm in sorted(set(cands)):
        r = cp.chat(f"把 {NAME} 沿{nm}分开")
        if "切分预览" in r["reply"]:
            reply = r
            break
    assert reply is not None, f"候选路都切不开围栏: {sorted(set(cands))}"
    assert cp.pending and cp.pending["kind"] == "split"
    assert reply["pending"] and len(reply["pending"]["result"]) == 2


def test_split_apply_removes_parent(cp):
    """split 提交：父围栏对象被移除，保留侧子围栏继承父名（净 +1）。"""
    parent = cp.sess.find_exact(NAME)
    pid = parent["id"]
    before = len(cp.sess.fences)
    r = cp.apply()
    assert "已应用" in r["reply"]
    assert len(cp.sess.fences) == before + 1
    assert not any(f["id"] == pid for f in cp.sess.fences), \
        "父围栏对象未被移除——apply 只追加子围栏会造成区域重复"
    assert sum(f["name"] == NAME for f in cp.sess.fences) == 1, \
        "保留侧子围栏应恰好继承一次父名"


def test_merge_wiring(cp):
    """merge 预览/提交走 merge_preview/merge_commit（零副作用协议）。"""
    kids = [f["name"] for f in cp.sess.fences if f["name"].startswith(NAME)]
    assert len(kids) >= 2
    r = cp.chat(f"把 {kids[0]} 和 {kids[1]} 合并")
    assert "合并预览" in r["reply"]
    before = len(cp.sess.fences)
    r2 = cp.apply()
    assert "已应用" in r2["reply"]
    assert len(cp.sess.fences) == before - 1
