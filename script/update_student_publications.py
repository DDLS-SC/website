#!/usr/bin/env python3
"""Fetch DOIs from ORCID and write a publications list into student JSON files.

Examples:
  python script/update_student_publications.py --dry-run
  python script/update_student_publications.py
  python script/update_student_publications.py --student student/2024/thanadol.sutantiwanichkul.json
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from orcid_dois import (  # noqa: E402
    ROOT,
    collect_student_dois,
    save_student,
    student_json_paths,
)


def merge_publications(existing: list | None, fetched: list[str]) -> list[str]:
    """Merge existing and fetched DOIs; sorted unique bare DOIs."""
    from orcid_dois import normalize_doi

    merged: set[str] = set()
    for value in list(existing or []) + fetched:
        doi = normalize_doi(value) if isinstance(value, str) else None
        if doi:
            merged.add(doi)
    return sorted(merged)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update student JSON publications fields from ORCID DOIs."
    )
    parser.add_argument(
        "--student",
        type=Path,
        help="Single student JSON path (relative to repo root or absolute).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report changes without writing files.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds to wait between ORCID requests (default: 0.2).",
    )
    args = parser.parse_args()

    paths = student_json_paths(args.student)
    updated = 0
    unchanged = 0
    skipped = 0
    errors = 0

    print(f"Scanning {len(paths)} student JSON file(s)")
    if args.dry_run:
        print("Dry-run: no files will be written")
    print()

    for path in paths:
        rel = path.relative_to(ROOT)
        data, dois, status = collect_student_dois(path)
        name = data.get("name") or path.stem

        if status == "no_orcid":
            new_pubs = merge_publications(data.get("publications"), [])
            # Still ensure the field exists as [] for students without ORCID.
            if data.get("publications") == new_pubs and "publications" in data:
                unchanged += 1
                print(f"- {rel}: {name} — no ORCID, publications unchanged")
            else:
                data["publications"] = new_pubs
                if args.dry_run:
                    print(f"- {rel}: {name} — would set publications: []")
                else:
                    save_student(path, data)
                    print(f"- {rel}: {name} — set publications: []")
                updated += 1
            skipped += 1
            continue

        if status.startswith("error:"):
            errors += 1
            print(f"- {rel}: {name} — ERROR {status.removeprefix('error:')}")
            if args.delay > 0:
                time.sleep(args.delay)
            continue

        new_pubs = merge_publications(data.get("publications"), dois)
        old_pubs = data.get("publications")
        if old_pubs == new_pubs:
            unchanged += 1
            print(f"- {rel}: {name} — {len(new_pubs)} DOI(s), unchanged")
        else:
            data["publications"] = new_pubs
            if args.dry_run:
                print(
                    f"- {rel}: {name} — would write {len(new_pubs)} DOI(s): "
                    f"{', '.join(new_pubs) or '(none)'}"
                )
            else:
                save_student(path, data)
                print(f"- {rel}: {name} — wrote {len(new_pubs)} DOI(s)")
            updated += 1

        if args.delay > 0:
            time.sleep(args.delay)

    print()
    print(
        f"Summary: {len(paths)} files, {updated} updated, "
        f"{unchanged} unchanged, {skipped} without ORCID, {errors} errors"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
