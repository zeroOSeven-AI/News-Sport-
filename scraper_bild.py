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
import httpx  # Koristimo httpx umjesto requests jer je asinkron

# ==========================================
# KONFIGURACIJA (Sve na jednom mjestu)
# ==========================================
BASE_URL = "https://sportbild.bild.de"
START_URL = "https://m.sportbild.bild.de/"

MIN_IMAGE_WEIGHT_BYTES = 30000  # 30 KB
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5  # Broj članaka koje otvara PARALELNO u isto vrijeme

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
import httpx  # Koristimo httpx umjesto requests jer je asinkron

# ==========================================
# KONFIGURACIJA (Sve na jednom mjestu)
# ==========================================
BASE_URL = "https://sportbild.bild.de"
START_URL = "https://m.sportbild.bild.de/"

MIN_IMAGE_WEIGHT_BYTES = 30000  # 30 KB
MIN_IMAGE_WIDTH_PX = 400
MAX_NEWS_ITEMS = 20
CONCURRENT_TASKS = 5  # Broj članaka koje otvara PARALELNO u isto vrijeme

# IZMJENA: Dodan ID "4358b87671e45eb9c7baf66baab09622" koji označava sivi zamjenski logo
TRASH_MARKERS = [
    "bitter", "overlay", "live-ticker", 
    "banner", "f61f5128", "7af5745e",
    "4358b87671e45eb9c7baf66baab09622"
]

# POPIS PROKSIJA (Ovdje unesi svoje proksije ako ih imaš)
PROXY_LIST = [
    # "http://user:pass@proxy1.com:8080",
    # "http://user:pass@proxy2.com:8080",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========================================
# ASINKRONE POMOĆNE FUNKCIJE
# ==========================================

def get_focus_y(w: int, h: int) -> float:
    ratio = round(w / h, 2)
    if ratio >= 1.6: return 0.30
    if 0.9 <= ratio <= 1.1: return 0.22
    if 1.2 <= ratio <= 1.6: return 0.35
    return 0.5


async def get_image_info_async(url: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Asinkrano provjerava kvalitetu slike koristeći HTTPX."""
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


async def process_single_article(browser: Any, title: str, link: str) -> Optional[Dict[str, Any]]:
    """Otvara jedan članak s jedinstvenim IP-jem (proxy) i izvlači sliku."""
    proxy_config = None
    selected_proxy = None
    
    if PROXY_LIST:
        selected_proxy = random.choice(PROXY_LIST)
        proxy_config = {"server": selected_proxy}
        logging.info(f"🌐 Koristim proxy za članak: {selected_proxy}")

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        viewport={'width': 390, 'height': 844},
        proxy=proxy_config
    )
    
    page = await context.new_page()
    try:
        logging.info(f"🔍 Paralelno ulazim u: '{title[:30]}...'")
        await page.goto(link, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        images = soup.find_all('img')
        
        for img in images:
            src = img.get('data-src') or img.get('src')
            if not src: continue
            if src.startswith('/'): src = BASE_URL + src
            if any(marker in src.lower() for marker in TRASH_MARKERS): continue
                
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
    except Exception as e:
        logging.debug(f"Greška na članku {link}: {e}")
        return None
    finally:
        await context.close()

# ==========================================
# GLAVNA ASINKRONA LOGIKA
# ==========================================

async def scrape_bild_async() -> None:
    logging.info("🚀 Pokrećem ASINKRONO paralelno skeniranje...")
    
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
                logging.info(f"📦 Pokrećem paket od {len(chunk)} paralelna članka...")
                
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
                logging.info(f"🎉 Gotovo! 'bild.json' kreiran s {len(news_items[:MAX_NEWS_ITEMS])} vijesti.")
            
        except Exception as e:
            logging.error(f"❌ Kritična greška: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_bild_async())


# POPIS PROKSIJA (Ovdje unesi svoje proksije ako ih imaš)
# Format: "http://username:password@ip:port" ili samo "http://ip:port"
PROXY_LIST = [
    # "http://user:pass@proxy1.com:8080",
    # "http://user:pass@proxy2.com:8080",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========================================
# ASINKRONE POMOĆNE FUNKCIJE
# ==========================================

def get_focus_y(w: int, h: int) -> float:
    ratio = round(w / h, 2)
    if ratio >= 1.6: return 0.30
    if 0.9 <= ratio <= 1.1: return 0.22
    if 1.2 <= ratio <= 1.6: return 0.35
    return 0.5


async def get_image_info_async(url: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Asinkrano provjerava kvalitetu slike koristeći HTTPX."""
    if not url or not url.startswith('http') or "1x1" in url:
        return None
        
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        # Ako imamo proksije, koristimo ih i za skidanje slika
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


async def process_single_article(browser: Any, title: str, link: str) -> Optional[Dict[str, Any]]:
    """Otvara jedan članak s jedinstvenim IP-jem (proxy) i izvlači sliku."""
    proxy_config = None
    selected_proxy = None
    
    # Ako imamo definiranu listu proksija, uzmi jedan nasumično za ovaj članak
    if PROXY_LIST:
        selected_proxy = random.choice(PROXY_LIST)
        proxy_config = {"server": selected_proxy}
        logging.info(f"🌐 Koristim proxy za članak: {selected_proxy}")

    # Kreiramo potpuno novi kontekst (kao novi privatni prozor) s tim proksijem
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        viewport={'width': 390, 'height': 844},
        proxy=proxy_config
    )
    
    page = await context.new_page()
    try:
        logging.info(f"🔍 Paralelno ulazim u: '{title[:30]}...'")
        await page.goto(link, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        images = soup.find_all('img')
        
        for img in images:
            src = img.get('data-src') or img.get('src')
            if not src: continue
            if src.startswith('/'): src = BASE_URL + src
            if any(marker in src.lower() for marker in TRASH_MARKERS): continue
                
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
    except Exception as e:
        logging.debug(f"Greška na članku {link}: {e}")
        return None
    finally:
        await context.close()  # Zatvara prozor i uništava proxy sesiju nakon završetka

# ==========================================
# GLAVNA ASINKRONA LOGIKA
# ==========================================

async def scrape_bild_async() -> None:
    logging.info("🚀 Pokrećem ASINKRONO paralelno skeniranje...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # Glavna stranica se otvara bez proksija (ili možeš staviti i tu)
        main_context = await browser.new_context(viewport={'width': 390, 'height': 844})
        main_page = await main_context.new_page()
        
        try:
            await main_page.goto(START_URL, wait_until="networkidle", timeout=60000)
            await main_page.evaluate("window.scrollBy(0, 3000)")
            await main_page.wait_for_timeout(2000)
            
            soup = BeautifulSoup(await main_page.content(), 'html.parser')
            articles = soup.find_all('article')
            logging.info(f"📊 Detektirano {len(articles)} potencijalnih vijesti na naslovnici.")
            
            # Priprema liste zadataka za paralelno izvršavanje
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
            
            await main_context.close() # Više nam ne treba glavna stranica
            
            news_items: List[Dict[str, Any]] = []
            
            # Dijelimo zadatke u pakete (Chunke) kako ne bismo odjednom otvorili 50 artikala i zagušili procesor
            for i in range(0, len(tasks_to_process), CONCURRENT_TASKS):
                if len(news_items) >= MAX_NEWS_ITEMS:
                    break
                    
                chunk = tasks_to_process[i:i + CONCURRENT_TASKS]
                logging.info(f"📦 Pokrećem paket od {len(chunk)} paralelna članka...")
                
                # Ovdje se događa magija: asyncio.gather pokreće sve iz paketa ODJEDNOM
                async_tasks = [process_single_article(browser, title, link) for title, link in chunk]
                results = await asyncio.gather(*async_tasks)
                
                # Filtriraj rezultate koji su uspješno našli sliku
                for res in results:
                    if res:
                        news_items.append(res)
                        if len(news_items) >= MAX_NEWS_ITEMS:
                            break
                            
            if news_items:
                with open("bild.json", "w", encoding="utf-8") as f:
                    json.dump(news_items[:MAX_NEWS_ITEMS], f, ensure_ascii=False, indent=4)
                logging.info(f"🎉 Gotovo! 'bild.json' kreiran s {len(news_items[:MAX_NEWS_ITEMS])} vijesti.")
            
        except Exception as e:
            logging.error(f"❌ Kritična greška: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    # Pokretanje asinkronog loop-a
    asyncio.run(scrape_bild_async())
