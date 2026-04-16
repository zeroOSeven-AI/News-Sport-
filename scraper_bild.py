import json
import sys
import re
import requests
import time
import os
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

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
        
        # DODATNI FILTER: Ako je slika preuska ili premala, vjerojatno je banner
        if w < 300 or h < 150:
            return None
            
        return {"url": url, "w": w, "h": h, "focus_y": get_focus_y(w, h)}
    except:
        return None

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    # PROŠIRENA LISTA ZA ODSTREL: Sve što smrdi na grafiku/banner
    forbidden = [
        "ticker", "banner", "bitter", "score", "overlay", 
        "live-ticker", "placeholder", "teaser-graphic",
        "fallback", "default", "sharing"
    ]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Čistim Bild od svih boja bannera...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.evaluate("window.scrollBy(0, 3500)")
            time.sleep(5)

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')
            
            for art in articles:
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)
                all_imgs = art.find_all('img')

                if title_elem and link_elem and all_imgs:
                    title = title_elem.get_text(strip=True)
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link

                    valid_img_url = None
                    for img in all_imgs:
                        # Gledamo sve moguće izvore slike
                        temp_url = img.get('data-src') or img.get('src') or img.get('data-srcset')
                        if not temp_url: continue
                        
                        # Čistimo URL
                        clean_url = temp_url.split('?')[0].split(' ')[0]
                        if clean_url.startswith('/'): clean_url = "https://sportbild.bild.de" + clean_url
                        
                        # FILTRIRANJE: Ako nađeš bilo koju zabranjenu riječ, bježi
                        if any(word in clean_url.lower() for word in forbidden):
                            continue
                            
                        # Bildove prave fotke obično imaju dugi hash (npr. /69e.../)
                        # Grafike često imaju drugačiju strukturu, ali hash je najsigurniji
                        valid_img_url = clean_url
                        break
                    
                    # Ako nema čiste slike, preskačemo cijelu vijest bez milosti
                    if not valid_img_url:
                        continue

                    info = get_image_info(valid_img_url)
                    if info:
                        print(f"✅ Čista slika: {title[:35]}...")
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

            if news_items:
                with open("bild.json", 'w', encoding='utf-8') as f:
                    json.dump(news_items, f, ensure_ascii=False, indent=4)
                print(f"🎉 Gotovo! bild.json je očišćen. Ukupno: {len(news_items)}")
            
            browser.close()
        except Exception as e:
            print(f"❌ Greška: {str(e)}")
            browser.close()

if __name__ == "__main__":
    scrape_bild()
