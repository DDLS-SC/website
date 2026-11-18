#!/usr/bin/env python3
"""Add a paper to data/publications.json from its DOI, using Crossref for title, authors, journal and date.

Usage:
    python tools/add_publication.py 10.1038/s41586-021-03819-2 \\
        --students "Jane Doe; John Smith" --site Stockholm --area "Cell and molecular biology" \\
        [--code URL] [--data URL] [--preprint URL]

Copy the answers from the "Add a publication" GitHub issue into the options above,
check the printed entry, then commit data/publications.json.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBS = ROOT / "data" / "publications.json"
SITE = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
SITES = ["Stockholm", "Uppsala", "Linköping", "Umeå", "Gothenburg", "Lund"]
CROSSREF_TYPES = {"journal-article": "Article", "posted-content": "Preprint", "proceedings-article": "Conference paper",
                  "book-chapter": "Book chapter", "peer-review": "Review"}


def fetch_crossref(doi):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={"User-Agent": "DDLS-SC-website (https://github.com/DDLS-SC/website)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)["message"]
    except urllib.error.HTTPError as err:
        sys.exit(f"error: Crossref has no record for DOI {doi} (HTTP {err.code}). Check the DOI.")
    except urllib.error.URLError as err:
        sys.exit(f"error: could not reach Crossref: {err.reason}")


def entry_from_crossref(msg, doi):
    parts = (msg.get("published") or msg.get("published-online") or msg.get("published-print")
             or msg.get("issued") or msg.get("created"))["date-parts"][0]
    y, m, d = (list(parts) + [1, 1])[:3]
    authors = []
    for a in msg.get("author", []):
        name = " ".join(x for x in [a.get("given", ""), a.get("family", "")] if x) or a.get("name", "")
        if name:
            authors.append(name)
    venue = (msg.get("container-title") or [""])[0] or (msg.get("institution") or [{}])[0].get("name", "") \
        or msg.get("publisher", "")
    kind = CROSSREF_TYPES.get(msg.get("type", ""), "Article")
    return {
        "title": " ".join((msg.get("title") or ["(untitled)"])[0].split()),
        "authors": authors,
        "venue": venue,
        "year": y,
        "date": f"{y:04d}-{m:02d}-{d:02d}",
        "type": kind,
        "doi": doi,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("doi")
    parser.add_argument("--students", required=True, help="DDLS PhD students among the authors, separated by ';'")
    parser.add_argument("--site", required=True, choices=SITES)
    parser.add_argument("--area", required=True, choices=SITE["research_areas"])
    parser.add_argument("--preprint", default="")
    parser.add_argument("--code", default="")
    parser.add_argument("--data", default="")
    args = parser.parse_args()

    doi = args.doi.strip().removeprefix("https://doi.org/").removeprefix("doi:").strip()
    pubs = json.loads(PUBS.read_text(encoding="utf-8"))
    if any(p.get("doi", "").lower() == doi.lower() for p in pubs):
        sys.exit(f"error: {doi} is already in {PUBS.relative_to(ROOT)}")

    entry = entry_from_crossref(fetch_crossref(doi), doi)
    students = [s.strip() for s in args.students.split(";") if s.strip()]
    missing = [s for s in students if s not in entry["authors"]]
    if missing:
        print(f"warning: not found in the Crossref author list, check spelling: {', '.join(missing)}", file=sys.stderr)
        print(f"         Crossref authors: {', '.join(entry['authors'])}", file=sys.stderr)
    entry.update({"ddls_students": students, "preprint": args.preprint, "code": args.code,
                  "data": args.data, "site": args.site, "area": args.area})

    pubs.append(entry)
    pubs.sort(key=lambda p: p["date"], reverse=True)
    PUBS.write_text(json.dumps(pubs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"Added to {PUBS.relative_to(ROOT)}. Run `python build.py --serve` to check it.")


if __name__ == "__main__":
    main()
