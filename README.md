# TerritoryIR

领地单元片编译/重演/调整核心。

**一句话**：手绘围栏 → 压在统一铺盖上的真值片 T → 文字条款（slice/feat/band/pieces）
→ 条款回放片集合 S（Jaccard 验证）→ 片并集即围栏。人话描述 = 围栏的有损压缩，
J = 压缩保真度。

## 架构

```
Dataset（城市数据集）
  ├─ parents/pt      四级路网父地块（GCJ-02）
  ├─ spoly/sst/sbt   区划街道面（GCJ-02）
  ├─ feat_geoms/ftt  OSM 地物折线（WGS-84，查询时转 GCJ）
  ├─ U/Ut            统一铺盖：父地块 × 街道面 切片（原子单元）
  └─ FEATS/vocab     地物贴附索引、条款词表

compile_fence(fence) → {human_terms, engine_terms, T, S, engine_J, iou, ir}
semantics.ir_fence_from_semantics(areas, bounds, center) → S 片
semantics.split_pieces_by_road(ds, pieces, line, side) → (侧A片, 侧B片)
```

## 使用

```python
from territory_ir.dataset import Dataset
ds = Dataset.guangzhou(data_dir="data/gz")   # 数据路径可经 territory_ir_dataset.json 配置
row = ds.compile_fence(ds.reg["fences"][0])
```

数据路径优先级：`<data_dir>/territory_ir_dataset.json`（keys: roadnet_path,
streets_path, osm_path, km2_deg2, feat_buf_m, band_buf_m）→ 广州默认（~/Downloads 源文件）。

## 测试

```
pip install -e . && pytest tests/ -v
```

数据源缺失时测试自动跳过。
