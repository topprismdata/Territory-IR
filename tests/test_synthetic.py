"""合成数据集测试:用 synthetic_fixture.py 构造的 4 片/2 街道小数据集

可在 CI 跑通,无需业务方私有数据。验证:
- Dataset 加载合成 GeoJSON 不抛错
- U 铺盖构造正确(预期 4 片)
- compile_fence 输出 J=1.0(完美保真)
- 条款回放 vs 真值片一致
"""
import json
from pathlib import Path

import pytest

from tests.synthetic_fixture import make_synthetic_dataset
from territory_ir.dataset import Dataset


@pytest.fixture
def ds(tmp_path):
    data_dir = make_synthetic_dataset(tmp_path)
    return Dataset(
        data_dir=str(data_dir),
        roadnet_path=str(data_dir / "roadnet.geojson"),
        streets_path=str(data_dir / "streets.geojson"),
        osm_path=str(data_dir / "osm.json"),
        name="synthetic",
    )


class TestDatasetConstruction:
    def test_parents_loaded(self, ds):
        assert len(ds.parents) == 4

    def test_tessellation_count(self, ds):
        """4 父地块 × 2 街道面 = 4 片(每块被一个街道完全覆盖,无切分)"""
        assert len(ds.U) == 4

    def test_street_names_present(self, ds):
        assert "街道A" in ds.spoly_by_name
        assert "街道B" in ds.spoly_by_name
        assert len(ds.spoly_by_name) == 2

    def test_pieces_have_street_labels(self, ds):
        """每片必须有主街道标签"""
        for k in range(len(ds.U)):
            geom, main_st, within_st, parent_idx = ds.U[k]
            assert main_st in ("街道A", "街道B")
            assert within_st in ("街道A", "街道B")


class TestCompileFence:
    """合成围栏A(右上象限)的编译应产出 J=1.0"""

    def test_compile_returns_valid_row(self, ds):
        fence = ds.reg["fences"][0]
        row = ds.compile_fence(fence)
        assert row["T"], "真值片不应为空"
        assert row["S"], "条款回放片不应为空"
        assert row["human_terms"], "人话描述不应为空"

    def test_j_perfect(self, ds):
        fence = ds.reg["fences"][0]
        row = ds.compile_fence(fence)
        # 合成数据片粒度刚好等于围栏 = 完美对齐
        assert row["engine_J"] == 1.0, f"合成数据 J 应=1.0, 实际={row['engine_J']}"

    def test_truth_pieces_subset(self, ds):
        """围栏A 覆盖右上象限,完整包含的父地块仅右上 1 片"""
        fence = ds.reg["fences"][0]
        row = ds.compile_fence(fence)
        T = set(row["T"])
        assert len(T) == 1, f"真值片应=1(右上), 实际={len(T)}"

    def test_replay_matches_truth(self, ds):
        """S 应等于 T(完美回放)"""
        fence = ds.reg["fences"][0]
        row = ds.compile_fence(fence)
        assert set(row["S"]) == set(row["T"])


class TestClauseVocabulary:
    def test_block_clause(self, ds):
        """block 条款按街道全选片"""
        ds.vocab()  # 构建
        clause = {"type": "block", "street": "街道A"}
        pieces = ds.clause_pieces(clause)
        assert len(pieces) == 2  # 街道A 覆盖 2 片

    def test_pieces_clause(self, ds):
        clause = {"type": "pieces", "ids": [0, 1]}
        pieces = ds.clause_pieces(clause)
        assert pieces == {0, 1}


class TestSyntheticRoadsAndFences:
    def test_roads_loaded(self, ds):
        assert len(ds.feat_names) >= 3
        assert "横向大道" in ds.feat_names
        assert "纵向大道" in ds.feat_names

    def test_multiple_fences_available(self, ds):
        fences = ds.reg["fences"]
        assert len(fences) >= 2
        names = [f["dealer"] for f in fences]
        assert "测试经销商A" in names
        assert "测试经销商B" in names

    def test_road_line_lookup(self, ds):
        from territory_ir.semantics import road_line_gcj
        line = road_line_gcj(ds, "横向大道")
        assert not line.is_empty
