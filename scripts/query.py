from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import get_settings
from src.generator.llm import create_llm_from_settings
from src.generator.unified_engine import build_unified_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask a question against the local index.")
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    llm = create_llm_from_settings(settings)
    engine = build_unified_engine(settings, llm=llm)
    result = engine.answer(args.question, top_k=args.top_k)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
