"""
event_finder – Synchronous hackathon-event scrapers.

Public API (all return ``list[dict]`` with keys
``name``, ``location``, ``date``, ``url``, ``description``, ``platform``):

    scrape_devpost(location, num)
    scrape_mlh(location, num)
    get_fallback_hackathons(location, num)
    search_hackathons(query, location, num)

Every function catches exceptions internally and returns ``[]`` on failure.
Designed to be called from async code via ``loop.run_in_executor``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─── Helpers ────────────────────────────────────────────────────────────────

_CURRENT_YEAR = datetime.now().year

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}


def _make_client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=15.0,
        follow_redirects=True,
    )


def _parse_date(raw: str, fallback_year: Optional[int] = None) -> str:
    """Best-effort normaliser for messy date strings.

    Handles formats like:
        "Mar 06 - 09, 2026"
        "FEB 20 - 22"
        "April 3-5"
        "2026-04-15"  (ISO)
    Returns the cleaned string (or the original on failure).
    """
    if not raw:
        return ""
    raw = raw.strip()

    # Already ISO-ish
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw

    year = fallback_year or _CURRENT_YEAR

    # "Mar 06 - 09, 2026" / "March 6-9, 2026"
    m = re.match(
        r"([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})(?:\s*,?\s*(\d{4}))?", raw
    )
    if m:
        mon = m.group(1).lower()
        mon_num = _MONTH_MAP.get(mon[:3], 0)
        y = int(m.group(4)) if m.group(4) else year
        if mon_num:
            return f"{y}-{mon_num:02d}-{int(m.group(2)):02d}"
        return raw

    # "FEB 20 - MAR 01, 2026" (cross-month)
    m = re.match(
        r"([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*([A-Za-z]+)\s+(\d{1,2})(?:\s*,?\s*(\d{4}))?",
        raw,
    )
    if m:
        mon = m.group(1).lower()
        mon_num = _MONTH_MAP.get(mon[:3], 0)
        y = int(m.group(5)) if m.group(5) else year
        if mon_num:
            return f"{y}-{mon_num:02d}-{int(m.group(2)):02d}"
        return raw

    return raw


_REGION_COUNTRIES = {
    "europe": {
        "france", "germany", "spain", "italy", "portugal", "netherlands",
        "belgium", "switzerland", "austria", "sweden", "norway", "denmark",
        "finland", "ireland", "poland", "czech", "greece", "romania",
        "hungary", "croatia", "uk", "united kingdom", "england", "scotland",
    },
    "asia": {
        "japan", "china", "india", "korea", "singapore", "thailand",
        "vietnam", "indonesia", "malaysia", "philippines", "taiwan",
        "hong kong", "pakistan", "bangladesh", "sri lanka", "nepal",
    },
    "north america": {
        "united states", "us", "usa", "canada", "mexico",
    },
    "south america": {
        "brazil", "argentina", "chile", "colombia", "peru",
    },
    "africa": {
        "nigeria", "kenya", "south africa", "egypt", "ghana", "morocco",
    },
}


def _location_matches(event_loc: str, query_loc: str) -> bool:
    """Loose word-overlap check for location filtering with region awareness."""
    if not query_loc:
        return True
    query_lower = query_loc.lower().strip()
    query_words = set(query_lower.replace(",", " ").split())
    # "anywhere" / "worldwide" / "global" match everything
    if query_words & {"anywhere", "worldwide", "global", "any", "all"}:
        return True
    event_lower = event_loc.lower().replace(",", " ").strip()
    event_words = set(event_lower.split())

    # Direct word overlap
    if query_words & event_words:
        return True

    # Region-to-country expansion (e.g. "Europe" matches "France")
    for region, countries in _REGION_COUNTRIES.items():
        if region in query_lower or query_lower in region:
            for country in countries:
                if country in event_lower:
                    return True

    # Substring match (e.g. "san francisco" in "San Francisco, CA")
    if query_lower in event_lower or event_lower in query_lower:
        return True

    return False


def _dedup(events: list[dict]) -> list[dict]:
    """Remove duplicates by (lowercase name, url)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for ev in events:
        key = (ev.get("name", "").lower().strip(), ev.get("url", "").strip())
        if key not in seen:
            seen.add(key)
            out.append(ev)
    return out


# ─── Devpost ────────────────────────────────────────────────────────────────

def scrape_devpost(location: str = "", num: int = 10) -> list[dict]:
    """Fetch upcoming + open hackathons from the Devpost JSON API."""
    results: list[dict] = []
    try:
        with _make_client() as client:
            for status in ("upcoming", "open"):
                try:
                    resp = client.get(
                        "https://devpost.com/api/hackathons",
                        params={
                            "status": status,
                            "page": 1,
                            "per_page": max(num * 2, 20),
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.debug("Devpost %s fetch failed: %s", status, exc)
                    continue

                hackathons = data.get("hackathons", [])
                for h in hackathons:
                    ev_loc = ""
                    dl = h.get("displayed_location")
                    if isinstance(dl, dict):
                        ev_loc = dl.get("location", "")
                    elif isinstance(dl, str):
                        ev_loc = dl
                    if not ev_loc:
                        ev_loc = "Online"

                    if not _location_matches(ev_loc, location):
                        continue

                    themes = h.get("themes", [])
                    theme_str = ", ".join(
                        t.get("name", t) if isinstance(t, dict) else str(t)
                        for t in (themes or [])
                    )
                    prize = h.get("prize_amount", "")
                    org = h.get("organization_name", "")
                    desc_parts = [theme_str, f"Prize: {prize}" if prize else "", f"By: {org}" if org else ""]
                    description = " | ".join(p for p in desc_parts if p)

                    results.append({
                        "name": h.get("title", "Untitled"),
                        "location": ev_loc,
                        "date": h.get("submission_period_dates", ""),
                        "url": h.get("url", ""),
                        "description": description,
                        "platform": "Devpost",
                    })

                    if len(results) >= num:
                        return results[:num]

    except Exception as exc:
        logger.warning("scrape_devpost error: %s", exc)
    return results[:num]


# ─── MLH ────────────────────────────────────────────────────────────────────

def scrape_mlh(location: str = "", num: int = 10) -> list[dict]:
    """Scrape Major League Hacks event listing pages."""
    results: list[dict] = []
    try:
        with _make_client() as client:
            for year in (_CURRENT_YEAR, _CURRENT_YEAR + 1):
                url = f"https://mlh.io/seasons/{year}/events"
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except Exception as exc:
                    logger.debug("MLH %d fetch failed: %s", year, exc)
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # MLH wraps each event in an <a> with class containing "event-link"
                # or inside a container div. Try multiple selectors.
                event_links = (
                    soup.select("a.event-link")
                    or soup.select("div.event-wrapper a[href]")
                    or soup.select("div.container a[href*='http']")
                )

                if not event_links:
                    # Broader fallback: find all anchors containing h3
                    event_links = [a for a in soup.find_all("a", href=True) if a.find("h3")]

                for link in event_links:
                    href = link.get("href", "")
                    if not href or href == "#":
                        continue

                    h3 = link.find("h3")
                    name = h3.get_text(strip=True) if h3 else ""
                    if not name:
                        continue

                    # Extract paragraphs: typically date, location, format
                    paragraphs = [p.get_text(strip=True) for p in link.find_all("p")]
                    date_str = paragraphs[0] if len(paragraphs) > 0 else ""
                    ev_loc = paragraphs[1] if len(paragraphs) > 1 else ""
                    fmt = paragraphs[2] if len(paragraphs) > 2 else ""

                    date_str = _parse_date(date_str, fallback_year=year)

                    if not _location_matches(ev_loc or "Online", location):
                        continue

                    results.append({
                        "name": name,
                        "location": ev_loc or "Online",
                        "date": date_str,
                        "url": href,
                        "description": fmt,
                        "platform": "MLH",
                    })

                    if len(results) >= num:
                        return results[:num]

    except Exception as exc:
        logger.warning("scrape_mlh error: %s", exc)
    return results[:num]


# ─── ETHGlobal ──────────────────────────────────────────────────────────────

def _scrape_ethglobal(location: str = "", num: int = 10) -> list[dict]:
    """Best-effort scrape of ETHGlobal events page (Next.js RSC)."""
    results: list[dict] = []
    try:
        with _make_client() as client:
            resp = client.get("https://ethglobal.com/events")
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        # Strategy 1: parse <a> tags with /events/ hrefs
        seen_slugs: set[str] = set()
        seen_names: set[str] = set()
        for a_tag in soup.find_all("a", href=re.compile(r"/events/[^/]+")):
            href = a_tag.get("href", "")
            if href in ("/events", "/events/"):
                continue

            # Extract slug as canonical name (e.g. "/events/cannes" → "cannes")
            slug = href.rstrip("/").rsplit("/", 1)[-1]
            if slug in seen_slugs or slug == "events":
                continue
            seen_slugs.add(slug)

            # Build a clean name from the slug, prefer the <h3>/<h4> if present
            heading = a_tag.find(["h3", "h4"])
            if heading:
                name = heading.get_text(strip=True)
            else:
                # Titlecase the slug: "cannes" → "ETHGlobal Cannes"
                name = f"ETHGlobal {slug.replace('-', ' ').title()}"

            if not name or len(name) < 3:
                continue
            seen_names.add(name.lower())

            # Try to extract location/date from child <p> or <span> tags
            ev_loc = ""
            ev_date = ""
            for child in a_tag.find_all(["p", "span"]):
                txt = child.get_text(strip=True)
                if not txt:
                    continue
                # Location heuristic: contains a comma (city, country)
                if "," in txt and not ev_loc:
                    ev_loc = txt
                # Date heuristic: contains month name
                elif re.search(r"(?i)jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", txt) and not ev_date:
                    ev_date = txt

            full_url = f"https://ethglobal.com{href}" if href.startswith("/") else href

            results.append({
                "name": name,
                "location": ev_loc,
                "date": ev_date,
                "url": full_url,
                "description": "Ethereum hackathon",
                "platform": "ETHGlobal",
            })

        # Strategy 2: extract from __next_f script chunks
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if "__next_f" not in script_text and "event" not in script_text.lower():
                continue
            # Look for JSON-like event objects
            for m in re.finditer(
                r'"name"\s*:\s*"([^"]+)".*?"(?:city|location)"\s*:\s*"([^"]*)".*?"(?:start|date)"\s*:\s*"([^"]*)"',
                script_text,
            ):
                ev_name, ev_loc, ev_date = m.group(1), m.group(2), m.group(3)
                if ev_name.lower() in seen_names:
                    continue
                seen_names.add(ev_name.lower())
                results.append({
                    "name": ev_name,
                    "location": ev_loc or "",
                    "date": ev_date,
                    "url": "https://ethglobal.com/events",
                    "description": "Ethereum hackathon",
                    "platform": "ETHGlobal",
                })

        # Filter by location
        if location:
            results = [r for r in results if _location_matches(r.get("location", ""), location) or not r.get("location")]

    except Exception as exc:
        logger.debug("_scrape_ethglobal error: %s", exc)
    return results[:num]


# ─── Eventbrite ─────────────────────────────────────────────────────────────

_EVENTBRITE_SLUGS = {
    "europe": "europe",
    "uk": "united-kingdom",
    "us": "united-states",
    "usa": "united-states",
    "united states": "united-states",
    "canada": "canada",
    "india": "india",
    "germany": "germany",
    "france": "france",
    "netherlands": "netherlands",
    "spain": "spain",
    "australia": "australia",
    "singapore": "singapore",
    "japan": "japan",
    "brazil": "brazil",
    "london": "united-kingdom--london",
    "new york": "ny--new-york",
    "san francisco": "ca--san-francisco",
    "berlin": "germany--berlin",
    "paris": "france--paris",
}


def _eventbrite_slug(location: str) -> str:
    loc_lower = location.lower().strip()
    for key, slug in _EVENTBRITE_SLUGS.items():
        if key in loc_lower or loc_lower in key:
            return slug
    return "online"


def _scrape_eventbrite(location: str = "", num: int = 10) -> list[dict]:
    """Extract hackathon events from Eventbrite's __SERVER_DATA__ JSON."""
    results: list[dict] = []
    try:
        slug = _eventbrite_slug(location)
        url = f"https://www.eventbrite.com/d/{slug}/hackathon/"

        with _make_client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text

        # Extract __SERVER_DATA__
        m = re.search(r"window\.__SERVER_DATA__\s*=\s*({.*?});?\s*</script>", html, re.DOTALL)
        if not m:
            return results

        import json
        try:
            server_data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return results

        # Navigate to event listings — structure varies, search recursively
        events = _extract_eventbrite_events(server_data)

        for ev in events:
            name = ev.get("name", "") or ev.get("title", "")
            if not name:
                continue
            ev_url = ev.get("url", "")
            start_date = ev.get("start_date", "") or ev.get("startDate", "")
            summary = ev.get("summary", "") or ev.get("description", "")
            ev_loc = ev.get("primary_venue", {}).get("address", {}).get("city", "") if isinstance(ev.get("primary_venue"), dict) else ""

            results.append({
                "name": name,
                "location": ev_loc or location or "See event page",
                "date": start_date,
                "url": ev_url,
                "description": summary[:200] if summary else "Hackathon on Eventbrite",
                "platform": "Eventbrite",
            })
            if len(results) >= num:
                break

    except Exception as exc:
        logger.debug("_scrape_eventbrite error: %s", exc)
    return results[:num]


def _extract_eventbrite_events(data, depth: int = 0) -> list[dict]:
    """Recursively dig into Eventbrite's __SERVER_DATA__ for event objects."""
    if depth > 8:
        return []
    results: list[dict] = []
    if isinstance(data, dict):
        # Check if this dict looks like an event
        if "name" in data and ("url" in data or "tickets_url" in data):
            results.append(data)
        for v in data.values():
            results.extend(_extract_eventbrite_events(v, depth + 1))
    elif isinstance(data, list):
        for item in data:
            results.extend(_extract_eventbrite_events(item, depth + 1))
    return results


# ─── Curated Fallback ──────────────────────────────────────────────────────

_CURATED_PLATFORMS = [
    {
        "name": "Devpost — Browse Hackathons",
        "url": "https://devpost.com/hackathons",
        "description": "Largest hackathon platform. Browse upcoming online and in-person hackathons.",
    },
    {
        "name": "MLH — Season Events",
        "url": "https://mlh.io/seasons/2026/events",
        "description": "Major League Hacks official season events for students and developers.",
    },
    {
        "name": "ETHGlobal — Ethereum Hackathons",
        "url": "https://ethglobal.com/events",
        "description": "Premier Ethereum and Web3 hackathon series, both online and in-person.",
    },
    {
        "name": "Eventbrite — Hackathon Events",
        "url": "https://www.eventbrite.com/d/online/hackathon/",
        "description": "Discover hackathons listed on Eventbrite worldwide.",
    },
    {
        "name": "Luma — Tech Events",
        "url": "https://lu.ma/discover",
        "description": "Community-driven event platform with many hackathons and tech meetups.",
    },
    {
        "name": "Hack Club — High School Hackathons",
        "url": "https://hackathons.hackclub.com/",
        "description": "Hackathons for high school students, organized by Hack Club community.",
    },
    {
        "name": "lablab.ai — AI Hackathons",
        "url": "https://lablab.ai/event",
        "description": "AI-focused hackathons with tutorials, mentorship, and prizes.",
    },
]


def get_fallback_hackathons(location: str = "", num: int = 7) -> list[dict]:
    """Return a curated list of hackathon platform URLs when scrapers fail."""
    results: list[dict] = []
    for p in _CURATED_PLATFORMS:
        results.append({
            "name": p["name"],
            "location": location or "Worldwide",
            "date": "Ongoing — check website",
            "url": p["url"],
            "description": p["description"],
            "platform": "Curated",
        })
        if len(results) >= num:
            break
    return results


# ─── Aggregated Search ─────────────────────────────────────────────────────

def search_hackathons(
    query: str = "hackathons",
    location: str = "",
    num: int = 10,
) -> list[dict]:
    """Aggregate results from all scrapers, deduplicate, and keyword-rank."""
    all_results: list[dict] = []

    # Run each scraper, catching failures individually
    for scraper, label in [
        (lambda: scrape_devpost(location, num), "Devpost"),
        (lambda: scrape_mlh(location, num), "MLH"),
        (lambda: _scrape_ethglobal(location, num), "ETHGlobal"),
        (lambda: _scrape_eventbrite(location, num), "Eventbrite"),
    ]:
        try:
            all_results.extend(scraper())
        except Exception as exc:
            logger.debug("search_hackathons %s failed: %s", label, exc)

    # Deduplicate
    all_results = _dedup(all_results)

    # If we got nothing from live scrapers, use curated fallback
    if not all_results:
        all_results = get_fallback_hackathons(location, num)

    # Keyword ranking: score each result by query-word overlap
    if query:
        query_words = set(query.lower().split())
        # Remove generic filler words
        query_words -= {"in", "for", "the", "a", "an", "and", "or", "of", "to", "near"}

        def _score(ev: dict) -> int:
            blob = " ".join([
                ev.get("name", ""),
                ev.get("description", ""),
                ev.get("location", ""),
                ev.get("platform", ""),
            ]).lower()
            return sum(1 for w in query_words if w in blob)

        all_results.sort(key=_score, reverse=True)

    return all_results[:num]
