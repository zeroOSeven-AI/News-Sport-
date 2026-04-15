import json
import re
import requests
from io import BytesIO
from PIL import Image

# ============================================
# 🎯 FOCUS LOGIKA
# ============================================
def get_focus_y(w, h):
    ratio = round(w / h, 2)
    if ratio >= 1.6:
        return 0.35
    if 0.9 <= ratio <= 1.1:
        return 0.25
    return 0.5

def get_image_info(url):
    if not url or not url.startswith('http'):
        return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=10, headers=headers)
        img = Image.open(BytesIO(res.content))
        w, h = img.size
        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h)
        }
    except:
        return None

def clean_title(title):
    if not title: return ""
    title = re.sub(r'\s*-\s*ESPN.*$', '', title, flags=re.IGNORECASE)
    return title.strip()

def scrape_espn():
    api_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/news?limit=50"
    try:
        print("🚀 ESPN API: Dohvaćam podatke...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(api_url, headers=headers, timeout=30)
        data = response.json()
        articles = data.get('articles', [])
        
        news_items = []
        for art in articles:
            raw_title = art.get('headline', '')
            link = art.get('links', {}).get('web', {}).get('href', '')
            images = art.get('images', [])
            image_url = images[0].get('url', '') if images else ""

            if raw_title and link and image_url:
                title = clean_title(raw_title)
                if len(title) < 15 or "/video/" in link: continue

                info = get_image_info(image_url)
                if info:
                    print(f"✅ Meta spremna: {title[:40]}...")
                    news_items.append({
                        "title": title,
                        "link": link,
                        "image_url": info["url"],
                        "w": info["w"],
                        "h": info["h"],
                        "focus_y": info["focus_y"],
                        "source_title1": "ESPN",
                        "source_title2": "FOOTBALL",
                        "source_color": "#ff0021",
                        "flag": "🇺🇸"
                    })

            if len(news_items) >= 15: break

        with open('espn.json', 'w', encoding='utf-8') as f:
            json.dump(news_items, f, ensure_ascii=False, indent=4)
        print("✅ ESPN JSON spreman (bez lokalnih slika).")

    except Exception as e:
        print(f"❌ Greška: {e}")

if __name__ == "__main__":
    scrape_espn()
