"""Dataset.guangzhou 路径解析测试 (修复 issue #1)

覆盖:
- territory_ir_dataset.json 优先(已存在机制)
- 环境变量 TIR_GZ_ROADNET / TIR_GZ_STREETS 覆盖 ~/Downloads
- 无配置无环境变量时,warn + 回退 ~/Downloads
"""
import json
import os
import warnings
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path):
    """构造最小可用 data_dir:region.json + osm + 空 streets"""
    (tmp_path / "region.json").write_text(json.dumps({"fences": [], "stores": []}))
    (tmp_path / "gz_osm_full.json").write_text(json.dumps(
        {"roads": [], "rivers": [], "adm6": []}))
    (tmp_path / "empty_streets.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": []}))
    return tmp_path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """每个测试前清掉相关环境变量"""
    for k in ("TIR_GZ_ROADNET", "TIR_GZ_STREETS", "TIR_DATA"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def real_roadnet_path():
    """真实广州路网(已放在 ~/Downloads)"""
    p = Path("/Users/mac/Downloads/边界数据-路网-到区县带海岸线-四级路网-广东省-广州市.geojson")
    if not p.exists():
        pytest.skip("广州路网数据不在 ~/Downloads,跳过依赖真实数据的测试")
    return str(p)


class TestConfigPriority:
    """territory_ir_dataset.json 是最高优先级"""

    def test_config_file_used_when_present(self, tmp_data_dir, real_roadnet_path):
        cfg = {
            "roadnet_path": real_roadnet_path,
            "streets_path": str(tmp_data_dir / "empty_streets.geojson"),
            "osm_path": str(tmp_data_dir / "gz_osm_full.json"),
        }
        (tmp_data_dir / "territory_ir_dataset.json").write_text(json.dumps(cfg))

        from territory_ir.dataset import Dataset
        ds = Dataset.guangzhou(data_dir=str(tmp_data_dir))
        assert ds.roadnet_path == real_roadnet_path
        assert len(ds.parents) > 1000  # 真实路网父地块数


class TestEnvOverride:
    """环境变量优先级高于 ~/Downloads 硬编码"""

    def test_roadnet_env_var_used(self, tmp_data_dir, real_roadnet_path, monkeypatch):
        monkeypatch.setenv("TIR_GZ_ROADNET", real_roadnet_path)
        monkeypatch.setenv("TIR_GZ_STREETS", str(tmp_data_dir / "empty_streets.geojson"))

        from territory_ir.dataset import Dataset
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # 不再 warn 因为走了 env
            ds = Dataset.guangzhou(data_dir=str(tmp_data_dir))
        assert ds.roadnet_path == real_roadnet_path
        assert len(ds.parents) > 1000

    def test_streets_env_var_used(self, tmp_data_dir, real_roadnet_path, monkeypatch):
        monkeypatch.setenv("TIR_GZ_ROADNET", real_roadnet_path)
        monkeypatch.setenv("TIR_GZ_STREETS", str(tmp_data_dir / "empty_streets.geojson"))

        from territory_ir.dataset import Dataset
        ds = Dataset.guangzhou(data_dir=str(tmp_data_dir))
        assert ds.streets_path == str(tmp_data_dir / "empty_streets.geojson")


class TestFallbackWarns:
    """无配置无环境变量:warn + 回退 ~/Downloads"""

    def test_warns_on_hardcoded_fallback(self, tmp_data_dir):
        from territory_ir.dataset import Dataset
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(FileNotFoundError):
                # 无 env,无 config,应回退到 ~/Downloads/... 路径,然后该路径不存在抛错
                Dataset.guangzhou(data_dir=str(tmp_data_dir))

        # 必须有我们的 UserWarning
        ours = [w for w in caught if "硬编码" in str(w.message)
                and "TIR_GZ_ROADNET" in str(w.message)]
        assert ours, f"未发出硬编码回退警告;实际: {[str(w.message) for w in caught]}"

    def test_no_warn_when_env_var_present(self, tmp_data_dir, real_roadnet_path, monkeypatch):
        """环境变量提供路径时不应再 warn"""
        monkeypatch.setenv("TIR_GZ_ROADNET", real_roadnet_path)
        monkeypatch.setenv("TIR_GZ_STREETS", str(tmp_data_dir / "empty_streets.geojson"))

        from territory_ir.dataset import Dataset
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Dataset.guangzhou(data_dir=str(tmp_data_dir))

        ours = [w for w in caught if "硬编码" in str(w.message)]
        assert not ours, f"不该警告却警告了: {[str(w.message) for w in ours]}"

    def test_no_warn_when_config_present(self, tmp_data_dir, real_roadnet_path):
        cfg = {
            "roadnet_path": real_roadnet_path,
            "streets_path": str(tmp_data_dir / "empty_streets.geojson"),
            "osm_path": str(tmp_data_dir / "gz_osm_full.json"),
        }
        (tmp_data_dir / "territory_ir_dataset.json").write_text(json.dumps(cfg))

        from territory_ir.dataset import Dataset
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Dataset.guangzhou(data_dir=str(tmp_data_dir))

        ours = [w for w in caught if "硬编码" in str(w.message)]
        assert not ours, f"不该警告却警告了: {[str(w.message) for w in ours]}"
