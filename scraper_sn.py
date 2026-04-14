import json
import sys
import re
import requests
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os

OUTPUT_DIR = "images"
os.makedirs(OUTPUT_DIR, exist_ok=True)


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

        filename = f"{OUTPUT_DIR}/img_{index}.jpg"
        cropped.save(filename, "JPEG", quality=85)

        return filename

    except Exception as e:
        print(f"⚠️ Slika fail: {e}")
        return ""


# ============================================
# 📰 SCRAPER
# ============================================
def scrape_sn():
    url = "https://sportske.jutarnji.hr/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            soup = BeautifulSoup(page.content(), 'html.parser')

            news_items = []
            articles = soup.find_all('article')

            for i, art in enumerate(articles):

                title_elem = art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if not (title_elem and link_elem):
                    continue

                # TITLE CLEAN
                title = title_elem.get_text(strip=True)
                title = re.sub(r'^[:\s–|-]+', '', title)

                link = link_elem['href']
                if link.startswith('/'):
                    link = "https://sportske.jutarnji.hr" + link

                image = ""
                if img_elem:
                    image = img_elem.get('data-src') or img_elem.get('src') or ""

                if image.startswith('/'):
                    image = "https://sportske.jutarnji.hr" + image

                # DIMENSIONS
                try:
                    res = requests.get(image, stream=True, timeout=5)
                    img_test = Image.open(BytesIO(res.raw.read(2048)))
                    w, h = img_test.size
                    ratio = round(w / h, 2)
                except:
                    w, h, ratio = 0, 0, 0

                # 🔥 PROCESS IMAGE
                local_img = process_image(image, i, ratio)

                news_items.append({
                    "title": title,
                    "link": link,
                    "image": local_img,  # 👈 sada lokalna cropana slika
                    "ratio": ratio
                })

                if len(news_items) >= 15:
                    break

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)

            print("✅ Gotovo — sve slike 16:9")
            browser.close()

        except Exception as e:
            print("Greška:", e)
            browser.close()
            sys.exit(1)


if __name__ == "__main__":
    scrape_sn()
