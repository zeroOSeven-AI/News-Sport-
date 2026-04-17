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
        
        # PROVJERA TEŽINE DATOTEKE (u bajtovima)
        # Ove njihove grafike su obično jako lagane (npr. ispod 30KB)
        content_length = len(res.content)
        if content_length < 35000: # 35KB prag - prilagodi ako treba
            print(f"⚠️ Slika odbijena zbog težine ({content_length} bytes): {url[:50]}")
            return None

        img = Image.open(BytesIO(res.content))
        w, h = img.size
        return {"url": url, "w": w, "h": h, "focus_y": get_focus_y(w, h)}
    except Exception as e:
        print(f"❌ Error u get_image_info: {e}")
        return None

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    # Dodajemo ID-ove koje si poslao kao sumnjive
    trash_markers = ["7af5745e", "eb64ff1c", "bitter", "overlay", "live-ticker"]
    placeholder = "https://raw.githubusercontent.com/zeroOSeven-AI/News-Sport-/main/placeholder.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Pokrećem scraping s provjerom težine slika...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.evaluate("window.scrollBy(0, 3500)")
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

                    valid_img = None
                    # Prolazimo kroz sve slike u članku da nađemo onu koja nije banner
                    for img in all_imgs:
                        tmp_url = img.get('data-src') or img.get('src')
                        if not tmp_url: continue
                        if tmp_url.startswith('/'): tmp_url = "https://sportbild.bild.de" + tmp_url
                        
                        # Prva provjera: URL markeri
                        if any(m in tmp_url.lower() for m in trash_markers):
                            continue
                        
                        # Druga provjera: Težina i dimenzije
                        info = get_image_info(tmp_url)
                        if info:
                            valid_img = info
                            break
                    
                    # Ako nismo našli ništa čisto, koristi placeholder da ostane najnovija vijest
                    if not valid_img:
                        print(f"ℹ️ Koristim placeholder za: {title[:30]}")
                        valid_img = {"url": placeholder, "w": 800, "h": 600, "focus_y": 0.3}

                    news_items.append({
                        "title": title,
                        "link": link,
                        "image_url": valid_img["url"],
                        "w": valid_img["w"],
                        "h": valid_img["h"],
                        "focus_y": valid_img["focus_y"],
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
