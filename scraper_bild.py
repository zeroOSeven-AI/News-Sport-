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

# Funkcija za određivanje fokusa slike (za iOS widget)
def get_focus_y(w, h):
    ratio = round(w / h, 2)
    if ratio >= 1.6: return 0.30
    if 0.9 <= ratio <= 1.1: return 0.22
    if 1.2 <= ratio <= 1.6: return 0.35
    return 0.5

# Dohvaćanje informacija o slici i dodatna provjera dimenzija
def get_image_info(url):
    if not url or not url.startswith('http') or "1x1" in url:
        return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=10, headers=headers)
        img = Image.open(BytesIO(res.content))
        w, h = img.size
        
        # Banneri su često manji ili čudnih proporcija - filtriramo ih
        if w < 400 or h < 200:
            return None
            
        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h)
        }
    except:
        return None

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    
    # CRNA LISTA: Hash-ovi i ključne riječi iz žutih/šarenih bannera
    trash_hashes = [
        "7af5745e", # Žuta slika koju si poslao
        "b481d26b", # Live ticker žutilo
        "f61f5128306af4d83d2914d9df75b8a6", # Generalni banner ID
        "ec0c785",  # Često se pojavljuje kod grafika
    ]
    
    forbidden_keywords = ["ticker", "banner", "bitter", "overlay", "live-score", "graphic"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Pokrećem scraping Bilda (Anti-Banner mode)...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Skrolamo malo dublje da prisilimo učitavanje pravih slika
            page.evaluate("window.scrollBy(0, 3500)")
            time.sleep(5) 

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')
            
            print(f"📊 Analiziram {len(articles)} artikala...")

            for art in articles:
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)
                all_imgs = art.find_all('img')

                if title_elem and link_elem and all_imgs:
                    title = title_elem.get_text(strip=True)
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link

                    # TRAŽENJE ČISTE FOTOGRAFIJE
                    final_img_url = None
                    for img in all_imgs:
                        # Gledamo sve moguće izvore (data-src je najčešći kod Bilda)
                        temp_url = img.get('data-src') or img.get('src') or img.get('data-srcset')
                        if not temp_url: continue
                        
                        # Čistimo URL od smeća
                        clean_url = temp_url.split('?')[0].split(' ')[0]
                        if clean_url.startswith('/'): clean_url = "https://sportbild.bild.de" + clean_url
                        
                        # RIGOROZNA PROVJERA:
                        # 1. Je li u URL-u neka zabranjena riječ?
                        is_trash_text = any(word in clean_url.lower() for word in forbidden_keywords)
                        # 2. Sadrži li URL neki od poznatih "loših" hash-ova?
                        is_trash_hash = any(h in clean_url for h in trash_hashes)
                        
                        if not is_trash_text and not is_trash_hash:
                            final_img_url = clean_url
                            break
                    
                    # AKO NISMO NAŠLI ČISTU SLIKU, PRESKOČI CIJELU VIJEST
                    if not final_img_url:
                        print(f"⏭️ Preskačem (Nađen banner/grafika): {title[:30]}")
                        continue

                    info = get_image_info(final_img_url)
                    if info:
                        print(f"✅ Dodano: {title[:40]}...")
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

            # SPREMANJE
            if news_items:
                with open('bild.json', 'w', encoding='utf-8') as f:
                    json.dump(news_items, f, ensure_ascii=False, indent=4)
                print(f"🎉 USPJEH! bild.json stvoren s {len(news_items)} čistih vijesti.")
            else:
                print("⚠️ Nema vijesti koje su prošle filter. Provjeri stranicu!")

            browser.close()

        except Exception as e:
            print(f"❌ Greška: {str(e)}")
            browser.close()

if __name__ == "__main__":
    scrape_bild()
