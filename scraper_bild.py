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

OUTPUT_DIR = "images_bild"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 🔒 STANDARD DIMENZIJE
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720  # Direktno 16:9

# ============================================
# 🎯 FOCUS LOGIKA
# ============================================
def get_focus_y(ratio):
    if ratio >= 1.6:
        return 0.30
    if 0.9 <= ratio <= 1.1:
        return 0.22
    if 1.2 <= ratio <= 1.6:
        return 0.35
    # Ako ništa ne upadne, vrati sredinu (sigurnosni osigurač)
    return 0.5

# ============================================
# ✂️ CROP + RESIZE (FIXED)
# ============================================
def crop_and_resize(img):
    # Osiguraj RGB mod (briše transparency ako postoji)
    img = img.convert("RGB")
    w, h = img.size
    target_ratio = 16 / 9
    current_ratio = w / h

    focusY = get_focus_y(current_ratio)

    if current_ratio > target_ratio:
        # PREŠIROKA → režemo strane simetrično
        new_w = int(h * target_ratio)
        x = (w - new_w) // 2
        cropped = img.crop((x, 0, x + new_w, h))
    else:
        # PREVISOKA → režemo gore/dolje prema focusY
        new_h = int(w / target_ratio)
        focus_px = int(h * focusY)
        y = max(0, min(h - new_h, focus_px - new_h // 2))
        cropped = img.crop((0, y, w, y + new_h))

    # 🔥 FORCE RESIZE na točne piksele
    resized = cropped.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)
    return resized

# ============================================
# 🖼️ DOWNLOAD + PROCESS
# ============================================
def process_image(url, index):
    if not url or not url.startswith('http') or "1x1" in url:
        return "", 0, 0, 0

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=15, headers=headers)
        img = Image.open(BytesIO(res.content))

        orig_w, orig_h = img.size
        ratio = round(orig_w / orig_h, 2)

        final_img = crop_and_resize(img)

        filename = f"{OUTPUT_DIR}/bild_{index}.jpg"
        
        # 💾 SAVE s fiksiranim DPI-em i bez nepotrebnih metapodataka
        final_img.save(
            filename, 
            "JPEG", 
            quality=85, 
            subsampling=0, 
            dpi=(72, 72),
            icc_profile=None,
            exif=b""
        )

        return filename, TARGET_WIDTH, TARGET_HEIGHT, ratio

    except Exception as e:
        print(f"⚠️ Problem sa slikom {index}: {e}")
        return "", 0, 0, 0

# ============================================
# 📰 SCRAPER
# ============================================
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
            print(f"🚀 Otvaram Bild")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(2)

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')

            for i, art in enumerate(articles):
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()

                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportbild.bild.de" + link

                    image_url = ""
                    if img_elem:
                        image_url = img_elem.get('data-src') or img_elem.get('src')

                    if not image_url or "1x1" in image_url:
                        source_tag = art.find('source')
                        if source_tag:
                            image_url = source_tag.get('srcset','').split(' ')[0]

                    if image_url and image_url.startswith('/'):
                        image_url = "https://sportbild.bild.de" + image_url

                    if image_url:
                        print(f"📸 Obrada {i+1}: {title[:30]}...")
                        local, w, h, ratio = process_image(image_url, i)

                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": local,
                            "width": w,
                            "height": h,
                            "ratio": ratio,
                            "source_title1": "SPORT",
                            "source_title2": "BILD",
                            "source_color": "#fc4e4e",
                            "flag": "🇩🇪"
                        })

                if len(news_items) >= 20:
                    break

            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)

            print("✅ GOTOVO - Sve slike su sada točno 1280x720 (72 DPI)")
            browser.close()

        except Exception as e:
            print("❌ Greška u scraperu:", e)
            browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
