import json
import sys
import re
import requests
import time
import os
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def get_focus_y(w, h):
    ratio = round(w / h, 2)
    if ratio >= 1.6: return 0.30
    if 0.9 <= ratio <= 1.1: return 0.22
    if 1.2 <= ratio <= 1.6: return 0.35
    return 0.5

def get_image_info(url):
    if not url or not url.startswith('http') or "1x1" in url:
        return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=10, headers=headers)
        # Filter za težinu: prave fotke su teže od grafika
        if len(res.content) < 30000:
            return None
        img = Image.open(BytesIO(res.content))
        w, h = img.size
        # Izbjegavamo premale slike
        if w < 400: return None
        return {"url": url, "w": w, "h": h, "focus_y": get_focus_y(w, h)}
    except:
        return None

def get_clean_image_from_article(browser_context, article_url):
    """Otvara članak i traži prvu kvalitetnu fotografiju."""
    page = None
    try:
        page = browser_context.new_page()
        page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
        # Kratko čekanje da se slike procesiraju
        time.sleep(1.5)
        soup = BeautifulSoup(page.content(), 'html.parser')
        
        # Bild u člancima slike drži u 'img' tagovima, često s data-src
        images = soup.find_all('img')
        for img in images:
            src = img.get('data-src') or img.get('src')
            if not src: continue
            if src.startswith('/'): src = "https://sportbild.bild.de" + src
            
            # Provjera je li to prava slika (bez teksta i markera)
            trash_markers = ["bitter", "overlay", "live-ticker", "banner", "f61f5128", "7af5745e"]
            if any(m in src.lower() for m in trash_markers):
                continue
                
            info = get_image_info(src)
            if info:
                page.close()
                return info
        
        if page: page.close()
        return None
    except:
        if page: page.close()
        return None

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
            print(f"🚀 Pokrećem dubinsko skeniranje: svaka vijest = ulaz u članak...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            # Skrolamo da povučemo listu članaka
            page.evaluate("window.scrollBy(0, 3000)")
            time.sleep(2)

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')
            
            print(f"📊 Nađeno {len(articles)} potencijalnih vijesti.")

            for art in articles:
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)

                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link

                    # ZA SVAKU VIJEST ULAZIMO UNUTRA
                    print(f"🔍 Ulazim u: {title[:40]}...")
                    final_info = get_clean_image_from_article(context, link)

                    if final_info:
                        print(f"✅ Nađena čista slika.")
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image_url": final_info["url"],
                            "w": final_info["w"],
                            "h": final_info["h"],
                            "focus_y": final_info["focus_y"],
                            "source_title1": "SPORT",
                            "source_title2": "BILD",
                            "source_color": "#fc4e4e",
                            "flag": "🇩🇪"
                        })
                    else:
                        print(f"⏭️ Preskačem, nema čiste slike unutar članka.")

                if len(news_items) >= 20: break

            if news_items:
                with open("bild.json", 'w', encoding='utf-8') as f:
                    json.dump(news_items, f, ensure_ascii=False, indent=4)
                print(f"🎉 Gotovo! bild.json je spreman s {len(news_items)} vijesti.")
            
            browser.close()
        except Exception as e:
            print(f"❌ Glavna greška: {str(e)}")
            browser.close()

if __name__ == "__main__":
    scrape_bild()
