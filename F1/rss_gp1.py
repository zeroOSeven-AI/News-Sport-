
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import feedparser
import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageFile

# ==========================================
# CONFIG — GP1
# ==========================================

START_URL = "https://www.gp1.hr/feed/"

OUTPUT_FILE = Path("F1/gp1.json")

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ==========================================
# DATE PARSER
# ==========================================

def to_iso(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None

    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        try:
            dt = datetime.fromisoformat(
                date_str.replace("Z", "+00:00")
            )
            return dt.isoformat()
        except Exception:
            return None


# ==========================================
# TEXT CLEANUP
# ==========================================

def clean_text(value: Any) -> Optional[str]:
    if not value:
        return None

    if isinstance(value, list):
        value = " ".join(str(item) for item in value)

    text = BeautifulSoup(str(value), "html.parser").get_text(
        " ", strip=True
    )
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


# ==========================================
# IMAGE FOCUS — SAME AS F1
# ==========================================

def get_focus_y(w: int, h: int) -> float:
    if h <= 0:
        return 0.5

    ratio = round(w / h, 2)

    if ratio >= 1.6:
        return 0.35

    if 0.9 <= ratio <= 1.1:
        return 0.25

    return 0.5


# ==========================================
# IMAGE EXTRACTION
# ==========================================

def extract_image(entry: Dict[str, Any]) -> Optional[str]:
    img_url = ""

    # 1. Media RSS
    media = entry.get("media_content")

    if isinstance(media, list):
        for item in media:
            if isinstance(item, dict) and item.get("url"):
                img_url = item["url"]
                break

    # 2. Thumbnail
    if not img_url:
        thumbnails = entry.get("media_thumbnail")

        if isinstance(thumbnails, list):
            for item in thumbnails:
                if isinstance(item, dict) and item.get("url"):
                    img_url = item["url"]
                    break

    # 3. Enclosures
    if not img_url:
        enclosures = entry.get("enclosures")

        if isinstance(enclosures, list):
            for item in enclosures:
                if not isinstance(item, dict):
                    continue

                candidate = item.get("href") or item.get("url")
                mime = item.get("type", "")

                if candidate and (
                    mime.startswith("image/")
                    or re.search(
                        r"\.(jpg|jpeg|png|webp|avif)(?:\?|$)",
                        candidate,
                        re.IGNORECASE,
                    )
                ):
                    img_url = candidate
                    break

    # 4. WordPress content / description
    if not img_url:
        content_parts = entry.get("content", [])
        description = entry.get("description", "")
        summary = entry.get("summary", "")

        content_html = ""

        if isinstance(content_parts, list):
            for item in content_parts:
                if isinstance(item, dict):
                    content_html += " " + item.get("value", "")

        search_text = (
            content_html + " " + str(description) + " " + str(summary)
        )

        soup = BeautifulSoup(search_text, "html.parser")
        image = soup.find("img")

        if image:
            img_url = (
                image.get("src")
                or image.get("data-src")
                or image.get("data-lazy-src")
                or ""
            )

            if not img_url:
                srcset = image.get("srcset", "")
                if srcset:
                    img_url = srcset.split(",")[0].strip().split(" ")[0]

    # 5. Remove WordPress thumbnail dimensions
    if img_url:
        img_url = re.sub(
            r"-\d+x\d+(?=\.(?:jpg|jpeg|png|webp|avif)(?:\?|$))",
            "",
            img_url,
            flags=re.IGNORECASE,
        )

    if not img_url.startswith(("http://", "https://")):
        return None

    if "1x1" in img_url.lower() or "placeholder" in img_url.lower():
        return None

    return img_url


# ==========================================
# IMAGE VALIDATION — SAME RULES AS F1
# ==========================================

async def get_image_info_async(
    client: httpx.AsyncClient,
    url: Optional[str],
) -> Optional[Dict[str, Any]]:

    if not url:
        return None

    try:
        response = await client.get(url)
        response.raise_for_status()

        content = response.content

        # Minimum image file size
        if len(content) < MIN_IMAGE_WEIGHT_BYTES:
            return None

        # Validate actual image data
        ImageFile.LOAD_TRUNCATED_IMAGES = False

        with Image.open(BytesIO(content)) as img:
            img.verify()

        with Image.open(BytesIO(content)) as img:
            w, h = img.size

        if w < MIN_IMAGE_WIDTH_PX or h <= 0:
            return None

        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h),
        }

    except Exception as e:
        logging.debug("Image rejected (%s): %s", url, e)
        return None


# ==========================================
# FETCH RSS
# ==========================================

async def fetch_feed(client: httpx.AsyncClient) -> Any:
    response = await client.get(START_URL)

    logging.info("FEED STATUS: %s", response.status_code)
    logging.info("FEED SIZE: %s bytes", len(response.content))

    response.raise_for_status()

    feed = feedparser.parse(response.content)

    if getattr(feed, "bozo", False):
        logging.warning(
            "RSS parsing warning: %s",
            getattr(feed, "bozo_exception", "Unknown error"),
        )

    return feed


# ==========================================
# PROCESS SINGLE ARTICLE
# ==========================================

async def process(
    entry: Dict[str, Any],
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:

    async with semaphore:
        title = clean_text(entry.get("title"))
        link = entry.get("link", "")

        if not title or not link:
            return None

        logging.info("Processing GP1: %s", title[:60])

        image_url = extract_image(entry)

        image_info = await get_image_info_async(
            client,
            image_url,
        )

        # Match F1 behavior: skip articles without valid images
        if not image_info:
            logging.info("Image rejected or missing: %s", title[:50])
            return None

        content_parts = entry.get("content", [])
        content_html = ""

        if isinstance(content_parts, list):
            for item in content_parts:
                if isinstance(item, dict):
                    content_html += " " + item.get("value", "")

        description = (
            clean_text(entry.get("description"))
            or clean_text(entry.get("summary"))
            or clean_text(content_html)
        )

        author = clean_text(entry.get("author"))

        if not author:
            authors = entry.get("authors", [])

            if isinstance(authors, list) and authors:
                first_author = authors[0]

                if isinstance(first_author, dict):
                    author = clean_text(first_author.get("name"))

        published_at = to_iso(
            entry.get("published")
            or entry.get("updated")
            or entry.get("created")
        )

        # Exact shared schema used by the F1 app
        return {
            "title": title,
            "link": link,

            "image_url": image_info["url"],
            "w": image_info["w"],
            "h": image_info["h"],
            "focus_y": image_info["focus_y"],

            "published_at": published_at,
            "author": author,
            "description": description,

            "source_title1": "GP1",
            "source_title2": "F1",
            "source_color": "#FF0000",
            "flag": "🇭🇷",
        }


# ==========================================
# SAVE JSON — SAME STRUCTURE AS F1
# ==========================================

def save_json(articles: List[Dict[str, Any]]) -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            articles,
            file,
            ensure_ascii=False,
            indent=4,
        )

    logging.info(
        "Saved %s articles to %s",
        len(articles),
        OUTPUT_FILE,
    )


# ==========================================
# MAIN PIPELINE
# ==========================================

async def run() -> None:
    logging.info("Starting GP1 RSS pipeline...")

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/rss+xml, application/xml, "
            "text/xml, text/html, */*"
        ),
        "Accept-Language": "hr-HR,hr;q=0.9,en;q=0.8",
    }

    timeout = httpx.Timeout(20.0, connect=10.0)

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
    ) as client:

        try:
            feed = await fetch_feed(client)
        except Exception as e:
            logging.error("Unable to fetch GP1 RSS: %s", e)
            return

        entries = list(getattr(feed, "entries", []))

        logging.info("RSS ITEMS: %s", len(entries))

        if not entries:
            logging.warning(
                "RSS feed is empty. Existing JSON file was not overwritten."
            )
            return

        semaphore = asyncio.Semaphore(CONCURRENT_TASKS)

        selected_entries = entries[:MAX_NEWS_ITEMS]

        results = await asyncio.gather(
            *[
                process(entry, client, semaphore)
                for entry in selected_entries
            ],
            return_exceptions=True,
        )

        articles: List[Dict[str, Any]] = []

        for result in results:
            if isinstance(result, Exception):
                logging.error("Article processing failed: %s", result)
            elif result:
                articles.append(result)

        save_json(articles)

        logging.info(
            "GP1 pipeline finished: %s valid articles",
            len(articles),
        )


# ==========================================
# ENTRYPOINT
# ==========================================

if __name__ == "__main__":
    asyncio.run(run())
