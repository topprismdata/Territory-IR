# Engineering Standards & Hermetic Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Territory-IR into a production-grade, standardized Python project with hermetic CI (<5s), complete lint/type/coverage toolchains (ruff, black, mypy, pytest-cov), pre-commit gates, and formal project conventions (AGENTS.md, CONTRIBUTING.md, CHANGELOG.md).

**Architecture:** Extend synthetic data fixture to support full pipeline (roads, multi-fence, split/merge/Copilot); categorize tests into hermetic vs local-data; configure pyproject.toml as single source of truth for all tools; install pre-commit and GitHub Actions CI matrix; document workflows and freeze debt hotspots.

**Tech Stack:** Python 3.10/3.12, pytest, pytest-cov, ruff, black, mypy, pre-commit, GitHub Actions, shapely.

---

### Task 1: Extend Synthetic Dataset Fixture with Roads, Rivers, and Multiple Fences

**Files:**
- Modify: `tests/synthetic_fixture.py`
- Test: `tests/test_synthetic.py`

- [ ] **Step 1: Write test asserting synthetic dataset has roads, multiple fences, and road geometries**

In `tests/test_synthetic.py`, add `TestSyntheticRoadsAndFences`:

```python
class TestSyntheticRoadsAndFences:
    def test_roads_loaded(self, ds):
        assert len(ds.feat_names) >= 3
        assert "横向大道" in ds.feat_names
        assert "纵向大道" in ds.feat_names

    def test_multiple_fences_available(self, ds):
        fences = ds.reg["fences"]
        assert len(fences) >= 2
        names = [f["dealer"] for f in fences]
        assert "测试经销商A" in names
        assert "测试经销商B" in names

    def test_road_line_lookup(self, ds):
        from territory_ir.semantics import road_line_gcj
        line = road_line_gcj(ds, "横向大道")
        assert not line.is_empty
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/ghb/territory-ir && python3 -m pytest tests/test_synthetic.py::TestSyntheticRoadsAndFences -v
```
Expected: FAIL with `AssertionError: assert len(ds.feat_names) >= 3` (currently 0 roads in `osm.json`).

- [ ] **Step 3: Update `tests/synthetic_fixture.py` with roads, rivers, and multiple fences**

In `tests/synthetic_fixture.py`, update `osm_path` and `region_path` generation:

```python
    # 构造横穿网格的道路与河流 (WKT linestring)
    # 网格范围: lon 113.0-113.2, lat 22.8-23.2
    roads = [
        {"name": "横向大道", "cls": "primary", "wkt": "LINESTRING (113.0 23.0, 113.2 23.0)"},
        {"name": "纵向大道", "cls": "primary", "wkt": "LINESTRING (113.1 22.8, 113.1 23.2)"},
        {"name": "斜穿大道", "cls": "secondary", "wkt": "LINESTRING (113.0 22.8, 113.2 23.2)"},
    ]
    rivers = [
        {"name": "中心河", "wkt": "LINESTRING (113.0 22.95, 113.2 22.95)"}
    ]
    osm_path = tmp_path / "osm.json"
    osm_path.write_text(json.dumps({"roads": roads, "rivers": rivers, "adm6": []}, ensure_ascii=False))

    region_path = tmp_path / "region.json"
    # 两个测试围栏: 围栏A (右上), 围栏B (左上)
    fence_a = {
        "area_id": "test-1", "dealer": "测试经销商A",
        "rings": [[[113.1, 23.0], [113.2, 23.0], [113.2, 23.2], [113.1, 23.2], [113.1, 23.0]]],
        "area_km2": 3.0,
    }
    fence_b = {
        "area_id": "test-2", "dealer": "测试经销商B",
        "rings": [[[113.0, 23.0], [113.1, 23.0], [113.1, 23.2], [113.0, 23.2], [113.0, 23.0]]],
        "area_km2": 3.0,
    }
    region_path.write_text(json.dumps({"fences": [fence_a, fence_b], "stores": []}, ensure_ascii=False))
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/ghb/territory-ir && python3 -m pytest tests/test_synthetic.py -v
```
Expected: PASS (all tests in `test_synthetic.py` pass).

- [ ] **Step 5: Commit**

```bash
cd /Users/ghb/territory-ir && git add tests/synthetic_fixture.py tests/test_synthetic.py
git commit -m "test(synthetic): 扩充合成路网、河流与多围栏夹具"
```

---

### Task 2: Hermetic Integration Tests for Pipeline & Pytest Marker Configuration

**Files:**
- Create: `tests/test_synthetic_pipeline.py`
- Modify: `tests/test_gz_smoke.py`
- Modify: `tests/test_server_split.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Configure `local_data` marker in `pyproject.toml`**

Add pytest configuration to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "local_data: 依赖本机大体积真实地理数据的测试（CI默认跳过）",
]
```

- [ ] **Step 2: Add `@pytest.mark.local_data` to unhermetic tests**

In `tests/test_gz_smoke.py`:
```python
pytestmark = pytest.mark.local_data
```

In `tests/test_server_split.py`:
```python
pytestmark = pytest.mark.local_data
```

- [ ] **Step 3: Create `tests/test_synthetic_pipeline.py` testing split, merge, and Copilot in memory**

```python
"""合成数据集上的全管线测试（完全密闭，不依赖任何本地私有数据，可在任何机器与CI秒级运行）。"""
import tempfile
from pathlib import Path
import pytest

from tests.synthetic_fixture import make_synthetic_dataset
from territory_ir.dataset import Dataset
from territory_ir.session import Session
from server import Copilot


@pytest.fixture
def syn_env(tmp_path):
    data_dir = make_synthetic_dataset(tmp_path)
    ds = Dataset(
        data_dir=str(data_dir),
        roadnet_path=str(data_dir / "roadnet.geojson"),
        streets_path=str(data_dir / "streets.geojson"),
        osm_path=str(data_dir / "osm.json"),
        name="synthetic",
    )
    sess_dir = tmp_path / "sessions"
    sess = Session(ds, persist_dir=str(sess_dir))
    return ds, sess, data_dir, sess_dir


def test_synthetic_session_import_and_describe(syn_env):
    ds, sess, _, _ = syn_env
    ring = [[113.1, 23.0], [113.2, 23.0], [113.2, 23.2], [113.1, 23.2], [113.1, 23.0]]
    fence = sess.import_ring("测试导入", ring)
    assert fence["name"] == "测试导入"
    assert fence["km2"] > 0
    assert len(fence["pieces"]) > 0


def test_synthetic_session_merge(syn_env):
    ds, sess, _, _ = syn_env
    # 导入两个相邻围栏
    ring1 = [[113.0, 23.0], [113.1, 23.0], [113.1, 23.2], [113.0, 23.2], [113.0, 23.0]]
    ring2 = [[113.1, 23.0], [113.2, 23.0], [113.2, 23.2], [113.1, 23.2], [113.1, 23.0]]
    sess.import_ring("左块", ring1)
    sess.import_ring("右块", ring2)
    assert len(sess.fences) == 2

    # 零副作用预览
    merged = sess.merge_preview(["左块", "右块"])
    assert "左块+右块" in merged["name"]
    assert len(sess.fences) == 2  # 未变

    # 提交合并
    sess.merge_commit()
    assert len(sess.fences) == 1
    assert "左块+右块" in sess.fences[0]["name"]


def test_synthetic_copilot_chat_and_api(syn_env, monkeypatch):
    ds, _, data_dir, sess_dir = syn_env
    # 模拟 Dataset.guangzhou 指向合成数据目录，验证 Copilot 真实对话分发
    monkeypatch.setattr(Dataset, "guangzhou", classmethod(lambda cls, data_dir: ds))
    cp = Copilot(data_dir=data_dir, persist_dir=sess_dir)
    ring = [[113.0, 23.0], [113.2, 23.0], [113.2, 23.2], [113.0, 23.2], [113.0, 23.0]]
    cp.sess.import_ring("总区", ring)

    # 验证描述指令
    r_desc = cp.chat("描述 总区")
    assert "总区" in r_desc["reply"]

    # 验证清空指令
    r_clear = cp.chat("清空全部")
    assert "已清空" in r_clear["reply"]
    assert len(cp.sess.fences) == 0
```

- [ ] **Step 4: Run hermetic test suite and verify speed (<5s)**

Run:
```bash
cd /Users/ghb/territory-ir && python3 -m pytest -m "not local_data" -v
```
Expected: PASS (All hermetic tests pass within seconds).

- [ ] **Step 5: Commit**

```bash
cd /Users/ghb/territory-ir && git add pyproject.toml tests/test_synthetic_pipeline.py tests/test_gz_smoke.py tests/test_server_split.py
git commit -m "test(hermetic): 建立纯内存全管线测试并标记本地大文件测试"
```

---

### Task 3: Quality Toolchain Configuration in `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Check dependencies in `pyproject.toml`**

Ensure `dev` includes `pytest`, `pytest-cov`, `ruff`, `black`, `mypy`.

- [ ] **Step 2: Add complete configurations for ruff, black, mypy, and coverage to `pyproject.toml`**

Append to `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-cov>=5",
    "ruff>=0.4",
    "black>=24.4",
    "mypy>=1.10",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "local_data: 依赖本机大体积真实地理数据的测试（CI默认跳过）",
]
addopts = "-m 'not local_data'"

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
    "RUF001", "RUF002", "RUF003",  # 中文全角标点与文本符号误报
    "E501",                        # 格式化由 black 统一负责，不硬报超长
    "B008",                        # 函数默认参数调用
]

[tool.black]
line-length = 88
target-version = ["py310"]

[tool.mypy]
python_version = "3.10"
ignore_missing_imports = true
check_untyped_defs = true
warn_redundant_casts = true
warn_unused_ignores = true

[tool.coverage.run]
source = ["territory_ir", "server"]
omit = [
    "tests/*",
    "scripts/*",
    "**/__pycache__/*",
]

[tool.coverage.report]
fail_under = 35.0
show_missing = true
skip_covered = false
```

- [ ] **Step 3: Verify pytest-cov runs using new pyproject options**

Run:
```bash
cd /Users/ghb/territory-ir && python3 -m pytest --cov=territory_ir --cov=server --cov-report=term
```
Expected: PASS with terminal coverage report displayed.

- [ ] **Step 4: Commit**

```bash
cd /Users/ghb/territory-ir && git add pyproject.toml
git commit -m "chore(config): pyproject.toml 集中化配置 ruff/black/mypy/pytest-cov"
```

---

### Task 4: Global Code Formatting & Blame Ignore Configuration

**Files:**
- Modify: All `.py` files in `territory_ir/`, `tests/`, `server.py`
- Create: `.git-blame-ignore-revs`

- [ ] **Step 1: Run ruff check and autofix**

Run:
```bash
cd /Users/ghb/territory-ir && python3 -m ruff check --fix .
```
Expected: Autofixes imports, pyupgrade, comprehension idioms.

- [ ] **Step 2: Run black formatter across repository**

Run:
```bash
cd /Users/ghb/territory-ir && python3 -m black .
```
Expected: Reformats files to 88-column standard.

- [ ] **Step 3: Run hermetic test suite to confirm zero regressions from formatting**

Run:
```bash
cd /Users/ghb/territory-ir && python3 -m pytest
```
Expected: All tests PASS.

- [ ] **Step 4: Commit formatting changes**

```bash
cd /Users/ghb/territory-ir && git add -u
git commit -m "style: black + ruff 全仓代码规范化重排"
```

- [ ] **Step 5: Record format commit hash in `.git-blame-ignore-revs`**

```bash
cd /Users/ghb/territory-ir
HASH=$(git rev-parse HEAD)
echo "# 全仓 black + ruff 样式重排提交，在 git blame 中忽略" > .git-blame-ignore-revs
echo "$HASH" >> .git-blame-ignore-revs
git add .git-blame-ignore-revs
git commit -m "chore: 添加 .git-blame-ignore-revs 避免格式化污染 blame"
```

---

### Task 5: Setup Pre-Commit Hooks & Bootstrap Script

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `scripts/bootstrap.sh`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

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
        args: ['--maxkb=1000']

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

- [ ] **Step 2: Write `scripts/bootstrap.sh` for one-command developer setup**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "==> 安装项目开发依赖..."
pip install -e ".[dev]"

echo "==> 安装 git pre-commit 钩子..."
if command -v pre-commit >/dev/null 2>&1; then
    pre-commit install
    echo "✓ pre-commit 钩子安装成功"
else
    echo "⚠ pre-commit 未找到，请先 pip install pre-commit"
fi

echo "==> 配置 git blame 忽略格式化提交..."
git config blame.ignoreRevsFile .git-blame-ignore-revs || true

echo "==> 运行快速密闭测试验证环境..."
pytest
echo "✓ 开发环境就绪！"
```

- [ ] **Step 3: Make `scripts/bootstrap.sh` executable and test it**

Run:
```bash
cd /Users/ghb/territory-ir && chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/ghb/territory-ir && git add .pre-commit-config.yaml scripts/bootstrap.sh
git commit -m "ci(pre-commit): 建立本地 pre-commit 门禁与 bootstrap 一键脚本"
```

---

### Task 6: Setup GitHub Actions CI Workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  lint-and-test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.12"]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Ruff Lint Check
        run: ruff check .

      - name: Black Format Check
        run: black --check .

      - name: Mypy Type Check
        run: mypy territory_ir/ server.py

      - name: Run Hermetic Pytest with Coverage
        run: |
          pytest --cov=territory_ir --cov=server --cov-report=xml --cov-report=term-missing

      - name: Publish Coverage Summary
        if: matrix.python-version == '3.10'
        run: |
          echo "### 📊 测试覆盖率报告 (Python ${{ matrix.python-version }})" >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
          coverage report >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
```

- [ ] **Step 2: Dry-run workflow steps locally**

Run:
```bash
cd /Users/ghb/territory-ir
ruff check .
black --check .
mypy territory_ir/ server.py
pytest --cov=territory_ir --cov=server
```
Expected: All four commands succeed with code 0.

- [ ] **Step 3: Commit**

```bash
cd /Users/ghb/territory-ir && git add .github/workflows/ci.yml
git commit -m "ci(github): 添加 GitHub Actions 双版本 (3.10/3.12) 自动化持续集成流水线"
```

---

### Task 7: Establish Project Conventions (AGENTS.md, CONTRIBUTING.md, CHANGELOG.md)

**Files:**
- Create: `AGENTS.md`
- Create: `CONTRIBUTING.md`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Create `AGENTS.md` specifying AI agent operational constraints**

```markdown
# AGENTS.md — Territory-IR 智能体开发规范

> 本规范约束所有在本仓库进行代码修改的 AI Coding Agents（Claude Code, Cursor, Copilot 等）。
> 修改前必须先阅读本文件。

## 1. 绝对红线 (Hard Rules)
1. **数据隐私铁律 (防范 C3 再次发生)**: 严禁将客户真实名称、门店经纬度、未脱敏 GeoJSON 围栏加入 Git 跟踪。测试必须使用 `SyntheticDataset`。
2. **测试驱动与密闭性**: 任何几何算法或 Session 状态修改，必须同步补齐基于合成夹具的单测。绝不允许新写依赖本地绝对路径的不可移植测试。
3. **Session 隔离**: 单元测试中实例化 `Session`/`Copilot` 时，必须使用临时目录 (`tmp_path`)，严禁读写根目录 `sessions/default.json`。
4. **验证门红线**: 每次提交前必须确保 `ruff check .`、`black --check .`、`pytest` 100% 绿灯通过。

## 2. 冻结负债清单 (Complexity Debt)
以下区域已被代码审查定级为高复杂度区，重构前必须经专项方案评审，严禁在日常修改中无故扩大复杂度：
- `territory_ir/dataset.py: _build` (圈复杂度 38)
- `server.py: make_handler / chat` (圈复杂度 20)

## 3. Git 提交规范
- 必须遵循 Conventional Commits：`feat:`, `fix:`, `refactor:`, `test:`, `style:`, `chore:`, `docs:`。
- 每次逻辑变更小步提交，不要大包堆积。
```

- [ ] **Step 2: Create `CONTRIBUTING.md` for human and agent developers**

```markdown
# 贡献指南 (Contributing to Territory-IR)

感谢参与 Territory-IR 的开发与维护！

## 快速上手
1. 安装 Python 3.10 或更高版本。
2. 运行一键配置脚本：
   ```bash
   ./scripts/bootstrap.sh
   ```
3. 运行测试套件：
   ```bash
   pytest
   ```

## 本地代码检查
提交前可手动运行全套静态检查：
```bash
ruff check --fix .
black .
mypy territory_ir/ server.py
pytest --cov
```

## 测试规范
- 默认测试集是**完全密闭的合成测试**，可在零配置下几秒内完成。
- 若需跑本地真实广州数据，使用：
  ```bash
  pytest -m "local_data"
  ```
```

- [ ] **Step 3: Create `CHANGELOG.md` starting at `v0.3.0`**

```markdown
# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-09-06

### Fixed
- **A1**: 沿路切分/合并改接 `split_preview`/`split_commit` 与 `merge_preview`/`merge_commit` 零副作用协议，彻底修复 UI 点切分抛 `AttributeError` 阻断缺陷，且真正移除父围栏。
- **A2**: 删除 `territory_ir/session.py` 中 10 处重复的 `clear`/`to_geojson`/legacy `merge` 历史坏合并残留。
- **A4**: 服务端业务校验错误 (`ValueError`) 与内部异常分流，支持带异常类型可诊断输出。
- **B1**: 面积计算废弃广州硬编码 `0.92` 纬度修正因子，改为动态按环平均纬度计算 `cos` 因子。
- **B2**: GeoJSON `MultiPolygon` 导入改为多部件完整保留独立成围栏，消除静默丢失几何缺陷。
- **C2**: Web 对话工作台 LLM 回复执行 HTML 实体转义防范反射型 XSS，并修复制定/放弃后残留死按钮缺陷。
- **M1-M7**: 包含文件上下文管理器优化、路网哈希缓存、主入口数据目录判定保护、POST 请求体上限防护与 CBR 意图案例库封顶去重。

### Added
- 建立基于 `SyntheticDataset` 的纯内存全管线密闭测试体系，CI 环境脱离私有大体积数据秒级通过。
- 引入 `ruff`, `black`, `mypy`, `pytest-cov` 现代质量工具链与 `pyproject.toml` 统一配置。
- 建立 `.pre-commit-config.yaml` 本地提交流水线与 `.github/workflows/ci.yml` (Python 3.10/3.12 矩阵) 自动化持续集成。
- 制定 `AGENTS.md`、`CONTRIBUTING.md` 与 `CHANGELOG.md` 标准项目管理规范。
```

- [ ] **Step 4: Verify all docs have no broken links or missing files**

Run:
```bash
cd /Users/ghb/territory-ir && ls -la AGENTS.md CONTRIBUTING.md CHANGELOG.md
```
Expected: All three files exist.

- [ ] **Step 5: Commit**

```bash
cd /Users/ghb/territory-ir && git add AGENTS.md CONTRIBUTING.md CHANGELOG.md
git commit -m "docs(norm): 制定 AGENTS 协作规范、CONTRIBUTING 贡献指南与 CHANGELOG 历史记录"
```
