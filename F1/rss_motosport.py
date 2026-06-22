import asyncio
import json
import logging
import random
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

import httpx
import feedparser
from bs4 import BeautifulSoup
from PIL import Image
from playwright.async_api import async_playwright

# ==========================================
# CONFIG
# ==========================================
START_URL = "https://www.motorsport-magazin.com/rss/formel1.xml"

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

PROXY_LIST = []

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# ==========================================
# IMAGE HELPERS
# ==========================================
def get_focus_y(w: int, h: int) -> float:
    ratio = round(w / h, 2)
    if ratio >= 1.6:
        return 0.35
    if 0.9 <= ratio <= 1.1:
        return 0.25
    return 0.5


async def get_image_info_async(url: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not url or not url.startswith("http") or "1x1" in url:
        return None

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        }

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
# ARTICLE PROCESSING
# ==========================================
async def process_single_article(browser, title: str, link: str) -> Optional[Dict[str, Any]]:
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        viewport={"width": 1280, "height": 720},
    )

    page = await context.new_page()

    try:
        logging.info(f"🔍 {title[:40]}...")
        await page.goto(link, wait_until="domcontentloaded", timeout=30000)

        soup = BeautifulSoup(await page.content(), "html.parser")

        src = None

        # 1. OG IMAGE
        og = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        if og and og.get("content"):
            src = og["content"]

        # 2. JSON-LD fallback
        if not src:
            scripts = soup.find_all("script", type="application/ld+json")
            for s in scripts:
                try:
                    data = json.loads(s.string)

                    if isinstance(data, list):
                        data = data[0]

                    if isinstance(data, dict) and "image" in data:
                        img = data["image"]
                        if isinstance(img, list):
                            src = img[0]
                        elif isinstance(img, dict):
                            src = img.get("url")
                        else:
                            src = img
                        break
                except Exception:
                    continue

        if not src:
            return None

        if "placeholder" in src.lower():
            return None

        image = await get_image_info_async(src)

        if not image:
            return None

        return {
            "title": title,
            "link": link,
            "image_url": image["url"],
            "w": image["w"],
            "h": image["h"],
            "focus_y": image["focus_y"],
            "source_title1": "MOTORSPORT MAGAZIN",
            "source_title2": "F1",
            "source_color": "#FFD300",
            "flag": "🇩🇪",
        }

    except Exception:
        return None

    finally:
        await context.close()


# ==========================================
# MAIN SCRAPER
# ==========================================
async def scrape_motorsport_async():
    logging.info("🚀 Motorsport scraper start")

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/rss+xml,application/xml"
    }

    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        r = await client.get(START_URL)
        feed = feedparser.parse(r.text)

    tasks = []

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "")

        if title and link:
            tasks.append((title, link))

    logging.info(f"📊 Feed items: {len(tasks)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        results = []

        for i in range(0, len(tasks), CONCURRENT_TASKS):
            if len(results) >= MAX_NEWS_ITEMS:
                break

            chunk = tasks[i:i + CONCURRENT_TASKS]

            jobs = [
                process_single_article(browser, t, l)
                for t, l in chunk
            ]

            out = await asyncio.gather(*jobs)

            for item in out:
                if item:
                    results.append(item)

        await browser.close()

    with open("F1/motorsport_magazin.json", "w", encoding="utf-8") as f:
        json.dump(results[:MAX_NEWS_ITEMS], f, ensure_ascii=False, indent=4)

    logging.info(f"✅ Done: {len(results)} items")


if __name__ == "__main__":
    asyncio.run(scrape_motorsport_async())
