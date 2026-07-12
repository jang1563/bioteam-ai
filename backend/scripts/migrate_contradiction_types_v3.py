#!/usr/bin/env python3
"""Normalize contradiction_entry.types to canonical v3 taxonomy.

Usage:
  cd backend
  uv run python -m scripts.migrate_contradiction_types_v3 --dry-run
  uv run python -m scripts.migrate_contradiction_types_v3
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.db.database import create_db_and_tables, engine  # noqa: E402
from app.engines.ambiguity.taxonomy import normalize_type_list  # noqa: E402
from app.models.evidence import ContradictionEntry  # noqa: E402
from sqlmodel import Session, select  # noqa: E402


def run(dry_run: bool) -> int:
    create_db_and_tables()

    scanned = 0
    updated = 0
    unchanged = 0
    unmapped = 0

    with Session(engine) as session:
        entries = session.exec(select(ContradictionEntry)).all()
        for entry in entries:
            scanned += 1
            before = list(entry.types or [])
            after = normalize_type_list(before)

            if not before:
                unchanged += 1
                continue

            if not after:
                unmapped += 1
                continue

            if after == before:
                unchanged += 1
                continue

            updated += 1
            print(f"UPDATE {entry.id}: {before} -> {after}")
            if not dry_run:
                entry.types = after
                session.add(entry)

        if not dry_run and updated:
            session.commit()

    print("\nSummary")
    print(f"  scanned   : {scanned}")
    print(f"  updated   : {updated}")
    print(f"  unchanged : {unchanged}")
    print(f"  unmapped  : {unmapped}")
    print(f"  dry_run   : {dry_run}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
