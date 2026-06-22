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

# ==========================================
# KONFIG
# ==========================================
BASE_URL = "https://m.sportbild.bild.de"
START_URL = "https://m.sportbild.bild.de/fussball/startseite/fussball/home-33017580.sportMobile.html"

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========================================
# POMOĆNE FUNKCIJE
# ==========================================

def get_focus_y(w: int, h: int) -> float:
    ratio = round(w / h, 2)
    if ratio >= 1.6:
        return 0.30
    if 0.9 <= ratio <= 1.1:
        return 0.22
    if 1.2 <= ratio <= 1.6:
        return 0.35
    return 0.5


async def get_image_info_async(url: str) -> Optional[Dict[str, Any]]:
    if not url or not url.startswith("http") or "1x1" in url:
        return None

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
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
# SINGLE ARTICLE
# ==========================================

async def process_single_article(title: str, link: str) -> Optional[Dict[str, Any]]:
    published_at = None
    author = None
    description = None
    src = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={"width": 390, "height": 844},
        )

        page = await context.new_page()

        try:
            logging.info(f"🔍 Article: {title[:40]}")
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
            # JSON-LD FALLBACK (ključan dio)
            # ==========================================
            json_ld_tags = soup.find_all("script", type="application/ld+json")

            for tag in json_ld_tags:
                try:
                    if not tag.string:
                        continue

                    data = json.loads(tag.string)

                    if isinstance(data, dict) and data.get("@type") in ["NewsArticle", "Article"]:

                        if not src and "image" in data:
                            if isinstance(data["image"], list):
                                src = data["image"][0]
                            elif isinstance(data["image"], dict):
                                src = data["image"].get("url")
                            else:
                                src = data["image"]

                        published_at = data.get("datePublished") or data.get("dateModified")

                        if "author" in data:
                            if isinstance(data["author"], list):
                                author = data["author"][0].get("name")
                            elif isinstance(data["author"], dict):
                                author = data["author"].get("name")

                        description = data.get("description")

                except Exception:
                    continue

            if not src:
                logging.info(f"❌ No image: {title}")
                return None

            if src.startswith("/"):
                src = BASE_URL + src

            image_info = await get_image_info_async(src)

            if not image_info:
                logging.info(f"⚠️ Image invalid: {title}")
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

                "source_title1": "SPORT",
                "source_title2": "BILD",
                "source_color": "#fc4e4e",
                "flag": "🇩🇪",
            }

        except Exception as e:
            logging.error(f"❌ Error article: {e}")
            return None

        finally:
            await context.close()
            await browser.close()


# ==========================================
# MAIN SCRAPER
# ==========================================

async def scrape_bild():
    logging.info("🚀 Starting BILD scraper...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844}
        )

        page = await context.new_page()

        await page.goto(START_URL, wait_until="networkidle")
        await page.evaluate("window.scrollBy(0, 2500)")
        await page.wait_for_timeout(2000)

        soup = BeautifulSoup(await page.content(), "html.parser")
        articles = soup.find_all("article")

        logging.info(f"📊 Found: {len(articles)} articles")

        tasks = []

        for art in articles:
            title_elem = art.find(["h2", "h3", "h4"])
            link_elem = art.find("a", href=True)

            if title_elem and link_elem:
                title = re.sub(r"^[:\s–|-]+", "", title_elem.get_text(strip=True))
                link = link_elem["href"]

                if link.startswith("/"):
                    link = BASE_URL + link

                tasks.append((title, link))

        await context.close()

        results: List[Dict[str, Any]] = []

        for i in range(0, len(tasks), CONCURRENT_TASKS):
            if len(results) >= MAX_NEWS_ITEMS:
                break

            chunk = tasks[i : i + CONCURRENT_TASKS]

            coros = [
                process_single_article(title, link)
                for title, link in chunk
            ]

            batch = await asyncio.gather(*coros)

            for item in batch:
                if item:
                    results.append(item)

                    if len(results) >= MAX_NEWS_ITEMS:
                        break

        if results:
            with open("Football/bild.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=4)

            logging.info(f"🎉 Done: {len(results)} articles saved")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(scrape_bild())
