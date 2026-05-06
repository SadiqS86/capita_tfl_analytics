#!/usr/bin/env python3
"""Assert supervisor routing: metrics → Genie; contract/governance → RAG."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.supervisor import classify_route


def main() -> None:
    cases = [
        ("Are we hitting our SLAs this month?", "genie"),
        ("What does the contract say about penalty clauses?", "rag"),
        ("What are our reporting obligations under the contract?", "rag"),
    ]
    failed = False
    for q, expected in cases:
        got = classify_route(q)
        ok = got == expected
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {q!r} -> {got} (expected {expected})")
        if not ok:
            failed = True
    if failed:
        sys.exit(1)
    print("All routing checks passed.")


if __name__ == "__main__":
    main()
