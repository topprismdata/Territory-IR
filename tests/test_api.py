"""WP12 Layer API：行为契约 + 合成金标（golden 哈希冻结）。

金标纪律：合成数据集上的 IR 输出（片集合/条款/J）逐位冻结——
改动语义必过金标，改坏了必红（与 coords-core 金标同模式）。
"""

import hashlib
import json

import pytest

from territory_ir.api import TerritoryAPI
from territory_ir.dataset import Dataset
from tests.synthetic_fixture import make_synthetic_dataset

RING_A = [
    [113.1, 23.0],
    [113.2, 23.0],
    [113.2, 23.2],
    [113.1, 23.2],
    [113.1, 23.0],
]  # 右上块
RING_LEFT = [
    [113.0, 23.0],
    [113.1, 23.0],
    [113.1, 23.2],
    [113.0, 23.2],
    [113.0, 23.0],
]  # 左上块


@pytest.fixture
def api(tmp_path):
    d = make_synthetic_dataset(tmp_path)
    ds = Dataset(
        data_dir=str(d),
        roadnet_path=str(d / "roadnet.geojson"),
        streets_path=str(d / "streets.geojson"),
        osm_path=str(d / "osm.json"),
        name="synthetic",
    )
    return TerritoryAPI(ds)


def _ir_digest(ir: dict) -> str:
    core = {
        "pieces": sorted(ir["pieces"]),
        "terms": ir["terms"],
        "engine_terms": ir.get("engine_terms", []),
        "j": ir.get("j"),
    }
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def test_compile_返回完整IR(api):
    ir = api.compile("右上", RING_A)
    assert ir["name"] == "右上"
    assert ir["pieces"] and ir["terms"]
    assert ir["km2"] > 0


def test_golden_合成右上块逐位冻结(api):
    """金标：右上块 = 2 个父地块（右上 2 象限片），条款含街道名。"""
    ir = api.compile("右上", RING_A)
    assert _ir_digest(ir) == "39a89ddc726fa76c", _ir_digest(ir)  # 首跑回填


def test_render_是terms投影且纯函数(api):
    ir = api.compile("右上", RING_A)
    assert api.render(ir) == list(ir["terms"])
    assert api.render(ir) is not ir["terms"]  # 不泄漏内部列表


def test_fence_from_text_确定性构建(api):
    ir = api.fence_from_text("左上", ["街道A"], {})
    assert ir["pieces"]
    # 确定性：两次调用片集一致
    ir2 = api.fence_from_text("左上2", ["街道A"], {})
    assert set(ir["pieces"]) == set(ir2["pieces"])


def test_validate_正常环(api):
    rep = api.validate(RING_A)
    assert rep.ok and not rep.errors


def test_validate_自交为error(api):
    bowtie = [
        [113.1, 23.0],
        [113.2, 23.1],
        [113.1, 23.1],
        [113.2, 23.0],
        [113.1, 23.0],
    ]
    rep = api.validate(bowtie)
    assert not rep.ok
    assert any(i.code == "SELF_INTERSECT" for i in rep.errors)


def test_validate_空环与退化(api):
    assert api.validate([]).errors[0].code == "EMPTY_RING"
    flat = [[113.1, 23.0], [113.15, 23.0], [113.2, 23.0], [113.1, 23.0]]
    rep = api.validate(flat)
    assert any(i.code in ("DEGENERATE", "NO_COVERAGE") for i in rep.errors)


def test_roundtrip_条款闭环J一致(api):
    """roundtrip 判据=片集合恒等（论文 J/43-43 口径）。

    iou 是重解析几何 vs 原环的参考量（吸附到片并集后允许 <1，
    编译保真 0.99 是另一指标，不在本判据内）。"""
    rt = api.roundtrip("右上", RING_A)
    assert rt.terms
    assert rt.passed  # j_exact 且无 error
    assert 0.0 < rt.iou <= 1.0  # 参考量存在且合法


def test_roundtrip_自交环给error(api):
    bowtie = [
        [113.1, 23.0],
        [113.2, 23.1],
        [113.1, 23.1],
        [113.2, 23.0],
        [113.1, 23.0],
    ]
    rt = api.roundtrip("坏环", bowtie)
    assert not rt.passed
