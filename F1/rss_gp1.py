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
START_URL = "https://www.gp1.hr/feed/"

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

PROXY_LIST = []

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# ==========================================
# IMAGE QUALITY
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        mounts = None
        if proxy:
            mounts = {
                "http://": httpx.AsyncHTTPTransport(proxy=proxy),
                "https://": httpx.AsyncHTTPTransport(proxy=proxy),
            }

        async with httpx.AsyncClient(mounts=mounts, timeout=10.0, headers=headers) as client:
            res = await client.get(url)

            if res.status_code != 200:
                return None

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
# ARTICLE PROCESSOR
# ==========================================
async def process_single_article(browser: Any, title: str, link: str) -> Optional[Dict[str, Any]]:
    proxy_config = None
    selected_proxy = None

    if PROXY_LIST:
        selected_proxy = random.choice(PROXY_LIST)
        proxy_config = {"server": selected_proxy}

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
        proxy=proxy_config,
    )

    page = await context.new_page()

    try:
        logging.info(f"🔍 GP1: {title[:40]}")

        await page.goto(link, wait_until="domcontentloaded", timeout=30000)
        soup = BeautifulSoup(await page.content(), "html.parser")

        src = None

        # OG IMAGE
        og = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        if og and og.get("content"):
            src = og["content"]

        # JSON-LD fallback
        if not src:
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(tag.string)
                    if isinstance(data, dict) and data.get("@type") == "NewsArticle":
                        img = data.get("image")
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

        if "placeholder" in src.lower() or "sys-fallback" in src.lower():
            return None

        img = await get_image_info_async(src, proxy=selected_proxy)
        if not img:
            return None

        return {
            "title": title,
            "link": link,
            "image_url": img["url"],
            "w": img["w"],
            "h": img["h"],
            "focus_y": img["focus_y"],
            "source_title1": "GP1",
            "source_title2": "F1",
            "source_color": "#FF0000",
            "flag": "🇭🇷",
        }

    except Exception:
        return None
    finally:
        await context.close()


# ==========================================
# MAIN SCRAPER (FIXED FEED HANDLING)
# ==========================================
async def scrape_gp1_async() -> None:
    logging.info("🚀 GP1 feed loading...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            res = await client.get(START_URL)

            if res.status_code != 200:
                logging.error(f"❌ Feed HTTP error: {res.status_code}")
                return

            xml = res.text.strip()

        # 🔥 CRITICAL FIX: sanity check
        if not xml or "<rss" not in xml:
            logging.error("❌ Feed nije XML (vjerojatno blocked HTML page)")
            return

        feed = feedparser.parse(xml)

        if not feed.entries:
            logging.error("❌ feedparser.entries = 0 (broken feed)")
            return

        tasks = []
        for e in feed.entries:
            title = e.get("title", "").strip()
            link = e.get("link", "")
            if title and link:
                tasks.append((title, link))

        logging.info(f"📊 GP1 entries: {len(tasks)}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            news = []

            for i in range(0, len(tasks), CONCURRENT_TASKS):
                if len(news) >= MAX_NEWS_ITEMS:
                    break

                chunk = tasks[i:i + CONCURRENT_TASKS]

                results = await asyncio.gather(
                    *[process_single_article(browser, t, l) for t, l in chunk]
                )

                for r in results:
                    if r:
                        news.append(r)
                        if len(news) >= MAX_NEWS_ITEMS:
                            break

            await browser.close()

        with open("F1/gp1.json", "w", encoding="utf-8") as f:
            json.dump(news[:MAX_NEWS_ITEMS], f, ensure_ascii=False, indent=4)

        logging.info(f"✅ GP1 done: {len(news)} articles")

    except Exception as e:
        logging.error(f"❌ GP1 fatal error: {e}")


if __name__ == "__main__":
    asyncio.run(scrape_gp1_async())
