#!/usr/bin/env python3
"""Build SVG research overview plots from student publication DOIs.

Uses the OpenAlex API for citations, field-weighted citation impact (FWCI),
and journal 2-year mean citedness (open proxy for impact factor).

Outputs under research/:
  publications_by_ra.svg
  publications_by_cohort.svg
  journal_impact.svg
  citation_impact_by_ra.svg
  topic_network.svg
  coauthor_network.svg
  summary.json

Examples:
  python3 script/plot_research_overview.py
  python3 script/plot_research_overview.py --refresh-cache
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDENT_ROOT = ROOT / "student"
OUT_DIR = ROOT / "research"
CACHE_PATH = OUT_DIR / ".cache" / "openalex_works.json"

USER_AGENT = "ddls-website-research/1.0 (mailto:ddls-rs@scilifelab.se)"
RA_COLORS = {
    "PMD": "#1f77b4",
    "CMB": "#2ca02c",
    "EBI": "#ff7f0e",
    "EB": "#9467bd",
}


# ---------------------------------------------------------------------------
# Data loading / OpenAlex
# ---------------------------------------------------------------------------


def load_students() -> list[dict]:
    students = []
    for path in sorted(STUDENT_ROOT.glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        dois = [d.lower().strip() for d in (data.get("publications") or []) if d]
        students.append(
            {
                "path": str(path.relative_to(ROOT)),
                "name": data.get("name") or path.stem,
                "ra": data.get("ra") or "?",
                "cohort": path.parent.name,
                "dois": dois,
            }
        )
    return students


def load_cache() -> dict:
    if CACHE_PATH.is_file():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _get_json(url: str, timeout: float = 30.0, retries: int = 3) -> dict | None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            if not raw.strip():
                raise ValueError("empty response")
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last_error = exc
            if exc.code in {429, 500, 502, 503, 504}:
                time.sleep(1.2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(1.2 * (attempt + 1))
    if last_error:
        raise last_error
    return None


def fetch_openalex_work(doi: str, timeout: float = 30.0) -> dict | None:
    url = "https://api.openalex.org/works/" + urllib.parse.quote(f"doi:{doi}", safe="")
    return _get_json(url, timeout=timeout)


def fetch_openalex_source(source_id: str, cache: dict, timeout: float = 30.0) -> dict | None:
    sources = cache.setdefault("sources", {})
    if source_id in sources:
        return sources[source_id]
    # OpenAlex accepts either full URL or short id like S3880285
    if source_id.startswith("https://openalex.org/"):
        short = source_id.rsplit("/", 1)[-1]
        url = f"https://api.openalex.org/sources/{short}"
    elif source_id.startswith("http"):
        url = source_id
    else:
        url = f"https://api.openalex.org/sources/{source_id}"
    try:
        payload = _get_json(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"    source fetch failed ({source_id}): {exc}")
        sources[source_id] = None
        return None
    if payload is None:
        sources[source_id] = None
        return None
    summary = {
        "id": payload.get("id"),
        "display_name": payload.get("display_name"),
        "2yr_mean_citedness": (payload.get("summary_stats") or {}).get("2yr_mean_citedness"),
        "h_index": (payload.get("summary_stats") or {}).get("h_index"),
    }
    sources[source_id] = summary
    return summary


def enrich_works(
    dois: list[str],
    *,
    refresh: bool = False,
    delay: float = 0.12,
) -> dict[str, dict]:
    cache = {} if refresh else load_cache()
    works = cache.setdefault("works", {})
    missing = [d for d in dois if refresh or d not in works]
    print(f"OpenAlex: {len(dois)} DOIs, {len(missing)} to fetch")
    for i, doi in enumerate(missing, 1):
        try:
            payload = fetch_openalex_work(doi)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {doi}: {exc}")
            works[doi] = {"error": str(exc)}
            continue
        if payload is None:
            works[doi] = {"missing": True}
            print(f"  · {i}/{len(missing)} {doi}: not found")
        else:
            source = ((payload.get("primary_location") or {}).get("source")) or {}
            source_id = source.get("id")
            journal_if = None
            journal_name = source.get("display_name")
            if source_id:
                src = fetch_openalex_source(source_id, cache)
                if src:
                    journal_if = src.get("2yr_mean_citedness")
                    journal_name = src.get("display_name") or journal_name
            topics = []
            for topic in (payload.get("topics") or [])[:5]:
                name = topic.get("display_name")
                if name:
                    topics.append(name)
            if not topics:
                for concept in (payload.get("concepts") or [])[:5]:
                    name = concept.get("display_name")
                    if name:
                        topics.append(name)
            authors = []
            for authorship in payload.get("authorships") or []:
                author = authorship.get("author") or {}
                name = author.get("display_name")
                if name:
                    authors.append(name)
            works[doi] = {
                "title": payload.get("display_name"),
                "year": payload.get("publication_year"),
                "cited_by_count": payload.get("cited_by_count") or 0,
                "fwci": payload.get("fwci"),
                "type": payload.get("type"),
                "journal": journal_name,
                "journal_impact": journal_if,
                "topics": topics,
                "authors": authors,
            }
            print(
                f"  · {i}/{len(missing)} {doi}: "
                f"cited={works[doi]['cited_by_count']} IF~={journal_if}"
            )
        if delay > 0:
            time.sleep(delay)
        if i % 20 == 0:
            save_cache(cache)
    save_cache(cache)
    return {d: works[d] for d in dois if d in works and not works[d].get("error") and not works[d].get("missing")}


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def svg_wrap(width: int, height: int, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f"  <title>{esc(title)}</title>\n"
        f'  <rect width="100%" height="100%" fill="#fafafa"/>\n'
        f"{body}\n</svg>\n"
    )


def bar_chart(
    series: list[tuple[str, float]],
    *,
    title: str,
    subtitle: str = "",
    width: int = 720,
    height: int = 420,
    colors: dict[str, str] | None = None,
    value_format: str = "{:.0f}",
) -> str:
    margin_l, margin_r, margin_t, margin_b = 70, 30, 70, 70
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    max_v = max((v for _, v in series), default=1) or 1
    n = max(len(series), 1)
    gap = 12
    bar_w = max(20, (plot_w - gap * (n + 1)) / n)
    parts = [
        f'  <text x="{width/2}" y="32" text-anchor="middle" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="20" font-weight="700" fill="#222">{esc(title)}</text>',
    ]
    if subtitle:
        parts.append(
            f'  <text x="{width/2}" y="54" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#666">{esc(subtitle)}</text>'
        )
    # y grid
    for i in range(5):
        y = margin_t + plot_h * i / 4
        val = max_v * (1 - i / 4)
        parts.append(
            f'  <line x1="{margin_l}" y1="{y:.1f}" x2="{width-margin_r}" y2="{y:.1f}" '
            f'stroke="#ddd" stroke-width="1"/>'
        )
        parts.append(
            f'  <text x="{margin_l-8}" y="{y+4:.1f}" text-anchor="end" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#666">'
            f"{value_format.format(val)}</text>"
        )
    for i, (label, value) in enumerate(series):
        x = margin_l + gap + i * (bar_w + gap)
        h = (value / max_v) * plot_h if max_v else 0
        y = margin_t + plot_h - h
        color = (colors or {}).get(label, "#4c78a8")
        parts.append(
            f'  <rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'fill="{color}" rx="4"/>'
        )
        parts.append(
            f'  <text x="{x + bar_w/2:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#222">'
            f"{value_format.format(value)}</text>"
        )
        parts.append(
            f'  <text x="{x + bar_w/2:.1f}" y="{height - margin_b + 22}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#333">{esc(label)}</text>'
        )
    return svg_wrap(width, height, "\n".join(parts), title)


def histogram_svg(
    values: list[float],
    *,
    title: str,
    subtitle: str,
    xlabel: str,
    bins: int = 10,
    width: int = 720,
    height: int = 420,
) -> str:
    if not values:
        body = (
            f'  <text x="{width/2}" y="{height/2}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="16" fill="#666">'
            f"No data</text>"
        )
        return svg_wrap(width, height, body, title)

    lo, hi = min(values), max(values)
    if hi <= lo:
        hi = lo + 1
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - lo) / step))
        counts[idx] += 1
    labels = [f"{lo + i*step:.1f}" for i in range(bins)]
    series = list(zip(labels, counts))
    # reuse bar chart with truncated labels
    short = [(f"{lo + (i+0.5)*step:.1f}", float(c)) for i, c in enumerate(counts)]
    svg = bar_chart(
        short,
        title=title,
        subtitle=subtitle + f" · {xlabel}",
        width=width,
        height=height,
        value_format="{:.0f}",
    )
    return svg


def network_svg(
    nodes: list[dict],
    edges: list[tuple[str, str, float]],
    *,
    title: str,
    subtitle: str = "",
    width: int = 800,
    height: int = 640,
) -> str:
    """Circular layout network; node dicts need id, label, size, color."""
    if not nodes:
        body = (
            f'  <text x="{width/2}" y="{height/2}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="16" fill="#666">'
            f"No network edges found</text>"
        )
        return svg_wrap(width, height, body, title)

    cx, cy = width / 2, height / 2 + 10
    radius = min(width, height) * 0.32
    n = len(nodes)
    pos = {}
    for i, node in enumerate(nodes):
        angle = 2 * math.pi * i / n - math.pi / 2
        pos[node["id"]] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))

    max_w = max((w for _, _, w in edges), default=1) or 1
    parts = [
        f'  <text x="{width/2}" y="28" text-anchor="middle" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="20" font-weight="700" fill="#222">{esc(title)}</text>',
    ]
    if subtitle:
        parts.append(
            f'  <text x="{width/2}" y="50" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#666">{esc(subtitle)}</text>'
        )

    for a, b, w in edges:
        if a not in pos or b not in pos:
            continue
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        stroke = 0.6 + 3.5 * (w / max_w)
        parts.append(
            f'  <line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#999" stroke-width="{stroke:.2f}" stroke-opacity="0.55"/>'
        )

    max_size = max((node.get("size", 1) for node in nodes), default=1) or 1
    for node in nodes:
        x, y = pos[node["id"]]
        r = 8 + 18 * math.sqrt(node.get("size", 1) / max_size)
        color = node.get("color", "#4c78a8")
        parts.append(
            f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}" '
            f'stroke="#fff" stroke-width="2"/>'
        )
        label = node["label"]
        if len(label) > 28:
            label = label[:25] + "…"
        parts.append(
            f'  <text x="{x:.1f}" y="{y + r + 14:.1f}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="10" fill="#333">{esc(label)}</text>'
        )
    return svg_wrap(width, height, "\n".join(parts), title)


def ranked_journal_svg(
    journals: list[dict],
    *,
    title: str,
    subtitle: str = "",
    width: int = 880,
    top_n: int = 20,
) -> str:
    """Horizontal ranking: journals by impact factor, with publication counts.

    Each journal dict: name, impact, count.
    """
    rows = sorted(
        [j for j in journals if j.get("impact") is not None],
        key=lambda j: (float(j["impact"]), int(j.get("count") or 0)),
        reverse=True,
    )[:top_n]
    if not rows:
        body = (
            f'  <text x="{width/2}" y="200" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="16" fill="#666">'
            f"No journal impact data</text>"
        )
        return svg_wrap(width, 400, body, title)

    margin_l, margin_r, margin_t, margin_b = 280, 110, 70, 40
    row_h = 28
    height = margin_t + margin_b + row_h * len(rows)
    plot_w = width - margin_l - margin_r
    max_impact = max(float(j["impact"]) for j in rows) or 1.0
    max_count = max(int(j.get("count") or 1) for j in rows) or 1

    parts = [
        f'  <text x="{width/2}" y="28" text-anchor="middle" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="20" font-weight="700" fill="#222">{esc(title)}</text>',
    ]
    if subtitle:
        parts.append(
            f'  <text x="{width/2}" y="50" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#666">{esc(subtitle)}</text>'
        )
    # legend
    parts.append(
        f'  <rect x="{width - margin_r - 170}" y="18" width="14" height="10" fill="#4c78a8" rx="2"/>'
        f'  <text x="{width - margin_r - 150}" y="27" font-family="Helvetica, Arial, sans-serif" '
        f'font-size="11" fill="#444">Impact (2yr citedness)</text>'
    )
    parts.append(
        f'  <circle cx="{width - margin_r - 170 + 7}" cy="42" r="5" fill="#e45756"/>'
        f'  <text x="{width - margin_r - 150}" y="46" font-family="Helvetica, Arial, sans-serif" '
        f'font-size="11" fill="#444">Publications</text>'
    )

    for i, journal in enumerate(rows):
        y = margin_t + i * row_h
        name = journal["name"] or "Unknown"
        if len(name) > 36:
            name = name[:33] + "…"
        impact = float(journal["impact"])
        count = int(journal.get("count") or 0)
        bar_w = (impact / max_impact) * plot_w
        parts.append(
            f'  <text x="{margin_l - 10}" y="{y + 16}" text-anchor="end" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#333">{esc(name)}</text>'
        )
        parts.append(
            f'  <rect x="{margin_l}" y="{y + 4}" width="{bar_w:.1f}" height="16" '
            f'fill="#4c78a8" rx="3"/>'
        )
        parts.append(
            f'  <text x="{margin_l + bar_w + 6:.1f}" y="{y + 16}" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#222">'
            f"{impact:.1f}</text>"
        )
        # publication count marker sized by count
        cx = width - margin_r + 36
        r = 4 + 10 * math.sqrt(count / max_count)
        parts.append(
            f'  <circle cx="{cx}" cy="{y + 12}" r="{r:.1f}" fill="#e45756" fill-opacity="0.85"/>'
        )
        parts.append(
            f'  <text x="{cx + r + 6:.1f}" y="{y + 16}" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#333">'
            f"n={count}</text>"
        )

    return svg_wrap(width, height, "\n".join(parts), title)


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------


def norm_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^a-z\s\-]", "", name)
    return re.sub(r"\s+", " ", name)


def build_summary(students: list[dict], works: dict[str, dict]) -> dict:
    pubs_by_ra: Counter = Counter()
    pubs_by_cohort: Counter = Counter()
    citations_by_ra: Counter = Counter()
    fwci_by_ra: dict[str, list[float]] = defaultdict(list)
    journal_ifs: list[float] = []
    journal_if_by_ra: dict[str, list[float]] = defaultdict(list)
    topic_counts: Counter = Counter()
    topic_pairs: Counter = Counter()
    doi_students: dict[str, list[str]] = defaultdict(list)
    seen_doi_for_metrics: set[str] = set()
    journal_counts: Counter = Counter()
    journal_impact_map: dict[str, float] = {}

    for student in students:
        ra = student["ra"]
        cohort = student["cohort"]
        pubs_by_cohort[cohort] += len(student["dois"])
        for doi in student["dois"]:
            pubs_by_ra[ra] += 1
            doi_students[doi].append(student["name"])
            work = works.get(doi)
            if not work:
                continue
            citations_by_ra[ra] += int(work.get("cited_by_count") or 0)
            if work.get("fwci") is not None:
                fwci_by_ra[ra].append(float(work["fwci"]))
            if work.get("journal_impact") is not None:
                jif = float(work["journal_impact"])
                journal_if_by_ra[ra].append(jif)
                if doi not in seen_doi_for_metrics:
                    journal_ifs.append(jif)
            topics = work.get("topics") or []
            # Count topic co-occurrence and journals once per unique DOI.
            if doi not in seen_doi_for_metrics:
                journal = (work.get("journal") or "Unknown").strip() or "Unknown"
                journal_counts[journal] += 1
                if work.get("journal_impact") is not None:
                    journal_impact_map[journal] = float(work["journal_impact"])
                for t in topics:
                    topic_counts[t] += 1
                for i, a in enumerate(topics):
                    for b in topics[i + 1 :]:
                        pair = tuple(sorted((a, b)))
                        topic_pairs[pair] += 1
            seen_doi_for_metrics.add(doi)

    # student co-authorship via shared DOIs
    coauthor: Counter = Counter()
    for doi, names in doi_students.items():
        unique = sorted(set(names))
        for i, a in enumerate(unique):
            for b in unique[i + 1 :]:
                coauthor[(a, b)] += 1

    # also try OpenAlex author-name matching across all works
    student_by_norm = {norm_name(s["name"]): s["name"] for s in students}
    for doi, work in works.items():
        matched = []
        for author in work.get("authors") or []:
            key = norm_name(author)
            # exact or last-name + first-token match
            if key in student_by_norm:
                matched.append(student_by_norm[key])
                continue
            parts = key.split()
            if len(parts) >= 2:
                for skey, sname in student_by_norm.items():
                    sp = skey.split()
                    if len(sp) >= 2 and sp[-1] == parts[-1] and sp[0][0] == parts[0][0]:
                        matched.append(sname)
        matched = sorted(set(matched))
        for i, a in enumerate(matched):
            for b in matched[i + 1 :]:
                coauthor[(a, b)] += 1

    return {
        "students_total": len(students),
        "students_with_publications": sum(1 for s in students if s["dois"]),
        "unique_dois": len({d for s in students for d in s["dois"]}),
        "works_resolved": len(works),
        "publications_by_ra": dict(pubs_by_ra),
        "publications_by_cohort": dict(pubs_by_cohort),
        "citations_by_ra": dict(citations_by_ra),
        "mean_fwci_by_ra": {
            ra: (sum(vals) / len(vals) if vals else 0.0) for ra, vals in fwci_by_ra.items()
        },
        "mean_journal_impact_by_ra": {
            ra: (sum(vals) / len(vals) if vals else 0.0)
            for ra, vals in journal_if_by_ra.items()
        },
        "journal_impacts": journal_ifs,
        "journals": [
            {
                "name": name,
                "count": count,
                "impact": journal_impact_map.get(name),
            }
            for name, count in journal_counts.most_common()
        ],
        "top_topics": topic_counts.most_common(20),
        "topic_pairs": topic_pairs.most_common(40),
        "coauthors": coauthor.most_common(40),
        "note": (
            "journal_impact is OpenAlex source 2yr_mean_citedness "
            "(open proxy related to journal impact factor, not Clarivate JIF)."
        ),
    }


def write_plots(summary: dict, students: list[dict]) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    ra_order = ["PMD", "CMB", "EBI", "EB"]
    pubs_ra = [(ra, float(summary["publications_by_ra"].get(ra, 0))) for ra in ra_order]
    path = OUT_DIR / "publications_by_ra.svg"
    path.write_text(
        bar_chart(
            pubs_ra,
            title="Publications by research area",
            subtitle="DOI counts from student ORCID profiles",
            colors=RA_COLORS,
        ),
        encoding="utf-8",
    )
    written.append(path)

    cohorts = sorted(summary["publications_by_cohort"])
    pubs_cohort = [
        (c, float(summary["publications_by_cohort"][c])) for c in cohorts
    ]
    path = OUT_DIR / "publications_by_cohort.svg"
    path.write_text(
        bar_chart(
            pubs_cohort,
            title="Publications by intake year",
            subtitle="Sum of DOIs listed on student profiles",
            colors={c: "#4c78a8" for c in cohorts},
        ),
        encoding="utf-8",
    )
    written.append(path)

    path = OUT_DIR / "journal_impact.svg"
    path.write_text(
        histogram_svg(
            summary["journal_impacts"],
            title="Journal impact distribution",
            subtitle="OpenAlex 2-year mean citedness (IF proxy)",
            xlabel="2yr mean citedness",
            bins=8,
        ),
        encoding="utf-8",
    )
    written.append(path)

    impact_series = [
        (ra, float(summary["mean_journal_impact_by_ra"].get(ra, 0.0))) for ra in ra_order
    ]
    path = OUT_DIR / "citation_impact_by_ra.svg"
    # dual: show mean journal IF and also annotate FWCI via second chart content
    fwci_series = [
        (ra, float(summary["mean_fwci_by_ra"].get(ra, 0.0))) for ra in ra_order
    ]
    path.write_text(
        bar_chart(
            fwci_series,
            title="Mean field-weighted citation impact (FWCI)",
            subtitle="OpenAlex FWCI by research area · 1.0 ≈ field average",
            colors=RA_COLORS,
            value_format="{:.2f}",
        ),
        encoding="utf-8",
    )
    written.append(path)

    # journal IF by RA as separate helpful plot
    path = OUT_DIR / "journal_impact_by_ra.svg"
    path.write_text(
        bar_chart(
            impact_series,
            title="Mean journal impact by research area",
            subtitle="OpenAlex 2yr mean citedness of publication venues",
            colors=RA_COLORS,
            value_format="{:.1f}",
        ),
        encoding="utf-8",
    )
    written.append(path)

    # journals ranked by impact factor, with publication counts
    path = OUT_DIR / "journal_rank_impact_pubs.svg"
    path.write_text(
        ranked_journal_svg(
            summary.get("journals") or [],
            title="Journals ranked by impact",
            subtitle="Bar = OpenAlex 2yr mean citedness · red marker = publication count",
            top_n=20,
        ),
        encoding="utf-8",
    )
    written.append(path)

    # topic network: top topics + strongest pairs among them
    top_topics = [t for t, _ in summary["top_topics"][:12]]
    top_set = set(top_topics)
    topic_nodes = [
        {
            "id": t,
            "label": t,
            "size": float(dict(summary["top_topics"]).get(t, 1)),
            "color": "#e45756",
        }
        for t in top_topics
    ]
    topic_edges = [
        (a, b, float(w))
        for (a, b), w in summary["topic_pairs"]
        if a in top_set and b in top_set
    ][:30]
    path = OUT_DIR / "topic_network.svg"
    path.write_text(
        network_svg(
            topic_nodes,
            topic_edges,
            title="Research topic network",
            subtitle="Co-occurring OpenAlex topics on student papers",
        ),
        encoding="utf-8",
    )
    written.append(path)

    # coauthor network among students
    edge_names = Counter()
    for (a, b), w in summary["coauthors"]:
        edge_names[(a, b)] += w
    # keep top connected students
    degree: Counter = Counter()
    for (a, b), w in edge_names.items():
        degree[a] += w
        degree[b] += w
    keep = {n for n, _ in degree.most_common(18)}
    student_meta = {s["name"]: s for s in students}
    co_nodes = [
        {
            "id": name,
            "label": name.split()[0] + " " + name.split()[-1][:1] + "."
            if " " in name
            else name,
            "size": float(degree[name]),
            "color": RA_COLORS.get(student_meta.get(name, {}).get("ra", ""), "#4c78a8"),
        }
        for name in keep
    ]
    co_edges = [
        (a, b, float(w))
        for (a, b), w in edge_names.items()
        if a in keep and b in keep
    ]
    path = OUT_DIR / "coauthor_network.svg"
    path.write_text(
        network_svg(
            co_nodes,
            co_edges,
            title="Student co-authorship network",
            subtitle="Shared DOIs / matched OpenAlex authorships · node colour = RA",
        ),
        encoding="utf-8",
    )
    written.append(path)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate SVG research overview plots from student DOIs."
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Refetch OpenAlex metadata even if cached.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.12,
        help="Delay between OpenAlex requests (default: 0.12s).",
    )
    args = parser.parse_args()

    students = load_students()
    dois = sorted({d for s in students for d in s["dois"]})
    print(f"Students: {len(students)} · unique DOIs: {len(dois)}")
    works = enrich_works(dois, refresh=args.refresh_cache, delay=args.delay)
    summary = build_summary(students, works)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUT_DIR / "summary.json"
    # make JSON-serializable
    serializable = dict(summary)
    serializable["journals"] = summary.get("journals") or []
    serializable["top_topics"] = [
        {"topic": t, "count": c} for t, c in summary["top_topics"]
    ]
    serializable["topic_pairs"] = [
        {"a": a, "b": b, "weight": w} for (a, b), w in summary["topic_pairs"]
    ]
    serializable["coauthors"] = [
        {"a": a, "b": b, "weight": w} for (a, b), w in summary["coauthors"]
    ]
    summary_path.write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    written = write_plots(summary, students)
    print()
    print(f"Wrote {summary_path.relative_to(ROOT)}")
    for path in written:
        print(f"Wrote {path.relative_to(ROOT)}")
    print(
        f"Resolved {summary['works_resolved']}/{summary['unique_dois']} works · "
        f"mean journal IF proxy values: {len(summary['journal_impacts'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
