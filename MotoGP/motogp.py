
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from datetime import datetime, timezone
from io import BytesIO

import httpx
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from playwright.async_api import async_playwright


# ==========================================
# CONFIG
# ==========================================

START_URL = "https://www.motogp.com/en/news/latest-news"

OUTPUT_FILE = Path("MotoGP/motogp_official.json")

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400

MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

SOURCE_TITLE1 = "MotoGP"
SOURCE_TITLE2 = "MotoGP"
SOURCE_COLOR = "#00AEEF"
SOURCE_FLAG = "🏁"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# ==========================================
# TEXT UTILS
# ==========================================

def clean_text(value: Optional[str]) -> str:

    if not value:
        return ""

    text = BeautifulSoup(
        str(value),
        "html.parser"
    ).get_text(" ", strip=True)

    return " ".join(text.split())


def normalize_url(url: str) -> str:

    if not url:
        return ""

    return urljoin(
        "https://www.motogp.com",
        url
    )


# ==========================================
# IMAGE UTILS
# ==========================================

def get_focus_y(w: int, h: int) -> float:

    if h <= 0:
        return 0.5

    ratio = w / h

    if ratio >= 1.6:
        return 0.35

    if 0.9 <= ratio <= 1.1:
        return 0.25

    return 0.5


async def get_image_info_async(
    client: httpx.AsyncClient,
    url: str,
) -> Optional[Dict[str, Any]]:

    if not url or not url.startswith(("http://", "https://")):
        return None

    if "1x1" in url or "placeholder" in url.lower():
        return None

    try:

        response = await client.get(url)
        response.raise_for_status()

        if len(response.content) < MIN_IMAGE_WEIGHT_BYTES:
            return None

        with Image.open(BytesIO(response.content)) as img:
            img.verify()

        with Image.open(BytesIO(response.content)) as img:
            w, h = img.size

        if w < MIN_IMAGE_WIDTH_PX or h <= 0:
            return None

        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h),
        }

    except (
        httpx.HTTPError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:

        logging.warning(
            "Greška sa slikom %s: %s",
            url,
            exc,
        )

        return None


# ==========================================
# ARTICLE LINK DISCOVERY
# ==========================================

async def get_article_links(page: Any) -> List[Dict[str, str]]:

    logging.info("Dohvaćam popis MotoGP vijesti...")

    await page.goto(
        START_URL,
        wait_until="domcontentloaded",
        timeout=45000,
    )

    await page.wait_for_timeout(3000)

    # Scroll to trigger lazy-loaded content
    for _ in range(3):

        await page.evaluate(
            "window.scrollTo(0, document.body.scrollHeight)"
        )

        await page.wait_for_timeout(1200)

    soup = BeautifulSoup(
        await page.content(),
        "html.parser"
    )

    articles = []
    seen = set()

    for a in soup.select("a[href]"):

        href = a.get("href", "")

        if not href:
            continue

        link = normalize_url(href)

        # Only MotoGP news article URLs
        if "/en/news/" not in link:
            continue

        if link.rstrip("/") == START_URL.rstrip("/"):
            continue

        if link in seen:
            continue

        title = clean_text(a.get_text(" ", strip=True))

        if not title:
            title = clean_text(a.get("aria-label"))

        if not title:
            image = a.find("img")

            if image:
                title = clean_text(
                    image.get("alt")
                )

        if len(title) < 15:
            continue

        seen.add(link)

        articles.append({
            "title": title,
            "link": link,
        })

    logging.info(
        "Pronađeno poveznica: %d",
        len(articles)
    )

    return articles[:MAX_NEWS_ITEMS * 3]


# ==========================================
# JSON-LD HELPERS
# ==========================================

def find_article_data(data: Any) -> Optional[Dict[str, Any]]:

    if isinstance(data, list):

        for item in data:

            result = find_article_data(item)

            if result:
                return result

    if not isinstance(data, dict):
        return None

    article_types = [
        "NewsArticle",
        "Article",
        "ReportageNewsArticle",
        "BlogPosting",
    ]

    item_type = data.get("@type", [])

    if isinstance(item_type, str):
        item_type = [item_type]

    if any(t in article_types for t in item_type):
        return data

    if "@graph" in data:
        return find_article_data(data["@graph"])

    return None


def extract_author(data: Any) -> Optional[str]:

    if not data:
        return None

    if isinstance(data, list):

        names = [
            extract_author(item)
            for item in data
        ]

        names = [name for name in names if name]

        return ", ".join(names) if names else None

    if isinstance(data, dict):
        return clean_text(
            data.get("name")
        ) or None

    return clean_text(data) or None


def extract_image(data: Any) -> Optional[str]:

    if not data:
        return None

    if isinstance(data, str):
        return data

    if isinstance(data, list):

        for item in data:

            result = extract_image(item)

            if result:
                return result

    if isinstance(data, dict):

        return (
            data.get("url")
            or data.get("contentUrl")
        )

    return None


# ==========================================
# ARTICLE SCRAPER
# ==========================================

async def process_single_article(
    browser: Any,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    article: Dict[str, str],
) -> Optional[Dict[str, Any]]:

    title = article["title"]
    link = article["link"]

    context = None

    async with semaphore:

        try:

            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={
                    "width": 1280,
                    "height": 720,
                },
            )

            page = await context.new_page()

            logging.info(
                "Obrađujem: %s",
                title[:65]
            )

            await page.goto(
                link,
                wait_until="domcontentloaded",
                timeout=40000,
            )

            await page.wait_for_timeout(1000)

            soup = BeautifulSoup(
                await page.content(),
                "html.parser"
            )

            # ==================================
            # META HELPER
            # ==================================

            def meta_content(*selectors: str) -> Optional[str]:

                for selector in selectors:

                    tag = soup.select_one(selector)

                    if tag and tag.get("content"):

                        return tag["content"].strip()

                return None

            # ==================================
            # JSON-LD
            # ==================================

            json_article = None

            for tag in soup.find_all(
                "script",
                type="application/ld+json"
            ):

                try:

                    raw = (
                        tag.string
                        or tag.get_text()
                    )

                    if not raw:
                        continue

                    data = json.loads(raw)

                    json_article = find_article_data(data)

                    if json_article:
                        break

                except Exception:
                    continue

            # ==================================
            # TITLE
            # ==================================

            final_title = (
                clean_text(
                    json_article.get("headline")
                )
                if json_article else ""
            )

            if not final_title:

                final_title = meta_content(
                    'meta[property="og:title"]',
                    'meta[name="twitter:title"]',
                ) or title

            # ==================================
            # IMAGE
            # ==================================

            image_url = meta_content(
                'meta[property="og:image"]',
                'meta[name="twitter:image"]',
            )

            if not image_url and json_article:

                image_url = extract_image(
                    json_article.get("image")
                )

            if not image_url:

                logging.info(
                    "Nema slike: %s",
                    final_title[:60]
                )

                return None

            image_url = normalize_url(image_url)

            image = await get_image_info_async(
                client,
                image_url,
            )

            if not image:

                logging.info(
                    "Slika nije valjana: %s",
                    final_title[:60]
                )

                return None

            # ==================================
            # DESCRIPTION
            # ==================================

            description = (
                (
                    json_article.get("description")
                    if json_article else None
                )
                or meta_content(
                    'meta[property="og:description"]',
                    'meta[name="description"]',
                    'meta[name="twitter:description"]',
                )
            )

            description = clean_text(description) or None

            # ==================================
            # AUTHOR
            # ==================================

            author = None

            if json_article:
                author = extract_author(
                    json_article.get("author")
                )

            if not author:

                author = meta_content(
                    'meta[name="author"]',
                    'meta[property="article:author"]',
                )

            # ==================================
            # DATE
            # ==================================

            published_at = None

            if json_article:

                published_at = (
                    json_article.get("datePublished")
                    or json_article.get("dateModified")
                )

            if not published_at:

                published_at = meta_content(
                    'meta[property="article:published_time"]',
                    'meta[name="date"]',
                )

            # ==================================
            # RESULT
            # ==================================

            return {

                "title": final_title,

                "link": link,

                "image_url": image["url"],

                "w": image["w"],

                "h": image["h"],

                "focus_y": image["focus_y"],

                "published_at": published_at,

                "author": author,

                "description": description,

                "source_title1": SOURCE_TITLE1,

                "source_title2": SOURCE_TITLE2,

                "source_color": SOURCE_COLOR,

                "flag": SOURCE_FLAG,
            }

        except Exception:

            logging.exception(
                "Greška pri obradi članka: %s",
                link
            )

            return None

        finally:

            if context is not None:

                try:
                    await context.close()

                except Exception:
                    pass


# ==========================================
# MAIN SCRAPER
# ==========================================

async def scrape_motogp_async():

    logging.info(
        "Pokrećem MotoGP službeni scraper..."
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.motogp.com/",
    }

    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers=headers,
    ) as client:

        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True
            )

            try:

                listing_context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={
                        "width": 1280,
                        "height": 900,
                    },
                )

                listing_page = await listing_context.new_page()

                articles = await get_article_links(
                    listing_page
                )

                await listing_context.close()

                if not articles:

                    logging.error(
                        "Nisu pronađeni članci. "
                        "Postojeći JSON ostaje sačuvan."
                    )

                    return

                semaphore = asyncio.Semaphore(
                    CONCURRENT_TASKS
                )

                results = []

                for i in range(
                    0,
                    len(articles),
                    CONCURRENT_TASKS
                ):

                    if len(results) >= MAX_NEWS_ITEMS:
                        break

                    batch = articles[
                        i:i + CONCURRENT_TASKS
                    ]

                    tasks = [

                        process_single_article(
                            browser,
                            client,
                            semaphore,
                            article,
                        )

                        for article in batch
                    ]

                    outcomes = await asyncio.gather(
                        *tasks,
                        return_exceptions=True,
                    )

                    for item in outcomes:

                        if isinstance(item, BaseException):

                            logging.error(
                                "Zadatak nije uspio: %r",
                                item,
                            )

                        elif item:

                            results.append(item)

                            if len(results) >= MAX_NEWS_ITEMS:
                                break

            finally:

                await browser.close()

    # ======================================
    # SAVE JSON
    # ======================================

    if not results:

        logging.error(
            "Nijedan članak nije uspješno obrađen. "
            "Postojeći JSON neće biti prepisan."
        )

        return

    temp_file = OUTPUT_FILE.with_suffix(".tmp")

    with temp_file.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            results,
            f,
            ensure_ascii=False,
            indent=4,
        )

    temp_file.replace(
        OUTPUT_FILE
    )

    logging.info(
        "Gotovo! Spremljeno %d MotoGP vijesti u %s",
        len(results),
        OUTPUT_FILE,
    )


# ==========================================
# START
# ==========================================

if __name__ == "__main__":

    asyncio.run(
        scrape_motogp_async()
    )
