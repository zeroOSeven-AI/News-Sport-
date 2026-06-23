import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import feedparser
import httpx
from email.utils import parsedate_to_datetime

START_URL = "https://www.gp1.hr/feed/"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def to_iso(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return None


def extract_image(entry: Dict[str, Any]) -> str:
    # 1. media_content (najčešće WordPress)
    media = entry.get("media_content")
    if media and isinstance(media, list) and "url" in media[0]:
        return media[0]["url"]

    # 2. media_thumbnail
    thumb = entry.get("media_thumbnail")
    if thumb and isinstance(thumb, list) and "url" in thumb[0]:
        return thumb[0]["url"]

    # 3. enclosure
    enclosures = entry.get("enclosures")
    if enclosures and isinstance(enclosures, list) and "href" in enclosures[0]:
        return enclosures[0]["href"]

    return ""


async def fetch_feed() -> Any:
    headers = {"User-Agent": "Mozilla/5.0"}

    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        r = await client.get(START_URL)

    return feedparser.parse(r.text)


async def process(entry: Dict[str, Any]) -> Dict[str, Any]:
    title = entry.get("title", "")
    link = entry.get("link", "")

    image_url = extract_image(entry)

    return {
        "title": title,
        "link": link,
        "author": entry.get("author", ""),
        "published_at": to_iso(entry.get("published") or entry.get("updated")),
        "image_url": image_url,
        "w": 0,
        "h": 0,
        "focus_y": 0.5,
        "source_title1": "GP1",
        "source_title2": "F1",
        "source_color": "#FF0000",
        "flag": "🇭🇷"
    }


async def run():
    feed = await fetch_feed()

    logging.info(f"FEED ITEMS: {len(feed.entries)}")

    articles: List[Dict[str, Any]] = []

    for e in feed.entries:
        articles.append(await process(e))

    output = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "rss_gp1.py",
        "articles": articles
    }

    with open("F1/gp1.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"OK: {len(articles)} articles")


if __name__ == "__main__":
    asyncio.run(run())