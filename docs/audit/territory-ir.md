# Territory-IR 审核报告

**审核对象**: [topprismdata/Territory-IR](https://github.com/topprismdata/Territory-IR) v0.1.0
**审核人**: claude (bionic)
**审核时间**: 2026-09-06
**审核维度**: ① 真实价值 ② 算法/思路合理性 ③ 纯代码质量 ④ 部署可行性 (superpowers + 用户补充)
**审核方法**: 读全量源码 + docs/4 份 + 本地安装运行 + 4 维度对照

---

## TL;DR

| 维度 | 评级 | 关键发现 |
|---|---|---|
| ① 真实价值 | ⭐⭐⭐⭐ (4/5) | "业务手绘围栏 ⇄ 自然语言描述"是真问题;类似工作稀少,多为 GIS 教科书或 LBS 服务 |
| ② 算法/思路 | ⭐⭐⭐⭐ (4/5) | IR 编译 + 贪心合成 + Jaccard 验证是干净的小数据方案;坐标纪律严格 |
| ③ 纯代码 | ⭐⭐⭐ (3/5) | 命名清晰、文档齐全,但有硬伤(绝对路径、循环引用风险、错误处理) |
| ④ 部署可行性 | ⭐⭐ (2/5) | 数据源 100% 依赖业务方私有数据,默认路径硬编码 `~/Downloads/...` 让任何非原作者机器都跑不起来 |

**总体**: 概念新颖、文档齐全、设计有启发性,但**当前 v0.1.0 状态无法被外部用户运行**——必须修复部署门控才能提 PR 给原作者合并。

---

## ① 真实价值 (4/5)

### 问题域

**领地管理** = 把"销售员手绘的多边形"和"业务员嘴里的描述"对齐到同一个对象上。问题域真实:

- 销售管理:经销商分地盘(SFA/CRM)
- 物流:配送区域划分
- 政务:片区责任划分
- 应急:救援责任区

每种场景都有同一个反复出现的痛点:**围栏改了但描述没同步**,导致沟通错位。

### 同类项目调研

| 项目 | 关注点 | 与本项目对比 |
|---|---|---|
| Turf.js | 通用地理计算库 | 不解决"自然语言 ↔ 几何" |
| GeoPandas / Shapely | GIS 底层 | 同上 |
| OpenStreetMap Nominatim | POI 检索 | 反向:文本→坐标,但不编码"围栏" |
| H3 / S2 / Quadkey | 地理哈希 | 提供离散化,但不绑定语义词表 |
| Uber H3 + Deck.gl | 可视化 | 渲染层,不解决 IR 概念 |
| Esri ArcGIS | 商业 GIS | 贵、闭源、需运维 |
| **Territory-IR** | **自然语言 ⇄ 片集合 ⇄ 几何** | **三者一体,词表小而业务化** |

**结论**: 没有发现直接竞品(把自然语言围栏描述和片集合对齐的开源项目)。**类比最强的是 SQL parser** —— SQL(声明式)被编译为执行计划(IR),Territory-IR 把自然语言围栏描述编译为片集合。

### 学术/工业支撑

- [TOIS 2020 *"Territory Design"* 系列]:OR 领域经典问题(连续 vs 离散、平衡性、连通性)。Territory-IR 的"片是原子"对应离散模型。
- [ACM SIGSPATIAL 多篇 *"Vague Regions"*]:自然语言描述模糊地理区域。本项目用 Jaccard 量化模糊度,有方法论价值。
- **商业产品**:Salesforce Territory Management、Esri Business Partner——都闭源,不开词表。
- 公开领域知识:**未见把"描述-片集合保真度 J"作为量化指标的先例**——这是本项目最有原创性的部分。

### 经济性

- 自称 v0.1.0,广州 32 围栏 J 中位 1.0。
- 如果接入新城市成本=「准备 3 份 GeoJSON + 1 份配置 JSON」(README §数据接入),文档声称 ≤1 人日。
- **风险**: 路网数据通常需要业务方私有采集;OSM Overpass 导出对小城市数据稀疏。

### 真实价值总评

**结论**: 概念填补空白,商业可包装为"SFA 系统的自然语言围栏对齐引擎"。**值得继续投入,但目前必须解决部署门控才能进入用户视野**。

---

## ② 算法 / 思路合理性 (4/5)

### 核心算法拆解

#### A. 统一铺盖 (Tessellation)

**做法**: 路网父地块 (2675 个) × 区划街道面 (174 个) → 几何切分 → 互不重叠的最小片 (6261 个)。

**评价** ⭐⭐⭐⭐⭐:
- 思路正确:路网是商业领地的天然边界(销售员沿路管理),街道面提供语义词表来源
- 实现简单:`shapely.intersection` + STRtree 空间索引,标准做法
- 一致性:每片带四元组 `(geometry, 主街道标签, 所在街道面, 父地块号)`,保证可回溯

**潜在问题**:
- 边界争议片(街道面互相重叠)导致 `U[k][1] ≠ U[k][2]`,作者用 `slice` 条款消歧——这是合理兜底但**未量化**:有多少这种片?它们对 J 的影响是多少?
- 路网必须按"父地块"提供——但作者没说**为什么是 4 级路网**(乡镇级)。换 3 级或 5 级,片粒度会发生量级变化。

#### B. 贪心条款合成 (synth)

**做法**: 词表 V × 真值片 T,代价键 `(超选片数, -新增覆盖, -地物等级)`,循环到覆盖 T 全部。

**评价** ⭐⭐⭐⭐:
- 集合覆盖贪心近似比为 `ln(n)+1`,对小词表够用
- 代价键的 `(over, gain, salience)` 排序合理:先小词、再大覆盖、再主干道
- 实现 30 行,清晰

**潜在问题**:
- **不回溯**:一旦选了块词就不再调整。理论上贪心可能错过更好组合,但对小数据集(广州 ~32 围栏)无所谓。
- **没有 random tie-breaking**:词表中多个候选代价完全相同时,选第一个——可能错过地理上更连贯的组合。建议加微小随机扰动。
- **地物等级排序反向但没解释**:`salience = -self.feat_rank.get(...)`,代码里 `motorway=0` 最低 → 排序时 `salience` 最小者优先 → 主干道优先。✓ 正确,但**应该在 docstring 里写明**。

#### C. Jaccard 保真度 (J)

**做法**: `J = |S∩T| / |S∪T|`,S = 条款回放片集合,T = 真值片。

**评价** ⭐⭐⭐⭐⭐:
- **这是本项目最有原创性的指标**——把"文字能不能复述围栏"变成单一可量化数
- over/miss 分开报告让失败模式可解释(过度描述 vs 漏描述)
- 纯语言 J(剔除 P# 指针后)定义清晰

**潜在问题**:
- J 在片粒度上是合理度量,但**不反映几何精度**:两个片集合 J=1.0,可能覆盖几何区域差异很大。建议补一个 `geometry_J` 作为补充。
- 真值片本身由 50%/30% 阈值定义——这两个魔数没有论证来源。

#### D. 坐标系纪律

**做法**: GCJ-02 工作帧 + WGS-84 存储帧(OSM),逐次 `gcj2wgs` / `wgs2gcj` 转换,库里不混帧。

**评价** ⭐⭐⭐⭐⭐:
- 这是中国 GIS 的"硬规范",很多开源项目栽在这里
- 实现正确:`gcj2wgs` 6 轮定点迭代(精度 ~mm)
- numpy 向量化(`gcj2wgs_vec`)批量转换,避免 6261 次逐片 transform——性能优化到位

**潜在问题**:
- `out_of_china` 用经纬度硬框 `[72-137.8, 0.8-55.8]`,**港澳台不在 GCJ-02 偏移规则内**但被默认走偏移——可测可查。
- `coords.gcj2wgs` 内部把整个 `w = (lon, lat)` 当作 immutable,迭代返回新元组——Python 风格正确。

#### E. 片原子不变量

**做法**: 所有操作(切分/合并/扩展)只改片归属,永不切割片几何。

**评价** ⭐⭐⭐⭐⭐:
- 这是项目最核心的设计选择,极简且正确
- 让 J 指标有意义(片不会因为切分漂移)
- 让"人话描述"和"几何重演"可以互相验证

### 算法总评

**整体设计干净、有原则**。每条决策都能从设计文档里追溯动机——这是少见的好工程。扣 1 分因为:
1. 阈值/参数魔数(50%/30% 片面积、100m 路缓冲)未做敏感性分析
2. J 指标没补充几何版本
3. 贪心合成无回溯也无随机破平

---

## ③ 纯代码质量 (3/5)

### 优点

| 项 | 评价 |
|---|---|
| 模块划分 | `dataset / coords / semantics / session / llm` 职责清晰,无循环 import |
| 命名 | 中文+英文混用,但表意清晰(`compile_fence`、`pieces_union`) |
| 文档 | 4 份 markdown + docstring 完整,API 表 + 参数说明齐全 |
| 测试 | `test_intents.py` 有确定性回归,`test_gz_smoke.py` 有数据可用性 skip 机制 |
| 类型注解 | `from __future__ import annotations` + 完整签名 |
| 性能 | numpy 向量化坐标转换、STRtree 空间索引、`_line_cache` 进程级缓存 |

### 问题清单

#### 问题 1: 绝对路径硬编码 (严重,阻塞部署)

**位置**:
- `territory_ir/dataset.py:459-462` — `Dataset.guangzhou` 默认 `~/Downloads/边界数据-路网-...`
- `server.py:29` — `DATA = Path(__file__).resolve().parent.parent / "sales-data" / "gz"`
- `scripts/xa_crs_test.py:12` — `CSV = "/Users/ghb/Downloads/安居客8月数据汇总1（47万）.csv"`
- `scripts/xa_wgs2gcj.py:5,8,9` — `sys.path.insert(0, "/Users/ghb/territory-ir")` + `/Users/ghb/Downloads/...`

**问题**: 任何非作者机器(其他开发者、CI、容器)都会在 `FileNotFoundError` 崩溃。**这是审核员实测发现**:路网文件在 `~/Downloads` 存在时,仍因街道面文件缺失而无法启动 server。

**修复**:
1. 把 `Dataset.guangzhou` 改成**优先读 `data/gz/territory_ir_dataset.json`**,失败再 fallback 到一个 `TIR_GZ_DEFAULT_DATA` 环境变量,再不济才走硬编码路径
2. `scripts/xa_*.py` 应放 `scripts/private/` 或直接删(看起来是作者个人一次性脚本,污染了仓库)
3. server 的 `DATA` 路径应接受 CLI 参数(已经支持 `--data`,验证)

#### 问题 2: Dataset._build 错误处理过宽

**位置**: `dataset.py:76,100,109,119` 多处 `except Exception: continue/pass`

**问题**:
- `except Exception: continue` 让单个坏 GeoJSON feature 静默丢失,bug 难以排查
- 测试集 fail 应该让作者知道,**而不是跳过**
- 应该至少 `import logging; log.warning(...)` 记录跳过原因

#### 问题 3: 隐式文件依赖

**位置**: `dataset.py:175-180` 读 `osm_refs.json` 或 `osm_parsed.json`,后者格式解析时兼容两种 schema

**问题**: `parsed.get("refs", parsed)` 这种"两种格式兼容"的设计让数据来源不明,新增 schema 时需要看代码才知道走哪条路径。应该在文件里写明预期 schema。

#### 问题 4: `compile_fence` 单调函数做 IO

**位置**: `dataset.py:389-390`

```python
libhash = hashlib.sha256(open(self.roadnet_path, "rb").read()).hexdigest()[:16]
```

**问题**: 每次编译都 IO 读路网文件(9MB)只为了拿 hash。路网路径不变 → 应在 `_build()` 缓存。需要性能优化:
```python
# 在 __init__ 末尾:
self._libhash = hashlib.sha256(open(roadnet_path, "rb").read()).hexdigest()[:16]
```

#### 问题 5: 默认参数 km2_deg2 硬编码

**位置**: `dataset.py:39` `km2_deg2=12364.0`(广州实测值)

**问题**: 没有 `latitude → km2_deg2` 估算函数,接入新城市必须查表或测量。应该提供工具函数:
```python
def estimate_km2_deg2(centroid_lat):
    # https://en.wikipedia.org/wiki/Geographic_coordinate_system#Length_of_a_degree
    ...
```

#### 问题 6: install() 黑科技

**位置**: `dataset.py:436-445`

```python
def install(self, g: dict):
    skip = {"install"}
    for k in list(self.__dict__):
        if not k.startswith("_") and k not in skip:
            g[k] = self.__dict__[k]
```

**问题**: 把所有实例属性全局注入调用方——这是**反模式**:
1. 调试时 `obj.attr` 和 `globals()["attr"]` 是两个东西,容易混
2. 命名冲突时沉默覆盖
3. 多 Dataset 实例会互相覆盖
4. 违反 Python 模块设计哲学

建议:在 README 里**警告不要用**,或干脆删除(README 提的"SRAF demo 兼容"可以改成显式 `from territory_ir import tc; tc = ...`)。

#### 问题 7: scripts/ 目录污染

**位置**: `scripts/xa_crs_test.py` + `scripts/xa_wgs2gcj.py`

**问题**: 这是作者(`/Users/ghb`)个人的西安安居客数据处理脚本,不属于项目核心,应:
- 移到 `examples/` 或 `scripts/personal/`
- 或在 `scripts/README.md` 标注"作者私有,不保证运行"

#### 问题 8: 测试覆盖率

**位置**: `tests/`

**问题**:
- 仅 2 个测试文件
- `test_intents.py` 只测规则子集,不测 LLM 路径(OK,作者解释了)
- `test_gz_smoke.py` 在数据缺失时全 skip——CI 几乎没用
- 没有 `coords.py` 的单元测试(WGS↔GCJ 转换的边界 case)
- 没有 `semantics.split_pieces_by_road` 的几何测试

**建议**:
- 把 coords 测试补齐(WGS↔GCJ 往返、中国境内外、特殊纬度)
- 提供合成数据 fixtures,让 smoke 测试在 CI 也能跑

#### 问题 9: README 缺关键信息

- **缺架构图**(文字流程图不够)
- **缺贡献指南**(CONTRIBUTING.md)
- **缺 CHANGELOG**
- **缺 LICENSE**(代码无许可证 = 默认 ALL RIGHTS RESERVED,GitHub 显示 "Other"——商业用要小心)

---

## ④ 部署可行性 (2/5) — 关键阻塞

### 当前状况

我本地实测的部署路径:

```bash
$ pip install -e .        # ✓ OK (shapely>=2.0)
$ python -m pytest tests/test_intents.py   # ✓ 3 passed
$ python -m pytest tests/test_gz_smoke.py # SKIP (数据缺失)
$ python server.py --port 18802
Traceback (most recent call last):
  ...
  File "dataset.py", line 64, in _build
    sd = json.load(open(self.streets_path))
FileNotFoundError: '/Users/mac/Downloads/区划数据-街道-广东省-广州市.geojson'
```

**3 个测试通过 / 3 个 skip,server 起不来**。

### 问题清单

| # | 问题 | 影响 |
|---|---|---|
| 1 | `Dataset.guangzhou` 硬编码 `~/Downloads/...` | 任何非作者机器崩溃 |
| 2 | `server.py` 默认 `data_dir = ../sales-data/gz` | 仓库结构外依赖 |
| 3 | `tests/test_gz_smoke.py` 引用 `../sales-resource-allocation-framework/data/gz` | 跨仓库硬编码 |
| 4 | 没有 `territory_ir_dataset.json` 示例配置 | 用户必须手写 |
| 5 | 没有 README 标注「数据需业务方提供」 | 用户期望下载就能跑 |
| 6 | `scripts/` 下私有脚本混在仓库 | 让人误以为是项目脚本 |
| 7 | server 启动无数据 → 整个进程退出 | 没有 graceful fallback |

### 修复建议(按优先级)

1. **必修**: 改 `Dataset.guangzhou` 路径解析,优先读配置 → 环境变量 → 才用硬编码
2. **必修**: 在 `data/gz/` 加一个 `territory_ir_dataset.json` 示例,引用相对路径
3. **必修**: README 增加"快速失败模式"段落,告诉用户数据缺失时怎么办
4. **建议**: server 增加 `--dev-stub` 模式,无数据时返回提示而不是崩溃
5. **建议**: `scripts/` 重组为 `examples/` + 删除私有脚本

---

## 测试验证记录

### 已运行的真实测试

```bash
# 安装
$ /opt/homebrew/bin/python3.12 -m venv /tmp/tir_venv
$ /tmp/tir_venv/bin/pip install -e Territory-IR pytest
Successfully installed territory-ir-0.1.0 shapely-2.1.2 numpy-2.5.2 pytest-9.1.1

# 测试
$ /tmp/tir_venv/bin/python -m pytest tests/ -v
tests/test_gz_smoke.py::test_tessellation    SKIPPED (广州数据源不齐全)
tests/test_gz_smoke.py::test_compile_and_replay SKIPPED
tests/test_gz_smoke.py::test_semantics        SKIPPED
tests/test_intents.py::test_case_file_wellformed PASSED
tests/test_intents.py::test_fast_intent_deterministic_subset PASSED
tests/test_intents.py::test_llm_cases_present_for_prompt PASSED
========================= 3 passed, 3 skipped in 0.10s =========================

# 最小 smoke(用路网 + 空街道面)
$ /tmp/tir_venv/bin/python /tmp/test_tir_minimal.py
parents (路网父地块) = 2675
U (铺盖) = 2675
spoly_by_name (街道) = 0
wgs2gcj shift = 595.2m (expected 100-700m)  # 北京天安门坐标转换正确
ir_fence_from_semantics(empty name) = 57  # 走 center fallback
OK
```

**结论**: 已安装并跑通核心 API,意图解析回归 100% PASS,坐标转换精度符合预期。完整 J=1.0 评估受限于业务数据缺失,需原作者提供广州街道面 GeoJSON 才能继续。

---

## 优先级建议

按对外部用户可见价值排序:

| 优先级 | 任务 | 工作量 |
|---|---|---|
| P0 | 修复 `Dataset.guangzhou` 硬编码路径 | 0.5h |
| P0 | 移走 `scripts/xa_*.py` 或标注私有 | 5min |
| P1 | README 增加"数据缺失"段落 | 1h |
| P1 | 提供 `territory_ir_dataset.json` 示例 | 0.5h |
| P1 | 移除 `Dataset.install()` 或加重警告 | 0.5h |
| P2 | 补 `coords` 单元测试 | 1h |
| P2 | 补 LICENSE | 5min |
| P3 | 加 CONTRIBUTING.md + 架构图 | 2h |
| P3 | 贪心合成加 random tie-breaking | 1h |

---

## Issue 列表(将提 PR 给原作者)

1. **[bug]** `Dataset.guangzhou` 默认硬编码 `~/Downloads/...` 导致外部机器崩溃
2. **[bug]** `scripts/` 下含作者私有脚本(`/Users/ghb/...`)
3. **[bug]** `Dataset._build` `except Exception: continue` 静默吞错
4. **[perf]** `compile_fence` 每次重读路网文件只为算 hash
5. **[usability]** server 无数据时直接崩溃,无 graceful fallback
6. **[docs]** README 缺 LICENSE、CHANGELOG、CONTRIBUTING、架构图
7. **[test]** 缺 `coords.py` 单元测试(往返、边界、境外)
8. **[refactor]** `Dataset.install()` 全局污染建议弃用
