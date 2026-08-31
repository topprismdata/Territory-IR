# API 参考

## Dataset

```python
from territory_ir.dataset import Dataset
```

### 构造

```python
Dataset(*, data_dir, roadnet_path, streets_path, osm_path,
        name="default", km2_deg2=12364.0,
        feat_buf_m=100.0, band_buf_m=150.0)
Dataset.guangzhou(data_dir)   # 广州预置：读 territory_ir_dataset.json 或回退默认路径
```

| 参数 | 说明 |
|---|---|
| `data_dir` | 区域包目录（含 region.json、gz_osm_full.json、unit_attributes.json） |
| `roadnet_path` | 四级路网 GeoJSON（父地块，GCJ-02） |
| `streets_path` | 区划街道面 GeoJSON（GCJ-02） |
| `osm_path` | OSM 解析数据（地物 WGS-84 + 行政界） |
| `km2_deg2` | 度²→km² 系数（广州 12364，按纬度标定） |
| `feat_buf_m` | 地物贴附缓冲（米，路/河沿条款用） |
| `band_buf_m` | 界带判定缓冲（米） |

### 属性（构建后可用）

| 属性 | 类型 | 说明 |
|---|---|---|
| `U` | list[tuple] | 统一铺盖：`(geometry, 主街道, 所在街道面, 父地块号)` |
| `Ut` | STRtree | U 几何空间索引 |
| `parents / pt` | list / STRtree | 路网父地块 |
| `spoly / sst / sbt` | — | 街道面 / 索引 / 边界并集 |
| `spoly_by_name` | dict | 街道名 → 面 |
| `feat_geoms / feat_names / feat_rank / ftt` | — | OSM 地物（WGS） |
| `FEATS` | defaultdict(set) | 地物名 → 片号集合 |
| `reg` | dict | region.json 原文（围栏/门店） |
| `data_dir` | Path | 区域包目录 |

### 方法

```python
compile_fence(fence: dict) -> dict
```
单围栏编译。`fence = {"area_id", "dealer", "rings": [[[lon,lat]...]], "area_km2"}`。
返回行结构：

| 键 | 说明 |
|---|---|
| `human_terms` | 人话描述短语列表 |
| `engine_terms` | 引擎条款标签列表（含 P# 兜底） |
| `ir` | `{"ir_version", "tessellation", "unit_library", "clauses", "annotations"}` |
| `T` / `S` | 真值片号 / 条款回放片号（排序列表） |
| `engine_J / engine_hit / engine_over / engine_miss` | 复现指标 |
| `iou / cover` | 几何指标（重演 vs 手绘） |
| `km2` | 围栏面积 |

```python
clause_pieces(clause: dict) -> set        # 条款 → 片集合
vocab() -> list[(label, clause, pieces)]  # 全词表（懒构建）
eval_sir(ir: dict) -> (S, bands)
synth(zg: Polygon, T: set) -> [(label, clause)]   # 贪心条款合成
verbalize(chosen, zg) -> list[str]        # 条款 → 人话
feats_of(k: int) -> set[str]              # 片的贴附地物名
iou_v(a, b) -> float                      # 两几何 IoU
install(g: dict)                          # 兼容安装（旧模块属性访问）
```

## semantics

```python
from territory_ir import semantics
```

```python
pieces_union(ds, pieces) -> Geometry
    # 片并集（保留 MultiPolygon）

osm_catalog(ds) -> dict
    # {"roads": {名: 段列表(WGS)}, "rivers": {}, "refs": {},
    #  "districts": {街道名: {"polys": [环(GCJ)]}}}
    # 供 LLM 地标抽取与 lookup_geometry 使用

road_line_gcj(ds, name: str) -> LineString|MultiLineString
    # OSM 地物(WGS) → GCJ 折线并集；找不到抛 ValueError
    # name 为子串包含匹配

split_pieces_by_road(ds, pieces, line, side) -> (chosen, other)
    # side ∈ west/east/south/north；片按质心相对最近路段法向分堆
    # 只分堆，不切割几何

select_pieces(ds, pieces, selector) -> (chosen, desc)
    # selector：整个区域 / 东|南|西|北半区 / 街道名 / 区名
    # 未识别抛 ValueError

street_district_map(ds) -> dict
    # street → district（unit_attributes.json 众数）

ir_fence_from_semantics(ds, areas, bounds, center) -> set
    # areas: ["联和街道", ...]（街道/区名）
    # bounds: {"北": "广汕公路", ...}（方向界；北界=保留路南）
    # center: [lon, lat]（无 areas 时 6km 半径兜底）
    # 返回片号集合；空集 = 语义未命中（调用方应给出可读错误）
```

## coords

```python
from territory_ir import coords

coords.wgs2gcj(lon, lat) -> (lon, lat)
coords.gcj2wgs(lon, lat) -> (lon, lat)     # 6 轮迭代收敛
coords.out_of_china(lon, lat) -> bool
coords.convert(pt, to_wgs: bool) -> (lon, lat)   # 境外原样返回
```

## 错误约定

- `semantics.road_line_gcj` / `select_pieces`：命名失败抛 `ValueError`
- `ir_fence_from_semantics`：**永不抛错**，未命中返回空集（调用方负责
  转成可读错误，如 demo_server 的 400「IR 语义未命中单元库」）
