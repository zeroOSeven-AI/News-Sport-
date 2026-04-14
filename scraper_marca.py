import json
import sys
import re
import requests
import time
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os

# folder za slike
OUTPUT_DIR = "images_marca"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================
# 🎯 FOCUS LOGIKA (Manualno centriranje)
# ============================================
def get_focus_y(ratio):
    # Marca često ima dinamične slike, 0.35 je 'sweet spot' za njihove nogometaše
    if ratio > 1.6:   
        return 0.30
    if 0.9 <= ratio <= 1.1:  
        return 0.20
    if 1.2 <= ratio <= 1.6:  
        return 0.35
    return 0.5


# ============================================
# ✂️ CROP U 16:9
# ============================================
def crop_to_16_9(img, focusY):
    w, h = img.size
    target_ratio = 16 / 9
    current_ratio = w / h

    if current_ratio > target_ratio:
        # Preširoko → režemo stranice
        new_w = int(h * target_ratio)
        x = (w - new_w) // 2
        return img.crop((x, 0, x + new_w, h))
    else:
        # Previsoko → režemo visinu (ovdje focusY igra ulogu)
        new_h = int(w / target_ratio)
        focus_px = int(h * focusY)
        y = max(0, min(h - new_h, focus_px - new_h // 2))
        return img.crop((0, y, w, y + new_h))


# ============================================
# 🖼️ DOWNLOAD + CROP + INFO
# ============================================
def process_and_get_info(url, index):
    if not url or not url.startswith('http'):
        return "", 0, 0, 0
    try:
        # Marca nekad blokira botove, pa dodajemo osnovni header
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=15, headers=headers)
        img = Image.open(BytesIO(res.content)).convert("RGB")

        orig_w, orig_h = img.size
        orig_ratio = round(orig_w / orig_h, 2)

        focusY = get_focus_y(orig_ratio)
        cropped = crop_to_16_9(img, focusY)

        filename = f"{OUTPUT_DIR}/marca_{index}.jpg"
        cropped.save(filename, "JPEG", quality=85)

        new_w, new_h = cropped.size
        return filename, new_w, new_h, orig_ratio

    except Exception as e:
        print(f"⚠️ Slika fail: {e}")
        return "", 0, 0, 0


# ============================================
# 📰 SCRAPER
# ============================================
def scrape_marca():
    url = "https://www.marca.com/en/football.html"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Postavljamo Desktop profil za stabilniji BeautifulSoup
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        try:
            print(f"🚀 Otvaram Marcu: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3) # Kratki delay za renderiranje slika
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')

            for i, art in enumerate(articles):
                title_elem = art.find(['h2', 'h3'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if not (title_elem and link_elem):
                    continue

                title = title_elem.get_text(strip=True)
                link = link_elem['href']

                # --- IZVLAČENJE SLIKE ---
                image_url = ""
                if img_elem:
                    image_url = img_elem.get('src') or img_elem.get('data-src')
                    if image_url and 'pixel.gif' in image_url:
                        image_url = ""

                if not image_url:
                    source_tag = art.find('source')
                    if source_tag and source_tag.get('srcset'):
                        image_url = source_tag.get('srcset').split(',')[0].split(' ')[0]

                if image_url and image_url.startswith('//'):
                    image_url = "https:" + image_url

                # 🔥 OBRADA (Crop i mjerenje)
                if image_url:
                    print(f"📸 Obrađujem sliku {len(news_items)+1}: {title[:40]}...")
                    local_img, width, height, ratio = process_and_get_info(image_url, len(news_items))
                else:
                    local_img, width, height, ratio = "", 0, 0, 0

                # DODAVANJE U FINALNU LISTU
                news_items.append({
                    "title": title,
                    "link": link,
                    "image": local_img,
                    "width": width,
                    "height": height,
                    "ratio": ratio,
                    "source_title1": "MARCA",
                    "source_title2": "SPORT",
                    "source_color": "#ff4b00",
                    "flag": "🇪🇸"
                })

                if len(news_items) >= 20:
                    break

            # SPREMANJE JSON-a
            with open('marca.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"✅ Marca gotova — {len(news_items)} vijesti spremno za widget.")
            browser.close()

        except Exception as e:
            print(f"❌ Greška kod Marce: {e}")
            if 'browser' in locals(): browser.close()
            sys.exit(1)


if __name__ == "__main__":
    scrape_marca()
