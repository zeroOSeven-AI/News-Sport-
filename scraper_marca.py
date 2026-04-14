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
OUTPUT_DIR = "images"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================
# 🎯 FOCUS LOGIKA
# ============================================
def get_focus_y(ratio):
    if ratio > 1.6:   # wide (ESPN)
        return 0.30
    if 0.9 <= ratio <= 1.1:  # square (Bild/Sportske)
        return 0.20
    if 1.2 <= ratio <= 1.6:  # Marca
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
        # preširoko → crop širinu
        new_w = int(h * target_ratio)
        x = (w - new_w) // 2
        return img.crop((x, 0, x + new_w, h))
    else:
        # previsoko → crop visinu
        new_h = int(w / target_ratio)
        focus_px = int(h * focusY)
        y = max(0, min(h - new_h, focus_px - new_h // 2))
        return img.crop((0, y, w, y + new_h))


# ============================================
# 🖼️ DOWNLOAD + CROP
# ============================================
def process_image(url, index, ratio):
    try:
        res = requests.get(url, timeout=10)
        img = Image.open(BytesIO(res.content)).convert("RGB")

        focusY = get_focus_y(ratio)
        cropped = crop_to_16_9(img, focusY)

        filename = f"{OUTPUT_DIR}/marca_{index}.jpg"
        cropped.save(filename, "JPEG", quality=85)

        return filename

    except Exception as e:
        print(f"⚠️ Slika fail: {e}")
        return ""


# ============================================
# 📏 RESOLUTION
# ============================================
def get_image_resolution(url):
    if not url or not url.startswith('http'):
        return 0, 0, 0
    try:
        response = requests.get(url, stream=True, timeout=10)
        header = response.raw.read(2048)
        img = Image.open(BytesIO(header))
        w, h = img.size
        return w, h, round(w / h, 2)
    except:
        return 0, 0, 0


# ============================================
# 📰 SCRAPER
# ============================================
def scrape_marca():
    url = "https://www.marca.com/en/football.html"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            print(f"Otvaram Marcu: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
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

                image = ""
                if img_elem:
                    image = img_elem.get('src') or img_elem.get('data-src')
                    if image and 'pixel.gif' in image:
                        image = ""

                if not image:
                    source_tag = art.find('source')
                    if source_tag and source_tag.get('srcset'):
                        image = source_tag.get('srcset').split(',')[0].split(' ')[0]

                if image and image.startswith('//'):
                    image = "https:" + image

                # 📏 DIMENZIJE
                width, height, ratio = 0, 0, 0
                if image:
                    print(f"Mjerim: {title[:40]}...")
                    width, height, ratio = get_image_resolution(image)

                # 🔥 KLJUČ: crop slika
                processed_img = process_image(image, i, ratio)

                news_items.append({
                    "title": title,
                    "link": link,
                    "image": processed_img,  # 👈 sada uniformno
                    "ratio": ratio
                })

                if len(news_items) >= 20:
                    break

            with open('marca.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"✅ Gotovo — {len(news_items)} vijesti (16:9)")
            browser.close()

        except Exception as e:
            print(f"Greška kod Marce: {e}")
            if 'browser' in locals(): browser.close()
            sys.exit(1)


if __name__ == "__main__":
    scrape_marca()
