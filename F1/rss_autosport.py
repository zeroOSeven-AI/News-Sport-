import asyncio
import json
import logging
import random
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from PIL import Image
from playwright.async_api import async_playwright
import httpx
import feedparser

# ==========================================
# CONFIG
# ==========================================
START_URL = "https://www.autosport.com/rss/f1/news"

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

PROXY_LIST = []

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# ==========================================
# HELPERS
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        mounts = None
        if proxy:
            mounts = {
                "http://": httpx.AsyncHTTPTransport(proxy=proxy),
                "https://": httpx.AsyncHTTPTransport(proxy=proxy),
            }

        async with httpx.AsyncClient(mounts=mounts, timeout=10.0, headers=headers) as client:
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
async def process_single_article(browser: Any, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = entry.get("title", "").strip()
    link = entry.get("link", "")
    published = entry.get("published", "") or entry.get("updated", "")

    if not title or not link:
        return None

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
        logging.info(f"🔍 Article: {title[:40]}")

        await page.goto(link, wait_until="domcontentloaded", timeout=30000)
        soup = BeautifulSoup(await page.content(), "html.parser")

        src = None

        # 1. OG image
        og_image = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        if og_image and og_image.get("content"):
            src = og_image["content"]

        # 2. JSON-LD fallback
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

        image_info = await get_image_info_async(src, proxy=selected_proxy)
        if not image_info:
            return None

        return {
            "title": title,
            "link": link,
            "published": published,
            "image_url": image_info["url"],
            "w": image_info["w"],
            "h": image_info["h"],
            "focus_y": image_info["focus_y"],
            "source_title1": "AUTOSPORT",
            "source_title2": "F1",
            "source_color": "#000000",
            "flag": "🇬🇧",
        }

    except Exception:
        return None
    finally:
        await context.close()


# ==========================================
# MAIN
# ==========================================
async def scrape_autosport_async() -> None:
    logging.info("🚀 Loading Autosport RSS feed...")

    try:
        feed = feedparser.parse(START_URL)

        if not feed.entries:
            logging.warning("⚠️ Empty feed")
            return

        logging.info(f"📊 Feed items: {len(feed.entries)}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            news_items: List[Dict[str, Any]] = []

            for i in range(0, len(feed.entries), CONCURRENT_TASKS):
                if len(news_items) >= MAX_NEWS_ITEMS:
                    break

                chunk = feed.entries[i : i + CONCURRENT_TASKS]

                tasks = [process_single_article(browser, entry) for entry in chunk]
                results = await asyncio.gather(*tasks)

                for r in results:
                    if r:
                        news_items.append(r)
                        if len(news_items) >= MAX_NEWS_ITEMS:
                            break

            await browser.close()

        if news_items:
            with open("F1/autosport.json", "w", encoding="utf-8") as f:
                json.dump(news_items[:MAX_NEWS_ITEMS], f, ensure_ascii=False, indent=4)

            logging.info(f"✅ Saved {len(news_items)} articles")

    except Exception as e:
        logging.error(f"❌ Fatal error: {e}")


if __name__ == "__main__":
    asyncio.run(scrape_autosport_async())
