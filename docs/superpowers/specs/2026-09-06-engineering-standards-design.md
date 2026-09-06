# Territory-IR 工程规范重塑与密闭化测试设计规范

- **状态**: 已批准 (Approved)
- **日期**: 2026-09-06
- **设计人**: TopPrism / AI Team
- **范围**: `topprismdata/Territory-IR` 单仓库
- **基线版本**: `v0.3.0`

---

## 1. 背景与目标

### 1.1 现状问题
在 2026-09-06 代码审查（Issue #4）后，虽已完成 A1–A4 / B1–B2 / C2 等关键缺陷修复，但工程规范层仍处于**严重缺失**状态：
1. **零 CI 与门禁**: 仓库无 `.github`、无 `pre-commit`，提交直接进 main，测试与语法全靠自觉。
2. **零统一代码风格与类型配置**: 无 `[tool.ruff]`、无 `[tool.black]`、无 `[tool.mypy]`；审查报告确认有 159 处真实格式违规与 13 文件需重排。
3. **测试严重不密闭**: 40 个已有测试中，核心管线测试（`test_gz_smoke.py`、`test_server_split.py`）依赖本机 `/Users/ghb` 的外部私有数据与 `~/Downloads` 真实路网，换机器或在 CI 环境下全部跳过。**编译、切分、合并的主线在持续集成环境下实为零覆盖**。
4. **无开发行为规范**: 缺少 `AGENTS.md`（约束 AI 编码行为）、`CONTRIBUTING.md`（约束人类贡献）、`CHANGELOG.md`（追踪版本变更）。

### 1.2 改造目标
1. **测试密闭化**: 构建纯内存、零外部依赖的合成测试数据集（`SyntheticDataset`），使主线管线（编译、拆分、合并、描述、Copilot 交互）在 CI 下以秒级（<5 秒）全绿跑通。
2. **工具链统一**: 在 `pyproject.toml` 中配置 `ruff`、`black`、`mypy`、`pytest-cov`，压制全角标点误报，确立基线棘轮门槛（ratchet）。
3. **自动化门禁**: 建立 `.pre-commit-config.yaml`（本地）与 `.github/workflows/ci.yml`（Python 3.10/3.12 双版本矩阵），PR 必绿才可合并。
4. **规约层补齐**: 落地 `AGENTS.md`（含数据防泄露铁律与复杂度负债清单）、`CONTRIBUTING.md`、`CHANGELOG.md`，规范化版本发布。

---

## 2. 测试架构设计（金字塔重塑）

### 2.1 测试分层定义
系统测试分为三层，CI 默认只执行前两层（确保快速、确定、密闭）：

```
┌─────────────────────────────────────────────────────────────┐
│ Level 3: 本地真实数据冒烟 (Local Smoke)                      │
│ - 标识: @pytest.mark.local_data                            │
│ - 范围: tests/test_gz_smoke.py, tests/test_server_split.py   │
│ - 运行时间: ~140s+                                          │
│ - 触发条件: 显式传参 pytest -m "local_data"                  │
├─────────────────────────────────────────────────────────────┤
│ Level 2: 合成集成测试 (Synthetic Integration) - CI 核心      │
│ - 标识: 默认执行                                            │
│ - 范围: tests/test_synthetic.py, tests/test_server_api.py    │
│ - 载体: tests/synthetic_fixture.py (扩建为完整 SyntheticDS) │
│ - 覆盖: compile_fence / split / merge / describe / Copilot │
│ - 运行时间: < 3s                                            │
├─────────────────────────────────────────────────────────────┤
│ Level 1: 纯算法单元测试 (Unit Tests)                         │
│ - 范围: tests/test_coords.py, tests/test_intents.py          │
│ - 覆盖: GCJ/WGS 坐标转换、意图正则快路径、CBR 案例去重与封顶  │
│ - 运行时间: < 0.5s                                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 `SyntheticDataset` 扩建规范 (`tests/synthetic_fixture.py`)
为了在不加载外部几十兆 GeoJSON 的前提下测全管线，扩展合成夹具：
1. **空间网格**: 20×20 规则父地块（WGS 坐标系），覆盖 `[113.30, 23.10]` 到 `[113.35, 23.15]`，自动派生 `STRtree` 与四级拓扑。
2. **区划街道面**: 3 个连续街道多边形（"天河南街道"、"冼村街道"、"猎德街道"），具备真实相交与跨界切片特性。
3. **地物道路**: 4 条基准折线道路：
   - 道路 A ("天河路"): 东西向线性穿透
   - 道路 B ("广州大道"): 南北向线性穿透
   - 道路 C ("黄埔大道"): 东西向平行线（供 corridor 走廊判定）
   - 道路 D ("斜穿大道"): 对角线（供 enclosed 三角围合与弯曲道路分堆判定）
4. **几何边缘用例**:
   - 带洞多边形（Hole Polygon）
   - 多部件多边形（MultiPolygon 2–3 块独立面）
   - 极小碎多边形（验证面积阈值过滤逻辑）
5. **Session 实例隔离**:
   - `SyntheticSession` 强制将 `persist_dir` 导向 pytest 的 `tmp_path`，绝对禁止触碰 `sessions/default.json`。

### 2.3 pytest 标记配置 (`pyproject.toml`)
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "local_data: 依赖本机大体积真实地理数据的测试（CI 默认跳过）",
]
addopts = "-m 'not local_data'"
```

---

## 3. 代码质量工具链设计

### 3.1 配置文件集中化 (`pyproject.toml`)

#### Ruff 配置
```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "RUF001", "RUF002", "RUF003",  # 中文全角标点误报（必须忽略）
    "E501",                        # 超长行先由 black 控制，不作死门禁
    "B008",                        # 函数默认参数中的调用（兼容旧代码）
]
```

#### Black 配置
```toml
[tool.black]
line-length = 88
target-version = ["py310"]
```

#### Mypy 配置（宽松渐进模式）
```toml
[tool.mypy]
python_version = "3.10"
ignore_missing_imports = true
check_untyped_defs = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_return_any = false
no_implicit_optional = false
```

#### Coverage 配置与棘轮机制
```toml
[tool.coverage.run]
source = ["territory_ir", "server"]
omit = [
    "tests/*",
    "scripts/*",
    "**/__pycache__/*",
]

[tool.coverage.report]
fail_under = 45.0  # 初始基线设为 45%，后续随测试完善只能递增（棘轮策略）
show_missing = true
skip_covered = false
```

### 3.2 全仓一次性格式化策略
为防止历史格式问题分散在各个业务提交中，本计划单独安排一次全局格式化：
- 执行 `black .`
- 执行 `ruff check --fix .`
- 独立提交 `style: black + ruff 全仓代码规范化重排`。

---

## 4. 自动化门禁体系设计

### 4.1 本地门禁 (`.pre-commit-config.yaml`)
```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=1000']  # 防范 C3 业务数据大文件误提交

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: ["shapely>=2.0", "numpy>=1.24"]
        args: [--config-file=pyproject.toml]
```

### 4.2 CI 工作流 (`.github/workflows/ci.yml`)
```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-level: build
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint with Ruff
        run: ruff check .

      - name: Format check with Black
        run: black --check .

      - name: Type check with Mypy
        run: mypy territory_ir/ server.py

      - name: Run Hermetic Test Suite
        run: |
          pytest -m "not local_data" \
            --cov=territory_ir \
            --cov=server \
            --cov-report=xml \
            --cov-report=term-missing

      - name: Upload coverage to GitHub Summary
        if: matrix.python-version == '3.10'
        run: |
          echo "### 覆盖率概况" >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
          coverage report >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
```

---

## 5. 项目规约与协作文档设计

### 5.1 `AGENTS.md` (AI 研发协作契约)
设立 4 条绝对红线（Hard Rules）：
1. **数据隐私铁律 (C3 防范)**: 严禁将客户真实名称、门店经纬度、未脱敏的 GeoJSON 围栏加入 Git 跟踪。测试必须使用 `SyntheticDataset`。
2. **测试驱动与密闭性**: 任何几何算法或 Session 状态修改，必须同步补齐基于合成夹具的单测，绝不允许新写依赖本地数据路径的不可移植测试。
3. **Session 隔离**: 单元测试中实例化 `Session`/`Copilot` 时，必须使用临时目录，严禁读写根目录 `sessions/default.json`。
4. **负债清单登记**: `territory_ir/dataset.py: _build` (复杂度 38) 与 `server.py: chat` (复杂度 20) 列为冻结负债区，不得无故扩大复杂度。

### 5.2 `CONTRIBUTING.md`
包含：
- 一键开发初始化命令：`pip install -e ".[dev]" && pre-commit install`
- 统一提交规范：Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `style:`, `chore:`)
- 分支与 PR 规范：main 分支受保护，改动走 PR + 必须跑通 CI 矩阵。

### 5.3 `CHANGELOG.md`
以 Keep a Changelog 格式建立，追溯至 `v0.3.0`，完整收录本次审查修复（A1–A4, B1–B2, C2, M1–M7）与工程化基线重塑。

---

## 6. 实施路线图（4 阶段，信号优先）

- **Phase 1: 测试密闭化与合成夹具扩建**
  - 扩充 `tests/synthetic_fixture.py`
  - 将编译/拆分/合并/Copilot 逻辑完全覆盖于合成数据（新增 `tests/test_server_api.py`）
  - 给真实数据测试打上 `@pytest.mark.local_data` 标签
  - 验证：脱离本地数据在无网/干净目录下 `pytest -m "not local_data"` 100% 通过（<3s）。
- **Phase 2: 代码质量基线配置与一次性格式化**
  - 更新 `pyproject.toml`（写入 ruff, black, mypy, coverage, pytest 标记）
  - 执行全局格式化与坏味道清理，作为单一提交落盘
  - 跑一次全量覆盖率，锁定 `fail_under` 初始基准值。
- **Phase 3: 自动化门禁落地**
  - 编写 `.pre-commit-config.yaml`
  - 编写 `.github/workflows/ci.yml`
  - 本地验证 `pre-commit run --all-files` 100% 绿色。
- **Phase 4: 规范文档与发布沉淀**
  - 编写 `AGENTS.md`、`CONTRIBUTING.md`、`CHANGELOG.md`
  - 校验全部链接与引用，提交推送。

---

## 7. 风险与回滚方案

| 风险项 | 应对策略 |
|---|---|
| Black 全局格式化产生大量 git diff，影响后续 blame | 建立 `.git-blame-ignore-revs` 文件，将格式化提交 SHA 写入，消除 blame 污染。 |
| Mypy 在宽松模式下仍有少量无法轻易解决的类型报错 | 采用局部 `# type: ignore` 并注明原因，坚决不降级为完全关闭检查。 |
| CI runner 在 GitHub 侧下载依赖超时 | 启用 `actions/setup-python` 的 pip 缓存机制；精简 dev 依赖列表。 |
