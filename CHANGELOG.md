# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-09-06

针对 issue #4 代码审查的集中修复（A1–A4 / B1–B2 / C2 / M1–M7），以及同周期完成的工程规范重塑（密闭测试 + 质量工具链 + CI）。

### Fixed

- **A1**: 沿路切分/合并改接 `split_preview`/`split_commit` 与 `merge_preview`/`merge_commit` 零副作用协议，彻底修复 UI 点切分抛 `AttributeError` 阻断缺陷，且真正移除父围栏。
- **A2**: 删除 `territory_ir/session.py` 中 10 处重复的 `clear`/`to_geojson`/legacy `merge` 历史坏合并残留。
- **A4**: 服务端业务校验错误 (`ValueError`) 与内部异常分流，支持带异常类型可诊断输出。
- **B1**: 面积计算废弃广州硬编码 `0.92` 纬度修正因子，改为动态按环平均纬度计算 `cos` 因子。
- **B2**: GeoJSON `MultiPolygon` 导入改为多部件完整保留独立成围栏，消除静默丢失几何缺陷。
- **C2**: Web 对话工作台 LLM 回复执行 HTML 实体转义防范反射型 XSS，并修复制定/放弃后残留死按钮缺陷。
- **M1–M7**: 包含文件上下文管理器优化、路网哈希缓存、主入口数据目录判定保护、POST 请求体上限防护与 CBR 意图案例库封顶去重。
- **潜伏 bug**: `server.py` LLM 路径曾向 `parse_intent(fence_names: list)` 传入 dict，`join` 恒得到键名、真实围栏名从未送达；密闭测试桩绕过该路径未暴露。在 mypy 全量类型收敛中被发现并修复（`fix(types)` 提交）。

### Added

- 建立基于合成夹具 (`tests/synthetic_fixture.py`) 的纯内存全管线密闭测试体系，CI 环境脱离私有大体积数据秒级通过；本地大文件测试以 `local_data` 标记隔离。
- 引入 `ruff`、`black`、`mypy`、`pytest-cov` 现代质量工具链，`pyproject.toml` 作为统一配置源（含 numpy stub 的 mypy override、`fail_under = 35` 覆盖率门）。
- 建立 `.pre-commit-config.yaml` 本地提交流水线（whitespace/eof/large-files/ruff/black/mypy）与 `scripts/bootstrap.sh` 一键环境脚本。
- 新增 `.github/workflows/ci.yml`：Python 3.10 / 3.12 双版本矩阵自动化持续集成（lint + format + type + hermetic pytest + coverage）。
- 制定 `AGENTS.md`（智能体协作红线与环境漂移案例）、`CONTRIBUTING.md`（贡献流程）与 `CHANGELOG.md`（本文件）标准项目管理规范。
