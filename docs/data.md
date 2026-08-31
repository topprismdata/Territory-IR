# 数据接入指南

TerritoryIR 以**城市数据集**为单位工作。接入一座新城市需要三份源数据
+ 区域包目录。本页说明格式、坐标系与配置方法。

## 1. 源数据清单（以广州为例）

| 文件 | 角色 | 坐标系 | 关键字段 |
|---|---|---|---|
| `边界数据-路网-到区县带海岸线-四级路网-广东省-广州市.geojson` | **父地块**（铺盖的底） | GCJ-02 | `properties["街道[内置]"]`、`properties["区[内置]"]`；`geometry` 为 Polygon |
| `区划数据-街道-广东省-广州市.geojson` | **街道面**（切分器 + 条款空间） | GCJ-02 | `properties["街道[内置]"]`（或 `街道`/`name`）；Polygon/MultiPolygon |
| `gz_osm_full.json` | **OSM 地物**（feat 条款、界带） | WGS-84 | `roads:[{name, cls, wkt}]`、`rivers:[{name, wkt}]`、`adm6:[{name, wkt}]` |

> ⚠️ 帧纪律：源文件如上标注；库内 OSM 地物保持 WGS，与 GCJ 片做空间
> 运算时**逐次转换**（`feats_of` / `road_line_gcj`），不落混帧数据。

## 2. 区域包目录（data_dir）

```
data/gz/
├── region.json                    # {"fences":[...], "stores":[...], "kinds":{}}
│     fences[i] = {area_id, dealer, rings:[[[lon,lat]...]], area_km2}
├── gz_osm_full.json
├── unit_attributes.json           # {"units":[{id, district, street, roads, ...}]}
│                                   # （可选：street→district 映射供区名选择器）
├── territory_compiled.json        # 编译产物（运行时生成/更新）
└── territory_ir_dataset.json      # ★ 数据集配置（本页 §3）
```

## 3. territory_ir_dataset.json

```json
{
  "roadnet_path": "~/Downloads/边界数据-路网-...-广州市.geojson",
  "streets_path": "~/Downloads/区划数据-街道-...-广州市.geojson",
  "osm_path":     "gz_osm_full.json",
  "km2_deg2":     12364.0,
  "feat_buf_m":   100,
  "band_buf_m":   150
}
```

- 相对路径相对 `data_dir`；`~` 会展开
- 不存在时回退广州默认路径（仅供本机开发，生产请显式配置）
- 改配置后重建 Dataset 即可（构建约 8 秒/广州）

## 4. 接入新城市清单

1. ☐ 拿到该城市（或覆盖目标范围的）四级路网 GeoJSON，确认属性含街道/区名
2. ☑ 街道面 GeoJSON，街道名属性与路网 `街道[内置]` **同源同拼写**
3. ☐ 用 Overpass/等工具导出 OSM：roads（带 name/cls/highway）、rivers、
   admin_level=6 边界，转 WKT 组装 `osm_full` 结构
4. ☐ 建 `region.json`（手绘围栏 + 门店），统一 GCJ-02
5. ☐ 写 `territory_ir_dataset.json`
6. ☐ 冒烟：`ds.compile_fence(一条围栏)`，确认 `J≥0.9、片数>0`

## 5. 帧约定（必读）

| 数据 | 帧 |
|---|---|
| 路网 / 街道面 / 围栏 / 门店 / 片 | **GCJ-02**（工作帧） |
| OSM 地物 / 行政界 | WGS-84（存储帧） |

库内凡涉及跨帧空间运算（地物贴附、沿路分堆），均以
`coords.gcj2wgs / wgs2gcj` 逐次转换。**不要**把 OSM 数据预先转成 GCJ
落库，也不要去掉转换直接叠算。

## 6. 已知边界情况

- 街道面互相重叠的边界争议片：`U[k][1] ≠ U[k][2]`，由 `slice` 条款
  消歧；贪心可能落到 `pieces`（P# 指针）兜底——纯语言 J 会因此下降
- 手绘围栏自相交（如一笔画 Two 瓣）：编译前 `buffer(0)` 会自然分瓣，
  瓣即独立地盘（广州亨啡源案例）
- 围栏边界切在片中间：IoU 受片粒度限制（0.6~1.0 属正常）
