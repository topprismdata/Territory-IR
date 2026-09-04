# TerritoryIR

**领地单元片编译 / 重演 / 调整核心。**

把业务手绘的销售领地围栏，编译成"基本单元片集合 + 可读文字描述"，
并用 Jaccard 指标验证文字描述能否无损复现同一片集合。自然语言（合同描述、
调整指令）通过 IR 条款解析直接落到片集合，实现"围栏 = 描述 = 调整对象"
三位一体。

```
手绘围栏（GCJ-02 多边形）
    │  压射（≥50% 片内 或 ≥30% 围栏面积）
    ▼
真值片 T ──── 统一铺盖 U（四级路网父地块 × 区划街道面 切片，6261 片/广州）
    │  贪心条款合成（net-gain）
    ▼
IR 条款（slice / feat / block / band / pieces）
    │  回放 clause_pieces()
    ▼
重演片 S ──→ 片并集 = 重演围栏        J = |S∩T| / |S∪T|
    │
    └── 人话描述（verbalize）："凤凰街道 | 联和街道沿天慧路 | …"
```

## 核心理念

1. **片是唯一事实**。围栏、描述、调整全部以片集合为决策对象；围栏是片并集的
   几何视图，描述是片集合的有损压缩。
2. **J 是描述的保真度**。J=1.0 表示文字条款无损编码了围栏压住的全部片；
   纯语言词（不含 P# 指针）的 J 衡量"说得清的地盘"比例。
3. **不切割几何**。所有调整（半区切分、沿路分堆）都是片归属变更，片是原子。
4. **坐标系单一**。单元库/围栏统一 GCJ-02；OSM 地物（WGS-84）在查询时
   逐次转换，库里不混帧。

## 安装

```bash
pip install -e /path/to/territory-ir     # shapely>=2.0
```

## 快速开始

```python
from territory_ir.dataset import Dataset

ds = Dataset.guangzhou(data_dir="data/gz")   # 首次构建约 8 秒

# 1) 编译：手绘围栏 → 真值片 + 条款 + 人话 + 验证
row = ds.compile_fence(ds.reg["fences"][0])
row["human_terms"]   # ['凤凰街道', '联和街道沿天慧路', ...]
row["engine_J"]      # 1.0（条款回放 vs 真值片的 Jaccard）
row["iou"]           # 0.99（重演几何 vs 手绘多边形）
row["T"], row["S"]   # 真值片号 / 条款回放片号

# 2) 重演：片集合 → 几何
from territory_ir.semantics import pieces_union
u = pieces_union(ds, row["S"])            # shapely 多边形
ring = list(u.exterior.coords)

# 3) 语义构面：自然语言结构 → 片集合
from territory_ir.semantics import ir_fence_from_semantics
pieces = ir_fence_from_semantics(
    ds,
    areas=["联和街道"],                    # 街道全域
    bounds={"北": "广汕公路", "南": "开创大道"},  # 方向界（北界=片在路南）
    center=None)                           # 无街道时的中心兜底（6km 半径）

# 4) 沿路分堆（调整用，不切割几何）
from territory_ir.semantics import road_line_gcj, split_pieces_by_road
line = road_line_gcj(ds, "花莞高速")
west, east = split_pieces_by_road(ds, pieces, line, "west")
```

## 数据配置

`Dataset.guangzhou(data_dir=...)` 按以下优先级解析数据源：

1. `<data_dir>/territory_ir_dataset.json` 存在时按其配置：
   ```json
   {
     "roadnet_path": "/path/四级路网.geojson",
     "streets_path": "/path/区划街道.geojson",
     "osm_path":     "/path/gz_osm_full.json",
     "km2_deg2": 12364.0,
     "feat_buf_m": 100,
     "band_buf_m": 150
   }
   ```
2. 否则回退广州默认（~/Downloads 下的源文件 + `<data_dir>/gz_osm_full.json`）。

新城市接入 = 准备同结构的三份源数据 + 一份配置 JSON，无需改代码。

## 模块导览

| 模块 | 职责 |
|---|---|
| `dataset.Dataset` | 数据加载、统一铺盖 U、词表、`compile_fence`、兼容安装 |
| `semantics` | 片并集、osm 目录、沿路分堆、片区选择器、语义构面 |
| `coords` | GCJ-02 ⇄ WGS-84 转换 |

深入阅读：

- [docs/concepts.md](docs/concepts.md) —— 铺盖/真值片/条款词法/J 指标的设计原理
- [docs/api.md](docs/api.md) —— 全量 API 签名与返回结构
- [docs/data.md](docs/data.md) —— 数据格式、新城市接入清单、坐标系纪律
- [docs/actions.md](docs/actions.md) —— 动作清单（业务审阅版）

详细 API 见 [docs/api.md](docs/api.md)，概念与指标见
[docs/concepts.md](docs/concepts.md)，数据接入见 [docs/data.md](docs/data.md)。

## 兼容层（SRAF demo 集成）

`Dataset.install(globals())` 把数据集全部公共名（`U`、`spoly_by_name`、
`compile_fence`…）拷入调用方全局命名空间，供旧式模块属性访问
（`tc.U[k][0]`）无缝迁移。

## 测试

```bash
python -m pytest tests/ -v    # 数据源缺失时自动跳过
```

## 版本

- **v0.1.0** 首次独立抽取（自 SRAF demo RC3.0）。广州数据集 32 围栏
  编译 J 中位 1.0；语义构面/沿路分堆 E2E 验证通过。
