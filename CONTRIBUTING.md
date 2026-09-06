# 贡献指南 (Contributing to Territory-IR)

感谢参与 Territory-IR 的开发与维护！人人与 AI Agent 一体适用。

## 快速上手

1. 安装 Python 3.10 或更高版本（3.12 亦可，CI 双版本矩阵验证）。
2. 运行一键配置脚本（创建 venv、`pip install -e ".[dev]"`、安装 pre-commit 钩子）：

   ```bash
   ./scripts/bootstrap.sh
   ```

3. 跑一遍测试套件确认环境就绪：

   ```bash
   pytest
   ```

## 本地验证门（提交前四项全绿）

```bash
ruff check .
black --check .
mypy territory_ir/ server.py
pytest
```

提交时 pre-commit 会自动复跑同款检查；`mypy` 请注意逐文件式调用与目录式调用的结果差异（详见 `AGENTS.md` §3）。

## 测试规范

- 默认 `pytest`（`pyproject.toml` 已配 `addopts = "-m 'not local_data'"`）只跑**密闭合成测试**：零配置、秒级、与 CI 完全同款。
- 需要本机真实广州大体积数据时手动指定：

  ```bash
  pytest -m "local_data"
  ```

- 新增测试默认必须密闭（合成夹具 + `tmp_path`）；确需真实数据的，模块级加 `pytestmark = pytest.mark.local_data`，并遵守 `AGENTS.md` §1 的数据隐私红线。

## 分支与 PR 规范

- `main` 受保护，**禁止**直接 push。
- 特性分支命名前缀：`feat/`、`fix/`、`docs/`、`test/` 等。
- 一律通过 PR 合并；PR 必须通过 CI 矩阵（Python 3.10 与 3.12 上的 ruff / black / mypy / pytest+coverage）。
- 提交信息遵循 Conventional Commits（见 `AGENTS.md` §5）。
