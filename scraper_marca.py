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
# 🎯 FOCUS LOGIKA (Meta-podaci za Scriptable)
# ============================================
def get_focus_y(w, h):
    ratio = round(w / h, 2)
    if ratio > 1.6:
        return 0.30
    if 0.9 <= ratio <= 1.1:
        return 0.20
    if 1.2 <= ratio <= 1.6:
        return 0.35
    return 0.5

# ============================================
# 🖼️ IMAGE INFO (Dohvaćanje dimenzija bez spremanja)
# ============================================
def get_image_info(url):
    if not url or not url.startswith('http'):
        return None
    try:
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
    except Exception as e:
        print(f"⚠️ Image info error: {e}")
        return None

# ============================================
# 📰 MARCA SCRAPER
# ============================================
def scrape_marca():
    url = "https://www.marca.com/en/football.html"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print("🚀 Otvaram Marcu (Meta-data mode)...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            # Skrolanje da se učitaju slike
            page.evaluate("window.scrollBy(0, 1500)")
            time.sleep(2)

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if not (title_elem and link_elem):
                    continue

                title = title_elem.get_text(strip=True)
                link = link_elem['href']
                if not link.startswith('http'):
                    link = "https://www.marca.com" + link

                image_url = ""
                if img_elem:
                    image_url = img_elem.get('src') or img_elem.get('data-src') or img_elem.get('srcset')
                    if image_url and ',' in image_url:
                        image_url = image_url.split(',')[0].split(' ')[0]
                    
                    if image_url and ('pixel.gif' in image_url or image_url.startswith('data:')):
                        image_url = ""

                if not image_url:
                    source_tag = art.find('source')
                    if source_tag and source_tag.get('srcset'):
                        image_url = source_tag.get('srcset').split(',')[0].split(' ')[0]

                if image_url and image_url.startswith('//'):
                    image_url = "https:" + image_url

                if image_url:
                    # Provjera duplikata
                    if any(item['title'] == title for item in news_items):
                        continue
                        
                    print(f"✅ Dohvaćam info: {title[:40]}...")
                    info = get_image_info(image_url)
                    
                    if info:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image_url": info["url"],
                            "w": info["w"],
                            "h": info["h"],
                            "focus_y": info["focus_y"],
                            "source_title1": "MARCA",
                            "source_title2": "SPORT",
                            "source_color": "#ff4b00",
                            "flag": "🇪🇸"
                        })

                if len(news_items) >= 20:
                    break

            with open('marca.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)

            print(f"✅ MARCA GOTOVO - Generiran JSON sa {len(news_items)} vijesti.")
            browser.close()

        except Exception as e:
            print("❌ Greška u scraperu:", e)
            browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_marca()
