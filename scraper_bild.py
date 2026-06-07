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

# ==========================================
# KONFIGURACIJA
# ==========================================
BASE_URL = "https://sportbild.bild.de"
START_URL = "https://m.sportbild.bild.de/"

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
    if ratio >= 1.6: return 0.30
    if 0.9 <= ratio <= 1.1: return 0.22
    if 1.2 <= ratio <= 1.6: return 0.35
    return 0.5


async def get_image_info_async(url: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not url or not url.startswith('http') or "1x1" in url:
        return None
        
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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
# PROCESIRANJE JEDNOG ČLANKA (FlashScore stil)
# ==========================================

async def process_single_article(browser: Any, title: str, link: str) -> Optional[Dict[str, Any]]:
    proxy_config = None
    selected_proxy = None
    
    if PROXY_LIST:
        selected_proxy = random.choice(PROXY_LIST)
        proxy_config = {"server": selected_proxy}

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        viewport={'width': 390, 'height': 844},
        proxy=proxy_config
    )
    
    page = await context.new_page()
    try:
        logging.info(f"🔍 Otvaram članak: '{title[:30]}...'")
        await page.goto(link, wait_until="domcontentloaded", timeout=30000)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        
        # -----------------------------------------------------------------
        # PRAVI DETEKTOR GLAVNE SLIKE (Ciljamo isključivo Meta tagove)
        # -----------------------------------------------------------------
        src = None
        
        # Tražimo službenu Open Graph sliku koju Bild servira vanjskim servisima
        og_image = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        if og_image and og_image.get("content"):
            src = og_image["content"]
            
        # Ako iz nekog razloga nema og:image, tražimo sliku u strogo definiranom JSON-LD bloku
        if not src:
            json_ld_tags = soup.find_all("script", type="application/ld+json")
            for tag in json_ld_tags:
                try:
                    js_data = json.loads(tag.string)
                    # Ako je struktura NewsArticle, u njoj se nalazi 'image' polje
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

        # Ako članak nema službenu naslovnu sliku u zaglavlju, ignoriramo ga.
        # Nema više šetanja po HTML-u i kupljenja smeća s dna stranice!
        if not src:
            return None
            
        if src.startswith('/'): src = BASE_URL + src
        
        # Preskačemo ako je u pitanju očiti sistemski fallback/placeholder tekst u URL-u
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
                "source_title1": "SPORT",
                "source_title2": "BILD",
                "source_color": "#fc4e4e",
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

async def scrape_bild_async() -> None:
    logging.info("🚀 Pokrećem stabilno HTML skeniranje preko glave stranice...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        main_context = await browser.new_context(viewport={'width': 390, 'height': 844})
        main_page = await main_context.new_page()
        
        try:
            await main_page.goto(START_URL, wait_until="networkidle", timeout=60000)
            await main_page.evaluate("window.scrollBy(0, 3000)")
            await main_page.wait_for_timeout(2000)
            
            soup = BeautifulSoup(await main_page.content(), 'html.parser')
            articles = soup.find_all('article')
            logging.info(f"📊 Detektirano {len(articles)} potencijalnih vijesti na naslovnici.")
            
            tasks_to_process = []
            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    link = link_elem['href']
                    if link.startswith('/'): link = BASE_URL + link
                    
                    tasks_to_process.append((title, link))
            
            await main_context.close()
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
                            
            if news_items:
                with open("bild.json", "w", encoding="utf-8") as f:
                    json.dump(news_items[:MAX_NEWS_ITEMS], f, ensure_ascii=False, indent=4)
                logging.info(f"🎉 Gotovo! 'bild.json' uspješno spremljen s {len(news_items[:MAX_NEWS_ITEMS])} artikala.")
            
        except Exception as e:
            logging.error(f"❌ Kritična greška: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_bild_async())
