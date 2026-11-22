"""Helpers for fetching publication DOIs from the ORCID public API."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

ORCID_RE = re.compile(
    r"(?:https?://(?:orcid\.org|www\.orcid\.org)/)?"
    r"(?P<id>\d{4}-\d{4}-\d{4}-\d{3}[\dX])\s*$",
    re.IGNORECASE,
)
DOI_RE = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)

ROOT = Path(__file__).resolve().parents[1]
STUDENT_ROOT = ROOT / "student"
NOT_AVAILABLE = "not available"


def parse_orcid(value: str | None) -> str | None:
    """Return a bare ORCID iD, or None if missing/invalid."""
    if not value or value.strip().lower() == NOT_AVAILABLE:
        return None
    match = ORCID_RE.search(value.strip())
    return match.group("id").upper() if match else None


def normalize_doi(value: str | None) -> str | None:
    """Return a bare DOI (lowercase), or None if not a DOI."""
    if not value:
        return None
    text = value.strip()
    match = DOI_RE.search(text)
    if not match:
        return None
    return match.group(1).rstrip(").,;").lower()


def student_json_paths(student: Path | None = None) -> list[Path]:
    """Return student JSON paths under student/, optionally a single file."""
    if student is not None:
        path = student if student.is_absolute() else ROOT / student
        if not path.is_file():
            raise FileNotFoundError(f"Student JSON not found: {path}")
        return [path]
    return sorted(STUDENT_ROOT.glob("*/*.json"))


def load_student(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_student(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _external_ids(node: dict | None) -> Iterable[dict]:
    if not node:
        return []
    return node.get("external-id") or []


def dois_from_works_payload(payload: dict) -> list[str]:
    """Extract unique DOIs from an ORCID /works JSON response."""
    found: set[str] = set()
    for group in payload.get("group") or []:
        for ext in _external_ids(group.get("external-ids")):
            if (ext.get("external-id-type") or "").lower() != "doi":
                continue
            doi = normalize_doi(ext.get("external-id-value"))
            if doi:
                found.add(doi)
        for summary in group.get("work-summary") or []:
            for ext in _external_ids(summary.get("external-ids")):
                if (ext.get("external-id-type") or "").lower() != "doi":
                    continue
                doi = normalize_doi(ext.get("external-id-value"))
                if doi:
                    found.add(doi)
    return sorted(found)


def fetch_orcid_works(orcid_id: str, *, timeout: float = 30.0) -> dict:
    """Fetch the public works summary for an ORCID iD."""
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ddls-website-student-dois/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_dois_for_orcid(
    orcid_id: str,
    *,
    timeout: float = 30.0,
    retries: int = 3,
) -> list[str]:
    """Fetch and normalize DOIs for an ORCID iD, with simple retries."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            payload = fetch_orcid_works(orcid_id, timeout=timeout)
            return dois_from_works_payload(payload)
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 404: no public works record; treat as empty.
            if exc.code == 404:
                return []
            if exc.code == 429 or 500 <= exc.code < 600:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def collect_student_dois(
    path: Path,
    *,
    timeout: float = 30.0,
) -> tuple[dict, list[str], str]:
    """
    Load a student JSON and return (data, dois, status).

    status is one of: ok, no_orcid, error:<message>
    """
    data = load_student(path)
    orcid_id = parse_orcid(data.get("orcid"))
    if not orcid_id:
        return data, [], "no_orcid"
    try:
        dois = fetch_dois_for_orcid(orcid_id, timeout=timeout)
        return data, dois, "ok"
    except Exception as exc:  # noqa: BLE001 - surface any network/parse failure
        return data, [], f"error:{exc}"
