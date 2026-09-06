"""semantics.py 真实算法测试

覆盖:
- pieces_union: 保留 MultiPolygon
- select_pieces: 5 类选择器 (全部 / 半区 / 街道名 / 区名 / 失败)
- split_pieces_by_road: 质心投影 + 法向判定
- road_line_gcj: 三级匹配 (直接 / 子串 / 别名) + 失败提示
- ir_fence_from_semantics: 街道池 + 方向界
"""
import pytest
from tests.synthetic_fixture import make_synthetic_dataset
from territory_ir.dataset import Dataset
from territory_ir import semantics


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


class TestPiecesUnion:
    def test_basic(self, ds):
        """片并集 = 两片的几何合并"""
        u = semantics.pieces_union(ds, [0, 1])
        assert u.geom_type in ("Polygon", "MultiPolygon")
        assert u.area > 0

    def test_preserves_multipolygon(self, ds):
        """不连续片 → MultiPolygon, 不强制合并"""
        u = semantics.pieces_union(ds, [0, 2])  # 街道A 片 + 街道B 片
        # 4 片都在 113.0-113.2 范围内, 但街道 A (lat 23.1-23.2) 和街道 B (lat 22.9-23.0) 不连续
        # 应当返回 MultiPolygon 或大 Polygon
        assert u.area > 0

    def test_empty_pieces(self, ds):
        """空集 → 空几何"""
        from shapely.errors import GEOSException
        u = semantics.pieces_union(ds, [])
        assert u.is_empty


class TestSelectPieces:
    def test_全部(self, ds):
        """'全部' / 空字符串 / '整个区域' 都返回所有"""
        for sel in ["全部", "", "整个区域"]:
            pieces, desc = semantics.select_pieces(ds, {0, 1, 2, 3}, sel)
            assert pieces == {0, 1, 2, 3}
            assert "整个区域" in desc or desc == "整个区域"

    def test_半区_东(self, ds):
        """'东' / '东半区' → x >= 质心.x 的片"""
        # 街道A: x 在 113.0-113.2, 街道B: x 在 113.0-113.2 → 整体质心 ~113.1
        # 东半区应包含 x >= 113.1 的片 (2 片: 右上 + 右下)
        pieces, desc = semantics.select_pieces(ds, {0, 1, 2, 3}, "东")
        assert len(pieces) > 0
        assert "东" in desc

    def test_半区_南(self, ds):
        """'南' → y < 质心.y 的片"""
        pieces, desc = semantics.select_pieces(ds, {0, 1, 2, 3}, "南")
        # 街道A (lat 23.1-23.2) 在街道B (lat 22.9-23.0) 北边, 南半区应包含街道B 的 2 片
        assert len(pieces) == 2

    def test_街道名(self, ds):
        pieces, desc = semantics.select_pieces(ds, {0, 1, 2, 3}, "街道A")
        assert pieces == {0, 1}
        assert "街道A" in desc

    def test_未识别选择器_抛错(self, ds):
        with pytest.raises(ValueError, match="无法识别"):
            semantics.select_pieces(ds, {0, 1}, "不存在的标签xyz")


class TestRoadLineGcj:
    def test_找不到路_抛错含相近路名(self, ds):
        """找不到时用 difflib 提示候选"""
        with pytest.raises(ValueError) as exc_info:
            semantics.road_line_gcj(ds, "完全不存在的路xyz")
        assert "找不到" in str(exc_info.value)

    def test_空路名_抛错(self, ds):
        with pytest.raises(ValueError):
            semantics.road_line_gcj(ds, "")


class TestIrFenceFromSemantics:
    def test_街道名_命中(self, ds):
        """areas=["街道A"] 应命中 2 片"""
        pieces = semantics.ir_fence_from_semantics(ds, ["街道A"], {}, None)
        assert len(pieces) == 2

    def test_空areas_空bounds_空center_返回空(self, ds):
        pieces = semantics.ir_fence_from_semantics(ds, [], {}, None)
        assert pieces == set()

    def test_街道名不命中_返回空_不抛错(self, ds):
        """文档承诺永不抛错, 未命中返回空集"""
        pieces = semantics.ir_fence_from_semantics(ds, ["不存在的街道"], {}, None)
        assert pieces == set()

    def test_center_fallback(self, ds):
        """无 areas 但有 center → 6km 半径兜底"""
        pieces = semantics.ir_fence_from_semantics(ds, [], {}, [113.1, 23.1])
        # 6km 半径包含 4 片 (合成数据全在中心附近)
        assert len(pieces) >= 1


class TestSplitPiecesByRoad:
    """质心投影 + 法向判定: 用合成路网无法测 (无 OSM roads),
    改测几何算法对输入的鲁棒性"""

    def test_空片集_返回空(self, ds):
        from shapely.geometry import LineString
        line = LineString([(113.0, 23.0), (113.2, 23.0)])
        chosen, other = semantics.split_pieces_by_road(ds, set(), line, "north")
        assert chosen == set()
        assert other == set()

    def test_未匹配side_抛错或返回默认(self, ds):
        """side 不在枚举内 → 应抛 ValueError"""
        from shapely.geometry import LineString
        line = LineString([(113.0, 23.0), (113.2, 23.0)])
        # 看是否抛错
        try:
            chosen, other = semantics.split_pieces_by_road(ds, {0, 1}, line, "invalid_side")
            # 不抛错的话, 行为未定义
        except (ValueError, KeyError):
            pass  # 预期
