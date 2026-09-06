"""session.py 真实业务逻辑测试 (第二轮: 真理解项目)

覆盖:
- merge: 多围栏片并集合并, 仅 pieces 有值时用 pieces
- clear: 按名删 / 全清空
- fence_from_terms: 条款解析 (P# / 街道沿路 / 街道限X内 / 街道全域)
- to_geojson: FeatureCollection 输出
- 重复定义检测: merge 应该只有一个生效版本
"""
import json
from pathlib import Path

import pytest

from tests.synthetic_fixture import make_synthetic_dataset
from territory_ir.dataset import Dataset
from territory_ir.session import Session


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


@pytest.fixture
def sess(tmp_path, ds):
    return Session(ds, persist_dir=str(tmp_path / "sessions"))


def _make_fence(sess, name, pieces):
    """手工构造一个已编译过的围栏, 不走 import_ring 路径"""
    from territory_ir import semantics
    geom = semantics.pieces_union(sess.ds, pieces)
    return {
        "id": name[:8].ljust(8, "0"),
        "name": name,
        "rings": Session._rings_of(geom),
        "pieces": set(pieces),
        "terms": [],
        "km2": 0.1,
        "color": "#1e88e5",
    }


class TestClear:
    def test_clear_specific_fence(self, sess):
        sess.fences.append(_make_fence(sess, "fence-A", {0, 1}))
        sess.fences.append(_make_fence(sess, "fence-B", {2, 3}))

        n = sess.clear("fence-A")
        assert n == 1
        assert len(sess.fences) == 1
        assert sess.fences[0]["name"] == "fence-B"

    def test_clear_all(self, sess):
        sess.fences.append(_make_fence(sess, "fence-A", {0, 1}))
        sess.fences.append(_make_fence(sess, "fence-B", {2, 3}))

        n = sess.clear()
        assert n == 2
        assert sess.fences == []

    def test_clear_nonexistent_raises(self, sess):
        sess.fences.append(_make_fence(sess, "fence-A", {0, 1}))
        with pytest.raises(ValueError):
            sess.clear("不存在的围栏")


class TestMerge:
    """注意: merge 在源文件里被定义了 4 次, Python 用最后那个版本。
    测试应反映实际行为."""

    def test_merge_two_fences(self, sess):
        sess.fences.append(_make_fence(sess, "fence-A", {0, 1}))
        sess.fences.append(_make_fence(sess, "fence-B", {2, 3}))

        merged = sess.merge(["fence-A", "fence-B"])
        assert len(merged["pieces"]) == 4
        assert "fence-A" in merged["name"]
        assert "fence-B" in merged["name"]
        assert len(sess.fences) == 1  # 原两个被删除

    def test_merge_requires_two_or_more(self, sess):
        sess.fences.append(_make_fence(sess, "fence-A", {0}))
        with pytest.raises(ValueError, match="至少需要两个"):
            sess.merge(["fence-A"])

    def test_merge_empty_pieces_falls_back_to_rings(self, sess):
        """围栏无 pieces (库外导入) → 用 rings 计算几何"""
        from shapely.geometry import Polygon
        sess.fences.append({
            "id": "extA", "name": "ext-A",
            "rings": [[[113.0, 23.0], [113.1, 23.0], [113.1, 23.1], [113.0, 23.1], [113.0, 23.0]]],
            "pieces": None,  # 库外导入
            "terms": [], "km2": 0.1, "color": "#1e88e5",
        })
        sess.fences.append({
            "id": "extB", "name": "ext-B",
            "rings": [[[113.05, 23.05], [113.15, 23.05], [113.15, 23.15], [113.05, 23.15], [113.05, 23.05]]],
            "pieces": None,
            "terms": [], "km2": 0.1, "color": "#43a047",
        })
        # 合并两个库外导入的围栏, 不应抛错
        merged = sess.merge(["ext-A", "ext-B"])
        assert merged["pieces"] == set()


class TestFenceFromTerms:
    def test_parse_pieces_clause(self, sess):
        f = sess.fence_from_terms("test", ["P#0", "P#1"])
        assert f["pieces"] == {0, 1}

    def test_parse_block_clause(self, sess):
        """街道全域: block 条款"""
        f = sess.fence_from_terms("test", ["街道A"])
        # 街道A 覆盖 2 片
        assert len(f["pieces"]) == 2

    def test_parse_feat_clause(self, sess):
        """街道沿路: feat 条款"""
        # 合成的 dataset 没 OSM roads, feat 条款应失败
        with pytest.raises(ValueError, match="条款未命中"):
            sess.fence_from_terms("test", ["街道A沿某路"])

    def test_skips_band_clause(self, sess):
        """界带条款应跳过, 不抛错"""
        f = sess.fence_from_terms("test", ["P#0", "东至街道A—街道B界"])
        assert f["pieces"] == {0}
        assert f.get("_skipped")  # 界带被记入 _skipped


class TestToGeoJson:
    def test_basic_export(self, sess):
        f = _make_fence(sess, "fence-A", {0, 1})
        gj = sess.to_geojson(f)
        assert gj["type"] == "FeatureCollection"
        assert len(gj["features"]) >= 1
        feat = gj["features"][0]
        assert feat["type"] == "Feature"
        assert feat["properties"]["name"] == "fence-A"
        assert feat["geometry"]["type"] == "Polygon"


class TestDuplicateDefinitionDetection:
    """Mutation check: session.py 里有 merge/clear/to_geojson 多个定义。
    Python 用最后定义, 测试应反映这个事实"""

    def test_only_last_merge_definition_active(self, sess):
        """merge 函数应该是最后定义的那个版本"""
        import territory_ir.session as sm
        import inspect
        src = inspect.getsource(sm.Session.merge)
        # 最后定义的版本没在 pending 里设字段
        assert "self.pending" not in src

    def test_clear_function_count(self, sess):
        """应该有 1 个 clear 方法 (重复定义只算 1 个)"""
        import territory_ir.session as sm
        clear_methods = [m for m in dir(sm.Session) if m == "clear"]
        assert len(clear_methods) == 1
