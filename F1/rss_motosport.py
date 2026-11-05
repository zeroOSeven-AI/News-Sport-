
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from io import BytesIO
from calendar import timegm

import feedparser
import httpx
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from playwright.async_api import async_playwright


START_URL = "https://www.motorsport-magazin.com/rss/formel1.xml"

OUTPUT_FILE = Path("F1/motorsport_magazin.json")

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400

MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

SOURCE_TITLE1 = "MOTORSPORT MAGAZIN"
SOURCE_TITLE2 = "F1"
SOURCE_COLOR = "#FFD300"
SOURCE_FLAG = "🇩🇪"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# --------------------------------------------------
# IMAGE FOCUS
# --------------------------------------------------

def get_focus_y(w: int, h: int) -> float:

    if h <= 0:
        return 0.5

    ratio = w / h

    if ratio >= 1.6:
        return 0.5

    if 0.9 <= ratio <= 1.1:
        return 0.5

    return 0.5


# --------------------------------------------------
# IMAGE URL FIX
# --------------------------------------------------

def fix_image_url(url: str) -> str:

    if not url:
        return url

    # Remove Motorsport Magazin blue-frame variant
    url = url.replace("/n_fb/", "/")

    return url


# --------------------------------------------------
# PUBLISHED DATE
# --------------------------------------------------

def get_published_at(entry: Any) -> Optional[str]:

    parsed = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
    )

    if parsed:
        try:
            return datetime.fromtimestamp(
                timegm(parsed),
                tz=timezone.utc,
            ).isoformat()

        except (ValueError, OverflowError, TypeError):
            pass

    return None


# --------------------------------------------------
# TEXT CLEANING
# --------------------------------------------------

def clean_text(value: Optional[str]) -> str:

    if not value:
        return ""

    text = BeautifulSoup(
        value,
        "html.parser"
    ).get_text(" ", strip=True)

    return " ".join(text.split())


def get_article_title(entry: Any, soup: BeautifulSoup) -> str:

    rss_title = clean_text(entry.get("title"))

    og_title = soup.find(
        "meta",
        property="og:title"
    )

    page_title = ""

    if og_title and og_title.get("content"):
        page_title = clean_text(
            og_title["content"]
        )

    if "\ufffd" in rss_title and page_title:
        return page_title

    return rss_title or page_title


# --------------------------------------------------
# IMAGE INFORMATION
# --------------------------------------------------

async def get_image_info_async(
    client: httpx.AsyncClient,
    url: str,
) -> Optional[dict]:

    if not url or not url.startswith(("http://", "https://")):
        return None

    if "1x1" in url:
        return None

    try:

        response = await client.get(url)
        response.raise_for_status()

        if len(response.content) < MIN_IMAGE_WEIGHT_BYTES:

            logging.info(
                "Slika je premala: %s",
                url
            )

            return None

        with Image.open(BytesIO(response.content)) as img:
            img.verify()

        with Image.open(BytesIO(response.content)) as img:
            w, h = img.size

        if w < MIN_IMAGE_WIDTH_PX or h <= 0:

            logging.info(
                "Nedovoljne dimenzije slike: %s (%s x %s)",
                url,
                w,
                h,
            )

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
            "Ne mogu dohvatiti sliku %s: %s",
            url,
            exc,
        )

        return None


# --------------------------------------------------
# PROCESS SINGLE ARTICLE
# --------------------------------------------------

async def process_single_article(
    browser: Any,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    entry: Any,
) -> Optional[dict]:

    link = entry.get("link", "")

    if not link:
        return None

    context = None

    async with semaphore:

        try:

            context = await browser.new_context(

                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),

                viewport={
                    "width": 1280,
                    "height": 720,
                },
            )

            page = await context.new_page()

            await page.goto(
                link,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            soup = BeautifulSoup(
                await page.content(),
                "html.parser"
            )

            # TITLE
            title = get_article_title(
                entry,
                soup
            )

            logging.info(
                "Obrađujem: %s",
                title[:70]
            )

            # META DATA HELPER
            def meta_content(*selectors: str) -> Optional[str]:

                for selector in selectors:

                    tag = soup.select_one(selector)

                    if tag and tag.get("content"):

                        return tag["content"].strip()

                return None

            # IMAGE
            image_url = meta_content(
                'meta[property="og:image"]',
                'meta[name="twitter:image"]',
            )

            if not image_url:

                logging.warning(
                    "Nema glavne slike: %s",
                    link
                )

                return None

            # FIX BLUE FRAME IN IMAGE URL
            original_image_url = image_url

            image_url = fix_image_url(image_url)

            if image_url != original_image_url:

                logging.info(
                    "Ispravljen URL slike: %s",
                    image_url
                )

            image = await get_image_info_async(
                client,
                image_url
            )

            if not image:

                logging.warning(
                    "Nema valjane slike: %s",
                    link
                )

                return None

            # DESCRIPTION
            description = (
                meta_content(
                    'meta[property="og:description"]',
                    'meta[name="description"]',
                    'meta[name="twitter:description"]',
                )
                or clean_text(entry.get("summary"))
            )

            # AUTHOR
            author = meta_content(
                'meta[name="author"]',
                'meta[property="article:author"]',
            )

            if not author:

                author = (
                    clean_text(entry.get("author"))
                    or None
                )

            # PUBLISHED DATE
            published_at = (
                meta_content(
                    'meta[property="article:published_time"]'
                )
                or get_published_at(entry)
            )

            # RESULT
            return {

                "title": title,

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

                except Exception as exc:

                    logging.warning(
                        "Kontekst je već zatvoren za %s: %s",
                        link,
                        exc,
                    )


# --------------------------------------------------
# MAIN SCRAPER
# --------------------------------------------------

async def scrape_motorsport_async():

    logging.info(
        "Dohvaćam RSS feed..."
    )

    async with httpx.AsyncClient(

        timeout=15.0,

        follow_redirects=True,

        headers={
            "User-Agent": "Mozilla/5.0",
        },

    ) as client:

        response = await client.get(
            START_URL
        )

        response.raise_for_status()

        # Use raw bytes to preserve German characters
        feed = feedparser.parse(
            response.content
        )

        if not feed.entries:

            logging.error(
                "RSS feed je prazan. "
                "Postojeći JSON ostaje sačuvan."
            )

            return

        entries = feed.entries[:MAX_NEWS_ITEMS]

        logging.info(
            "Pronađeno članaka u RSS-u: %d",
            len(entries)
        )

        semaphore = asyncio.Semaphore(
            CONCURRENT_TASKS
        )

        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True
            )

            try:

                tasks = [

                    process_single_article(
                        browser,
                        client,
                        semaphore,
                        entry,
                    )

                    for entry in entries
                ]

                outcomes = await asyncio.gather(
                    *tasks,
                    return_exceptions=True,
                )

                results = []

                for outcome in outcomes:

                    if isinstance(outcome, BaseException):

                        logging.error(
                            "Zadatak nije uspio: %r",
                            outcome,
                        )

                    elif outcome is not None:

                        results.append(outcome)

            finally:

                try:

                    await browser.close()

                except Exception as exc:

                    logging.warning(
                        "Preglednik je već zatvoren: %s",
                        exc,
                    )

    # --------------------------------------------------
    # SAVE JSON
    # --------------------------------------------------

    if not results:

        logging.error(
            "Nijedan članak nije uspješno obrađen. "
            "Postojeći JSON neće biti prepisan."
        )

        return

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = OUTPUT_FILE.with_suffix(
        ".tmp"
    )

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
        "Gotovo! Spremljeno %d vijesti u %s",
        len(results),
        OUTPUT_FILE,
    )


# --------------------------------------------------
# START
# --------------------------------------------------

if __name__ == "__main__":

    asyncio.run(
        scrape_motorsport_async()
    )
