
import asyncio
import json
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from playwright.async_api import async_playwright


# ==========================================
# CONFIG
# ==========================================

START_URL = "https://sportklub.hr/automoto/motogp/"

OUTPUT_FILE = Path("MotoGP/sportklub.json")

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400

MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5
MAX_CATEGORY_PAGES = 5

SOURCE_TITLE1 = "SPORT"
SOURCE_TITLE2 = "KLUB"
SOURCE_COLOR = "#E30613"
SOURCE_FLAG = "🇭🇷"

BASE_DOMAIN = "sportklub.hr"
CATEGORY_PATH = "/automoto/motogp/"

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


def normalize_url(url: str, base_url: str = START_URL) -> str:

    if not url:
        return ""

    url = urljoin(base_url, url).split("#")[0]

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return ""

    return urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),
        parsed.path,
        "",
        parsed.query,
        "",
    ))


def is_sportklub_url(url: str) -> bool:

    if not url:
        return False

    parsed = urlparse(url)

    return (
        parsed.netloc.lower().endswith(BASE_DOMAIN)
        and parsed.scheme in ("http", "https")
    )


def is_motogp_article_url(url: str) -> bool:

    if not is_sportklub_url(url):
        return False

    path = urlparse(url).path.rstrip("/")

    if not path.startswith(CATEGORY_PATH.rstrip("/") + "/"):
        return False

    excluded = [
        "/page/",
        "/category/",
        "/tag/",
        "/author/",
    ]

    if any(item in path for item in excluded):
        return False

    return len(path.split("/")) >= 4


def get_meta(
    soup: BeautifulSoup,
    *selectors: str,
) -> Optional[str]:

    for selector in selectors:

        tag = soup.select_one(selector)

        if not tag:
            continue

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
            or value.get("@id")
        )

    return None


def extract_srcset(srcset: Optional[str]) -> Optional[str]:

    if not srcset:
        return None

    candidates = []

    for item in srcset.split(","):

        parts = item.strip().split()

        if not parts:
            continue

        url = parts[0]
        width = 0

        if len(parts) > 1:

            match = re.search(r"(\d+)w", parts[1])

            if match:
                width = int(match.group(1))

        candidates.append((width, url))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


def get_image_from_tag(image_tag) -> Optional[str]:

    if not image_tag:
        return None

    for attribute in (
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-image",
        "src",
    ):

        value = image_tag.get(attribute)

        if value and not value.startswith("data:image"):
            return value

    return (
        extract_srcset(image_tag.get("data-srcset"))
        or extract_srcset(image_tag.get("srcset"))
    )


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

    for key in ("@graph", "mainEntity", "mainEntityOfPage"):

        if key in data:

            result = find_article_data(data[key])

            if result:
                return result

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


def get_json_article(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:

    for tag in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            raw = tag.string or tag.get_text()

            if not raw:
                continue

            data = json.loads(raw)

            result = find_article_data(data)

            if result:
                return result

        except Exception:
            continue

    return None


# ==========================================
# CATEGORY PAGINATION
# ==========================================

async def get_category_pages(page: Any) -> List[str]:

    pages = [START_URL]
    seen = {START_URL}

    try:

        soup = BeautifulSoup(
            await page.content(),
            "html.parser"
        )

        # Rel next
        next_tag = soup.select_one(
            'a[rel="next"][href], link[rel="next"][href]'
        )

        if next_tag:

            next_url = normalize_url(
                next_tag.get("href", ""),
                START_URL,
            )

            if next_url and next_url not in seen:
                pages.append(next_url)
                seen.add(next_url)

        # Pagination links
        for link_tag in soup.select(
            ".pagination a[href], "
            ".nav-links a[href], "
            ".page-numbers[href], "
            "a.next[href]"
        ):

            href = normalize_url(
                link_tag.get("href", ""),
                START_URL,
            )

            if not href or href in seen:
                continue

            parsed = urlparse(href)

            if (
                is_sportklub_url(href)
                and parsed.path.rstrip("/") == CATEGORY_PATH.rstrip("/")
                and parsed.query
            ):

                pages.append(href)
                seen.add(href)

            elif (
                is_sportklub_url(href)
                and parsed.path.startswith(
                    CATEGORY_PATH.rstrip("/") + "/page/"
                )
            ):

                pages.append(href)
                seen.add(href)

            if len(pages) >= MAX_CATEGORY_PAGES:
                break

    except Exception:

        logging.exception(
            "Greška pri pronalasku paginacije."
        )

    return pages[:MAX_CATEGORY_PAGES]


# ==========================================
# CATEGORY SCRAPER
# ==========================================

async def get_article_links(
    page: Any,
) -> List[Dict[str, str]]:

    logging.info(
        "Dohvaćam MotoGP članke sa Sport Kluba..."
    )

    articles = []
    seen = set()

    try:

        response = await page.goto(
            START_URL,
            wait_until="domcontentloaded",
            timeout=45000,
        )

        if response and response.status >= 400:

            logging.error(
                "Sport Klub vraća HTTP %s",
                response.status,
            )

            return []

        await page.wait_for_timeout(1500)

        category_pages = await get_category_pages(page)

    except Exception:

        logging.exception(
            "Ne mogu otvoriti Sport Klub MotoGP rubriku."
        )

        return []

    for page_number, category_url in enumerate(
        category_pages,
        start=1,
    ):

        logging.info(
            "Pregledavam kategoriju %d/%d: %s",
            page_number,
            len(category_pages),
            category_url,
        )

        try:

            response = await page.goto(
                category_url,
                wait_until="domcontentloaded",
                timeout=45000,
            )

            if response and response.status >= 400:

                logging.warning(
                    "HTTP %s: %s",
                    response.status,
                    category_url,
                )

                continue

            await page.wait_for_timeout(1000)

            soup = BeautifulSoup(
                await page.content(),
                "html.parser",
            )

            page_articles = []

            # Prvo pokušaj pronaći članke unutar kartica
            containers = soup.select(
                "article, "
                ".post, "
                ".article, "
                ".news-item, "
                ".card, "
                "[class*='article'], "
                "[class*='post']"
            )

            for container in containers:

                link_tag = container.select_one(
                    "h1 a[href], "
                    "h2 a[href], "
                    "h3 a[href], "
                    "h4 a[href], "
                    "a[href]"
                )

                if not link_tag:
                    continue

                link = normalize_url(
                    link_tag.get("href", ""),
                    category_url,
                )

                if not is_motogp_article_url(link):
                    continue

                title = clean_text(
                    link_tag.get_text(" ", strip=True)
                )

                if len(title) < 10:
                    title = clean_text(
                        link_tag.get("title")
                    )

                if len(title) < 10:
                    continue

                image_tag = container.select_one("img")

                image_url = get_image_from_tag(image_tag)

                date_tag = container.select_one(
                    "time[datetime], "
                    "[class*='date'], "
                    "[class*='time']"
                )

                published_at = None

                if date_tag:

                    published_at = (
                        date_tag.get("datetime")
                        or date_tag.get("content")
                        or clean_text(date_tag.get_text())
                    )

                page_articles.append({
                    "title": title,
                    "link": link,
                    "image_url": normalize_url(
                        image_url,
                        category_url,
                    ) if image_url else "",
                    "published_at": published_at or "",
                })

            # Fallback: svi linkovi iz MotoGP rubrike
            if not page_articles:

                for link_tag in soup.select("a[href]"):

                    link = normalize_url(
                        link_tag.get("href", ""),
                        category_url,
                    )

                    if not is_motogp_article_url(link):
                        continue

                    title = clean_text(
                        link_tag.get_text(" ", strip=True)
                    )

                    if len(title) < 10:
                        title = clean_text(
                            link_tag.get("title")
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

            if len(articles) >= MAX_NEWS_ITEMS * 2:
                break

        except Exception:

            logging.exception(
                "Greška pri dohvaćanju: %s",
                category_url,
            )

    logging.info(
        "Ukupno pronađeno članaka: %d",
        len(articles),
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
                    "height": 900,
                },
            )

            page = await context.new_page()

            logging.info(
                "Obrađujem: %s",
                title[:65],
            )

            response = await page.goto(
                link,
                wait_until="domcontentloaded",
                timeout=45000,
            )

            if response and response.status >= 400:

                logging.warning(
                    "Članak vraća HTTP %s: %s",
                    response.status,
                    link,
                )

                return None

            await page.wait_for_timeout(700)

            soup = BeautifulSoup(
                await page.content(),
                "html.parser",
            )

            json_article = get_json_article(soup)

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

                final_title = clean_text(
                    get_meta(
                        soup,
                        'meta[property="og:title"]',
                        'meta[name="twitter:title"]',
                    )
                    or ""
                )

            if not final_title:

                heading = soup.select_one(
                    "h1, .article-title, .post-title"
                )

                if heading:
                    final_title = clean_text(
                        heading.get_text(" ", strip=True)
                    )

            if not final_title:
                final_title = title

            # ==================================
            # IMAGE
            # ==================================

            image_url = get_meta(
                soup,
                'meta[property="og:image"]',
                'meta[name="twitter:image"]',
                'meta[property="og:image:secure_url"]',
            )

            if not image_url and json_article:

                image_url = extract_image_url(
                    json_article.get("image")
                )

            if not image_url:

                image_tag = soup.select_one(
                    ".article-image img, "
                    ".article__image img, "
                    ".featured-image img, "
                    ".post-thumbnail img, "
                    "article img, "
                    "main img"
                )

                image_url = get_image_from_tag(image_tag)

            if not image_url:
                image_url = article.get("image_url")

            if not image_url:

                logging.warning(
                    "Nema glavne slike: %s",
                    final_title[:60],
                )

                return None

            image_url = normalize_url(
                image_url,
                link,
            )

            image = await get_image_info_async(
                client,
                image_url,
            )

            if not image:

                logging.warning(
                    "Slika nije valjana: %s",
                    final_title[:60],
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
                    ".article-content p, "
                    ".article__content p, "
                    ".entry-content p, "
                    ".post-content p, "
                    "article p, "
                    "main p"
                )

                if paragraph:
                    description = paragraph.get_text(
                        " ",
                        strip=True,
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
                    ".author, "
                    ".author-name, "
                    ".article-author, "
                    ".byline, "
                    "[rel='author']"
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
                )

            if not published_at:

                published_at = get_meta(
                    soup,
                    'meta[property="article:published_time"]',
                    'meta[name="date"]',
                    'meta[name="pubdate"]',
                    'meta[itemprop="datePublished"]',
                )

            if not published_at:

                date_tag = soup.select_one(
                    "time[datetime], "
                    ".article-date, "
                    ".post-date"
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
                link,
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

async def scrape_sportklub_motogp_async():

    logging.info(
        "Pokrećem Sport Klub MotoGP scraper..."
    )

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://sportklub.hr/",
    }

    results = []

    async with httpx.AsyncClient(
        timeout=25.0,
        follow_redirects=True,
        headers=headers,
    ) as client:

        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True,
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
                    listing_page,
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

                for i in range(
                    0,
                    len(articles),
                    CONCURRENT_TASKS,
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
        encoding="utf-8",
    ) as f:

        json.dump(
            results,
            f,
            ensure_ascii=False,
            indent=4,
        )

    temp_file.replace(
        OUTPUT_FILE,
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
        scrape_sportklub_motogp_async()
    )
