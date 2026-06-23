import asyncio
import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional, Dict, Any, List

import feedparser
import httpx
from bs4 import BeautifulSoup
from PIL import Image

START_URL = "https://www.gp1.hr/feed/"

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
CONCURRENT_TASKS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def get_focus_y(w: int, h: int) -> float:
    ratio = round(w / h, 2)

    if ratio >= 1.6:
        return 0.35
    if 0.9 <= ratio <= 1.1:
        return 0.25
    return 0.5


def to_iso_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None

    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return None


async def get_image_info_async(url: str) -> Optional[Dict[str, Any]]:
    if not url or not url.startswith("http") or "1x1" in url:
        return None

    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        async with httpx.AsyncClient(
            timeout=10.0,
            headers=headers,
            follow_redirects=True
        ) as client:
            res = await client.get(url)

        if len(res.content) < MIN_IMAGE_WEIGHT_BYTES:
            return None

        img = Image.open(BytesIO(res.content))
        w, h = img.size

        if w < MIN_IMAGE_WIDTH_PX:
            return None

        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h)
        }

    except Exception as e:
        logging.error(f"Image error {url}: {e}")
        return None


async def process_single_article(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = entry.get("title", "")
    link = entry.get("link", "")

    logging.info(f"🔍 GP1: {title[:50]}")

    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        async with httpx.AsyncClient(
            timeout=20.0,
            headers=headers,
            follow_redirects=True
        ) as client:
            response = await client.get(link)

        soup = BeautifulSoup(response.text, "html.parser")

        image_url = None

        og = (
            soup.find("meta", property="og:image")
            or soup.find("meta", attrs={"name": "twitter:image"})
        )

        if og and og.get("content"):
            image_url = og["content"]

        if not image_url:
            return None

        image = await get_image_info_async(image_url)

        if not image:
            return None

        return {
            "title": title,
            "link": link,

            "author": entry.get("author", ""),
            "published_at": to_iso_date(
                entry.get("published")
                or entry.get("updated")
            ),

            "image_url": image["url"],
            "w": image["w"],
            "h": image["h"],
            "focus_y": image["focus_y"],

            "source_title1": "GP1",
            "source_title2": "F1",
            "source_color": "#FF0000",
            "flag": "🇭🇷"
        }

    except Exception as e:
        logging.error(f"Error processing article {link}: {e}")
        return None


async def scrape_gp1_async() -> None:
    feed = feedparser.parse(START_URL)

    semaphore = asyncio.Semaphore(CONCURRENT_TASKS)

    async def worker(entry):
        async with semaphore:
            return await process_single_article(entry)

    tasks = [worker(entry) for entry in feed.entries]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    articles: List[Dict[str, Any]] = []

    for item in results:
        if isinstance(item, Exception):
            logging.error(item)
            continue
        if item:
            articles.append(item)

    output = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "rss_gp1.py",
        "articles": articles
    }

    with open("F1/gp1.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logging.info(f"✅ Saved {len(articles)} articles")


if __name__ == "__main__":
    asyncio.run(scrape_gp1_async())