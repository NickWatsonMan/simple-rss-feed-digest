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
from html import escape

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


def build_digest_markdown(feeds, hours, max_per_cat, tz_name, min_items=1):
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

def build_digest_html(feeds, hours, max_per_cat, tz_name, min_items=1):
    """Generate a mobile-friendly HTML page."""
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
            if dt < window_start:
                continue
            sid = story_id(entry)
            if sid in seen:
                continue
            seen.add(sid)
            title = (entry.get("title") or "(no title)").strip()
            link = entry.get("link") or ""
            buckets[src].append({
                "title": title,
                "link": link,
                "dt": dt.astimezone(to_zone),
            })

    for cat in buckets:
        buckets[cat].sort(key=lambda x: x["dt"], reverse=True)
        buckets[cat] = buckets[cat][:max_per_cat]

    def slugify(s: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()

    non_empty_sources = [src for src in source_order if buckets.get(src)]
    if not non_empty_sources:
        non_empty_sources = []

    total_items = sum(len(buckets[c]) for c in buckets)
    date_str = now_local.strftime("%B %d, %Y")

    css = """
    :root { --fg:#0b0b0b; --sub:#6a6a6a; --bg:#fff; --card:#fff; --border:#eaeaea; --link:#0969da; --chip:#d0e7ff; }
    * { box-sizing: border-box; }
    html, body { margin:0; padding:0; background:var(--bg); color:var(--fg); }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; font-size: 17px; }
    header { position: sticky; top: 0; background: var(--bg); border-bottom: 1px solid var(--border); padding: 12px 16px; z-index: 10; }
    header h1 { font-size: 22px; margin: 0 0 2px; font-weight: 700; }
    header .sub { color: var(--sub); font-size: 14px; }
    main { padding: 12px; max-width: 820px; margin: 0 auto; }
    .tabs { position: sticky; top: 82px; background: var(--bg); border-bottom: 1px solid var(--border); padding: 8px 12px; display: flex; gap: 8px; overflow-x: auto; -webkit-overflow-scrolling: touch; }
    .tab-btn { white-space: nowrap; border: 1px solid var(--border); background: var(--card); padding: 6px 10px; border-radius: 999px; font-size: 13px; color: var(--fg); text-decoration: none; }
    .tab-btn.active { background: var(--chip); border-color: #bcd8ff; }
    section { margin: 18px 0 28px; }
    .sec-title { display:none; }
    .tab-section { display: none; }
    .tab-section.active { display: block; }
    .item { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; margin: 12px 0; }
    .title { font-size: 16px; font-weight: 300; margin: 0 0 6px; }
    .meta { color: var(--sub); font-size: 13px; }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .left { display: flex; align-items: center; gap: 8px; }
    .time-badge { display: inline-block; font-size: 12px; border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px; background:#fff; }
    .btn { display: inline-block; font-size: 13px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; text-decoration: none; color: #6a6a6a; background: #eaeaea00; }
    .btn:active { opacity: .75; }
    footer { color: var(--sub); font-size: 13px; text-align: center; padding: 24px 0 32px; }
    """

    parts = []
    parts.append("<!doctype html><html lang='en'><meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append(f"<title>Daily Tech Digest — {escape(date_str)}</title>")
    parts.append(f"<style>{css}</style>")
    parts.append("<body>")
    parts.append("<header>")
    parts.append(f"<h1>Daily Tech Digest</h1>")
    parts.append(f"<div class='sub'>{escape(date_str)}</div>")
    parts.append("</header>")
    parts.append("<main>")

    # Tabs navbar
    parts.append("<nav class='tabs'>")
    for idx, src in enumerate(non_empty_sources):
        sid = slugify(src)
        active = " active" if idx == 0 else ""
        parts.append(f"<button class='tab-btn{active}' data-target='sec-{sid}'>{escape(src)}</button>")
    parts.append("</nav>")

    for idx, src in enumerate(non_empty_sources):
        items = buckets.get(src, [])
        sid = slugify(src)
        section_class = "tab-section active" if idx == 0 else "tab-section"
        parts.append(f"<section id='sec-{sid}' class='{section_class}'>")
        for it in items:
            t = it["dt"].strftime("%-d-%b %H:%M")
            title = escape(it["title"])
            link = escape(it["link"])
            parts.append(
                f"<div class='item'>"
                f"<div class='title'>{title}</div>"
                f"<div class='row'>"
                f"  <div class='left meta'><span class='time-badge'>{t}</span></div>"
                f"  <a class='btn' href='{link}' target='_blank' rel='noopener'>Read</a>"
                f"</div>"
                f"</div>"
            )
        parts.append("</section>")

    if total_items < min_items:
        parts.append("<p class='meta'>(No items found in the selected window. Consider increasing the lookback.)</p>")

    parts.append("</main>")
    parts.append("<footer>Generated by Daily Tech Digest</footer>")

    script = """
    <script>
    (function(){
      const buttons = Array.from(document.querySelectorAll('.tab-btn'));
      const sections = Array.from(document.querySelectorAll('.tab-section'));
      function activate(id){
        sections.forEach(s=>s.classList.toggle('active', s.id===id));
        buttons.forEach(b=>b.classList.toggle('active', b.getAttribute('data-target')===id));
        history.replaceState(null, '', '#' + id.replace('sec-',''));
      }
      buttons.forEach(b=>b.addEventListener('click', ()=>activate(b.getAttribute('data-target'))));
      // Swipe navigation on the content area (iPhone-friendly)
      (function(){
        const el = document.querySelector('main');
        let startX = 0, startY = 0;
        const X_THRESHOLD = 60;  // min horizontal distance in px
        const Y_THRESHOLD = 40;  // max vertical slop in px
        el.addEventListener('touchstart', (e)=>{
          if (e.touches.length !== 1) return;
          startX = e.touches[0].clientX;
          startY = e.touches[0].clientY;
        }, {passive:true});
        el.addEventListener('touchend', (e)=>{
          if (e.changedTouches.length !== 1) return;
          const dx = e.changedTouches[0].clientX - startX;
          const dy = Math.abs(e.changedTouches[0].clientY - startY);
          if (Math.abs(dx) < X_THRESHOLD || dy > Y_THRESHOLD) return;
          const current = sections.findIndex(s => s.classList.contains('active'));
          if (current === -1) return;
          let next = current;
          if (dx < 0) next = Math.min(current + 1, sections.length - 1);   // swipe left → next tab
          else next = Math.max(current - 1, 0);                             // swipe right → prev tab
          if (next !== current) activate(sections[next].id);
        }, {passive:true});
      })();
      // On load: if there's a hash matching a section, activate it
      const hash = location.hash.replace('#','');
      if (hash) {
        const id = 'sec-' + hash;
        if (document.getElementById(id)) activate(id);
      }
    })();
    </script>
    """
    parts.append(script)

    parts.append("</body></html>")
    return "".join(parts)

def build_digest(feeds, hours, max_per_cat, tz_name, out_path, min_items=1):
    """Dispatch to HTML or Markdown based on the output filename extension."""
    if out_path.lower().endswith('.html'):
        return build_digest_html(feeds, hours, max_per_cat, tz_name, min_items)
    else:
        return build_digest_markdown(feeds, hours, max_per_cat, tz_name, min_items)


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
    output = build_digest(
        feeds=feeds,
        hours=args.hours,
        max_per_cat=args.max_per_cat,
        tz_name=args.tz,
        out_path=args.out,
    )
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
