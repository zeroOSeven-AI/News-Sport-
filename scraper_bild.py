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

# Mapa za spremanje kropanih slika
OUTPUT_DIR = "images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================
# 🎯 FOCUS LOGIKA (Za centriranje)
# ============================================
def get_focus_y(ratio):
    # Ako je slika široka, držimo se gornje trećine
    if ratio >= 1.6:       
        return 0.30
    # Ako je slika kvadratna (BILD često šalje ovakve), podižemo fokus na glave
    if 0.9 <= ratio <= 1.1:  
        return 0.22
    if 1.2 <= ratio <= 1.6:
        return 0.35
    return 0.5

# ============================================
# ✂️ CROP FUNKCIJA (Pretvara u 16:9)
# ============================================
def crop_to_16_9(img, focusY):
    w, h = img.size
    target_ratio = 16 / 9
    current_ratio = w / h

    if current_ratio > target_ratio:
        # Slika je preširoka - režemo stranice
        new_w = int(h * target_ratio)
        x = (w - new_w) // 2
        return img.crop((x, 0, x + new_w, h))
    else:
        # Slika je previsoka - režemo gore/dolje koristeći focusY
        new_h = int(w / target_ratio)
        focus_px = int(h * focusY)
        y = max(0, min(h - new_h, focus_px - new_h // 2))
        return img.crop((0, y, w, y + new_h))

# ============================================
# 🖼️ OBRADA SLIKE (Download + Crop + Save)
# ============================================
def process_and_get_info(url, index):
    if not url or not url.startswith('http') or "1x1" in url:
        return "", 0, 0, 0

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, timeout=10, headers=headers)
        img = Image.open(BytesIO(res.content)).convert("RGB")
        
        orig_w, orig_h = img.size
        orig_ratio = round(orig_w / orig_h, 2)

        # Izračunaj focus i kropaj
        focusY = get_focus_y(orig_ratio)
        cropped_img = crop_to_16_9(img, focusY)
        
        # Spremi kropanu sliku lokalno
        filename = f"{OUTPUT_DIR}/bild_{index}.jpg"
        cropped_img.save(filename, "JPEG", quality=85)
        
        # Vrati nove dimenzije kropane slike i originalni ratio
        new_w, new_h = cropped_img.size
        return filename, new_w, new_h, orig_ratio

    except Exception as e:
        print(f"⚠️ Problem sa slikom {url}: {e}")
        return "", 0, 0, 0

# ============================================
# 📰 GLAVNI SCRAPER
# ============================================
def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Otvaram Bild: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Skrolanje za učitavanje lazy-load slika
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(2)
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')

            for i, art in enumerate(articles):
                # Pronalazak naslova
                title_elem = art.find(['h2', 'h3', 'h4'], class_=re.compile(r'headline|title', re.I)) or art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    # Čišćenje naslova
                    full_text = title_elem.get_text(strip=True)
                    kicker = title_elem.find(['span', 'b', 'i'])
                    title = full_text.replace(kicker.get_text(strip=True), "").strip() if kicker else full_text
                    if len(title) < 10: title = full_text
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    # Link
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link
                    
                    # Pronalazak originalne slike
                    image_url = ""
                    if img_elem:
                        image_url = img_elem.get('data-src') or img_elem.get('src') or ""
                    
                    if not image_url or "1x1" in image_url:
                        source_tag = art.find('source')
                        if source_tag:
                            image_url = source_tag.get('srcset', '').split(' ')[0]

                    if image_url.startswith('/'):
                        image_url = "https://sportbild.bild.de" + image_url

                    # 🔥 OBRADA (Crop i spremanje)
                    print(f"📸 Obrađujem sliku {i+1}: {title[:30]}...")
                    local_img_path, width, height, ratio = process_and_get_info(image_url, i)

                    # Dodavanje u listu (ovdje je tvoja tražena struktura)
                    news_items.append({
                        "title": title,
                        "link": link,
                        "image": local_img_path, # Putanja do kropane slike
                        "width": width,
                        "height": height,
                        "ratio": ratio,
                        "source_title1": "SPORT",
                        "source_title2": "BILD",
                        "source_color": "#fc4e4e",
                        "flag": "🇩🇪"
                    })

                if len(news_items) >= 20:
                    break

            # Spremanje u JSON
            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"✅ Uspješno obrađeno {len(news_items)} vijesti. JSON i slike su spremni.")
            browser.close()

        except Exception as e:
            print(f"❌ Greška: {e}")
            if 'browser' in locals(): browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
