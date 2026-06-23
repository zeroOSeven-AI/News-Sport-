import asyncio
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import feedparser
import httpx
from email.utils import parsedate_to_datetime
from PIL import Image, ImageFile

START_URL = "https://www.gp1.hr/feed/"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ----------------------------
# DATE PARSER (PY3.9 SAFE)
# ----------------------------
def to_iso(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return None


# ----------------------------
# IMAGE EXTRACTION & CLEANUP
# ----------------------------
def extract_image(entry: Dict[str, Any]) -> str:
    img_url = ""
    
    # 1. Standard RSS fields
    media = entry.get("media_content")
    if media and isinstance(media, list) and "url" in media[0]:
        img_url = media[0]["url"]
    else:
        thumb = entry.get("media_thumbnail")
        if thumb and isinstance(thumb, list) and "url" in thumb[0]:
            img_url = thumb[0]["url"]
        else:
            enclosures = entry.get("enclosures")
            if enclosures and isinstance(enclosures, list) and "href" in enclosures[0]:
                img_url = enclosures[0]["href"]

    # 2. WordPress Fallback: Extract from content or description
    if not img_url:
        content_encoded = ""
        if "content" in entry and isinstance(entry["content"], list) and len(entry["content"]) > 0:
            content_encoded = entry["content"][0].get("value", "")
            
        description = entry.get("description", "")
        search_text = f"{content_encoded} {description}"

        if search_text.strip():
            match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', search_text)
            if match:
                img_url = match.group(1)

    # 3. Clean WordPress image dimensions to get the ORIGINAL image
    if img_url:
        img_url = re.sub(r'-\d+x\d+(?=\.[a-zA-Z]+$)', '', img_url)

    return img_url


# ----------------------------
# ASYNC IMAGE DIMENSIONS FETCH
# ----------------------------
async def get_image_dimensions(client: httpx.AsyncClient, url: str) -> tuple[int, int]:
    if not url:
        return 0, 0
    try:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                return 0, 0
            
            p = ImageFile.Parser()
            async for chunk in response.iter_bytes(chunk_size=1024):
                p.feed(chunk)
                if p.image:
                    return p.image.size  # (width, height)
                if len(p.data) > 32768:  # 32KB protection guard
                    break
    except Exception as e:
        logging.warning(f"Error fetching dimensions for {url}: {e}")
    return 0, 0


# ----------------------------
# FETCH RSS WITH SAFETY HEADERS
# ----------------------------
async def fetch_feed() -> Any:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,application/rss+xml;q=0.8,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    async with httpx.AsyncClient(
        timeout=20,
        headers=headers,
        follow_redirects=True
    ) as client:
        r = await client.get(START_URL)

    logging.info(f"FEED STATUS: {r.status_code}")
    logging.info(f"FEED SIZE: {len(r.content)} bytes")

    content_type = r.headers.get("content-type", "").lower()
    if "xml" not in content_type and "rss" not in content_type:
        logging.error("❌ NOT RSS FEED (likely blocked or HTML response)")
        return feedparser.parse(b"")

    return feedparser.parse(r.content)


# ----------------------------
# PROCESS ENTRY
# ----------------------------
async def process(entry: Dict[str, Any], client: httpx.AsyncClient) -> Dict[str, Any]:
    image_url = extract_image(entry)
    
    width, height = 0, 0
    if image_url:
        try:
            width, height = await get_image_dimensions(client, image_url)
        except Exception:
            pass

    return {
        "title": entry.get("title", ""),
        "link": entry.get("link", ""),
        "author": entry.get("author", ""),
        "published_at": to_iso(entry.get("published") or entry.get("updated")),
        "image_url": image_url,
        "w": width,
        "h": height,
        "focus_y": 0.5,
        "source_title1": "GP1",
        "source_title2": "F1",
        "source_color": "#FF0000",
        "flag": "🇭🇷"
    }


# ----------------------------
# MAIN RUN
# ----------------------------
async def run():
    feed = await fetch_feed()
    entries = getattr(feed, "entries", [])

    logging.info(f"FEED ITEMS: {len(entries)}")

    if not entries:
        logging.error("❌ FEED EMPTY - blocked or invalid RSS")
        output = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "rss_gp1.py",
            "articles": []
        }

        with open("F1/gp1.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print("OK: 0 articles (EMPTY FEED)")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as client:
        articles: List[Dict[str, Any]] = await asyncio.gather(
            *[process(e, client) for e in entries]
        )

    output = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "rss_gp1.py",
        "articles": articles
    }

    with open("F1/gp1.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"OK: {len(articles)} articles")


# ----------------------------
# ENTRYPOINT
# ----------------------------
if __name__ == "__main__":
    asyncio.run(run())
