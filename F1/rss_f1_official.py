import asyncio
import json
import logging
import random
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

import feedparser
import httpx
from bs4 import BeautifulSoup
from PIL import Image
from playwright.async_api import async_playwright

# ==========================================
# CONFIG
# ==========================================
START_URL = "https://www.formula1.com/en/latest/all.xml"

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# ==========================================
# IMAGE UTILS
# ==========================================

def get_focus_y(w: int, h: int) -> float:
    ratio = round(w / h, 2)
    if ratio >= 1.6:
        return 0.35
    if 0.9 <= ratio <= 1.1:
        return 0.25
    return 0.5


async def get_image_info_async(url: str) -> Optional[Dict[str, Any]]:
    if not url or not url.startswith("http") or "1x1" in url:
        return None

    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
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
                "focus_y": get_focus_y(w, h),
            }

    except Exception:
        return None


# ==========================================
# ARTICLE SCRAPER
# ==========================================

async def process_single_article(browser: Any, title: str, link: str) -> Optional[Dict[str, Any]]:
    published_at = None
    author = None
    description = None
    src = None

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        viewport={"width": 1280, "height": 720},
    )

    page = await context.new_page()

    try:
        logging.info(f"🔍 F1 article: {title[:40]}")
        await page.goto(link, wait_until="domcontentloaded", timeout=30000)

        soup = BeautifulSoup(await page.content(), "html.parser")

        # ==========================================
        # OG IMAGE
        # ==========================================
        og_image = soup.find("meta", property="og:image") or soup.find(
            "meta", property="twitter:image"
        )
        if og_image and og_image.get("content"):
            src = og_image["content"]

        # ==========================================
        # JSON-LD (MAIN DATA SOURCE)
        # ==========================================
        json_ld = soup.find_all("script", type="application/ld+json")

        for tag in json_ld:
            try:
                if not tag.string:
                    continue

                data = json.loads(tag.string)

                if isinstance(data, dict) and data.get("@type") in ["NewsArticle", "Article"]:

                    # IMAGE
                    if not src and "image" in data:
                        if isinstance(data["image"], list):
                            src = data["image"][0]
                        elif isinstance(data["image"], dict):
                            src = data["image"].get("url")
                        else:
                            src = data["image"]

                    # DATE
                    published_at = data.get("datePublished") or data.get("dateModified")

                    # AUTHOR
                    if "author" in data:
                        if isinstance(data["author"], list):
                            author = data["author"][0].get("name")
                        elif isinstance(data["author"], dict):
                            author = data["author"].get("name")

                    # DESCRIPTION
                    description = data.get("description")

            except Exception:
                continue

        # ==========================================
        # HARD FALLBACK
        # ==========================================
        if not src:
            logging.info(f"❌ No image: {title}")
            return None

        if "placeholder" in src.lower():
            return None

        image_info = await get_image_info_async(src)

        if not image_info:
            logging.info(f"⚠️ Image rejected: {title}")
            return None

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

            "source_title1": "FORMULA 1",
            "source_title2": "F1",
            "source_color": "#E10600",
            "flag": "🇬🇧",
        }

    except Exception as e:
        logging.error(f"❌ Article error: {e}")
        return None

    finally:
        await context.close()


# ==========================================
# MAIN SCRAPER
# ==========================================

async def scrape_f1_async():
    logging.info("🚀 Starting F1 RSS + scraping pipeline...")

    try:
        feed = feedparser.parse(START_URL)

        tasks = []

        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")

            title = re.sub(r"\s*-\s*Formula 1.*$", "", title).strip()

            if title and link:
                tasks.append((title, link))

        logging.info(f"📊 RSS items: {len(tasks)}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            results: List[Dict[str, Any]] = []

            for i in range(0, len(tasks), CONCURRENT_TASKS):
                if len(results) >= MAX_NEWS_ITEMS:
                    break

                chunk = tasks[i : i + CONCURRENT_TASKS]

                coros = [
                    process_single_article(browser, title, link)
                    for title, link in chunk
                ]

                batch = await asyncio.gather(*coros)

                for item in batch:
                    if item:
                        results.append(item)

                        if len(results) >= MAX_NEWS_ITEMS:
                            break

            await browser.close()

            if results:
                with open("F1/f1_official.json", "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=4)

                logging.info(f"🎉 Saved {len(results)} F1 articles")

    except Exception as e:
        logging.error(f"❌ F1 pipeline error: {e}")


if __name__ == "__main__":
    asyncio.run(scrape_f1_async())
