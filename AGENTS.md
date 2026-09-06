# AGENTS.md — Territory-IR 智能体开发规范

> 本规范约束所有在本仓库进行代码修改的 AI Coding Agents（Claude Code、Cursor、Copilot 等）。
> 动手修改前必须先通读本文件；与本文件冲突的口头指示一律以本文件为准。

## 1. 绝对红线 (Hard Rules)

### 1.1 数据隐私铁律 (C3 防线)

- **严禁**将以下任何内容加入 Git 跟踪：客户真实名称、门店经纬度坐标、未脱敏的 GeoJSON 围栏。
- 唯一例外（集成评审 #3 入册）：`data/gz/osm_refs.json`——公开 OSM 国道/省道编号几何参考（源自公开地图数据，无任何经销商 PII）。除该文件外，`data/` 下不得新增任何文件；确需入库须先按本条例外流程评审。
- **历史教训**：本仓库公开 Git 历史中曾混入真实经销商 GeoJSON（commit `901295c`，69 个文件）。即使事后删除文件，历史提交仍暴露数据。
- pre-commit 的 `check-added-large-files --maxkb=1000` 只能拦截大文件，**不能**替代人工遵守本条。
- 所有测试与文档示例必须使用 `tests/synthetic_fixture.py` 的合成数据（如 `测试经销商A/B`、虚构经纬度网格）。

### 1.2 测试密闭性

- 新增测试必须能在 `pytest -m "not local_data"` 下通过，不得依赖任何本地绝对路径或外部大文件。
- 确需本机真实地理数据的测试，必须在模块级标注：`pytestmark = pytest.mark.local_data`（CI 默认跳过）。

### 1.3 Session 隔离

- 单元测试中实例化 `Session` / `Copilot` 时，持久化目录必须使用 pytest 的 `tmp_path`。
- **严禁**读写仓库根目录的 `sessions/default.json`（那是真实用户工作状态）。

### 1.4 提交前验证门

每次提交前，以下四项必须全绿（即 pre-commit + CI 的本地预演）：

```bash
ruff check .
black --check .
mypy territory_ir/ server.py
pytest
```

## 2. 环境漂移防范（真实案例，非理论推演）

**同一道门禁在不同工具版本下会给出不同结果。** 本仓库本周期内实际踩过两个坑：

### 案例 A：numpy 2.5 stub × mypy `python_version = "3.10"`

- numpy 2.5 的类型 stub 使用了 Python 3.12 的 `type` 语句语法，`python_version = "3.10"` 的 mypy 解析时直接崩溃。
- 解法（已固化在 `pyproject.toml`）：对 numpy 静默跳过类型跟踪——

  ```toml
  [[tool.mypy.overrides]]
  module = "numpy.*"
  follow_imports = "skip"
  follow_imports_for_stubs = true
  ```

### 案例 B：ruff 0.4.4 × ruff 0.16 的 UP038 分歧

- pre-commit 钉死的 ruff 0.4.4 会对 `isinstance(x, (str, bytes))` 报 UP038，而开发环境安装的 ruff 0.16 **不再报**（规则行为已变）。两套工具对同一行代码判定相反。
- 解法：改写成版本无关的 PEP604 形式 `isinstance(x, str | bytes)`，新旧版本都接受。

### 沉淀规则

1. `.pre-commit-config.yaml` 的 rev 钉版必须与 `pyproject.toml` 的 `[project.optional-dependencies].dev` 版本范围保持同步；改一处必须改另一处。
2. 优先写版本无关的代码形式（如 PEP604 联合类型），不写依赖特定 lint 版本行为的代码。
3. 门禁结果互相矛盾时，**先怀疑工具版本漂移，而不是你的代码**。

## 3. mypy 调用盲区

- 目录式调用 `mypy territory_ir/` 与逐文件式调用 `mypy territory_ir/foo.py ...`（pre-commit 采用后者）**结果可能不同**。
- 实例：目录式曾漏报 `dataset.py` 中 2 个 JSON 键 `isinstance` 收窄错误，逐文件式才抓到（现已双双修复归零）。
- 结论：排查类型问题时以 pre-commit 的逐文件式结果为准；目录式绿灯**不能**作为免检依据。

## 4. 复杂度负债冻结区

以下区域已被代码审查定为高复杂度区，**严禁**在日常修改中扩大圈复杂度；重构前必须经专项设计评审：

| 位置 | 圈复杂度 | 状态 |
| --- | --- | --- |
| `territory_ir/dataset.py: Dataset._build` | 38 | 冻结 |
| `server.py: chat` / `server.py: make_handler` | 20 | 冻结 |

## 5. Git 提交规范

- 必须遵循 Conventional Commits：`feat:`、`fix:`、`refactor:`、`test:`、`style:`、`chore:`、`docs:`，可带 scope（如 `fix(types):`、`test(synthetic):`）。
- 每次逻辑变更小步提交，不要大包堆积；主题行一行说清，必要时正文补充动机与影响。
- `main` 受保护：改动一律走特性分支 + PR，CI 矩阵（Python 3.10 / 3.12）通过后方可合并。
