"""수동 데이터 갱신 CLI.

Usage::

    python scripts/refresh_data.py --all
    python scripts/refresh_data.py --population --unsold
    python scripts/refresh_data.py --score      # 신호 재계산만
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH 에 추가 (스크립트 직접 실행시)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import ingest  # noqa: E402


STEP_FLAGS = ["population", "unsold", "price", "supply", "subscription", "news", "score"]


def main() -> int:
    parser = argparse.ArgumentParser(description="부동산 시장 데이터 갱신")
    parser.add_argument("--all", action="store_true", help="모든 단계 실행")
    for step in STEP_FLAGS:
        parser.add_argument(f"--{step}", action="store_true", help=f"{step} 단계만 실행")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.all:
        steps = STEP_FLAGS
    else:
        steps = [s for s in STEP_FLAGS if getattr(args, s)]
        if not steps:
            parser.print_help()
            return 1

    summary = ingest.run(steps)
    print("\n=== 수집 결과 ===")
    for k, v in summary.items():
        status = "OK" if v >= 0 else "ERROR"
        print(f"  {k:14s} : {v:>6d} rows  [{status}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
