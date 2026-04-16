import json
import sys
import re
import requests
import time
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Fokus logika ostaje ista, ali se šalje kao broj (0.0 - 1.0)
def get_focus_y(w, h):
    ratio = round(w / h, 2)
    if ratio >= 1.6: return 0.30
    if 0.9 <= ratio <= 1.1: return 0.22
    if 1.2 <= ratio <= 1.6: return 0.35
    return 0.5

def get_image_info(url):
    if not url or not url.startswith('http') or "1x1" in url:
        return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=10, headers=headers)
        img = Image.open(BytesIO(res.content))
        w, h = img.size
        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h)
        }
    except:
        return None

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Scraping Bild (Meta-data mode)...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            # Skrolanje je nužno da se učitaju pravi URL-ovi slika
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(2)

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')

            for i, art in enumerate(articles):
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem and img_elem:
                    title = title_elem.get_text(strip=True)
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link

                    img_url = img_elem.get('data-src') or img_elem.get('src')
                    if img_url and img_url.startswith('/'): img_url = "https://sportbild.bild.de" + img_url

                    info = get_image_info(img_url)
                    if info:
                        print(f"✅ Dodano: {title[:30]}...")
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image_url": info["url"],
                            "w": info["w"],
                            "h": info["h"],
                            "focus_y": info["focus_y"],
                            "source_title1": "SPORT",
                            "source_title2": "BILD",
                            "source_color": "#fc4e4e",
                            "flag": "🇩🇪"
                        })

                if len(news_items) >= 20: break

            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON spreman bez lokalnih slika.")
            browser.close()

        except Exception as e:
            print("❌ Greška:", e)
            browser.close()

if __name__ == "__main__":
    scrape_bild()
