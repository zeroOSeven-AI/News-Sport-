import json
import sys
import re
import requests
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Funkcija koja "profi" mjeri sliku bez skidanja cijelog filea
def get_image_resolution(url):
    if not url or not url.startswith('http'):
        return 0, 0, 0
    try:
        # Stream=True je ključan - ne skida cijelu sliku!
        response = requests.get(url, stream=True, timeout=5)
        # Čitamo samo početak (header) gdje su podaci o rezoluciji
        header = response.raw.read(2048) 
        img = Image.open(BytesIO(header))
        w, h = img.size
        return w, h, round(w / h, 2)
    except:
        # Ako ne uspije (npr. krivi format), vraćamo nule
        return 0, 0, 0

def scrape_sn():
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Postavljamo veliki viewport da "vidimo" sve vijesti odmah
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # BeautifulSoup za brzu analizu HTML-a
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    # --- ČIŠĆENJE NASLOVA ---
                    full_text = title_elem.get_text(separator=" ", strip=True)
                    kicker = title_elem.find(['span', 'b', 'i'])
                    if kicker:
                        kicker_text = kicker.get_text(strip=True)
                        title = full_text.replace(kicker_text, "").strip()
                    else:
                        title = full_text
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    # --- LINK I SLIKA ---
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportske.jutarnji.hr" + link
                    
                    image = ""
                    if img_elem:
                        image = img_elem.get('data-src') or img_elem.get('src') or ""
                    
                    if image and image.startswith('/'):
                        image = "https://sportske.jutarnji.hr" + image

                    # --- PILLOW MJERENJE (OVO JE NOVO) ---
                    print(f"Mjerim sliku za: {title[:30]}...")
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

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Gotovo! Spremljeno {len(news_items)} vijesti.")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals(): browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_sn()
