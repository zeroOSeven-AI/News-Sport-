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

START_URL = "https://www.autosport.com/rss/f1/news"

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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

        return {"url": url, "w": w, "h": h, "focus_y": get_focus_y(w, h)}

    except Exception:
        return None


async def process_single_article(browser: Any, title: str, link: str):

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        viewport={"width": 1280, "height": 720},
    )

    page = await context.new_page()

    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=30000)

        soup = BeautifulSoup(await page.content(), "html.parser")

        src = None

        og = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        if og and og.get("content"):
            src = og["content"]

        if not src:
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
            "source_title1": "AUTOSPORT",
            "source_title2": "F1",
            "source_color": "#000000",
            "flag": "🇬🇧",
        }

    finally:
        await context.close()


async def scrape_autosport_async():

    feed = feedparser.parse(START_URL)
    tasks = [(e.get("title",""), e.get("link","")) for e in feed.entries]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        results = []

        for i in range(0, len(tasks), CONCURRENT_TASKS):

            chunk = tasks[i:i+CONCURRENT_TASKS]

            batch = await asyncio.gather(*[
                process_single_article(browser, t, l)
                for t, l in chunk
            ])

            for item in batch:
                if item:
                    results.append(item)

        await browser.close()

    with open("F1/autosport.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    asyncio.run(scrape_autosport_async())
