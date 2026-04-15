import json
import sys
import re
import requests
from io import BytesIO
from PIL import Image
import os

OUTPUT_DIR = "images_espn"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 🔒 STANDARD DIMENZIJA (KLJUČNO)
TARGET_WIDTH = 1280
TARGET_HEIGHT = int(TARGET_WIDTH * 9 / 16)

# ============================================
# 🎯 FOCUS LOGIKA
# ============================================
def get_focus_y(ratio):
    if ratio >= 1.6:
        return 0.35
    if 0.9 <= ratio <= 1.1:
        return 0.25
    return 0.5

# ============================================
# ✂️ CROP + RESIZE (FIX)
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

    # 🔥 KLJUČNO → svi dobiju ISTU VELIČINU
    resized = cropped.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)

    return resized

# ============================================
# 🖼️ OBRADA SLIKE
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

        filename = f"{OUTPUT_DIR}/espn_{index}.jpg"
        final_img.save(filename, "JPEG", quality=85)

        return filename, TARGET_WIDTH, TARGET_HEIGHT, ratio

    except Exception as e:
        print(f"⚠️ Slika fail: {e}")
        return "", 0, 0, 0

# ============================================
# CLEAN TITLE
# ============================================
def clean_title(title):
    if not title: return ""
    title = re.sub(r'\s*-\s*ESPN.*$', '', title, flags=re.IGNORECASE)
    return title.strip()

# ============================================
# 📰 ESPN API
# ============================================
def scrape_espn():
    api_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/news?limit=50"

    try:
        print("🚀 ESPN API...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(api_url, headers=headers, timeout=30)
        data = response.json()

        articles = data.get('articles', [])
        process_articles(articles)

    except Exception as e:
        print(f"❌ Greška: {e}")

def process_articles(articles):
    news_items = []

    for i, art in enumerate(articles):
        raw_title = art.get('headline', '')
        link = art.get('links', {}).get('web', {}).get('href', '')
        images = art.get('images', [])
        image_url = images[0].get('url', '') if images else ""

        if raw_title and link:
            title = clean_title(raw_title)

            if len(title) < 15 or "/video/" in link:
                continue

            print(f"📸 {len(news_items)+1}: {title[:40]}")

            local_img_path, width, height, ratio = process_and_get_info(
                image_url, len(news_items)
            )

            news_items.append({
                "title": title,
                "link": link,
                "image": local_img_path,
                "width": width,
                "height": height,
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

    print("✅ ESPN GOTOV - sve slike uniformne")

if __name__ == "__main__":
    scrape_espn()
