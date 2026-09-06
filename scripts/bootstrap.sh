#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "⚠ 警告：未检测到激活的 Python 虚拟环境（VIRTUAL_ENV 未设置），将使用系统/当前 python3。" >&2
    echo "  建议先激活 venv，例如：source .venv/bin/activate" >&2
fi

echo "==> 安装项目开发依赖..."
python3 -m pip install -e ".[dev]"

echo "==> 安装 git pre-commit 钩子..."
if ! command -v pre-commit >/dev/null 2>&1; then
    echo "✗ 致命错误：pre-commit 未安装（应随 .[dev] extras 提供），中止。" >&2
    echo "  请先运行：python3 -m pip install -e \".[dev]\" 后重试。" >&2
    exit 1
fi
pre-commit install
echo "✓ pre-commit 钩子安装成功"

echo "==> 配置 git blame 忽略格式化提交..."
git config blame.ignoreRevsFile .git-blame-ignore-revs

echo "==> 运行快速密闭测试验证环境..."
pytest
echo "✓ 开发环境就绪！"
