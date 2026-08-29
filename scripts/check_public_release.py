#!/usr/bin/env python3
"""Reject tracked paths that cannot be part of the code-only public release."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROHIBITED_PREFIXES = (
    "outputs/indexes/",
    "knowledge_base/",
    "evaluation/",
    "data/raw/",
    "data/processed/",
    "docs/superpowers/",
)
SECRET_FILENAMES = {
    ".env",
    "secrets.toml",
    "credentials.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".kdb")


def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _is_prohibited(path: str) -> bool:
    normalized = path.replace("\\", "/")
    name = Path(normalized).name.lower()
    return (
        normalized.startswith(PROHIBITED_PREFIXES)
        or "/.streamlit/" in f"/{normalized}"
        or name in SECRET_FILENAMES
        or name.endswith(SECRET_SUFFIXES)
    )


def check_repository(root: Path) -> list[str]:
    """Return sorted tracked paths that violate the public-release policy."""
    return sorted(path for path in _tracked_paths(root) if _is_prohibited(path))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = check_repository(root)
    if violations:
        print("公开发布检查失败：发现禁止公开的受跟踪路径：", file=sys.stderr)
        print(*violations, sep="\n", file=sys.stderr)
        return 1
    print("公开发布检查通过：未发现禁止公开的受跟踪路径。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
