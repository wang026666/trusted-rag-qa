import importlib.util
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "check_public_release.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_public_release", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _init_git_repo(root: Path, tracked_paths: list[str]) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for relative_path in tracked_paths:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)


def test_rejects_prebuilt_data_and_secret_paths(tmp_path: Path) -> None:
    _init_git_repo(
        tmp_path,
        [
            "src/app.py",
            "outputs/indexes/index.json",
            "knowledge_base/manifest.jsonl",
            "evaluation/qa_eval.jsonl",
            "secrets.toml",
            "config/deploy.pem",
        ],
    )

    violations = _load_module().check_repository(tmp_path)

    assert violations == [
        "config/deploy.pem",
        "evaluation/qa_eval.jsonl",
        "knowledge_base/manifest.jsonl",
        "outputs/indexes/index.json",
        "secrets.toml",
    ]


def test_allows_source_code_and_public_release_documents(tmp_path: Path) -> None:
    _init_git_repo(
        tmp_path,
        [
            "src/app.py",
            "scripts/build_index.py",
            "tests/test_app.py",
            "README.md",
            "DATA_AND_SECURITY.md",
            "LICENSE",
        ],
    )

    assert _load_module().check_repository(tmp_path) == []
