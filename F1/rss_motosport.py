import asyncio
import json
import logging
import random
import re
from io import BytesIO
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from PIL import Image
from playwright.async_api import BrowserContext, async_playwright
import httpx
import feedparser

# ==========================================
# KONFIGURACIJA
# ==========================================
START_URL = "https://www.motorsport-magazin.com/rss/formel1.xml"

MIN_IMAGE_WEIGHT_BYTES = 30000  # 30 KB
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5  # Broj članaka paralelno

PROXY_LIST = []

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========================================
# POMOĆNE FUNKCIJE
# ==========================================

def get_focus_y(w: int, h: int) -> float:
    ratio = round(w / h, 2)
    if ratio >= 1.6: return 0.35
    if 0.9 <= ratio <= 1.1: return 0.25
    return 0.5


async def get_image_info_async(url: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not url or not url.startswith('http') or "1x1" in url:
        return None
        
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        mounts = {"http://": httpx.AsyncHTTPTransport(proxy=proxy), "https://": httpx.AsyncHTTPTransport(proxy=proxy)} if proxy else None
        
        async with httpx.AsyncClient(mounts=mounts, timeout=10.0, headers=headers) as client:
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

# ==========================================
# PROCESIRANJE JEDNOG ČLANKA (Otvaranje i čitanje Meta oznaka)
# ==========================================

async def process_single_article(browser: Any, title: str, link: str) -> Optional[Dict[str, Any]]:
    proxy_config = None
    selected_proxy = None
    
    if PROXY_LIST:
        selected_proxy = random.choice(PROXY_LIST)
        proxy_config = {"server": selected_proxy}

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={'width': 1280, 'height': 720},
        proxy=proxy_config
    )
    
    page = await context.new_page()
    try:
        logging.info(f"🔍 Otvaram Motorsport Magazin članak: '{title[:30]}...'")
        await page.goto(link, wait_until="domcontentloaded", timeout=30000)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        src = None
        
        # 1. Ciljamo Open Graph sliku visoke rezolucije
        og_image = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        if og_image and og_image.get("content"):
            src = og_image["content"]
            
        # 2. Fallback na JSON-LD strukturu ako meta zakaže
        if not src:
            json_ld_tags = soup.find_all("script", type="application/ld+json")
            for tag in json_ld_tags:
                try:
                    js_data = json.loads(tag.string)
                    if isinstance(js_data, dict) and js_data.get("@type") == "NewsArticle":
                        if "image" in js_data:
                            if isinstance(js_data["image"], list) and js_data["image"]:
                                src = js_data["image"][0]
                            elif isinstance(js_data["image"], dict):
                                src = js_data["image"].get("url")
                            else:
                                src = js_data["image"]
                            break
                except Exception:
                    continue

        if not src:
            return None
        
        if "placeholder" in src.lower() or "sys-fallback" in src.lower():
            return None
                
        image_info = await get_image_info_async(src, proxy=selected_proxy)
        if image_info:
            return {
                "title": title,
                "link": link,
                "image_url": image_info["url"],
                "w": image_info["w"],
                "h": image_info["h"],
                "focus_y": image_info["focus_y"],
                "source_title1": "MOTORSPORT MAGAZIN",
                "source_title2": "F1",
                "source_color": "#FFD300",
                "flag": "🇩🇪"
            }
        return None
    except Exception:
        return None
    finally:
        await context.close()

# ==========================================
# GLAVNA ASINKRONA LOGIKA
# ==========================================

async def scrape_motorsport_async() -> None:
    logging.info("🚀 Pokrećem Motorsport Magazin XML feed parsiranje...")
    
    try:
        feed = feedparser.parse(START_URL)
        tasks_to_process = []
        
        for entry in feed.entries:
            title = entry.get('title', '').strip()
            link = entry.get('link', '')
            
            if title and link:
                tasks_to_process.append((title, link))
                
        logging.info(f"📊 Detektirano {len(tasks_to_process)} vijesti unutar XML feeda.")
        
        if not tasks_to_process:
            logging.warning("⚠️ XML feed je prazan ili nedostupan.")
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            news_items: List[Dict[str, Any]] = []
            
            for i in range(0, len(tasks_to_process), CONCURRENT_TASKS):
                if len(news_items) >= MAX_NEWS_ITEMS:
                    break
                    
                chunk = tasks_to_process[i:i + CONCURRENT_TASKS]
                logging.info(f"📦 Otvaram paket od {len(chunk)} paralelna članka...")
                
                async_tasks = [process_single_article(browser, title, link) for title, link in chunk]
                results = await asyncio.gather(*async_tasks)
                
                for res in results:
                    if res:
                        news_items.append(res)
                        if len(news_items) >= MAX_NEWS_ITEMS:
                            break
                            
            await browser.close()
            
            if news_items:
                # Spremanje izravno u F1 mapu projekta
                with open("F1/motorsport_magazin.json", "w", encoding="utf-8") as f:
                    json.dump(news_items[:MAX_NEWS_ITEMS], f, ensure_ascii=False, indent=4)
                logging.info(f"🎉 Gotovo! 'F1/motorsport_magazin.json' uspješno spremljen s {len(news_items[:MAX_NEWS_ITEMS])} artikala.")
            
    except Exception as e:
        logging.error(f"❌ Kritična greška u glavnom procesu: {e}")

if __name__ == "__main__":
    asyncio.run(scrape_motorsport_async())