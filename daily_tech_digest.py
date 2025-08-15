#!/usr/bin/env python3
"""
Daily Tech Digest generator
- Fetches RSS feeds
- Filters by recency (last N hours, default 24)
- De-duplicates stories
- Categorizes by simple keyword rules
- Outputs a Markdown digest you can paste into ChatGPT or email/slack

Usage:
  python daily_tech_digest.py --out digest.md --hours 24 --max-per-cat 7

Dependencies:
  pip install feedparser python-dateutil requests
"""

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import requests
from dateutil import tz

# -------------------------- Configuration --------------------------

DEFAULT_FEEDS = [
    # Technology & Startups
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.wired.com/feed/rss",
    "https://venturebeat.com/feed/",
    # Developer & Product Trends
    "https://news.ycombinator.com/rss",
    "https://www.producthunt.com/feed",
    # Specialized Innovation & Science
    "https://www.technologyreview.com/feed/",
    "https://spectrum.ieee.org/rss/fulltext",
    # Data Feed
    "https://databricks.com/feed",
    "https://towardsdatascience.com/feed",
    "https://aws.amazon.com/blogs/big-data/feed/"

]

FEED_NAME_MAP = {
    "techcrunch.com": "TechCrunch",
    "www.theverge.com": "The Verge",
    "www.wired.com": "Wired",
    "venturebeat.com": "VentureBeat",
    "news.ycombinator.com": "Hacker News",
    "www.producthunt.com": "Product Hunt",
    "www.technologyreview.com": "Technology Review",
    "spectrum.ieee.org": "Spectrum ieee",
    "databricks.com": "Databricks Blog",
    "towardsdatascience.com": "Towards Data Science",
    "aws.amazon.com": "AWS Big Data Blog",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def entry_datetime(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        t = getattr(entry, key, None) or entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def story_id(entry) -> str:
    link = entry.get("link") or ""
    title = entry.get("title") or ""
    h = hashlib.sha1(f"{link}|{title}".encode("utf-8")).hexdigest()
    return h


def within_window(dt: datetime, since: datetime) -> bool:
    return dt >= since


def fetch_feed(url: str):
    headers = {"User-Agent": "DailyTechDigest/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception as e:
        sys.stderr.write(f"[warn] Failed to fetch {url}: {e}\n")
        return {"entries": []}


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def feed_source_name(feed_url: str) -> str:
    d = domain_of(feed_url)
    return FEED_NAME_MAP.get(d, d or "source")


def build_digest(feeds, hours, max_per_cat, tz_name, min_items=1):
    to_zone = tz.gettz(tz_name) if tz_name else tz.tzlocal()
    now_local = datetime.now(to_zone)
    now_utc = now_local.astimezone(timezone.utc)
    window_start = now_utc - timedelta(hours=hours)

    seen = set()
    source_order = []
    buckets = {}

    for url in feeds:
        parsed = fetch_feed(url)
        src = feed_source_name(url)
        if src not in buckets:
            buckets[src] = []
            source_order.append(src)
        for entry in parsed.get("entries", []):
            dt = entry_datetime(entry)
            if not within_window(dt, window_start):
                continue
            sid = story_id(entry)
            if sid in seen:
                continue
            seen.add(sid)

            title = entry.get("title") or "(no title)"
            link = entry.get("link") or ""

            source = src
            buckets[source].append({
                "title": title.strip(),
                "link": link,
                "dt": dt.astimezone(to_zone),
            })

    for cat in buckets:
        buckets[cat].sort(key=lambda x: x["dt"], reverse=True)
        buckets[cat] = buckets[cat][:max_per_cat]

    date_str = now_local.strftime("%B %d, %Y")
    md_lines = []
    md_lines.append(f"📰 **Daily Tech Digest – {date_str}**\n")
    for src in source_order:
        items = buckets.get(src, [])
        if not items:
            continue
        md_lines.append(f"\n### {src}\n")
        for it in items:
            t = it["dt"].strftime("%H:%M")
            md_lines.append(f"- **{it['title']}** — {t} · [link]({it['link']})")

    total_items = sum(len(buckets[c]) for c in buckets)
    if total_items < min_items:
        md_lines.append("\n_(No items found in the selected window. Consider increasing --hours.)_")

    return "\n".join(md_lines)


def parse_args():
    ap = argparse.ArgumentParser(description="Generate a Daily Tech Digest (Markdown).")
    ap.add_argument("--out", default="digest.md", help="Output Markdown file path")
    ap.add_argument("--hours", type=int, default=72, help="Lookback window in hours")
    ap.add_argument("--max-per-cat", type=int, default=10, help="Max items per source")
    ap.add_argument("--tz", default=os.environ.get("DIGEST_TZ", "Asia/Tbilisi"),
                    help="Timezone for timestamps and header (e.g., Europe/London)")
    ap.add_argument("--feeds-file", default=None,
                    help="Optional path to a text file with one feed URL per line")
    return ap.parse_args()


def load_feeds(feeds_file):
    if not feeds_file:
        return DEFAULT_FEEDS
    urls = []
    with open(feeds_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls or DEFAULT_FEEDS


def main():
    args = parse_args()
    feeds = load_feeds(args.feeds_file)
    md = build_digest(
        feeds=feeds,
        hours=args.hours,
        max_per_cat=args.max_per_cat,
        tz_name=args.tz,
    )
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
