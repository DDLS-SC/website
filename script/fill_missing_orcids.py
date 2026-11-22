#!/usr/bin/env python3
"""Fill missing student ORCID iDs using OpenAlex + ORCID public search.

Priority:
  1. Students with Google Scholar but no ORCID
  2. Optionally all students without ORCID (--all)

Matching is conservative: name search, then require an institution/email/country
signal before accepting an ORCID. Ambiguous common names are skipped.

Examples:
  python3 script/fill_missing_orcids.py --dry-run
  python3 script/fill_missing_orcids.py
  python3 script/fill_missing_orcids.py --all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from orcid_dois import (  # noqa: E402
    NOT_AVAILABLE,
    ROOT,
    load_student,
    parse_orcid,
    save_student,
    student_json_paths,
)

USER_AGENT = "ddls-website-orcid-fill/1.0 (mailto:ddls-rs@scilifelab.se)"

# Rough university -> tokens used for OpenAlex institution matching
UNI_HINTS = {
    "uppsala university": ["uppsala"],
    "karolinska institutet": ["karolinska", "ki "],
    "kth royal institute of technology": ["kth", "royal institute of technology"],
    "lund university": ["lund"],
    "stockholm university": ["stockholm university", "stockholms universitet"],
    "linköping university": ["linköping", "linkoping"],
    "university of gothenburg": ["gothenburg", "göteborg", "goteborg"],
    "chalmers university of technology": ["chalmers"],
    "umeå university": ["umeå", "umea"],
    "swedish university of agricultural sciences": ["slu", "agricultural sciences"],
    "swedish museum of natural history": ["natural history", "nrm"],
}


def get_json(url: str, timeout: float = 30.0) -> dict | None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        if not raw.strip():
            return None
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def has_ggscholar(data: dict) -> bool:
    value = (data.get("ggscholar") or "").strip()
    return bool(value) and value.lower() != NOT_AVAILABLE


def institution_tokens(university: str) -> list[str]:
    key = (university or "").split("&")[0].strip().lower()
    for name, tokens in UNI_HINTS.items():
        if name in key or key in name:
            return tokens
    # fallback: significant words from university string
    words = re.findall(r"[a-zåäö]{4,}", key)
    return words[:3]


def inst_match(institutions: list[str], tokens: list[str]) -> bool:
    blob = " ".join(institutions).lower()
    return any(tok in blob for tok in tokens)


def email_domain_match(email: str, institutions: list[str]) -> bool:
    if not email or "@" not in email or email.lower() == NOT_AVAILABLE:
        return False
    domain = email.split("@", 1)[1].lower()
    # crude: check if domain stem appears in institution names
    stem = domain.split(".")[0]
    blob = " ".join(institutions).lower()
    return len(stem) >= 3 and stem in blob


def search_openalex_authors(name: str, per_page: int = 8) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "search": name,
            "per-page": str(per_page),
            "mailto": "ddls-rs@scilifelab.se",
        }
    )
    payload = get_json(f"https://api.openalex.org/authors?{query}")
    return list((payload or {}).get("results") or [])


def search_orcid(name: str) -> list[str]:
    """Return ORCID iDs from public name search."""
    parts = name.replace(",", " ").split()
    if len(parts) < 2:
        return []
    given = parts[0]
    family = parts[-1]
    # strip diacritics-ish by also trying ascii-ish query via original
    q = f'given-names:"{given}" AND family-name:"{family}"'
    url = "https://pub.orcid.org/v3.0/search/?" + urllib.parse.urlencode({"q": q})
    payload = get_json(url)
    if not payload:
        return []
    ids = []
    for item in payload.get("result") or []:
        path = ((item.get("orcid-identifier") or {}).get("path")) or ""
        if path:
            ids.append(path)
    return ids


def orcid_email_matches(orcid_id: str, email: str) -> bool:
    if not email or "@" not in email or email.lower() == NOT_AVAILABLE:
        return False
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/email"
    payload = get_json(url)
    if not payload:
        return False
    emails = [e.get("email", "").lower() for e in (payload.get("email") or [])]
    return email.lower() in emails


def pick_orcid(data: dict) -> tuple[str | None, str]:
    """Return (orcid_url_or_none, reason)."""
    name = data.get("name") or ""
    university = data.get("university") or ""
    email = data.get("email") or ""
    tokens = institution_tokens(university)

    # 1) ORCID public search + email confirmation is strongest
    for oid in search_orcid(name)[:5]:
        if orcid_email_matches(oid, email):
            return f"https://orcid.org/{oid}", "orcid_search_email"
        # also accept single ORCID hit when name is uncommon and SE-affiliated via OpenAlex later

    # 2) OpenAlex authors with institution match
    authors = search_openalex_authors(name)
    candidates = []
    for author in authors:
        orcid = author.get("orcid")
        if not orcid:
            continue
        insts = [
            i.get("display_name") or ""
            for i in (author.get("last_known_institutions") or [])
        ]
        score = 0
        reasons = []
        if inst_match(insts, tokens):
            score += 3
            reasons.append("institution")
        if email_domain_match(email, insts):
            score += 2
            reasons.append("email_domain")
        # Sweden country hint
        countries = [
            i.get("country_code") or ""
            for i in (author.get("last_known_institutions") or [])
        ]
        if "SE" in countries or "NO" in countries:  # NO for industrial/Oslo cases listed as KI
            score += 1
            reasons.append("nordic")
        if score >= 3:
            candidates.append((score, orcid, ",".join(reasons), author.get("display_name")))

    if len(candidates) == 1:
        _, orcid, reason, _ = candidates[0]
        return orcid, f"openalex:{reason}"
    if candidates:
        candidates.sort(reverse=True)
        # accept top if clearly better than second
        if candidates[0][0] >= candidates[1][0] + 2:
            _, orcid, reason, _ = candidates[0]
            return orcid, f"openalex:{reason}"
        return None, f"ambiguous_openalex:{len(candidates)}"

    # 3) Single ORCID search hit + OpenAlex SE/institution soft confirmation unavailable
    orcid_hits = search_orcid(name)
    if len(orcid_hits) == 1 and orcid_email_matches(orcid_hits[0], email):
        return f"https://orcid.org/{orcid_hits[0]}", "orcid_search_email"

    if not authors:
        return None, "no_candidates"
    if any(a.get("orcid") for a in authors):
        return None, "no_confident_match"
    return None, "openalex_profile_without_orcid"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill missing ORCID iDs for students (OpenAlex + ORCID search)."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Consider all students without ORCID (default: only those with ggscholar).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed updates without writing files.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Delay between API calls (default: 0.2).",
    )
    args = parser.parse_args()

    updated = 0
    skipped = 0
    failed = 0

    for path in student_json_paths():
        data = load_student(path)
        if parse_orcid(data.get("orcid")):
            continue
        if not args.all and not has_ggscholar(data):
            continue

        rel = path.relative_to(ROOT)
        name = data.get("name") or path.stem
        orcid, reason = pick_orcid(data)
        if args.delay > 0:
            time.sleep(args.delay)

        if not orcid:
            failed += 1
            print(f"- {rel}: {name} — skip ({reason})")
            skipped += 1
            continue

        print(f"- {rel}: {name} — {orcid} [{reason}]")
        if not args.dry_run:
            data["orcid"] = orcid
            save_student(path, data)
        updated += 1

    print()
    print(
        f"Summary: {updated} filled, {failed} unresolved "
        f"({'dry-run' if args.dry_run else 'written'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
