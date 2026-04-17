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
        img = Image.open(BytesIO(res.content))
        w, h = img.size
        # Grafike su često fiksne širine, prave fotke su veće
        return {"url": url, "w": w, "h": h, "focus_y": get_focus_y(w, h)}
    except:
        return None

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    trash_indicators = ["7af5745e", "b481d26b", "f61f5128", "ticker", "banner", "bitter", "overlay", "live-score"]
    # Link na tvoj logo ili neku čistu sportsku pozadinu na tvom GitHubu
    placeholder_img = "https://raw.githubusercontent.com/zeroOSeven-AI/News-Sport-/main/placeholder.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Scraping Bild (Smart-News mode)...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.evaluate("window.scrollBy(0, 3000)")
            time.sleep(5)

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')
            
            for art in articles:
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)
                all_imgs = art.find_all('img')

                if title_elem and link_elem and all_imgs:
                    title = title_elem.get_text(strip=True)
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link

                    # LOGIKA ZA ODABIR NAJBOLJE SLIKE
                    best_img = None
                    for img in all_imgs:
                        tmp = img.get('data-src') or img.get('src')
                        if not tmp: continue
                        if tmp.startswith('/'): tmp = "https://sportbild.bild.de" + tmp
                        
                        clean_url = tmp.split('?')[0]
                        is_trash = any(x in clean_url.lower() for x in trash_indicators)
                        
                        if not is_trash:
                            best_img = tmp
                            break # Našli smo čistu, izlazi
                    
                    # Ako su sve slike smeće, uzmi placeholder ali NE preskači vijest
                    final_img = best_img if best_img else placeholder_img
                    
                    info = get_image_info(final_img)
                    if not info: # Ako čak i placeholder propadne
                        info = {"url": final_img, "w": 800, "h": 600, "focus_y": 0.3}

                    print(f"✅ {'ČISTA' if best_img else 'FALLBACK'} vijest: {title[:35]}...")
                    news_items.append({
                        "title": title,
                        "link": link,
                        "image_url": info["url"],
                        "w": info["w"],
                        "h": info["h"],
                        "focus_y": info["focus_y"],
                        "source_title1": "SPORT",
                        "source_title2": "BILD",
                        "source_color": "#fc4e4e",
                        "flag": "🇩🇪"
                    })

                if len(news_items) >= 20: break

            if news_items:
                with open("bild.json", 'w', encoding='utf-8') as f:
                    json.dump(news_items, f, ensure_ascii=False, indent=4)
                print(f"🎉 bild.json spreman. Ukupno: {len(news_items)}")
            
            browser.close()
        except Exception as e:
            print(f"❌ Greška: {str(e)}")
            browser.close()

if __name__ == "__main__":
    scrape_bild()
