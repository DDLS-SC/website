#!/usr/bin/env python3
"""Summarise DDLS students with no publication traces in their JSON profiles.

A student is treated as having no publication trace when ``publications`` is
missing or an empty list. Reasons are split into:
  - no_orcid: ORCID missing / "not available"
  - orcid_no_works: ORCID present but no DOIs found

Examples:
  python3 script/summarise_students_without_publications.py
  python3 script/summarise_students_without_publications.py --json research/students_without_publications.json
  python3 script/summarise_students_without_publications.py --csv research/students_without_publications.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from orcid_dois import (  # noqa: E402
    NOT_AVAILABLE,
    ROOT,
    parse_orcid,
    student_json_paths,
)


def classify(data: dict) -> str | None:
    """Return reason code if no publications, else None."""
    pubs = data.get("publications")
    if pubs:
        return None
    if parse_orcid(data.get("orcid")):
        return "orcid_no_works"
    return "no_orcid"


def collect() -> dict:
    rows: list[dict] = []
    for path in student_json_paths():
        data = json.loads(path.read_text(encoding="utf-8"))
        reason = classify(data)
        if reason is None:
            continue
        rows.append(
            {
                "name": data.get("name") or path.stem,
                "cohort": path.parent.name,
                "ra": data.get("ra") or "?",
                "university": data.get("university") or NOT_AVAILABLE,
                "status": data.get("status") or NOT_AVAILABLE,
                "orcid": data.get("orcid") or NOT_AVAILABLE,
                "email": data.get("email") or NOT_AVAILABLE,
                "reason": reason,
                "path": str(path.relative_to(ROOT)),
            }
        )

    by_reason = Counter(r["reason"] for r in rows)
    by_ra = Counter(r["ra"] for r in rows)
    by_cohort = Counter(r["cohort"] for r in rows)
    by_ra_reason = Counter((r["ra"], r["reason"]) for r in rows)
    by_cohort_reason = Counter((r["cohort"], r["reason"]) for r in rows)

    total_students = len(student_json_paths())
    return {
        "total_students": total_students,
        "without_publications": len(rows),
        "with_publications": total_students - len(rows),
        "by_reason": dict(by_reason),
        "by_ra": dict(by_ra),
        "by_cohort": dict(by_cohort),
        "by_ra_reason": {
            f"{ra}|{reason}": count for (ra, reason), count in sorted(by_ra_reason.items())
        },
        "by_cohort_reason": {
            f"{cohort}|{reason}": count
            for (cohort, reason), count in sorted(by_cohort_reason.items())
        },
        "students": sorted(rows, key=lambda r: (r["cohort"], r["ra"], r["name"])),
    }


def print_summary(report: dict, *, show_names: bool) -> None:
    total = report["total_students"]
    none = report["without_publications"]
    with_pubs = report["with_publications"]
    print(f"Students total:              {total}")
    print(f"With publication DOIs:       {with_pubs}")
    print(f"No publication traces:       {none} ({100 * none / total:.1f}%)")
    print()
    print("By reason:")
    for reason, count in sorted(report["by_reason"].items()):
        label = {
            "no_orcid": "no ORCID on profile",
            "orcid_no_works": "ORCID present, no DOIs in ORCID works",
        }.get(reason, reason)
        print(f"  {count:4d}  {label}")
    print()
    print("By research area:")
    for ra, count in sorted(report["by_ra"].items()):
        print(f"  {ra:4s}  {count:4d}")
    print()
    print("By intake cohort:")
    for cohort, count in sorted(report["by_cohort"].items()):
        print(f"  {cohort}  {count:4d}")
    print()
    print("By cohort × reason:")
    for key, count in report["by_cohort_reason"].items():
        cohort, reason = key.split("|", 1)
        print(f"  {cohort}  {reason:16s}  {count:4d}")

    if show_names:
        print()
        print("Students without publication traces:")
        for row in report["students"]:
            print(
                f"  [{row['cohort']}|{row['ra']}|{row['reason']}] "
                f"{row['name']}  ({row['path']})"
            )


def write_json(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "name",
        "cohort",
        "ra",
        "university",
        "status",
        "reason",
        "orcid",
        "email",
        "path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["students"]:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarise students with no publication traces in student JSON files."
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Write full report JSON (e.g. research/students_without_publications.json).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Write student list CSV (e.g. research/students_without_publications.csv).",
    )
    parser.add_argument(
        "--names",
        action="store_true",
        help="Print each student name in the terminal summary.",
    )
    args = parser.parse_args()

    report = collect()
    print_summary(report, show_names=args.names)

    if args.json:
        out = args.json if args.json.is_absolute() else ROOT / args.json
        write_json(report, out)
        print(f"\nWrote {out.relative_to(ROOT)}")
    if args.csv:
        out = args.csv if args.csv.is_absolute() else ROOT / args.csv
        write_csv(report, out)
        print(f"Wrote {out.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
