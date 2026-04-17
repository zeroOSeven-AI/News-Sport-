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
        # Provjera težine: grafike su lagane, prave slike teške
        if len(res.content) < 35000:
            return None
        img = Image.open(BytesIO(res.content))
        w, h = img.size
        return {"url": url, "w": w, "h": h, "focus_y": get_focus_y(w, h)}
    except:
        return None

def get_clean_image_from_article(browser_context, article_url):
    """Ulazi u članak i traži prvu pravu sliku bez teksta."""
    try:
        page = browser_context.new_page()
        page.goto(article_url, wait_until="networkidle", timeout=30000)
        time.sleep(2)
        soup = BeautifulSoup(page.content(), 'html.parser')
        page.close()
        
        # U člancima slike obično imaju klasu ili su unutar figure taga
        all_imgs = soup.find_all('img')
        for img in all_imgs:
            src = img.get('data-src') or img.get('src')
            if src:
                if src.startswith('/'): src = "https://sportbild.bild.de" + src
                # Provjera je li slika prava (težina/dimenzije)
                info = get_image_info(src)
                if info:
                    return info
        return None
    except:
        return None

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    trash_markers = ["7af5745e", "eb64ff1c", "4d38f580", "bitter", "overlay", "live-ticker"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Scraping Bild (Deep-Dive mode)...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.evaluate("window.scrollBy(0, 3000)")
            time.sleep(3)

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')
            
            for art in articles:
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem and img_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link

                    img_url = img_elem.get('data-src') or img_elem.get('src')
                    if img_url and img_url.startswith('/'): img_url = "https://sportbild.bild.de" + img_url

                    # Provjera: Je li slika na naslovnici smeće?
                    is_trash = any(m in img_url.lower() for m in trash_markers)
                    
                    final_info = None
                    if is_trash:
                        print(f"🔍 Detektirana grafika. Ulazim u članak: {title[:30]}...")
                        final_info = get_clean_image_from_article(context, link)
                    else:
                        final_info = get_image_info(img_url)

                    # Ako smo našli dobru sliku (bilo na naslovnici ili unutra)
                    if final_info:
                        print(f"✅ Dodano: {title[:40]}...")
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

                if len(news_items) >= 20: break

            if news_items:
                with open("bild.json", 'w', encoding='utf-8') as f:
                    json.dump(news_items, f, ensure_ascii=False, indent=4)
                print(f"🎉 bild.json spreman s čistim slikama!")
            
            browser.close()
        except Exception as e:
            print(f"❌ Greška: {str(e)}")
            browser.close()

if __name__ == "__main__":
    scrape_bild()
