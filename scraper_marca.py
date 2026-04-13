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
    if not url or not url.startswith('http'):
        return 0, 0, 0
    try:
        response = requests.get(url, stream=True, timeout=10)
        header = response.raw.read(2048)
        img = Image.open(BytesIO(header))
        w, h = img.size
        return w, h, round(w / h, 2)
    except:
        return 0, 0, 0

def scrape_marca():
    url = "https://www.marca.com/en/football.html" # Engleska verzija Marce za nogomet
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            print(f"Otvaram Marcu: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3) # Marca ima puno skripti, dajemo im vremena
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            # Marca koristi 'article' tagove za vijesti
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem['href']
                    
                    # Slike kod Marce su često u 'src' ili 'data-src'
                    image = ""
                    if img_elem:
                        image = img_elem.get('src') or img_elem.get('data-src')
                        # Ako je slika mala (pixel-tracker), preskoči
                        if image and 'pixel.gif' in image:
                            image = ""

                    # Ako nema slike u img tagu, tražimo u source tagu (srcset)
                    if not image:
                        source_tag = art.find('source')
                        if source_tag and source_tag.get('srcset'):
                            image = source_tag.get('srcset').split(',')[0].split(' ')[0]

                    if image and image.startswith('//'):
                        image = "https:" + image

                    # Mjerenje rezolucije
                    width, height, ratio = 0, 0, 0
                    if image:
                        print(f"Mjerim sliku Marce: {title[:40]}...")
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

            with open('marca.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti iz Marce.")
            browser.close()

        except Exception as e:
            print(f"Greška kod Marce: {e}")
            if 'browser' in locals(): browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_marca()
