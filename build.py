#!/usr/bin/env python3
"""Build the static site from pages/, templates/, data/, course/, event/, news/ and static/ into dist/.

Usage:
    python build.py            # build into dist/
    python build.py --serve    # build, then serve dist/ on http://localhost:8000
"""
import argparse
import functools
import http.server
import json
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from site_calendar import build_calendar, build_ics

ROOT = Path(__file__).parent
DIST = ROOT / "dist"


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        sys.exit(f"error: {path.relative_to(ROOT)} is not valid JSON: {err}")


def build():
    site = load_json(ROOT / "site.json")
    data = {p.stem: load_json(p) for p in sorted((ROOT / "data").glob("*.json"))}

    # News items live in news/*.json (plus data/news.json), newest first.
    news = list(data.get("news", []))
    for path in sorted((ROOT / "news").glob("*.json")):
        news += load_json(path)
    data["news"] = sorted(news, key=lambda item: item["date"], reverse=True)

    pages = {p.stem for p in (ROOT / "pages").glob("*.html")}
    nav = {item["page"] for item in site["nav"]}
    if missing := nav - pages:
        sys.exit(f"error: site.json nav lists pages that do not exist: {sorted(missing)}")
    if extra := pages - nav:
        sys.exit(f"error: pages missing from site.json nav: {sorted(extra)}")

    env = Environment(
        loader=FileSystemLoader([ROOT / "pages", ROOT / "templates"]),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "static", DIST)

    calendar_view = build_calendar(ROOT, data)
    labels = {item["page"]: item["label"] for item in site["nav"]}
    for slug in sorted(pages):
        page = {"slug": slug, "label": labels[slug]}
        html = env.get_template(f"{slug}.html").render(
            site=site, data=data, page=page, calendar=calendar_view
        )
        (DIST / f"{slug}.html").write_text(html, encoding="utf-8")
    if calendar_view["agenda"]:
        (DIST / "calendar.ics").write_text(
            build_ics(calendar_view["agenda"], site["title"]), encoding="utf-8", newline=""
        )
    print(f"Built {len(pages)} pages into {DIST.relative_to(ROOT)}/")


def serve(port):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    print(f"Serving http://localhost:{port} (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("", port), handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serve", action="store_true", help="serve dist/ after building")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    build()
    if args.serve:
        try:
            serve(args.port)
        except KeyboardInterrupt:
            pass
