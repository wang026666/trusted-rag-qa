#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

for required_file in outputs/indexes/bm25_index.json outputs/indexes/vector_index.json; do
    if [ ! -s "$required_file" ]; then
        echo "缺少必要的索引文件：$required_file" >&2
        exit 1
    fi
done

exec "${PYTHON_BIN:-python}" scripts/run_app.py
