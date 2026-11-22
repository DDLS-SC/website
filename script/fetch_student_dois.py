#!/usr/bin/env python3
"""Fetch publication DOIs for students via ORCID and print a summary.

Does not write files. Use update_student_publications.py to persist results.

Examples:
  python script/fetch_student_dois.py
  python script/fetch_student_dois.py --dry-run
  python script/fetch_student_dois.py --student student/2024/thanadol.sutantiwanichkul.json
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
    parse_orcid,
    student_json_paths,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch student publication DOIs from ORCID (read-only)."
    )
    parser.add_argument(
        "--student",
        type=Path,
        help="Single student JSON path (relative to repo root or absolute).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Same as default: fetch and print only; no files are written.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds to wait between ORCID requests (default: 0.2).",
    )
    args = parser.parse_args()

    paths = student_json_paths(args.student)
    with_orcid = 0
    with_dois = 0
    total_dois = 0
    skipped = 0
    errors = 0

    print(f"Scanning {len(paths)} student JSON file(s)")
    if args.dry_run:
        print("Dry-run: no files will be written")
    print()

    for path in paths:
        data, dois, status = collect_student_dois(path)
        name = data.get("name") or path.stem
        rel = path.relative_to(ROOT)

        if status == "no_orcid":
            skipped += 1
            print(f"- {rel}: {name} — no ORCID, skip")
            continue

        with_orcid += 1
        if status.startswith("error:"):
            errors += 1
            print(f"- {rel}: {name} — ERROR {status.removeprefix('error:')}")
        else:
            orcid = parse_orcid(data.get("orcid"))
            total_dois += len(dois)
            if dois:
                with_dois += 1
            print(f"- {rel}: {name} ({orcid}) — {len(dois)} DOI(s)")
            for doi in dois:
                print(f"    {doi}")

        if args.delay > 0:
            time.sleep(args.delay)

    print()
    print(
        f"Summary: {len(paths)} files, {with_orcid} with ORCID, "
        f"{with_dois} with DOIs ({total_dois} total), "
        f"{skipped} skipped (no ORCID), {errors} errors"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
