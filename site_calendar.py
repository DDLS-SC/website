"""Turn course files and events into month grids and an agenda list for the Calendar page."""
import calendar
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _day(value):
    return date.fromisoformat(value)


def _range_label(start, end):
    if start == end:
        return f"{start.day} {start:%b %Y}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {end:%b %Y}"
    return f"{start.day} {start:%b} – {end.day} {end:%b %Y}"


STATUS_NOTE = {
    "completed": "This course has finished.",
    "closed": "Registration is closed.",
    "open": "Registration is open.",
    "upcoming": "It is coming up soon.",
}


def _summary(event):
    """One short, friendly paragraph shown when hovering over an item in the calendar."""
    where = f" in {event['location']}" if event["location"] else ""
    if event["kind"] == "course":
        kind = f"a {event['credits']}-credit course" if event.get("credits") else "a course"
        mode = event["format"].replace("&", "and").lower()
        text = f"{event['title']} is {kind}"
        text += f" ({mode})" if mode else ""
        text += f" taking place {event['when']}{where}"
        text += f", hosted by {event['host']}." if event["host"] else "."
        note = STATUS_NOTE.get(event["status"].lower(), f"Status: {event['status']}." if event["status"] else "")
        return f"{text} {note}".strip()
    text = f"{event['title']} takes place {event['when']}{where}."
    return f"{text} {event['details']}".strip()


def collect_events(root: Path, data: dict):
    """Courses (course/*.json) and events (event/*.json, data/events.json) as one list of dicts."""
    events = []
    for path in sorted((root / "course").glob("*.json")):
        for course in json.loads(path.read_text(encoding="utf-8")):
            start = _day(course["start_date"])
            end = _day(course.get("end_date") or course["start_date"])
            details = [
                f"{course['credits']} credits" if course.get("credits") else "",
                course.get("format", ""),
            ]
            events.append({
                "kind": "course",
                "title": course["name"],
                "start": start,
                "end": end,
                "location": course.get("location", ""),
                "host": course.get("host", ""),
                "status": course.get("status", ""),
                "link": course.get("link", ""),
                "details": " · ".join(d for d in details if d),
                "credits": course.get("credits"),
                "format": course.get("format", ""),
            })
    event_rows = list(data.get("events", []))
    for path in sorted((root / "event").glob("*.json")):
        event_rows += json.loads(path.read_text(encoding="utf-8"))
    for event in event_rows:
        start = _day(event["date"])
        end = _day(event.get("end_date") or event["date"])
        events.append({
            "kind": "event",
            "title": event["title"],
            "start": start,
            "end": end,
            "location": event.get("location", ""),
            "host": "",
            "status": "",
            "link": event.get("link", ""),
            "details": event.get("description", ""),
        })
    for event in events:
        if event["end"] < event["start"]:
            raise SystemExit(f"error: '{event['title']}' ends before it starts")
        event["when"] = _range_label(event["start"], event["end"])
        event["summary"] = _summary(event)
    return sorted(events, key=lambda e: (e["start"], e["title"]))


def build_calendar(root: Path, data: dict):
    events = collect_events(root, data)
    if not events:
        return {"months": [], "agenda": [], "weekdays": WEEKDAYS}

    by_day = {}
    for event in events:
        day = event["start"]
        while day <= event["end"]:
            by_day.setdefault(day, []).append(event)
            day += timedelta(days=1)

    first, last = events[0]["start"], max(e["end"] for e in events)
    months = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        weeks = []
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
            cells = []
            for day in week:
                in_month = day.month == month
                chips = []
                for event in by_day.get(day, []) if in_month else []:
                    chips.append({
                        "event": event,
                        # Label the first day of an event and each Monday so long events stay readable.
                        "label": day == event["start"] or day.weekday() == 0,
                        "starts": day == event["start"],
                        "ends": day == event["end"],
                    })
                cells.append({"day": day, "in_month": in_month, "chips": chips})
            weeks.append(cells)
        months.append({
            "key": f"{year}-{month:02d}",
            "title": f"{calendar.month_name[month]} {year}",
            "weeks": weeks,
        })
        month += 1
        if month > 12:
            year, month = year + 1, 1

    return {"months": months, "agenda": events, "weekdays": WEEKDAYS}


def _escape(text):
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")
    )


def _fold(line):
    """Fold a content line to 75 octets as required by RFC 5545."""
    out, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > (75 if not out else 74):
            out.append(current)
            current = char
        else:
            current += char
    out.append(current)
    return "\r\n ".join(out)


def build_ics(events, name):
    """An iCalendar file (all-day events) that can be imported into Google, Outlook or Apple Calendar."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DDLS Student Council//Website//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape(name)}",
    ]
    for event in events:
        uid = hashlib.sha1(f"{event['kind']}|{event['title']}|{event['start']}".encode()).hexdigest()
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@ddls-student-council",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{event['start']:%Y%m%d}",
            # All-day DTEND is exclusive, so add one day.
            f"DTEND;VALUE=DATE:{event['end'] + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(event['title'])}",
            f"DESCRIPTION:{_escape(event['summary'])}",
        ]
        if event["location"]:
            lines.append(f"LOCATION:{_escape(event['location'])}")
        if event["link"]:
            lines.append(f"URL:{event['link']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
