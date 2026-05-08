import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image
import re

# ============================================
# 🎯 FOCUS LOGIKA (Zadržano prema tvom predlošku)
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

# ============================================
# 🛠️ SCRAPER LOGIKA
# ============================================
def scrape_wbw():
    url = "https://whatboyswant.com/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        print(f"🚀 Scraping: {url}...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Tražimo artikle - na ovoj stranici su obično unutar 'article' tagova ili specifičnih klasa
        articles = soup.find_all('article', limit=20)
        
        news_items = []
        
        for art in articles:
            # Izvlačenje naslova i linka
            link_tag = art.find('a', href=True)
            title_tag = art.find(['h2', 'h3']) # Naslovi su obično u h2 ili h3
            
            if not link_tag or not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link = link_tag['href']
            if not link.startswith('http'):
                link = "https://whatboyswant.com" + link

            # Izvlačenje slike
            img_tag = art.find('img')
            image_url = ""
            if img_tag:
                # Provjeravamo 'src' ili 'data-src' (lazy loading)
                image_url = img_tag.get('data-src') or img_tag.get('src') or ""
            
            if title and link and image_url:
                # Obrada slike i focus_y
                info = get_image_info(image_url)
                if info:
                    print(f"✅ Dodano: {title[:40]}...")
                    news_items.append({
                        "title": title,
                        "link": link,
                        "image_url": info["url"],
                        "w": info["w"],
                        "h": info["h"],
                        "focus_y": info["focus_y"],
                        "source_title1": "WBW",
                        "source_title2": "LIFESTYLE",
                        "source_color": "#000000", # Crna tema stranice
                        "flag": "🌐"
                    })

            if len(news_items) >= 15:
                break

        # Slanje u JSON
        with open('wbw_news.json', 'w', encoding='utf-8') as f:
            json.dump(news_items, f, ensure_ascii=False, indent=4)
        
        print(f"\n✨ Gotovo! Prikupljeno {len(news_items)} vijesti u wbw_news.json")

    except Exception as e:
        print(f"❌ Greška pri scrapingu: {e}")

if __name__ == "__main__":
    scrape_wbw()
