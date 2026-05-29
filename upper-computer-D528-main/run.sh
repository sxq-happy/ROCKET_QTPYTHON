#!/usr/bin/env bash
# 使用项目本地 venv 运行小火炬上位机
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/venv"
PYTHON="$VENV/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "未找到虚拟环境: $VENV" >&2
  echo "请先在项目目录下创建 venv: python3 -m venv venv && venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

export QT_API=pyside6
cd "$ROOT"
exec "$PYTHON" main.py "$@"
