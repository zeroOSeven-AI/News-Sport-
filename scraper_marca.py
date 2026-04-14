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

OUTPUT_DIR = "images_marca"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 🔒 STANDARD (ISTI ZA SVE SOURCEOVE)
TARGET_WIDTH = 1280
TARGET_HEIGHT = int(TARGET_WIDTH * 9 / 16)

# ============================================
# 🎯 FOCUS LOGIKA
# ============================================
def get_focus_y(ratio):
    if ratio > 1.6:
        return 0.30
    if 0.9 <= ratio <= 1.1:
        return 0.20
    if 1.2 <= ratio <= 1.6:
        return 0.35
    return 0.5

# ============================================
# ✂️ CROP + RESIZE (KLJUČ)
# ============================================
def crop_and_resize(img):
    w, h = img.size
    target_ratio = 16 / 9
    current_ratio = w / h

    focusY = get_focus_y(current_ratio)

    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        x = (w - new_w) // 2
        cropped = img.crop((x, 0, x + new_w, h))
    else:
        new_h = int(w / target_ratio)
        focus_px = int(h * focusY)
        y = max(0, min(h - new_h, focus_px - new_h // 2))
        cropped = img.crop((0, y, w, y + new_h))

    # 🔥 OVO TI JE CIJELI PROBLEM BIO
    resized = cropped.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)

    return resized

# ============================================
# 🖼️ DOWNLOAD + PROCESS
# ============================================
def process_and_get_info(url, index):
    if not url or not url.startswith('http'):
        return "", 0, 0, 0

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=15, headers=headers)
        img = Image.open(BytesIO(res.content)).convert("RGB")

        orig_w, orig_h = img.size
        ratio = round(orig_w / orig_h, 2)

        final_img = crop_and_resize(img)

        filename = f"{OUTPUT_DIR}/marca_{index}.jpg"
        final_img.save(filename, "JPEG", quality=85)

        return filename, TARGET_WIDTH, TARGET_HEIGHT, ratio

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
        context = browser.new_context(
            user_agent="Mozilla/5.0",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        try:
            print("🚀 Marca start")
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

                if image_url:
                    print(f"📸 {len(news_items)+1}: {title[:40]}")
                    local_img, w, h, ratio = process_and_get_info(image_url, len(news_items))
                else:
                    local_img, w, h, ratio = "", 0, 0, 0

                news_items.append({
                    "title": title,
                    "link": link,
                    "image": local_img,
                    "width": w,
                    "height": h,
                    "ratio": ratio,
                    "source_title1": "MARCA",
                    "source_title2": "SPORT",
                    "source_color": "#ff4b00",
                    "flag": "🇪🇸"
                })

                if len(news_items) >= 20:
                    break

            with open('marca.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)

            print("✅ Marca FIXED (uniformne slike)")
            browser.close()

        except Exception as e:
            print("❌ Greška:", e)
            browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_marca()
