"""广州数据集冒烟测试：需要本机存在 Downloads 数据源，缺文件自动跳过。"""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.local_data

REPO = Path(__file__).resolve().parent.parent
GZ = Path(
    os.environ.get(
        "TIR_GZ_DATA",
        REPO.parent / "sales-resource-allocation-framework" / "data" / "gz",
    )
)
HOME = os.path.expanduser("~")
NEED = [
    GZ / "region.json",
    GZ / "gz_osm_full.json",
    Path(HOME)
    / "Downloads"
    / "边界数据-路网-到区县带海岸线-四级路网-广东省-广州市.geojson",
    Path(HOME) / "Downloads" / "区划数据-街道-广东省-广州市.geojson",
]


@pytest.fixture(scope="module")
def ds():
    if not all(p.exists() for p in NEED):
        pytest.skip("广州数据源不齐全，跳过")
    from territory_ir.dataset import Dataset

    return Dataset.guangzhou(data_dir=str(GZ))


def test_tessellation(ds):
    assert len(ds.U) > 5000
    assert len(ds.spoly_by_name) > 100
    assert "凤凰街道" in ds.spoly_by_name or len(ds.sname) > 0


def test_compile_and_replay(ds):
    fences = [
        f
        for f in ds.reg["fences"]
        if "佛山" not in f["dealer"] and "珠海" not in f["dealer"]
    ]
    assert fences
    row = ds.compile_fence(fences[0])
    assert row["engine_J"] >= 0.9, f"J={row['engine_J']}"
    assert len(row["S"]) == len(row["T"]) or row["engine_J"] > 0
    assert row["human_terms"]


def test_semantics(ds):
    from territory_ir import semantics

    areas = [s for s in ("联和街道", "凤凰街道") if s in ds.spoly_by_name]
    if not areas:
        pytest.skip("无匹配街道")
    pieces = semantics.ir_fence_from_semantics(ds, areas, {}, None)
    assert pieces, "语义构面返回空集"
