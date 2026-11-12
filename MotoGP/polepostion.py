
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from io import BytesIO

import httpx
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from playwright.async_api import async_playwright


# ==========================================
# CONFIG
# ==========================================

START_URL = "https://www.poleposition.hr/category/motogp/"

OUTPUT_FILE = Path("MotoGP/poleposition.json")

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400

MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

# Broj stranica kategorije koje će scraper pregledati
MAX_CATEGORY_PAGES = 5

SOURCE_TITLE1 = "POLE"
SOURCE_TITLE2 = "POSITION"
SOURCE_COLOR = "#111111"
SOURCE_FLAG = "🇭🇷"

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
        START_URL,
        url
    ).split("#")[0]


def get_meta(
    soup: BeautifulSoup,
    *selectors: str,
) -> Optional[str]:

    for selector in selectors:

        tag = soup.select_one(selector)

        if tag:

            value = (
                tag.get("content")
                or tag.get("datetime")
            )

            if value:
                return value.strip()

    return None


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


def extract_image_url(value: Any) -> Optional[str]:

    if not value:
        return None

    if isinstance(value, str):
        return value

    if isinstance(value, list):

        for item in value:

            result = extract_image_url(item)

            if result:
                return result

    if isinstance(value, dict):

        return (
            value.get("url")
            or value.get("contentUrl")
        )

    return None


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
        "BlogPosting",
        "ReportageNewsArticle",
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


# ==========================================
# CATEGORY SCRAPER
# ==========================================

async def get_article_links(
    page: Any,
) -> List[Dict[str, str]]:

    logging.info(
        "Dohvaćam MotoGP članke s Pole Positiona..."
    )

    articles = []
    seen = set()

    for page_number in range(1, MAX_CATEGORY_PAGES + 1):

        if page_number == 1:

            category_url = START_URL

        else:

            category_url = urljoin(
                START_URL,
                f"page/{page_number}/"
            )

        logging.info(
            "Pregledavam kategoriju: %s",
            category_url
        )

        try:

            response = await page.goto(
                category_url,
                wait_until="domcontentloaded",
                timeout=40000,
            )

            if response and response.status >= 400:

                logging.warning(
                    "Stranica vraća HTTP %s: %s",
                    response.status,
                    category_url,
                )

                break

            await page.wait_for_timeout(1200)

            soup = BeautifulSoup(
                await page.content(),
                "html.parser"
            )

            page_articles = []

            # Primarno čitanje WordPress članaka
            containers = soup.select(
                "article, .post, .type-post"
            )

            for container in containers:

                link_tag = container.select_one(
                    "h1 a[href], h2 a[href], h3 a[href], "
                    ".entry-title a[href], .post-title a[href]"
                )

                if not link_tag:
                    link_tag = container.select_one("a[href]")

                if not link_tag:
                    continue

                href = link_tag.get("href", "")

                link = normalize_url(href)

                if not link.startswith("https://www.poleposition.hr/"):
                    continue

                if "/category/" in link or "/page/" in link:
                    continue

                title = clean_text(
                    link_tag.get_text(" ", strip=True)
                )

                if len(title) < 10:
                    continue

                image_url = None

                image_tag = container.select_one("img")

                if image_tag:

                    image_url = (
                        image_tag.get("data-src")
                        or image_tag.get("data-lazy-src")
                        or image_tag.get("src")
                    )

                    if not image_url:

                        srcset = (
                            image_tag.get("data-srcset")
                            or image_tag.get("srcset")
                        )

                        if srcset:
                            image_url = srcset.split(",")[0].strip().split(" ")[0]

                date_tag = container.select_one(
                    "time[datetime], .entry-date, .posted-on"
                )

                published_at = None

                if date_tag:

                    published_at = (
                        date_tag.get("datetime")
                        or clean_text(date_tag.get_text())
                    )

                page_articles.append({
                    "title": title,
                    "link": link,
                    "image_url": normalize_url(image_url) if image_url else "",
                    "published_at": published_at or "",
                })

            # Fallback ako stranica ne koristi article elemente
            if not page_articles:

                for link_tag in soup.select(
                    "h2 a[href], h3 a[href], .entry-title a[href]"
                ):

                    link = normalize_url(
                        link_tag.get("href", "")
                    )

                    if (
                        not link.startswith("https://www.poleposition.hr/")
                        or "/category/" in link
                        or "/page/" in link
                    ):
                        continue

                    title = clean_text(
                        link_tag.get_text(" ", strip=True)
                    )

                    if len(title) < 10:
                        continue

                    page_articles.append({
                        "title": title,
                        "link": link,
                        "image_url": "",
                        "published_at": "",
                    })

            new_count = 0

            for article in page_articles:

                if article["link"] in seen:
                    continue

                seen.add(article["link"])
                articles.append(article)
                new_count += 1

            logging.info(
                "Stranica %d: pronađeno %d novih članaka",
                page_number,
                new_count,
            )

            if new_count == 0:
                break

            if len(articles) >= MAX_NEWS_ITEMS * 2:
                break

        except Exception:

            logging.exception(
                "Greška pri dohvaćanju kategorije: %s",
                category_url
            )

            break

    logging.info(
        "Ukupno pronađeno članaka: %d",
        len(articles)
    )

    return articles[:MAX_NEWS_ITEMS * 2]


# ==========================================
# PROCESS SINGLE ARTICLE
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

            await page.wait_for_timeout(800)

            soup = BeautifulSoup(
                await page.content(),
                "html.parser"
            )

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

            final_title = ""

            if json_article:
                final_title = clean_text(
                    json_article.get("headline")
                    or json_article.get("name")
                )

            if not final_title:

                final_title = (
                    get_meta(
                        soup,
                        'meta[property="og:title"]',
                        'meta[name="twitter:title"]',
                    )
                    or title
                )

                final_title = clean_text(final_title)

            # ==================================
            # IMAGE
            # ==================================

            image_url = get_meta(
                soup,
                'meta[property="og:image"]',
                'meta[name="twitter:image"]',
            )

            if not image_url and json_article:

                image_url = extract_image_url(
                    json_article.get("image")
                )

            if not image_url:

                image_url = article.get("image_url")

            if not image_url:

                image_tag = soup.select_one(
                    ".wp-post-image, "
                    ".post-thumbnail img, "
                    ".entry-content img, "
                    "article img"
                )

                if image_tag:

                    image_url = (
                        image_tag.get("data-src")
                        or image_tag.get("data-lazy-src")
                        or image_tag.get("src")
                    )

            if not image_url:

                logging.warning(
                    "Nema glavne slike: %s",
                    final_title[:60]
                )

                return None

            image_url = normalize_url(image_url)

            image = await get_image_info_async(
                client,
                image_url,
            )

            if not image:

                logging.warning(
                    "Slika nije valjana: %s",
                    final_title[:60]
                )

                return None

            # ==================================
            # DESCRIPTION
            # ==================================

            description = None

            if json_article:
                description = json_article.get("description")

            if not description:

                description = get_meta(
                    soup,
                    'meta[property="og:description"]',
                    'meta[name="description"]',
                    'meta[name="twitter:description"]',
                )

            if not description:

                paragraph = soup.select_one(
                    ".entry-content p, "
                    ".post-content p, "
                    "article p"
                )

                if paragraph:
                    description = paragraph.get_text(
                        " ",
                        strip=True
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

                author = get_meta(
                    soup,
                    'meta[name="author"]',
                    'meta[property="article:author"]',
                )

            if not author:

                author_tag = soup.select_one(
                    ".author, .author-name, .byline"
                )

                if author_tag:
                    author = clean_text(
                        author_tag.get_text()
                    )

            author = clean_text(author) or None

            # ==================================
            # PUBLISHED DATE
            # ==================================

            published_at = None

            if json_article:

                published_at = (
                    json_article.get("datePublished")
                    or json_article.get("dateCreated")
                    or json_article.get("dateModified")
                )

            if not published_at:

                published_at = get_meta(
                    soup,
                    'meta[property="article:published_time"]',
                    'meta[name="date"]',
                )

            if not published_at:

                date_tag = soup.select_one(
                    "time[datetime], .entry-date"
                )

                if date_tag:

                    published_at = (
                        date_tag.get("datetime")
                        or clean_text(date_tag.get_text())
                    )

            if not published_at:
                published_at = article.get("published_at") or None

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

async def scrape_poleposition_motogp_async():

    logging.info(
        "Pokrećem Pole Position MotoGP scraper..."
    )

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.poleposition.hr/",
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

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
        "Gotovo! Spremljeno %d članaka u %s",
        len(results),
        OUTPUT_FILE,
    )


# ==========================================
# START
# ==========================================

if __name__ == "__main__":

    asyncio.run(
        scrape_poleposition_motogp_async()
    )
