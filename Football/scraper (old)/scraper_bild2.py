import json
import sys
import re
import requests
import time
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def get_image_resolution(url):
    if not url or not url.startswith('http') or "1x1.png" in url:
        return 0, 0, 0
    try:
        # Bild nekad traži User-Agent čak i za slike
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
        response = requests.get(url, stream=True, timeout=10, headers=headers)
        header = response.raw.read(2048)
        img = Image.open(BytesIO(header))
        w, h = img.size
        return w, h, round(w / h, 2)
    except:
        return 0, 0, 0

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Koristimo mobilni profil jer je pregledniji za scrapanje
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"Otvaram Bild: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Polako skrolamo da se slike učitaju
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(2)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4'], class_=re.compile(r'headline|title', re.I))
                if not title_elem:
                    title_elem = art.find(['h2', 'h3', 'h4'])
                
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    # --- ČIŠĆENJE NASLOVA (Kicker logika) ---
                    kicker = title_elem.find(['span', 'b', 'i'])
                    full_text = title_elem.get_text(strip=True)
                    
                    if kicker:
                        kicker_text = kicker.get_text(strip=True)
                        title = full_text.replace(kicker_text, "").strip()
                    else:
                        title = full_text
                    
                    if len(title) < 10: title = full_text
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    # --- LINK ---
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportbild.bild.de" + link
                    
                    # --- SLIKA ---
                    image = ""
                    if img_elem:
                        image = img_elem.get('data-src') or img_elem.get('src') or ""
                        
                    # Bild specifičnost: ako je slika placeholder (1x1), traži u srcset
                    if not image or "1x1" in image:
                        source_tag = art.find('source')
                        if source_tag:
                            image = source_tag.get('srcset', '').split(' ')[0]

                    if image and image.startswith('/'):
                        image = "https://sportbild.bild.de" + image

                    # --- PILLOW MJERENJE ---
                    width, height, ratio = 0, 0, 0
                    if image and "http" in image:
                        print(f"Mjerim Bild sliku: {title[:30]}...")
                        width, height, ratio = get_image_resolution(image)

                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "width": width,
                            "height": height,
                            "ratio": ratio
                        })

                if len(news_items) >= 20:
                    break

            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti iz Bilda.")
            browser.close()

        except Exception as e:
            print(f"Greška kod Bilda: {e}")
            if 'browser' in locals(): browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
