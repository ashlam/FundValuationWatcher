#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
if [ ! -x "$(command -v "$PY")" ]; then
  echo "python3 未找到"; exit 1
fi
rm -rf build dist/FundValuationWatcher
if [ ! -d ".venv" ]; then
  "$PY" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install pyinstaller
pyinstaller -y FundValuationWatcher.spec
deactivate
echo "已生成 dist/FundValuationWatcher"
