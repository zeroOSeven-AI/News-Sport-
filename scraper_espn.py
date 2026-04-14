import json
import sys
import re
import requests
from io import BytesIO
from PIL import Image
import os

OUTPUT_DIR = "images"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================
# 🎯 FOCUS LOGIKA
# ============================================
def get_focus_y(ratio):
    if ratio >= 1.6:   # ESPN wide
        return 0.30
    if 0.9 <= ratio <= 1.1:
        return 0.20
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
# 🖼️ DOWNLOAD + PROCESS
# ============================================
def process_image(url, index, ratio):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=10, headers=headers)

        img = Image.open(BytesIO(res.content)).convert("RGB")

        focusY = get_focus_y(ratio)
        cropped = crop_to_16_9(img, focusY)

        filename = f"{OUTPUT_DIR}/espn_{index}.jpg"
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
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, stream=True, timeout=10, headers=headers)
        header = response.raw.read(2048)
        img = Image.open(BytesIO(header))
        w, h = img.size
        return w, h, round(w / h, 2)
    except:
        return 0, 0, 0


# ============================================
# 📰 MAIN
# ============================================
def scrape_espn():
    api_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/news?limit=50"
    
    try:
        print("ESPN API...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(api_url, headers=headers, timeout=30)
        data = response.json()
        articles = data.get('articles', [])
        
        process_articles(articles)

    except Exception as e:
        print(f"Greška: {e}")


# ============================================
# 🔄 PROCESS
# ============================================
def process_articles(articles):
    news_items = []

    for i, art in enumerate(articles):

        raw_title = art.get('headline', '')
        link = art.get('links', {}).get('web', {}).get('href', '')

        images = art.get('images', [])
        image = images[0].get('url', '') if images else ""

        if not (raw_title and link):
            continue

        title = re.sub(r'\s*-\s*ESPN.*$', '', raw_title).strip()

        if len(title) < 15 or "/video/" in link:
            continue

        # DIMENZIJE
        width, height, ratio = 0, 0, 0
        if image:
            print(f"Mjerim: {title[:40]}...")
            width, height, ratio = get_image_resolution(image)

        # 🔥 KLJUČ
        processed_img = process_image(image, i, ratio)

        news_items.append({
            "title": title,
            "link": link,
            "image": processed_img,
            "ratio": ratio,
            "source_title1": "ESPN",
            "source_title2": "FOOTBALL",
            "source_color": "#ff0021",
            "flag": "🇺🇸"
        })

        if len(news_items) >= 15:
            break

    with open('espn.json', 'w', encoding='utf-8') as f:
        json.dump(news_items, f, ensure_ascii=False, indent=4)

    print(f"✅ ESPN gotov ({len(news_items)})")


if __name__ == "__main__":
    scrape_espn()
