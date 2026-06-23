import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from io import BytesIO

import feedparser
import httpx
from bs4 import BeautifulSoup
from PIL import Image
from email.utils import parsedate_to_datetime

START_URL = "https://www.gp1.hr/feed/"

CONCURRENT_TASKS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def to_iso_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return None


def get_focus_y(w: int, h: int) -> float:
    ratio = w / h if h else 1

    if ratio >= 1.6:
        return 0.35
    if 0.9 <= ratio <= 1.1:
        return 0.25
    return 0.5


async def get_image_info(url: str) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(url)

        img = Image.open(BytesIO(r.content))
        w, h = img.size

        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h)
        }

    except Exception:
        return None


async def extract_image_from_article(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url)

        soup = BeautifulSoup(r.text, "html.parser")

        meta = soup.find("meta", property="og:image")
        if meta and meta.get("content"):
            return meta["content"]

        meta = soup.find("meta", attrs={"name": "twitter:image"})
        if meta and meta.get("content"):
            return meta["content"]

        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]

    except Exception:
        pass

    return ""


async def process_article(entry: Dict[str, Any]) -> Dict[str, Any]:
    title = entry.get("title", "")
    link = entry.get("link", "")

    logging.info(f"GP1: {title[:50]}")

    image_url = await extract_image_from_article(link)

    image_data = None
    w = h = 0
    focus_y = 0.5

    if image_url:
        image_data = await get_image_info(image_url)

    if image_data:
        image_url = image_data["url"]
        w = image_data["w"]
        h = image_data["h"]
        focus_y = image_data["focus_y"]

    return {
        "title": title,
        "link": link,
        "author": entry.get("author", ""),
        "published_at": to_iso_date(entry.get("published") or entry.get("updated")),
        "image_url": image_url,
        "w": w,
        "h": h,
        "focus_y": focus_y,
        "source_title1": "GP1",
        "source_title2": "F1",
        "source_color": "#FF0000",
        "flag": "🇭🇷"
    }


async def run():
    feed = feedparser.parse(START_URL)

    semaphore = asyncio.Semaphore(CONCURRENT_TASKS)

    async def worker(entry):
        async with semaphore:
            return await process_article(entry)

    results = await asyncio.gather(
        *[worker(e) for e in feed.entries],
        return_exceptions=True
    )

    articles: List[Dict[str, Any]] = []

    for r in results:
        if isinstance(r, Exception):
            continue
        if r:
            articles.append(r)

    output = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "rss_gp1.py",
        "articles": articles
    }

    with open("F1/gp1.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(articles)} articles")


if __name__ == "__main__":
    asyncio.run(run())