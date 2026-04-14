import json
import sys
import re
import requests
import time
from io import BytesIO
from PIL import Image
# Uvijek ostavljamo import na vrhu, on ne smeta
from playwright.sync_api import sync_playwright

def get_image_resolution(url):
    if not url or not url.startswith('http'):
        return 0, 0, 0
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
        response = requests.get(url, stream=True, timeout=10, headers=headers)
        header = response.raw.read(2048)
        img = Image.open(BytesIO(header))
        w, h = img.size
        return w, h, round(w / h, 2)
    except:
        return 0, 0, 0

def clean_title(title):
    if not title: return ""
    title = re.sub(r'\s*-\s*ESPN.*$', '', title, flags=re.IGNORECASE)
    return title.strip()

# --- OPCIJA 1: BRZI API PRISTUP (Trenutno aktivno) ---
def scrape_espn():
    api_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/news?limit=50"
    
    try:
        print(f"Pristupam ESPN API-ju (Requests)...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
        response = requests.get(api_url, headers=headers, timeout=30)
        data = response.json()
        articles = data.get('articles', [])
        
        process_articles(articles)

    except Exception as e:
        print(f"Greška kod ESPN API-ja: {e}")
        # Ako API padne, ovdje bi mogao automatski pozvati zakomentiranu funkciju
        # scrape_espn_playwright() 

# --- OPCIJA 2: PLAYWRIGHT PRISTUP (Zakomentirano za budućnost) ---
"""
def scrape_espn_playwright():
    url = "https://www.espn.com/soccer/" 
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        try:
            print(f"Otvaram ESPN preko Playwrighta: {url}")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Ovdje bi išla logika za BeautifulSoup ako skrejpamo HTML
            # content = page.content()
            # ...
            
            browser.close()
        except Exception as e:
            print(f"Playwright greška: {e}")
            browser.close()
"""

def process_articles(articles):
    news_items = []
    for art in articles:
        raw_title = art.get('headline', '')
        link = art.get('links', {}).get('web', {}).get('href', '')
        
        images = art.get('images', [])
        image = images[0].get('url', '') if images else ""

        if raw_title and link:
            title = clean_title(raw_title)
            if len(title) < 15 or "/video/" in link:
                continue
            
            width, height, ratio = 0, 0, 0
            if image:
                print(f"Mjerim sliku: {title[:40]}...")
                width, height, ratio = get_image_resolution(image)

            if not any(item['title'] == title for item in news_items):
                news_items.append({
                    "title": title,
                    "link": link,
                    "image": image,
                    "width": width,
                    "height": height,
                    "ratio": ratio,
                    "source_title1": "ESPN",
                    "source_title2": "FOOTBALL",
                    "source_color": "#ff0021",
                    "flag": "🇺🇸"
                })

        if len(news_items) >= 15:
            break

    with open('espn.json', 'w', encoding='utf-8') as f:
        json.dump(news_items, f, ensure_ascii=False, indent=4)
    print(f"Spremljeno {len(news_items)} vijesti.")

if __name__ == "__main__":
    scrape_espn()
