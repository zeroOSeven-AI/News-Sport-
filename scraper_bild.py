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

OUTPUT_DIR = "images"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================
# 🎯 FOCUS (BITNO ZA BILD)
# ============================================
def get_focus_y(ratio):
    if ratio >= 1.6:       # wide
        return 0.30
    if 0.9 <= ratio <= 1.1:  # square (BILD!)
        return 0.22
    if 1.2 <= ratio <= 1.6:
        return 0.35
    return 0.5


# ============================================
# ✂️ CROP 16:9
# ============================================
def crop_to_16_9(img, focusY):
    w, h = img.size
    target = 16 / 9
    current = w / h

    if current > target:
        new_w = int(h * target)
        x = (w - new_w) // 2
        return img.crop((x, 0, x + new_w, h))
    else:
        new_h = int(w / target)
        focus_px = int(h * focusY)
        y = max(0, min(h - new_h, focus_px - new_h // 2))
        return img.crop((0, y, w, y + new_h))


# ============================================
# 🖼️ DOWNLOAD + CROP
# ============================================
def process_image(url, index, ratio):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }

        res = requests.get(url, timeout=10, headers=headers)
        img = Image.open(BytesIO(res.content)).convert("RGB")

        focusY = get_focus_y(ratio)
        cropped = crop_to_16_9(img, focusY)

        filename = f"{OUTPUT_DIR}/bild_{index}.jpg"
        cropped.save(filename, "JPEG", quality=85)

        return filename

    except Exception as e:
        print(f"⚠️ Slika fail: {e}")
        return ""


# ============================================
# 📏 DIMENZIJE
# ============================================
def get_image_resolution(url):
    if not url or not url.startswith('http') or "1x1" in url:
        return 0, 0, 0
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, stream=True, timeout=10, headers=headers)
        header = response.raw.read(2048)
        img = Image.open(BytesIO(header))
        w, h = img.size
        return w, h, round(w / h, 2)
    except:
        return 0, 0, 0


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
            print(f"Otvaram Bild: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(2)

            soup = BeautifulSoup(page.content(), 'html.parser')

            news_items = []
            articles = soup.find_all('article')

            for i, art in enumerate(articles):

                title_elem = art.find(['h2', 'h3', 'h4'], class_=re.compile(r'headline|title', re.I)) \
                             or art.find(['h2', 'h3', 'h4'])

                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if not (title_elem and link_elem):
                    continue

                # TITLE CLEAN
                full_text = title_elem.get_text(strip=True)
                kicker = title_elem.find(['span', 'b', 'i'])

                if kicker:
                    title = full_text.replace(kicker.get_text(strip=True), "").strip()
                else:
                    title = full_text

                if len(title) < 10:
                    title = full_text

                title = re.sub(r'^[:\s–|-]+', '', title).strip()

                # LINK
                link = link_elem['href']
                if link.startswith('/'):
                    link = "https://sportbild.bild.de" + link

                # IMAGE
                image = ""
                if img_elem:
                    image = img_elem.get('data-src') or img_elem.get('src') or ""

                if not image or "1x1" in image:
                    source_tag = art.find('source')
                    if source_tag:
                        image = source_tag.get('srcset', '').split(' ')[0]

                if image.startswith('/'):
                    image = "https://sportbild.bild.de" + image

                # DIMENSIONS
                width, height, ratio = 0, 0, 0
                if image:
                    print(f"Mjerim: {title[:30]}...")
                    width, height, ratio = get_image_resolution(image)

                # 🔥 CROP
                processed_img = process_image(image, i, ratio)

                news_items.append({
                    "title": title,
                    "link": link,
                    "image": processed_img,
                    "ratio": ratio
                })

                if len(news_items) >= 20:
                    break

            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)

            print(f"✅ Bild gotov — {len(news_items)} vijesti")
            browser.close()

        except Exception as e:
            print(f"Greška kod Bilda: {e}")
            browser.close()
            sys.exit(1)


if __name__ == "__main__":
    scrape_bild()
