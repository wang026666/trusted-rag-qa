from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.retriever.index_integrity import inspect_index_directory


def main() -> int:
    health = inspect_index_directory(PROJECT_ROOT / "outputs" / "indexes")
    if not health["ready"]:
        details = "；".join(str(error) for error in health["errors"])
        print(f"预构建索引校验失败：{details}", file=sys.stderr)
        return 1
    app_path = PROJECT_ROOT / "app" / "streamlit_app.py"
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
