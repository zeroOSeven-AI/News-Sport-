import json
import sys
import re
import requests
import time
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# ============================================
# 🎯 FOCUS LOGIKA (Za dinamički prikaz)
# ============================================
def get_focus_y(w, h):
    ratio = round(w / h, 2)
    if ratio < 1.0:
        return 0.35
    if 1.0 <= ratio <= 1.2:
        return 0.30
    return 0.45

# ============================================
# 🖼️ IMAGE INFO (Dohvaćanje dimenzija)
# ============================================
def get_image_info(url):
    if not url or not url.startswith('http'):
        return None
    try:
        # User-Agent je ključan da nas Jutarnji ne blokira
        headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)'}
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

# ============================================
# 📰 SCRAPER
# ============================================
def scrape_sn():
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Otvaram Sportske Novosti (Meta-data mode)...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    # Čišćenje naslova od kickera (npr. "VIDEO:", "FOTO:")
                    full_text = title_elem.get_text(separator=" ", strip=True)
                    kicker = title_elem.find(['span', 'b', 'i'])
                    if kicker:
                        title = full_text.replace(kicker.get_text(strip=True), "").strip()
                    else:
                        title = full_text
                    
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportske.jutarnji.hr" + link
                    
                    image_url = ""
                    if img_elem:
                        image_url = img_elem.get('data-src') or img_elem.get('src') or ""
                    
                    if image_url and image_url.startswith('/'):
                        image_url = "https://sportske.jutarnji.hr" + image_url

                    if image_url and not any(item['title'] == title for item in news_items):
                        print(f"✅ Meta info: {title[:30]}...")
                        info = get_image_info(image_url)
                        
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
                                "source_color": "#007aff",
                                "flag": "🇭🇷"
                            })

                if len(news_items) >= 20:
                    break

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"✅ SN GOTOVO — JSON spreman za Scriptable")
            browser.close()

        except Exception as e:
            print(f"❌ Greška: {e}")
            browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_sn()
