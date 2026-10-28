
import asyncio
import json
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageFile
from playwright.async_api import async_playwright


# ==========================================
# CONFIG — GP1
# ==========================================

START_URL = "https://www.gp1.hr/feed/"
OUTPUT_FILE = Path("F1/gp1.json")

MIN_IMAGE_WEIGHT_BYTES = 30000
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,application/rss+xml;"
        "q=0.8,*/*;q=0.7"
    ),
    "Accept-Language": "hr-HR,hr;q=0.9,en;q=0.8",
}

# ==========================================
# DATE PARSER
# ==========================================

def to_iso(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None

    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(
                date_str.replace("Z", "+00:00")
            ).isoformat()
        except Exception:
            return None


# ==========================================
# TEXT CLEANUP
# ==========================================

def clean_text(value: Any) -> Optional[str]:
    if not value:
        return None

    if isinstance(value, list):
        value = " ".join(str(x) for x in value)

    text = BeautifulSoup(
        str(value), "html.parser"
    ).get_text(" ", strip=True)

    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


# ==========================================
# IMAGE FOCUS — SAME AS F1
# ==========================================

def get_focus_y(w: int, h: int) -> float:
    if h <= 0:
        return 0.5

    ratio = round(w / h, 2)

    if ratio >= 1.6:
        return 0.35

    if 0.9 <= ratio <= 1.1:
        return 0.25

    return 0.5


# ==========================================
# IMAGE URL NORMALIZATION
# ==========================================

def normalize_image_url(url: Any, base_url: str = "") -> Optional[str]:
    if not isinstance(url, str):
        return None

    url = url.strip().strip("\"'")

    if not url:
        return None

    url = urljoin(base_url, url)

    if not url.startswith(("http://", "https://")):
        return None

    lowered = url.lower()

    # WordPress emoji images are not article photos
    if "s.w.org/images/core/emoji/" in lowered:
        return None

    if re.search(
        r"(?:placeholder|spacer|blank)\.(?:png|gif|jpe?g|webp)(?:\?|$)",
        lowered,
    ):
        return None

    # Remove WordPress generated thumbnail dimensions
    url = re.sub(
        r"-\d+x\d+(?=\.(?:jpg|jpeg|png|webp|avif)(?:\?|$))",
        "",
        url,
        flags=re.IGNORECASE,
    )

    return url


# ==========================================
# IMAGE CANDIDATE EXTRACTION
# ==========================================

def extract_image_candidates(
    entry: Dict[str, Any],
) -> List[str]:
    candidates: List[str] = []

    def add(url: Any, base_url: str = "") -> None:
        normalized = normalize_image_url(url, base_url)

        if normalized and normalized not in candidates:
            candidates.append(normalized)

    # 1. RSS media:content
    for item in entry.get("media_content", []) or []:
        if isinstance(item, dict):
            add(item.get("url"), entry.get("link", ""))

    # 2. RSS media:thumbnail
    for item in entry.get("media_thumbnail", []) or []:
        if isinstance(item, dict):
            add(item.get("url"), entry.get("link", ""))

    # 3. RSS enclosures
    for item in entry.get("enclosures", []) or []:
        if not isinstance(item, dict):
            continue

        url = item.get("href") or item.get("url")
        mime = item.get("type", "")

        if mime.startswith("image/") or (
            url and re.search(
                r"\.(jpg|jpeg|png|webp|avif)(?:\?|$)",
                url,
                re.IGNORECASE,
            )
        ):
            add(url, entry.get("link", ""))

    # 4. WordPress content and description
    html_parts = []

    for item in entry.get("content", []) or []:
        if isinstance(item, dict):
            html_parts.append(item.get("value", ""))

    html_parts.extend([
        entry.get("description", ""),
        entry.get("summary", ""),
    ])

    summary_detail = entry.get("summary_detail")

    if isinstance(summary_detail, dict):
        html_parts.append(summary_detail.get("value", ""))

    for html in html_parts:
        if not html:
            continue

        soup = BeautifulSoup(str(html), "html.parser")

        for img in soup.find_all("img"):
            # Standard and lazy-loaded images
            for attr in (
                "data-src",
                "data-lazy-src",
                "data-original",
                "data-large-file",
                "src",
            ):
                add(img.get(attr), entry.get("link", ""))

            # Responsive images
            srcset = img.get("srcset") or img.get("data-srcset") or ""

            for candidate in srcset.split(","):
                parts = candidate.strip().split()

                if parts:
                    add(parts[0], entry.get("link", ""))

    return candidates


# ==========================================
# IMAGE VALIDATION — SAME AS F1
# ==========================================

async def get_image_info_async(
    client: httpx.AsyncClient,
    url: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not url:
        return None

    try:
        response = await client.get(url)
        response.raise_for_status()

        content = response.content

        if len(content) < MIN_IMAGE_WEIGHT_BYTES:
            return None

        # Verify the file is a valid image
        with Image.open(BytesIO(content)) as img:
            img.verify()

        with Image.open(BytesIO(content)) as img:
            w, h = img.size

        if w < MIN_IMAGE_WIDTH_PX or h <= 0:
            return None

        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h),
        }

    except Exception as e:
        logging.debug("Image rejected: %s (%s)", url, e)
        return None


async def find_valid_image(
    client: httpx.AsyncClient,
    candidates: List[str],
) -> Optional[Dict[str, Any]]:
    checked = set()

    for url in candidates:
        if url in checked:
            continue

        checked.add(url)

        info = await get_image_info_async(client, url)

        if info:
            return info

    return None


# ==========================================
# ARTICLE PAGE FALLBACK
# ==========================================

async def extract_article_metadata(
    browser: Any,
    link: str,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "image_candidates": [],
        "published_at": None,
        "author": None,
        "description": None,
    }

    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 720},
        locale="hr-HR",
    )

    page = await context.new_page()

    try:
        await page.goto(
            link,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        # Give the page a short chance to finish loading metadata
        await page.wait_for_timeout(500)

        soup = BeautifulSoup(
            await page.content(),
            "html.parser",
        )

        candidates: List[str] = []

        def add_candidate(url: Any) -> None:
            normalized = normalize_image_url(url, link)

            if normalized and normalized not in candidates:
                candidates.append(normalized)

        # 1. Open Graph / Twitter metadata
        for key in (
            "og:image",
            "og:image:secure_url",
            "twitter:image",
            "twitter:image:src",
        ):
            tag = soup.find("meta", property=key)

            if not tag:
                tag = soup.find("meta", attrs={"name": key})

            if tag and tag.get("content"):
                add_candidate(tag["content"])

        # 2. JSON-LD
        for tag in soup.find_all(
            "script",
            type="application/ld+json",
        ):
            raw = tag.string or tag.get_text()

            if not raw:
                continue

            try:
                data = json.loads(raw)
            except Exception:
                continue

            objects = data if isinstance(data, list) else [data]

            for obj in objects:
                if not isinstance(obj, dict):
                    continue

                graph = obj.get("@graph", [])

                if isinstance(graph, list):
                    objects.extend(
                        x for x in graph if isinstance(x, dict)
                    )

                obj_type = obj.get("@type", [])

                if isinstance(obj_type, str):
                    obj_type = [obj_type]

                if not any(
                    t in ("NewsArticle", "Article", "BlogPosting")
                    for t in obj_type
                ):
                    continue

                image = obj.get("image")

                if isinstance(image, str):
                    add_candidate(image)

                elif isinstance(image, dict):
                    add_candidate(image.get("url"))
                    add_candidate(image.get("contentUrl"))

                elif isinstance(image, list):
                    for image_item in image:
                        if isinstance(image_item, str):
                            add_candidate(image_item)
                        elif isinstance(image_item, dict):
                            add_candidate(image_item.get("url"))
                            add_candidate(image_item.get("contentUrl"))

                metadata["published_at"] = (
                    metadata["published_at"]
                    or obj.get("datePublished")
                    or obj.get("dateModified")
                )

                author = obj.get("author")

                if isinstance(author, dict):
                    metadata["author"] = (
                        metadata["author"] or author.get("name")
                    )

                elif isinstance(author, list):
                    for author_item in author:
                        if isinstance(author_item, dict):
                            metadata["author"] = (
                                metadata["author"]
                                or author_item.get("name")
                            )

                metadata["description"] = (
                    metadata["description"]
                    or clean_text(obj.get("description"))
                )

        # 3. Article images in HTML as final fallback
        for img in soup.find_all("img"):
            for attr in (
                "data-large-file",
                "data-src",
                "data-lazy-src",
                "data-original",
                "src",
            ):
                add_candidate(img.get(attr))

            srcset = img.get("srcset") or img.get("data-srcset") or ""

            for candidate in srcset.split(","):
                parts = candidate.strip().split()

                if parts:
                    add_candidate(parts[0])

        metadata["image_candidates"] = candidates

    except Exception as e:
        logging.warning(
            "Article metadata failed (%s): %s",
            link,
            e,
        )

    finally:
        await context.close()

    return metadata


# ==========================================
# PROCESS SINGLE ARTICLE
# ==========================================

async def process(
    entry: Dict[str, Any],
    client: httpx.AsyncClient,
    browser: Any,
    semaphore: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:
    async with semaphore:
        title = clean_text(entry.get("title"))
        link = entry.get("link", "")

        if not title or not link:
            return None

        logging.info("Processing GP1: %s", title[:60])

        # RSS image candidates
        candidates = extract_image_candidates(entry)

        # Try each RSS candidate before opening the article
        image_info = await find_valid_image(client, candidates)

        # Article-page fallback if RSS images are missing or invalid
        metadata: Dict[str, Any] = {
            "image_candidates": [],
            "published_at": None,
            "author": None,
            "description": None,
        }

        if not image_info:
            logging.info("Trying article-page image: %s", title[:50])

            metadata = await extract_article_metadata(
                browser,
                link,
            )

            image_info = await find_valid_image(
                client,
                metadata["image_candidates"],
            )

        if not image_info:
            logging.warning("No valid image: %s", title[:60])
            return None

        # Description
        content_parts = entry.get("content", []) or []
        content_html = " ".join(
            item.get("value", "")
            for item in content_parts
            if isinstance(item, dict)
        )

        description = (
            clean_text(entry.get("description"))
            or clean_text(entry.get("summary"))
            or clean_text(content_html)
            or metadata.get("description")
        )

        # Author
        author = clean_text(entry.get("author"))

        if not author:
            authors = entry.get("authors", [])

            if isinstance(authors, list):
                for item in authors:
                    if isinstance(item, dict) and item.get("name"):
                        author = clean_text(item["name"])
                        break

        author = author or clean_text(metadata.get("author"))

        # Publication date
        published_at = to_iso(
            entry.get("published")
            or entry.get("updated")
            or entry.get("created")
        )

        if not published_at:
            published_at = to_iso(metadata.get("published_at"))

        # Exact shared schema with F1
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

            "source_title1": "GP1",
            "source_title2": "F1",
            "source_color": "#FF0000",
            "flag": "🇭🇷",
        }


# ==========================================
# SAVE JSON
# ==========================================

def save_json(articles: List[Dict[str, Any]]) -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    temp_file = OUTPUT_FILE.with_suffix(".tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(
            articles,
            file,
            ensure_ascii=False,
            indent=4,
        )

    temp_file.replace(OUTPUT_FILE)

    logging.info(
        "Saved %s articles to %s",
        len(articles),
        OUTPUT_FILE,
    )


# ==========================================
# MAIN PIPELINE
# ==========================================

async def run() -> None:
    logging.info("Starting GP1 RSS + article scraping pipeline...")

    timeout = httpx.Timeout(20.0, connect=10.0)

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=HEADERS,
        follow_redirects=True,
    ) as client:

        try:
            response = await client.get(START_URL)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

        except Exception as e:
            logging.error("Unable to fetch GP1 RSS: %s", e)
            return

        entries = list(getattr(feed, "entries", []))

        logging.info("RSS ITEMS: %s", len(entries))

        if not entries:
            logging.error(
                "RSS feed empty. Existing JSON was not overwritten."
            )
            return

        semaphore = asyncio.Semaphore(CONCURRENT_TASKS)
        articles: List[Dict[str, Any]] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            try:
                # Process in batches, allowing more than 20 RSS entries
                # to be examined until 20 valid articles are found.
                for start in range(0, len(entries), CONCURRENT_TASKS):
                    if len(articles) >= MAX_NEWS_ITEMS:
                        break

                    batch = entries[
                        start:start + CONCURRENT_TASKS
                    ]

                    results = await asyncio.gather(
                        *[
                            process(
                                entry,
                                client,
                                browser,
                                semaphore,
                            )
                            for entry in batch
                        ],
                        return_exceptions=True,
                    )

                    for result in results:
                        if isinstance(result, Exception):
                            logging.error(
                                "Article processing error: %s",
                                result,
                            )
                        elif result:
                            articles.append(result)

                            if len(articles) >= MAX_NEWS_ITEMS:
                                break

            finally:
                await browser.close()

        # Keep the existing file intact if no articles were valid
        if not articles:
            logging.error(
                "No valid articles found. Existing JSON was not overwritten."
            )
            return

        save_json(articles)

        logging.info(
            "GP1 pipeline finished: %s valid articles",
            len(articles),
        )


# ==========================================
# ENTRYPOINT
# ==========================================

if __name__ == "__main__":
    asyncio.run(run())
