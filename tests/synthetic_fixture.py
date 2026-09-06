"""合成数据集 fixture:不依赖业务方私有数据,让 smoke 测试在 CI 也能跑

构造一个 2x2 网格,4 个父地块 + 2 个街道面:
- 路网(4 个 polygon,每块带 "街道[内置]" 属性)
- 街道面(2 个 polygon,各覆盖 2 个父地块)
- 期望:U 铺盖 = 4(每父地块被 1 个街道完全覆盖,无切分)
"""
import json
from pathlib import Path


def make_synthetic_dataset(tmp_path: Path) -> Path:
    """在 tmp_path 下生成完整 synthetic dataset,返回 data_dir"""
    # 街道面 A: 覆盖左上 + 右上 (lon 113.0-113.2, lat 23.0-23.2)
    # 街道面 B: 覆盖左下 + 右下 (lon 113.0-113.2, lat 22.8-23.0)
    street_a = {
        "type": "Feature", "properties": {"街道[内置]": "街道A"},
        "geometry": {"type": "Polygon", "coordinates": [[[113.0, 23.0], [113.2, 23.0],
                                                          [113.2, 23.2], [113.0, 23.2],
                                                          [113.0, 23.0]]]}}
    street_b = {
        "type": "Feature", "properties": {"街道[内置]": "街道B"},
        "geometry": {"type": "Polygon", "coordinates": [[[113.0, 22.8], [113.2, 22.8],
                                                          [113.2, 23.0], [113.0, 23.0],
                                                          [113.0, 22.8]]]}}
    streets_path = tmp_path / "streets.geojson"
    streets_path.write_text(json.dumps(
        {"type": "FeatureCollection", "features": [street_a, street_b]},
        ensure_ascii=False))

    parents = [
        {"type": "Feature", "properties": {"街道[内置]": "街道A", "区[内置]": "测试区"},
         "geometry": {"type": "Polygon",
                      "coordinates": [[[113.0, 23.1], [113.1, 23.1], [113.1, 23.2], [113.0, 23.2], [113.0, 23.1]]]}},
        {"type": "Feature", "properties": {"街道[内置]": "街道A", "区[内置]": "测试区"},
         "geometry": {"type": "Polygon",
                      "coordinates": [[[113.1, 23.1], [113.2, 23.1], [113.2, 23.2], [113.1, 23.2], [113.1, 23.1]]]}},
        {"type": "Feature", "properties": {"街道[内置]": "街道B", "区[内置]": "测试区"},
         "geometry": {"type": "Polygon",
                      "coordinates": [[[113.0, 22.9], [113.1, 22.9], [113.1, 23.0], [113.0, 23.0], [113.0, 22.9]]]}},
        {"type": "Feature", "properties": {"街道[内置]": "街道B", "区[内置]": "测试区"},
         "geometry": {"type": "Polygon",
                      "coordinates": [[[113.1, 22.9], [113.2, 22.9], [113.2, 23.0], [113.1, 23.0], [113.1, 22.9]]]}},
    ]
    roadnet_path = tmp_path / "roadnet.geojson"
    roadnet_path.write_text(json.dumps(
        {"type": "FeatureCollection", "features": parents},
        ensure_ascii=False))

    osm_path = tmp_path / "osm.json"
    osm_path.write_text(json.dumps({"roads": [], "rivers": [], "adm6": []}))

    region_path = tmp_path / "region.json"
    # 围栏:覆盖右上 + 右下 (lon 113.1-113.2, lat 22.9-23.2)
    fence = {
        "area_id": "test-1", "dealer": "测试经销商",
        "rings": [[[113.1, 22.9], [113.2, 22.9], [113.2, 23.2], [113.1, 23.2], [113.1, 22.9]]],
        "area_km2": 3.0,
    }
    region_path.write_text(json.dumps({"fences": [fence], "stores": []}, ensure_ascii=False))

    return tmp_path
