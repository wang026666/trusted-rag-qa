from __future__ import annotations

import re


def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    alnum = re.findall(r"[a-z0-9_]+", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    cjk_bigrams = [a + b for a, b in zip(cjk, cjk[1:])]
    return alnum + cjk + cjk_bigrams
