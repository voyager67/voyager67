#!/usr/bin/env python3
"""Generate a visual-only SVG of recent public GitHub activity."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

USERNAME = "voyager67"
API = f"https://api.github.com/users/{USERNAME}/events/public"
OUTPUT = Path("activity.svg")
DAYS = 90
MAX_PAGES = 3

COLORS = {
    "commits": "#a78bfa",
    "pull_requests": "#58a6ff",
    "issues": "#f2cc60",
    "reviews": "#3fb950",
    "other": "#8b949e",
}


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def fetch_events() -> list[dict]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "voyager67-profile-activity",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    events: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        request = urllib.request.Request(
            f"{API}?per_page=100&page={page}",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                batch = json.load(response)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            raise RuntimeError(f"GitHub Events API request failed on page {page}: {exc}") from exc
        if not isinstance(batch, list):
            raise RuntimeError("GitHub Events API returned an unexpected response.")
        events.extend(batch)
        if len(batch) < 100:
            break
    return events


def classify(event: dict) -> tuple[str | None, int]:
    event_type = event.get("type", "")
    payload = event.get("payload") or {}

    if event_type == "PushEvent":
        commits = max(int(payload.get("size") or 0), len(payload.get("commits") or []), 1)
        return "commits", commits
    if event_type in ("PullRequestEvent",):
        return "pull_requests", 1
    if event_type in ("IssuesEvent", "IssueCommentEvent"):
        return "issues", 1
    if event_type in (
        "PullRequestReviewEvent",
        "PullRequestReviewCommentEvent",
        "CommitCommentEvent",
    ):
        return "reviews", 1
    if event_type in (
        "CreateEvent",
        "DeleteEvent",
        "ForkEvent",
        "GollumEvent",
        "ReleaseEvent",
        "PublicEvent",
        "MemberEvent",
    ):
        return "other", 1

    # Deliberately ignore WatchEvent: profile activity must not show stars.
    return None, 0


def svg_text(x: int, y: int, value: str, size: int, color: str, weight: int = 400) -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}" font-family="Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif">'
        f'{escape(value)}</text>'
    )


def render_svg(events: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=DAYS)
    counts = Counter()
    daily = Counter()
    weekly = defaultdict(Counter)

    for event in events:
        created = event.get("created_at")
        if not created:
            continue
        try:
            stamp = parse_date(created)
        except (ValueError, TypeError):
            continue
        if stamp < cutoff or stamp > now + timedelta(minutes=5):
            continue
        category, amount = classify(event)
        if not category:
            continue
        day = stamp.date()
        week = day - timedelta(days=day.weekday())
        counts[category] += amount
        daily[day] += amount
        weekly[week][category] += amount

    total = sum(counts.values())
    labels = [
        ("COMMITS", "commits"),
        ("PULL REQUESTS", "pull_requests"),
        ("ISSUES", "issues"),
        ("REVIEWS", "reviews"),
        ("OTHER", "other"),
    ]

    width, height = 1080, 510
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Automatically refreshed visual summary of public GitHub commits, pull requests, issues, reviews, and other activity over the last 90 days">',
        '<defs><linearGradient id="panel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#161b22"/><stop offset="1" stop-color="#0d1117"/></linearGradient></defs>',
        '<rect x="1" y="1" width="1078" height="508" rx="18" fill="url(#panel)" stroke="#30363d"/>',
        svg_text(34, 42, "PUBLIC ACTIVITY", 20, "#f0f6fc", 700),
        svg_text(34, 66, "LAST 90 DAYS", 11, "#8b949e", 600),
        '<rect x="880" y="22" width="166" height="30" rx="15" fill="#142b23" stroke="#245b40"/>',
        '<circle cx="899" cy="37" r="4" fill="#3fb950"/>',
        svg_text(911, 41, "AUTO-REFRESH · 6H", 10, "#7ee787", 700),
        '<line x1="28" y1="84" x2="1052" y2="84" stroke="#30363d"/>',
    ]

    # Contribution-style heatmap, built from the public event stream.
    parts.append(svg_text(34, 111, "ACTIVITY CALENDAR", 12, "#c9d1d9", 700))
    parts.append(svg_text(1046, 111, f"{total:,} EVENTS", 10, "#8b949e", 600))
    start = now.date() - timedelta(days=90)
    start -= timedelta(days=start.weekday())
    cell = 12
    gap = 4
    x0, y0 = 36, 129
    day_names = [("MON", 0), ("WED", 2), ("FRI", 4)]
    for name, row in day_names:
        parts.append(svg_text(4, y0 + row * (cell + gap) + 10, name, 8, "#6e7681", 500))

    max_day = max(daily.values(), default=0)
    for index in range(13 * 7):
        day = start + timedelta(days=index)
        col = index // 7
        row = index % 7
        value = daily.get(day, 0)
        if value == 0:
            fill = "#21262d"
        elif value <= max(1, max_day * 0.2):
            fill = "#3b2e5f"
        elif value <= max(2, max_day * 0.4):
            fill = "#6846a5"
        elif value <= max(4, max_day * 0.7):
            fill = "#8b5cf6"
        else:
            fill = "#c4a7ff"
        x = x0 + col * (cell + gap)
        y = y0 + row * (cell + gap)
        tip = f"{day.isoformat()}: {value} public activity units"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{fill}">'
            f'<title>{escape(tip)}</title></rect>'
        )

    # Month markers above the calendar.
    month_seen = set()
    for col in range(13):
        week_day = start + timedelta(days=col * 7)
        marker = (week_day.year, week_day.month)
        if marker not in month_seen:
            month_seen.add(marker)
            parts.append(svg_text(x0 + col * (cell + gap), 122, week_day.strftime("%b").upper(), 8, "#6e7681", 500))

    # Activity categories: visual bars, with no star/watch category.
    parts.append(svg_text(34, 267, "ACTIVITY TYPES", 12, "#c9d1d9", 700))
    bar_x, bar_w = 190, 705
    max_count = max((counts[k] for _, k in labels), default=1) or 1
    row_y = 294
    for index, (label, key) in enumerate(labels):
        y = row_y + index * 34
        value = counts[key]
        color = COLORS[key]
        parts.append(svg_text(35, y + 12, label, 10, "#c9d1d9", 600))
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="12" rx="6" fill="#21262d"/>')
        fill_w = 0 if value == 0 else max(5, int(bar_w * value / max_count))
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{fill_w}" height="12" rx="6" fill="{color}"/>')
        parts.append(svg_text(930, y + 11, f"{value:,}", 11, "#f0f6fc", 700))

    # Compact weekly activity bars at the bottom.
    parts.append(svg_text(34, 482, "WEEKLY FLOW", 11, "#8b949e", 600))
    chart_x, chart_y, chart_h, chart_w = 190, 452, 68, 705
    weeks = [start + timedelta(days=7 * i) for i in range(13)]
    week_totals = [sum(weekly.get(week, {}).values()) for week in weeks]
    max_week = max(week_totals, default=1) or 1
    bar_gap = 9
    bw = (chart_w - bar_gap * 12) / 13
    for i, week in enumerate(weeks):
        x = chart_x + i * (bw + bar_gap)
        bottom = chart_y + chart_h
        values = weekly.get(week, Counter())
        for key in ("commits", "pull_requests", "issues", "reviews", "other"):
            amount = values.get(key, 0)
            if amount <= 0:
                continue
            segment_h = chart_h * amount / max_week
            bottom -= segment_h
            parts.append(
                f'<rect x="{x:.1f}" y="{bottom:.1f}" width="{bw:.1f}" height="{segment_h:.1f}" '
                f'rx="2" fill="{COLORS[key]}"/>'
            )
        if i in (0, 3, 6, 9, 12):
            parts.append(svg_text(int(x), 535 - 8, week.strftime("%d %b"), 8, "#6e7681", 500))

    parts.extend([
        '<line x1="28" y1="441" x2="1052" y2="441" stroke="#30363d"/>',
        '</svg>',
    ])
    return "\n".join(parts)


def main() -> int:
    try:
        events = fetch_events()
        svg = render_svg(events)
        OUTPUT.write_text(svg + "\n", encoding="utf-8")
        print(f"Updated {OUTPUT} from {len(events)} public events.")
        return 0
    except Exception as exc:  # Keep the last known-good SVG if the API is unavailable.
        print(f"Activity refresh failed; preserving the previous SVG: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
