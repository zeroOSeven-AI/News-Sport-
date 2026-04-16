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

# Funkcija za fokus (ostaje ista)
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
    # Riječi koje detektiraju žute bannere/tickere
    forbidden = ["ticker", "banner", "bitter", "score", "overlay", "live-ticker"]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Pokrećem scraping: {url}")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Skrolanje da se učitaju slike (lazy load)
            page.evaluate("window.scrollBy(0, 2500)")
            time.sleep(3) # Dajemo mu vremena da učita

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            # Bild koristi 'article' ili specifične klase
            articles = soup.find_all('article')
            
            print(f"📊 Pronađeno sirovih artikala: {len(articles)}")

            for art in articles:
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)
                all_imgs = art.find_all('img')

                if title_elem and link_elem and all_imgs:
                    title = title_elem.get_text(strip=True)
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link

                    # TRAŽENJE ČISTE SLIKE
                    final_img_url = None
                    for img in all_imgs:
                        temp_url = img.get('data-src') or img.get('src') or img.get('data-srcset')
                        if not temp_url: continue
                        
                        # Čišćenje URL-a od srcset parametara
                        clean_url = temp_url.split('?')[0].split(' ')[0]
                        if clean_url.startswith('/'): clean_url = "https://sportbild.bild.de" + clean_url
                        
                        # Provjera filtera
                        is_banner = any(word in clean_url.lower() for word in forbidden)
                        if not is_banner:
                            final_img_url = clean_url
                            break
                    
                    # Fallback ako nismo našli idealnu
                    if not final_img_url:
                        fallback = all_imgs[0].get('data-src') or all_imgs[0].get('src')
                        if fallback:
                            final_img_url = fallback.split('?')[0]
                            if final_img_url.startswith('/'): final_img_url = "https://sportbild.bild.de" + final_img_url

                    if final_img_url:
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

            # ZAPISIVANJE DATOTEKE
            if news_items:
                path = "bild.json"
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(news_items, f, ensure_ascii=False, indent=4)
                print(f"🎉 USPJEH! bild.json stvoren s {len(news_items)} vijesti.")
            else:
                print("❌ KATASTROFA: news_items je prazan. Provjeri selektore!")

            browser.close()

        except Exception as e:
            print(f"❌ GREŠKA: {str(e)}")
            browser.close()

if __name__ == "__main__":
    scrape_bild()
