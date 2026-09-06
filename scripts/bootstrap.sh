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
