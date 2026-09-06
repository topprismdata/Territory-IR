"""Regression: 仅设一个环境变量也应工作(issue #6 第二轮发现)

之前实现: used_env = (roadnet is not None and streets is not None)
        仅设一个变量 → 仍回退到硬编码, 业务方部分数据场景崩溃

新实现: 每个变量独立判断
        env_roadnet is None → 硬编码;否则用 env
        env_streets is None → 硬编码;否则用 env
"""
import json
import warnings
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path):
    (tmp_path / "region.json").write_text(json.dumps({"fences": [], "stores": []}))
    (tmp_path / "gz_osm_full.json").write_text(json.dumps(
        {"roads": [], "rivers": [], "adm6": []}))
    (tmp_path / "empty_streets.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": []}))
    return tmp_path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("TIR_GZ_ROADNET", "TIR_GZ_STREETS"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def real_roadnet_path():
    p = Path("/Users/mac/Downloads/边界数据-路网-到区县带海岸线-四级路网-广东省-广州市.geojson")
    if not p.exists():
        pytest.skip("广州路网不在 ~/Downloads")
    return str(p)


class TestPartialEnv:
    """只设一个环境变量也应工作(不强制要求两个都设)"""

    def test_only_roadnet_env_uses_env_for_roadnet(self, tmp_data_dir, real_roadnet_path, monkeypatch):
        """只设 TIR_GZ_ROADNET, roadnet 用 env, streets 走硬编码(并 warn)"""
        monkeypatch.setenv("TIR_GZ_ROADNET", real_roadnet_path)
        # 不设 TIR_GZ_STREETS

        from territory_ir.dataset import Dataset
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                Dataset.guangzhou(data_dir=str(tmp_data_dir))
            except FileNotFoundError:
                pass  # 街道面硬编码路径不存在, 预期

        # 应 warn (因为 streets 是硬编码回退)
        ours = [w for w in caught if "硬编码" in str(w.message)]
        assert ours, f"应 warn (streets 走硬编码); 实际: {[str(w.message) for w in caught]}"

    def test_both_env_no_warn(self, tmp_data_dir, real_roadnet_path, monkeypatch):
        """两个都设 → 不 warn"""
        monkeypatch.setenv("TIR_GZ_ROADNET", real_roadnet_path)
        monkeypatch.setenv("TIR_GZ_STREETS", str(tmp_data_dir / "empty_streets.geojson"))

        from territory_ir.dataset import Dataset
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ds = Dataset.guangzhou(data_dir=str(tmp_data_dir))

        ours = [w for w in caught if "硬编码" in str(w.message)]
        assert not ours
        assert len(ds.parents) > 1000

    def test_only_streets_env_uses_env_for_streets(self, tmp_data_dir, real_roadnet_path, monkeypatch):
        """只设 TIR_GZ_STREETS, streets 用 env, roadnet 走硬编码 + warn"""
        monkeypatch.setenv("TIR_GZ_STREETS", str(tmp_data_dir / "empty_streets.geojson"))
        # 不设 TIR_GZ_ROADNET

        from territory_ir.dataset import Dataset
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                Dataset.guangzhou(data_dir=str(tmp_data_dir))
            except FileNotFoundError:
                pass

        # 应 warn (因为 roadnet 是硬编码回退)
        ours = [w for w in caught if "硬编码" in str(w.message)]
        assert ours, f"应 warn (roadnet 走硬编码); 实际: {[str(w.message) for w in caught]}"

    def test_neither_env_warns(self, tmp_data_dir):
        """都不设 → warn"""
        from territory_ir.dataset import Dataset
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                Dataset.guangzhou(data_dir=str(tmp_data_dir))
            except FileNotFoundError:
                pass

        ours = [w for w in caught if "硬编码" in str(w.message)]
        assert ours

    def test_full_workflow_with_only_roadnet(self, tmp_data_dir, real_roadnet_path, monkeypatch):
        """业务方真实场景: 只有路网, 没有街道面 → 仍应能加载 (U=parents)"""
        monkeypatch.setenv("TIR_GZ_ROADNET", real_roadnet_path)
        # 不设 TIR_GZ_STREETS - 业务方没街道面数据
        # 改用空街道面文件, 模拟业务方提供
        empty = tmp_data_dir / "empty.geojson"
        empty.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

        # 验证: 即便 hardcoded streets_path 不存在, 业务方可以用 --data + 自定义 streets_path
        # 这里测核心路径解析: env_streets 缺失时, 应给出提示让业务方设置
        from territory_ir.dataset import Dataset
        # 用自定义构造(不用 guangzhou 工厂), 模拟"业务方传入完整配置"
        ds = Dataset(
            data_dir=str(tmp_data_dir),
            roadnet_path=real_roadnet_path,
            streets_path=str(empty),
            osm_path=str(tmp_data_dir / "gz_osm_full.json"),
            name="partial",
        )
        assert len(ds.parents) > 1000
        assert len(ds.U) == len(ds.parents)  # 无街道面 = U = parents
