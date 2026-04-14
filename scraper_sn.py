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
OUTPUT_DIR = "images_sn"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================
# 🎯 FOCUS LOGIKA (Za centriranje)
# ============================================
def get_focus_y(ratio):
    # Sportske često šalju portretne slike (ratio < 1)
    # Ako je slika visoka, fokusiramo se skroz na vrh (glave)
    if ratio < 1.0:
        return 0.20
    # Ako je kvadratna
    if 1.0 <= ratio <= 1.2:
        return 0.25
    # Standardni landscape
    return 0.35

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
        # Previsoko → režemo visinu koristeći fokus na glave
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
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=15, headers=headers)
        img = Image.open(BytesIO(res.content)).convert("RGB")

        orig_w, orig_h = img.size
        orig_ratio = round(orig_w / orig_h, 2)

        focusY = get_focus_y(orig_ratio)
        cropped = crop_to_16_9(img, focusY)

        filename = f"{OUTPUT_DIR}/sn_{index}.jpg"
        cropped.save(filename, "JPEG", quality=85)

        new_w, new_h = cropped.size
        return filename, new_w, new_h, orig_ratio

    except Exception as e:
        print(f"⚠️ Slika fail: {e}")
        return "", 0, 0, 0

# ============================================
# 📰 SCRAPER
# ============================================
def scrape_sn():
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        try:
            print(f"🚀 Otvaram Sportske Novosti: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for i, art in enumerate(articles):
                title_elem = art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    # --- ČIŠĆENJE NASLOVA ---
                    full_text = title_elem.get_text(separator=" ", strip=True)
                    kicker = title_elem.find(['span', 'b', 'i'])
                    if kicker:
                        kicker_text = kicker.get_text(strip=True)
                        title = full_text.replace(kicker_text, "").strip()
                    else:
                        title = full_text
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    # --- LINK ---
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportske.jutarnji.hr" + link
                    
                    # --- SLIKA ---
                    image_url = ""
                    if img_elem:
                        image_url = img_elem.get('data-src') or img_elem.get('src') or ""
                    
                    if image_url and image_url.startswith('/'):
                        image_url = "https://sportske.jutarnji.hr" + image_url

                    # 🔥 OBRADA (Crop i mjerenje)
                    if image_url:
                        print(f"📸 Obrađujem sliku {len(news_items)+1}: {title[:30]}...")
                        local_img, width, height, ratio = process_and_get_info(image_url, len(news_items))
                    else:
                        local_img, width, height, ratio = "", 0, 0, 0

                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": local_img,
                            "width": width,
                            "height": height,
                            "ratio": ratio,
                            "source_title1": "SPORTSKE",
                            "source_title2": "NOVOSTI",
                            "source_color": "#007aff",
                            "flag": "🇭🇷"
                        })

                if len(news_items) >= 20:
                    break

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"✅ Sportske gotove — {len(news_items)} vijesti spremno.")
            browser.close()

        except Exception as e:
            print(f"❌ Greška: {e}")
            if 'browser' in locals(): browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_sn()
