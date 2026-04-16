import json
import re
import requests
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# ============================================
# 🎯 TEST LOGIKA: LAGANJE DIMENZIJA
# ============================================
def get_fake_image_info(url):
    if not url or not url.startswith('http'):
        return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=10, headers=headers)
        img = Image.open(BytesIO(res.content))
        w, h = img.size
        
        # OVDJE JE TRIK: 
        # Govorimo mu da je slika visoka 1200 umjesto 640.
        # To bi trebalo 'podignuti' kadar jer Scriptable traži centar na 600px, 
        # a naša prava slika završava na 640px.
        return {
            "url": url,
            "w": w,
            "h": 1200, 
            "focus_y": 0.25 # Ostaje kao info, iako ga JS možda ne čita
        }
    except:
        return None

def scrape_sn():
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            print(f"🚀 Pokrećem test 'lažnih dimenzija'...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem and img_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportske.jutarnji.hr" + link
                    
                    img_url = img_elem.get('data-src') or img_elem.get('src') or ""
                    if img_url.startswith('/'): img_url = "https://sportske.jutarnji.hr" + img_url

                    # Primijeni lažne dimenzije
                    info = get_fake_image_info(img_url)
                    
                    if info:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image_url": info["url"],
                            "w": info["w"],
                            "h": info["h"],
                            "focus_y": info["focus_y"],
                            "source_title1": "SPORTSKE",
                            "source_title2": "NOVOSTI",
                            "flag": "🇭🇷"
                        })

                if len(news_items) >= 15: break

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"✅ JSON spreman. Testiraj na widgetu!")
            browser.close()

        except Exception as e:
            print(f"❌ Greška: {e}")
            browser.close()

if __name__ == "__main__":
    scrape_sn()
